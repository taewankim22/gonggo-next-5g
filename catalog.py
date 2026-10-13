"""Read-only, public document cache. Never receives or stores personal reviews."""
import datetime as dt
import json
from pathlib import Path
from core import fingerprint
from input_tools import inspect_input
from profiles import applied_facts,profile_rows
from independent_review import condition_rows
from planning import question_keys
from workspaces import seed_basic

def load_catalog(root):
    path=Path(root)/'data/catalog/index.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []

def status_label(record,today=None):
    today=today or dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    try:return '과거 검증 사례' if dt.date.fromisoformat(record['deadline'])<today else '마감 전 · 시작일 확인'
    except (KeyError,ValueError):return '접수 상태 확인 필요'

def available_record(root,record):
    if record.get('status')!='ready':return None
    base=(Path(root)/'data/catalog').resolve()
    try:
        source=(base/record['file']).resolve();extracted=(base/record['analysis']).resolve()
        if not source.is_relative_to(base) or not extracted.is_relative_to(base):return None
        data=source.read_bytes()
        if fingerprint(data)!=record['sha256']:return None
        parsed=json.loads(extracted.read_text(encoding='utf-8'))
        if parsed['source_hash']!=record['sha256']:return None
        return dict(notice=parsed['notice'],raw_notice=parsed['notice'],pages=parsed['pages'],pdf=data,
            source_hash=record['sha256'],source_filename=source.name,source_info=parsed.get('source_info',inspect_input(data,source.name)),
            evidence_basis=parsed.get('evidence_basis','Studio Parse'),notice_config=parsed['config'],
            catalog_source={'url':record['source_url'],'checked_at':record['checked_at']},
            last_mode='실제 AI 분석',screen=2,notice_trace=parsed.get('notice_trace',{}))
    except (KeyError,ValueError,OSError):return None

def cached_public(root,source_hash,agent_id,version):
    for record in load_catalog(root):
        if record.get('sha256')!=source_hash:continue
        state=available_record(root,record)
        if state and state['notice_config']=={'agent_id':agent_id,'config_id':str(version)}:return state
    return None

def card_review(root,record,profile):
    state=available_record(root,record)
    if not state:return {'rows':[],'matches':[],'unknowns':[],'conflicts':[]}
    notice=state['notice'];answers={'profile_facts':applied_facts(notice,profile,{})}
    seed_basic(state,notice,profile)
    answers.update({k:state.get('answer_'+k) for k in question_keys(notice,{})})
    rows=condition_rows(notice,answers,state['pages'])
    # Always expose limitations even when extraction omitted some fields.
    if not rows:
        rows=[dict(label='조건 구조화 미완료',status='확인 필요',reason='원문 전체 확인 필요',quote=notice.get('eligibility_rule',''),page=notice.get('eligibility_page',''))]
    return {'rows':rows,'matches':[r for r in rows if r['status']=='일치'],
            'unknowns':[r for r in rows if r['status']=='확인 필요'],'conflicts':[r for r in rows if r['status']=='불일치']}
