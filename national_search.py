"""Nationwide discovery. Search snippets are candidates, never eligibility evidence."""
import datetime as dt
import html
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from collect_notices import decode_html, normalized
from public_network import fetch

REGIONS = ('서울','부산','대구','인천','광주','대전','울산','세종','경기','강원','충북','충남','전북','전남','경북','경남','제주')
KINDS = ('장학금 장학생 모집','대학생 공모전 모집','대외활동 서포터즈 모집')
# Boards supplement nationwide search; they do not define its geographic scope.
SOURCES = (
    ('kosaf','한국장학재단','https://www.kosaf.go.kr/ko/notice.do'),
    ('ilju','일주학술문화재단','https://www.iljufoundation.org/html/NewsNoticeFront01.do'),
    ('asan','아산사회복지재단','https://www.asanfoundation.or.kr/af/foundation/notice/afFoundationNoticeList.do'),
    ('ku_sejong','고려대학교 세종캠퍼스 장학','https://sejong.korea.ac.kr/bbs/koreaSejong/659/artclList.do'),
    ('sejong','세종대학교 장학','https://www.sejong.ac.kr/kor/intro/notice7.do'),
)
AGGREGATORS = ('thinkcontest.com','wevity.com','linkareer.com','campuspick.com','contestkorea.com','all-con.co.kr',
              'thinkyou.co.kr','allforyoung.com','ssgsag.kr','dreamspon.com','contestalgo.com','gongmo.incruit.com',
              'blog.naver.com','m.blog.naver.com','tistory.com','ipsajeon.com','instagram.com','facebook.com')
NOTICE_WORDS = re.compile(r'장학|장학생|공모|경진|대회|해커톤|hack[\s-]*a[\s-]*thon|대외활동|서포터|봉사|멘토|아이디어|참가자', re.I)
RESULT_NOTICE = re.compile(r'(?:합격자|면접\s*대상자|선발\s*결과|선정\s*결과|심사\s*결과|수상작|수상자).{0,15}(?:발표|안내|공고)|(?:최종|서류)\s*합격')


@dataclass(repr=False)
class SearchConfig:
    api_key: str = field(repr=False)

    @property
    def enabled(self):
        return bool(self.api_key)


def search_config(values=None):
    values = values or {}
    return SearchConfig(str(values.get('api_key') or os.getenv('TAVILY_API_KEY','')).strip())


def search_plan(year=None):
    year = year or dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).year
    return [{'query':f'{"" if region=="전국" else str(year)} {region} {kind}'.strip(), 'region':region,'kind':kind}
            for region in ('전국',)+REGIONS for kind in KINDS]


class SearchError(ValueError):
    def __init__(self, message, fatal=False):
        super().__init__(message)
        self.fatal = fatal


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def tavily_search(config, query):
    if not config or not config.enabled:
        raise SearchError('Tavily 검색 API 연결이 필요합니다.', True)
    payload=dict(query=query,search_depth='basic',max_results=20,topic='general',time_range='month',
                 include_answer=False,include_raw_content=False,include_images=False,
                 auto_parameters=False,include_usage=True,exclude_domains=list(AGGREGATORS))
    request = urllib.request.Request('https://api.tavily.com/search',
        data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
        headers={'Authorization':'Bearer '+config.api_key,'Content-Type':'application/json',
                 'User-Agent':'GonggoNext/1.0'},method='POST')
    try:
        with urllib.request.build_opener(NoRedirect).open(request,timeout=20) as response:
            data = response.read(2*1024*1024+1)
        if len(data)>2*1024*1024:raise SearchError('검색 응답 크기가 너무 큽니다.')
        value = json.loads(data)
        if not isinstance(value,dict) or not isinstance(value.get('results'),list):
            raise SearchError('검색 응답 형식을 확인하지 못했습니다.')
        # Retain source discovery metadata only. Snippets/AI answers are never
        # eligibility evidence, nor are private profile values sent in queries.
        return {'items':[{'link':v.get('url',''),'title':v.get('title','')}
                         for v in value['results'] if isinstance(v,dict)],
                'credits':value.get('usage',{}).get('credits',1)}
    except urllib.error.HTTPError as exc:
        message = ('검색 API 인증·검색 권한을 확인해주세요.' if exc.code in (401,403) else
                   '검색 API 사용량 제한에 도달했습니다.' if exc.code in (429,432,433) else '검색 서버가 요청을 처리하지 못했습니다.')
        raise SearchError(message, exc.code in (400,401,403,422,429,432,433)) from None
    except (OSError,ValueError) as exc:
        if isinstance(exc,SearchError):raise
        raise SearchError('검색 서버 연결 또는 응답 처리에 실패했습니다.') from None


