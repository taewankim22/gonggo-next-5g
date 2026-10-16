"""Browser-owned drafts. Strict allowlist: never serialize all session state."""
import base64
import hashlib
import json
import re
from pathlib import Path
import streamlit as st
from core import fingerprint, validate_payload
from schema_builder import notice_schema

VERSION = 2
MAX_BYTES = 32 * 1024 * 1024
FIELDS = {'notice', 'pages', 'source_filename', 'source_info', 'source_hash',
          'evidence_basis', 'draft_answers', 'last_mode', 'screen'}
ANSWERS = {'answer_'+s for s in ('enrollment_status','remaining_terms','selected_center',
           'skills','weekly_visits','weekly_hours','long_term','review_stage',
           'unavailable_dates','other_facts','use_example')}
EXTRAS = {'profile_preset','schedule_state','show_later_questions'}
EXTRAS |= {'profile_overrides','profile_seeded','profile_provenance','notice_config','catalog_source','profile_revision','situation_responses'}

def allowed(key):
    return key in FIELDS | ANSWERS | EXTRAS or bool(re.fullmatch(
        r'(question_[a-f0-9]{12}_[a-f0-9]+|doc_[a-f0-9]{12}_[a-f0-9]+_(applies|ready|done)|fact_[a-f0-9]{12}_[a-f0-9]{12}_(mode|value|scale))',key))

def single_snapshot(state):
    if not state.get('notice') or not state.get('pdf'):
        return None
    values = {k: state[k] for k in state if allowed(k)}
    # Traces, API settings, review PDFs and AI review results are deliberately excluded.
    return {'version': 1, 'values': values,
            'original': base64.b64encode(state['pdf']).decode('ascii')}

def restore_single(payload):
    if not isinstance(payload,dict) or payload.get('version') != 1:
        raise ValueError('저장 형식을 읽을 수 없습니다.')
    if len(json.dumps(payload,ensure_ascii=False).encode()) > MAX_BYTES:
        raise ValueError('저장 데이터가 너무 큽니다.')
    values = payload.get('values')
    if not isinstance(values,dict):raise ValueError('저장 내용이 올바르지 않습니다.')
    values = {k:v for k,v in values.items() if allowed(k)}
    if values.get('last_mode') == '예시 화면 체험':
        notice=json.loads((Path(__file__).parent/'data/demo_notice.json').read_text(encoding='utf-8'))
        if values.get('notice') != notice:raise ValueError('예시 공고 버전이 달라 다시 열어주세요.')
    else:
        schema=notice_schema()
        # Existing drafts predate optional profile extraction. Never invent facts on migration.
        old=dict(values.get('notice') or {})
        if 'profile_conditions_json' in schema['properties']:old.setdefault('profile_conditions_json','')
        notice = validate_payload(old,schema)
    data = base64.b64decode(payload.get('original',''),validate=True)
    if not data or len(data)>15*1024*1024 or fingerprint(data)!=values.get('source_hash'):
        raise ValueError('저장한 원본과 공고가 일치하지 않습니다.')
    if values.get('last_mode') not in ('실제 AI 분석','예시 화면 체험'):
        raise ValueError('저장한 사용 모드를 확인할 수 없습니다.')
    if not isinstance(values.get('pages'),list) or not all(isinstance(p,str) for p in values['pages']):
        raise ValueError('원문 본문을 확인할 수 없습니다.')
    if values.get('last_mode') != '예시 화면 체험':
        from workflow_adapter import ground_notice
        notice = ground_notice(notice,values['pages'])
    if not isinstance(values.get('source_info',{}),dict):raise ValueError('원본 정보 오류')
    if not isinstance(values.get('source_filename'),str):raise ValueError('파일 이름 오류')
    for k,v in values.items():
        if k in ANSWERS | {'profile_preset','schedule_state','show_later_questions'} or k.startswith(('question_','doc_','fact_')):
            if v is not None and not isinstance(v,(str,int,float,bool)):
                raise ValueError('답변 형식 오류')
    if 'draft_answers' in values and not isinstance(values['draft_answers'],dict):
        raise ValueError('답변 형식 오류')
    screen=values.get('screen',2)
    values['screen']=screen if type(screen)==int and screen in (1,2,3,4) else 2
    if values['screen']==4 and 'draft_answers' not in values:values['screen']=3
    values.update(pdf=data,notice=notice,raw_notice=dict(notice))
    return values

def snapshot(state):
    from profiles import clean_profile
    active=single_snapshot(state)
    profile=clean_profile(state.get('common_profile',{}))
    records=dict(state.get('workspaces',{}))
    if active:records.pop(state.get('source_hash'),None)
    if not active and not profile and not records:return None
    return {'version':VERSION,'values':active['values'] if active else {},
            'original':active['original'] if active else '', 'profile':profile,
            'workspaces':records,'route':state.get('route','review' if active else 'home')}

