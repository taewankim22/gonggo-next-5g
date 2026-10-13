"""Browser-owned drafts. Strict allowlist: never serialize all session state."""
import base64
import hashlib
import json
import re
from pathlib import Path
import streamlit as st
from core import fingerprint, validate_payload
from schema_builder import notice_schema

VERSION = 1
MAX_BYTES = 32 * 1024 * 1024
FIELDS = {'notice', 'pages', 'source_filename', 'source_info', 'source_hash',
          'evidence_basis', 'draft_answers', 'last_mode', 'screen'}
ANSWERS = {'answer_'+s for s in ('enrollment_status','remaining_terms','selected_center',
           'skills','weekly_visits','weekly_hours','long_term','review_stage',
           'unavailable_dates','other_facts','use_example')}
EXTRAS = {'profile_preset','schedule_state','show_later_questions'}

def allowed(key):
    return key in FIELDS | ANSWERS | EXTRAS or bool(re.fullmatch(
        r'(question_[a-f0-9]{12}_[a-f0-9]+|doc_[a-f0-9]{12}_[a-f0-9]+_(applies|ready|done))',key))

def snapshot(state):
    if not state.get('notice') or not state.get('pdf'):
        return None
    values = {k: state[k] for k in state if allowed(k)}
    # Traces, API settings, review PDFs and AI review results are deliberately excluded.
    return {'version': VERSION, 'values': values,
            'original': base64.b64encode(state['pdf']).decode('ascii')}

def restore(payload):
    if not isinstance(payload,dict) or payload.get('version') != VERSION:
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
        notice = validate_payload(values.get('notice'),notice_schema())
    data = base64.b64decode(payload.get('original',''),validate=True)
    if not data or len(data)>15*1024*1024 or fingerprint(data)!=values.get('source_hash'):
        raise ValueError('저장한 원본과 공고가 일치하지 않습니다.')
    if values.get('last_mode') not in ('실제 AI 분석','예시 화면 체험'):
        raise ValueError('저장한 사용 모드를 확인할 수 없습니다.')
    if not isinstance(values.get('pages'),list) or not all(isinstance(p,str) for p in values['pages']):
        raise ValueError('원문 본문을 확인할 수 없습니다.')
    if not isinstance(values.get('source_info',{}),dict):raise ValueError('원본 정보 오류')
    if not isinstance(values.get('source_filename'),str):raise ValueError('파일 이름 오류')
    for k,v in values.items():
        if k in ANSWERS | EXTRAS or k.startswith(('question_','doc_')):
            if v is not None and not isinstance(v,(str,int,float,bool)):
                raise ValueError('답변 형식 오류')
    if 'draft_answers' in values and not isinstance(values['draft_answers'],dict):
        raise ValueError('답변 형식 오류')
    screen=values.get('screen',2)
    values['screen']=screen if type(screen)==int and screen in (1,2,3,4) else 2
    if values['screen']==4 and 'draft_answers' not in values:values['screen']=3
    values.update(pdf=data,notice=notice,raw_notice=dict(notice))
    return values

_bridge = st.components.v2.component('gonggo_draft_storage',
    js=(Path(__file__).parent/'browser_draft.js').read_text(encoding='utf-8'),
    html='<span role="status" aria-live="polite"></span>',
    css='\nspan { font-size:13px; line-height:1.6; color:#666; overflow-wrap:anywhere; }\n')

def bootstrap():
    """Complete the browser read before any default form can overwrite it."""
    ready=st.session_state.get('_draft_loaded',False)
    result=_bridge(key='draft_loader',data={'op':'idle' if ready else 'load'},
                   on_loaded_change=lambda:None)
    if ready:return
    if not result.loaded:
        st.caption('이 브라우저에 저장한 준비 내용을 불러오는 중…')
        st.stop()
    info=result.loaded
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

def save_browser():
    payload=snapshot(st.session_state)
    if st.session_state.get('_draft_storage_error'):
        st.warning('브라우저 저장을 사용할 수 없습니다. 준비 목록을 내려받으세요. 설정에서 저장 내용을 초기화하거나 브라우저 저장 허용을 확인할 수 있습니다.')
        return
    serialized=json.dumps(payload,ensure_ascii=False,sort_keys=True)
    digest=hashlib.sha256(serialized.encode()).hexdigest()
    deleting=st.session_state.get('_draft_delete',False)
    operation='delete' if deleting else 'save' if payload else 'idle'
    ack=_bridge(key='draft_writer',data={'op':operation,'payload':payload,'digest':digest},
                on_saved_change=lambda:None)
    if deleting and ack.saved and ack.saved.get('status')=='deleted':
        st.session_state.pop('_draft_delete',None)
        st.rerun()

def clear_draft():
    for key in list(st.session_state):
        if allowed(key) or key in ('pdf','pending_file','preparation','result','profile',
             'raw_notice','raw_review','review_hash','review_pdf','notice_trace','review_trace'):
            st.session_state.pop(key,None)
    st.session_state.screen=1
    st.session_state['_draft_delete']=True
    st.session_state.pop('_draft_storage_error',None)
    st.session_state.pop('_draft_restored',None)
    st.session_state['_upload_generation']=st.session_state.get('_upload_generation',0)+1