def public_title(text):
    value=html.unescape(str(text))
    if '<' in value:value=BeautifulSoup(value,'html.parser').get_text(' ',strip=True)
    return ' '.join(value.split())[:300]


def aggregator(url):
    host = urlsplit(url).hostname or ''
    return any(host==d or host.endswith('.'+d) for d in AGGREGATORS)


def candidate(url, title, source_name, region='전국', source_id='web'):
    url = normalized(url)
    host = urlsplit(url).hostname or ''
    if host in ('localhost','127.0.0.1','::1') or len(url)>3000:
        raise ValueError('공개 공고 주소를 확인해주세요.')
    return dict(url=url,title=public_title(title),source_name=source_name,source_id=source_id,
                source_kind='등록 기관 게시판' if source_id!='web' else '웹 검색 원문 · 기관 확인 필요',
                regions=[region], needs_original=aggregator(url),
                notice_purpose='결과·후속 안내' if RESULT_NOTICE.search(public_title(title)) else '모집 여부 확인 필요')


def board_candidates(source):
    ident,name,url = source
    response = fetch(url)
    soup = BeautifulSoup(decode_html(response),'html.parser')
    out = []
    for a in soup.select('a[href]'):
        title = public_title(a.get_text(' ',strip=True))
        if not NOTICE_WORDS.search(title):continue
        href = a['href']
        if ident=='asan':
            m=re.fullmatch(r'fnDetail\((\d+)\);?\s*return false;?',a.get('onclick','').strip())
            if m:href=href+'?idx='+m[1]+'&noticeTypeClsf=N'
        if ident=='ilju':
            m=re.fullmatch(r'listView\((\d+)\);?',a.get('onclick','').strip())
            if m:href='/html/NewsNoticeFront02.do?boardNo=1&contentNo='+m[1]
        if href.startswith(('javascript:', '#')):
            # Interpret only this known board's numeric ID; never execute page code.
            if ident=='kosaf':
                m=re.search(r"(?:view|detail)[\w]*\s*\(\s*['\"]?(\d+)", href, re.I)
                if m:href='?mode=view&seqNo='+m[1]
                else:continue
            else:continue
        full = urljoin(response.url,href)
        if urlsplit(full).netloc!=urlsplit(response.url).netloc:continue
        if not re.search(r'artclView|mode=view|[?&](?:seqNo|contentNo|idx|nttId)=|Detail',full,re.I):continue
        out.append(candidate(full,title,name,source_id=ident))
    return out