def restore(payload):
    from profiles import clean_profile
    if not isinstance(payload,dict):raise ValueError('저장 형식 오류')
    if payload.get('version')==1:return restore_single(payload)
    if payload.get('version')!=VERSION:raise ValueError('저장 형식 오류')
    if len(json.dumps(payload,ensure_ascii=False).encode())>MAX_BYTES:raise ValueError('저장 데이터가 너무 큽니다.')
    out=restore_single({**payload,'version':1}) if payload.get('original') else {}
    records={}
    for key,record in payload.get('workspaces',{}).items():
        restored=restore_single(record)
        if key!=restored['source_hash']:raise ValueError('공고 저장 키 오류')
        records[key]=single_snapshot(restored)
    out.update(common_profile=clean_profile(payload.get('profile',{})),workspaces=records,
               route=payload.get('route') if payload.get('route') in ('home','profile','catalog','review') else 'home')
    return out

_bridge = st.components.v2.component('gonggo_draft_storage',
    js=(Path(__file__).parent/'browser_draft.js').read_text(encoding='utf-8'),
    html='<span role="status" aria-live="polite"></span>',
    css='\nspan { font-size:13px; line-height:1.6; color:#666; overflow-wrap:anywhere; }\n')

def bootstrap():
    """Complete the browser read before any default form can overwrite it."""
    # Verification tabs never read, save, or delete the user's browser drafts.
    # Pin the mode for the session so removing the query cannot save test answers.
    st.session_state.setdefault('_verification_session',st.query_params.get('verification')=='1')
    if st.session_state['_verification_session']:
        st.info('검증용 임시 세션입니다. 기존 프로필·답변을 불러오거나 저장하지 않습니다.')
        return
    ready=st.session_state.get('_draft_loaded',False)
    result=_bridge(key='draft_loader',data={'op':'idle' if ready else 'load'},
                   on_loaded_change=lambda:None)
    if ready:return
    if not result.loaded:
        st.caption('이 브라우저에 저장한 준비 내용을 불러오는 중…')
        st.stop()
    info=result.loaded
    st.session_state['_draft_revision']=info.get('revision',0)
    if info.get('error'):
        st.session_state['_draft_storage_error']=True
    elif info.get('payload') and 'notice' not in st.session_state:
        try:
            st.session_state.update(restore(info['payload']))
            st.session_state['_draft_restored']=True
        except (ValueError,TypeError,KeyError):
            st.session_state['_draft_storage_error']=True
    st.session_state['_draft_loaded']=True
    st.rerun()

@st.fragment
def save_browser():
    if st.session_state.get('_verification_session'):return
    # IndexedDB acknowledgements must not rerun the whole app: a full rerun
    # interrupts an in-flight Studio poll and discards its completed result.
    payload=snapshot(st.session_state)
    if st.session_state.get('_draft_storage_error'):
        st.warning('브라우저 저장을 사용할 수 없습니다. 준비 목록을 내려받으세요. 설정에서 저장 내용을 초기화하거나 브라우저 저장 허용을 확인할 수 있습니다.')
        return
    serialized=json.dumps(payload,ensure_ascii=False,sort_keys=True)
    digest=hashlib.sha256(serialized.encode()).hexdigest()
    deleting=st.session_state.get('_draft_delete',False)
    operation='delete' if deleting else 'save' if payload else 'idle'
    if len(serialized.encode())>MAX_BYTES:
        st.error('저장 용량 32MB를 초과했습니다. 전체 준비 백업을 내려받고 불필요한 공고를 정리하세요. 이번 변경은 저장되지 않았습니다.')
        return
    ack=_bridge(key='draft_writer',data={'op':operation,'payload':payload,'digest':digest,'revision':st.session_state.get('_draft_revision',0)},
                on_saved_change=lambda:None)
    if ack.saved:
        if ack.saved.get('status')=='conflict':
            st.warning('다른 탭에서 먼저 저장했습니다. 이 탭은 덮어쓰지 않았습니다. 아래 백업을 저장하고 새로고침해주세요.')
            st.download_button('이 탭의 전체 준비 백업',serialized,'gonggo-private-backup.json','application/json',key='conflict_backup')
        elif ack.saved.get('status')=='error':st.error('브라우저 저장 실패. 현재 준비 목록을 내려받으세요.')
        elif 'revision' in ack.saved:st.session_state['_draft_revision']=ack.saved['revision']
    if deleting and ack.saved and ack.saved.get('status')=='deleted':
        st.session_state.pop('_draft_delete',None)
        st.rerun()

def clear_draft():
    for key in list(st.session_state):
        if allowed(key) or key in ('common_profile','workspaces','route','pdf','pending_file','preparation','result','profile',
             'raw_notice','raw_review','review_hash','review_pdf','notice_trace','review_trace','_notice_request'):
            st.session_state.pop(key,None)
    st.session_state.screen=1
    st.session_state['_draft_delete']=True
    st.session_state.pop('_draft_storage_error',None)
    st.session_state.pop('_draft_restored',None)
    st.session_state['_upload_generation']=st.session_state.get('_upload_generation',0)+1
