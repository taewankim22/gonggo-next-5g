import json
from pathlib import Path
import pytest
from browser_draft import snapshot, restore
from core import fingerprint

ROOT=Path(__file__).parents[1]
@pytest.fixture
def state():
    data=(ROOT/'data/hyundai_jump_13.pdf').read_bytes()
    return {'notice':json.loads((ROOT/'data/demo_notice.json').read_text(encoding='utf-8')),
            'pdf':data,'source_hash':fingerprint(data),'source_filename':'example.pdf',
            'pages':['테스트 원문'],'last_mode':'예시 화면 체험','screen':4,
            'draft_answers':{'weekly_visits':2},'answer_weekly_visits':2,
            'answer_other_facts':'다음 주부터 참여 가능',
            'doc_012345abcdef_abcdef_done':True,
            'doc_012345abcdef_abcdef_applies':'해당',
            'question_012345abcdef_abcdef':'확인했습니다'}

def test_roundtrip_file_answers_checklist_and_step(state):
    restored=restore(json.loads(json.dumps(snapshot(state))))
    for key in state:assert restored[key]==state[key]

def test_credentials_and_runtime_state_never_serialized(state):
    for k in ['api_key','upstage_api_key','UPSTAGE_API_KEY','notice_trace',
              'review_trace','raw_review','result','answer_api_key','doc_api_key','question_api_key','_notice_request']:
        state[k]='DO-NOT-SAVE-SECRET'
    assert 'DO-NOT-SAVE-SECRET' not in json.dumps(snapshot(state))

def test_restore_cannot_inject_credentials(state):
    payload=snapshot(state)
    payload['values']['api_key']='malicious'
    payload['values']['upstage_api_key']='malicious'
    assert 'api_key' not in restore(payload)
    assert 'upstage_api_key' not in restore(payload)

def test_mismatched_file_rejected(state):
    payload=snapshot(state);payload['values']['source_hash']='wrong'
    with pytest.raises(ValueError):restore(payload)

def test_invalid_schema_and_version_rejected(state):
    payload=snapshot(state);payload['version']=999
    with pytest.raises(ValueError):restore(payload)
    payload=snapshot(state);payload['values']['notice']={}
    with pytest.raises(ValueError):restore(payload)

def test_sessions_have_independent_snapshots(state):
    a=restore(snapshot(state));b=restore(snapshot(state))
    a['answer_other_facts']='첫 번째 사용자'
    assert b['answer_other_facts']=='다음 주부터 참여 가능'

def test_empty_session_does_not_create_or_overwrite_draft():
    assert snapshot({'api_key':'secret','answer_other_facts':'empty'}) is None

def test_live_notice_schema_roundtrip(state):
    from schema_builder import notice_schema
    notice={k:[] if spec['type']=='array' else '' for k,spec in notice_schema()['properties'].items()}
    notice.update({k:v for k,v in state['notice'].items() if k in notice})
    state.update(notice=notice,last_mode='실제 AI 분석')
    restored=restore(snapshot(state))
    assert restored['notice']['notice_title']==notice['notice_title']
    assert restored['pdf']==state['pdf']
    assert restored['answer_weekly_visits']==2