class DiscoveryStore:
    def __init__(self, root):
        self.path=Path(root)/'runtime/discovery.sqlite3'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS candidates (url TEXT PRIMARY KEY, payload TEXT NOT NULL, seen REAL NOT NULL, attempted REAL NOT NULL DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS queries (query TEXT PRIMARY KEY, updated REAL NOT NULL, result TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=15)
        try:
            with db:yield db
        finally:db.close()

    def remember(self, items):
        seen_at=time.time()
        with self.connect() as db:
            for item in items:
                old=db.execute('SELECT payload FROM candidates WHERE url=?',(item['url'],)).fetchone()
                merged=dict(item)
                if old:
                    prior=json.loads(old[0]);merged['regions']=sorted(set(prior.get('regions',[])+item.get('regions',[])))
                    # A search result must not erase a verified registered-board origin.
                    if prior.get('source_id')!='web' and item.get('source_id')=='web':
                        for k in ('source_id','source_name','source_kind'):merged[k]=prior[k]
                db.execute('INSERT INTO candidates(url,payload,seen) VALUES (?,?,?) ON CONFLICT(url) DO UPDATE SET payload=excluded.payload,seen=excluded.seen',
                           (item['url'],json.dumps(merged,ensure_ascii=False),seen_at))

    def items(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM candidates ORDER BY attempted ASC,seen DESC,rowid ASC')]

    def queue(self, urls=None):
        items=self.items()
        if isinstance(urls,(list,tuple)):
            by_url={c['url']:c for c in items}
            items=[by_url[url] for url in urls if url in by_url]
        elif urls is not None:items=[c for c in items if c['url'] in urls]
        return [c for c in items if not c.get('needs_original') and c.get('notice_purpose')!='결과·후속 안내']

    def attempted(self,url):
        with self.connect() as db:db.execute('UPDATE candidates SET attempted=? WHERE url=?',(time.time(),url))

    def cached_search(self,query,searcher):
        # Old result URLs are reclassified under the current source rules below.
        cache_key='tavily:basic:20:month:originals:v2:'+query
        with self.connect() as db:
            row=db.execute('SELECT updated,result FROM queries WHERE query=?',(cache_key,)).fetchone()
        if row and time.time()-row[0]<900:return json.loads(row[1]),True
        result=searcher(query)
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO queries VALUES (?,?,?)',(cache_key,time.time(),json.dumps(result,ensure_ascii=False)))
        return result,False


def discover_nationwide(root, config=None, progress=None, searcher=None, sources=SOURCES):
    """54 country/region/category queries, independent of private profile data.

    Each query retrieves up to 20 indexed links. This is nationwide coverage,
    not a claim to enumerate every announcement or every search-result page.
    """
    store=DiscoveryStore(root)
    stats=dict(sources=[],queries_completed=0,queries_total=54,query_cache_hits=0,search_credits=0,
               search_enabled=bool(config and config.enabled),errors=[],found=0)
    batches=[]
    def report(message):
        if progress:progress(message)
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures={pool.submit(board_candidates,s):s for s in sources}
        for f in as_completed(futures):
            source=futures[f]
            try:
                items=f.result();batches.append(items)
                stats['sources'].append(dict(name=source[1],url=source[2],count=len(items),status='확인' if items else '공고 링크 미확인'))
            except (ValueError,OSError):
                stats['sources'].append(dict(name=source[1],url=source[2],count=0,status='수집 실패 · 원문 확인 필요'))
            report(f'공식 출처 {len(stats["sources"])}/{len(sources)} 확인 중…')
    if config and config.enabled:
        # Sequential API calls stop immediately on credential/quota failures.
        for plan in search_plan():
            try:
                result,reused=store.cached_search(plan['query'],searcher or (lambda q:tavily_search(config,q)))
                items=[]
                for value in result['items']:
                    try:
                        item=candidate(value.get('link',''),value.get('title',''),'Tavily 웹 검색',plan['region'])
                        if NOTICE_WORDS.search(item['title']):items.append(item)
                    except (ValueError,TypeError):continue
                batches.append(items);stats['queries_completed']+=1;stats['query_cache_hits']+=int(reused)
                if not reused:stats['search_credits']+=result.get('credits',1)
            except SearchError as exc:
                stats['errors'].append(f'{plan["region"]} · {plan["kind"]}: {exc}')
                if exc.fatal:break
            report(f'전국·17개 시도 검색 {stats["queries_completed"]}/54 · 원문 후보 수집 중…')
    else:
        stats['errors'].append('검색 API 미연결: 전국 웹 검색은 실행하지 않았습니다. 등록 기관 게시판만 확인했습니다.')
    # Interleave query results so a single source/category cannot fill the queue.
    interleaved=[b[i] for i in range(max(map(len,batches),default=0)) for b in batches if i<len(b)]
    seen=set();out=[]
    for item in interleaved:
        if item['url'] not in seen:out.append(item);seen.add(item['url'])
    store.remember(interleaved)
    stats['found']=len(out)
    return out,stats
