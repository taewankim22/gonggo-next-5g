"""Shared public-only catalogue, with atomic publication and resumable Studio jobs.

No credentials, profiles or answers are accepted here. SQLite lives on the
Streamlit instance's ephemeral disk; the bundled catalogue remains the fallback.
"""
import datetime as dt
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from core import fingerprint, validate_payload
from input_tools import inspect_input, parse_pages, map_image_page
from schema_builder import notice_schema
from workflow_adapter import ground_notice


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class LiveCatalog:
    def __init__(self, root):
        self.path = Path(root)/'runtime/public_catalog.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, record TEXT NOT NULL, analysis TEXT NOT NULL, document BLOB NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, busy INTEGER NOT NULL, updated REAL NOT NULL, trace TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS scans (url TEXT PRIMARY KEY, manifest TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS content_analyses (id TEXT PRIMARY KEY, analysis TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def records(self):
        with self.connect() as db:
            saved=db.execute('SELECT record,analysis FROM records ORDER BY rowid DESC').fetchall()
        results=[]
        for record,analysis in saved:
            r=json.loads(record);a=json.loads(analysis)
            # Apply current evidence rules to old cached deadlines as well.
            r['deadline']=ground_notice(a['notice'],a['pages']).get('application_deadline','')
            results.append(r)
        return results

    def scans(self):
        with self.connect() as db:
            return {r[0]:json.loads(r[1]) for r in db.execute('SELECT url,manifest FROM scans')}

    def save_scan(self, manifest):
        # Only collector-owned public metadata, never a session/profile snapshot.
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO scans VALUES (?,?)',
                       (manifest['url'],json.dumps(manifest,ensure_ascii=False)))

    def state(self, record):
        with self.connect() as db:
            row = db.execute('SELECT record,analysis,document FROM records WHERE id=?', (record['id'],)).fetchone()
        if not row:
            return None
        stored, analysis, data = json.loads(row[0]), json.loads(row[1]), row[2]
        if stored.get('sha256') != record.get('sha256') or fingerprint(data) != analysis['source_hash']:
            return None
        notice=ground_notice(analysis['notice'],analysis['pages'])
        return dict(notice=notice, raw_notice=notice, pages=analysis['pages'], pdf=data,
                    source_hash=record['sha256'], source_filename=record['filename'], source_info=analysis['source_info'],
                    evidence_basis=record['evidence_basis'], notice_config=analysis['config'],
                    notice_trace=analysis['notice_trace'],
                    catalog_source={k:record[k] for k in ('source_url','checked_at','document_name','coverage_note')},
                    last_mode='실제 AI 분석', screen=2)

    def claim(self, job, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT busy,updated,trace FROM jobs WHERE id=?', (job,)).fetchone()
            if row and row[0] and now-row[1] < 900:
                raise ValueError('같은 공고를 분석 중입니다. 잠시 뒤 목록을 새로고침해주세요.')
            trace = json.loads(row[2]) if row else {}
            if trace.get('submission_started') and not trace.get('job_id'):
                raise ValueError('이전 요청의 실행 여부가 불명확합니다. 중복 호출을 막았습니다. 운영자가 Studio 실행 내역을 확인해야 합니다.')
            db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?,?)', (job,1,now,json.dumps(trace)))
        return trace

    def save_trace(self, job, trace):
        with self.connect() as db:
            db.execute('UPDATE jobs SET trace=?,updated=? WHERE id=?', (json.dumps(trace,ensure_ascii=False),time.time(),job))

    def release(self, job):
        with self.connect() as db:
            db.execute('UPDATE jobs SET busy=0 WHERE id=?', (job,))

    def publish(self, record, analysis, data):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?)',
                       (record['id'],json.dumps(record,ensure_ascii=False),json.dumps(analysis,ensure_ascii=False),data))
            key=fingerprint([record['sha256'],record['config']])
            db.execute('INSERT OR REPLACE INTO content_analyses VALUES (?,?)',(key,json.dumps(analysis,ensure_ascii=False)))

    def content_analysis(self, sha, config):
        with self.connect() as db:
            row=db.execute('SELECT analysis FROM content_analyses WHERE id=?',(fingerprint([sha,config]),)).fetchone()
            if row:return json.loads(row[0])
            # Reuse pre-migration completed analyses too; exact bytes + pinned config only.
            for record,analysis in db.execute('SELECT record,analysis FROM records'):
                r=json.loads(record)
                if r.get('sha256')==sha and r.get('config')==config:return json.loads(analysis)
        return None


class SavedTrace(dict):
    def __init__(self, initial, save):
        super().__init__(initial)
        self.save = save

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self.save(self)


def analyze_public(root, article, document_index, agent_id, version, runner, progress=None):
    """runner(data, filename, info, progress, trace) uses the existing team gate."""
    doc = article['documents'][document_index]
    data = doc['data']
    info = inspect_input(data, doc['filename'])
    sha = fingerprint(data)
    identity = 'web_' + fingerprint([article['url'],doc['document_url']])[:24]
    config = {'agent_id':agent_id,'config_id':str(version)}
    job = fingerprint([sha,config])
    cache = LiveCatalog(root)
    cached=cache.content_analysis(sha,config)
    initial = cache.claim(job) if not cached else {}
    claimed=not bool(cached)
    trace = SavedTrace(initial, lambda t:cache.save_trace(job,t))
    try:
        cached=cached or cache.content_analysis(sha,config)
        if cached:
            notice=cached['notice'];pages=cached['pages'];trace=cached['notice_trace']
        else:
            raw = runner(data, doc['filename'], info, progress, trace)
            notice = validate_payload(raw, notice_schema())
            ocr = parse_pages(trace.get('steps',[]))
            pages = ocr if any(ocr) else info['pages']
        if not any(pages) or not notice.get('notice_title','').strip():
            raise ValueError('공고 제목 또는 근거 본문을 읽지 못했습니다. 목록에 게시하지 않았습니다.')
        notice = map_image_page(ground_notice(notice,pages),info)
        remaining = len(article['documents'])-1 + len(article['warnings'])
        coverage = '분석 범위: '+doc['name']+'만 분석했습니다.'
        if remaining or article.get('attachment_limit_reached'):
            coverage += ' 다른 본문·첨부는 별도 확인이 필요합니다.'
        coverage += ' AI 분석 결과이며 전체 자격 충족을 확정하지 않습니다.'
        analyzed_at=cached.get('analyzed_at','') if cached else ''
        if not analyzed_at:analyzed_at=now_iso()
        record = dict(id=identity, title=article['title'], kind=notice.get('notice_type') or '기타',
                      deadline=notice.get('application_deadline',''), source_url=article['url'],
                      document_url=doc['document_url'], document_name=doc['name'], filename=doc['filename'],
                      checked_at=article['checked_at'], analyzed_at=analyzed_at, sha256=sha, status='ready',
                      storage='live', config=config, evidence_basis=doc['basis'], coverage_note=coverage,
                      tags=[notice.get('organizer',''),notice.get('notice_type','')],
                      warnings=article['warnings'], attachment_count=len(article['attachments']))
        record.update(source_name=article.get('source_name',''),source_kind=article.get('source_kind','등록 기관 게시판'),
                      resolved_url=article.get('resolved_url',article['url']))
        analysis = dict(source_hash=sha, notice=notice, pages=pages, source_info=info, config=config,
                        notice_trace=dict(trace),analyzed_at=analyzed_at)
        cache.publish(record,analysis,data)
        return record, bool(cached)
    finally:
        if claimed:cache.release(job)
