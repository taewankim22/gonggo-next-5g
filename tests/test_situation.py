"""Real stored analyses + isolated UI/state regression cases; no paid calls."""
import json
from pathlib import Path
import pytest
from core import fingerprint
from workflow_adapter import adapt_notice,ground_notice
from situation_questions import build_questionnaire,progress
from profiles import atomic_conditions

ROOT=Path(__file__).parents[1]

def fixture(name):
    x=json.loads((ROOT/'tests/fixtures'/f'{name}.json').read_text('utf-8'))
    return ground_notice(adapt_notice(x['raw']),x['pages']),x


def test_three_actual_notices_have_different_source_linked_questions():
    models=[]
    for f in ('routed_pdf13','evidence_scholarship21','evidence_hackathon21'):
        n,x=fixture(f);m=build_questionnaire(n,x['pages'],{},'지원 검토 중');models.append(m)
        assert m['current'] and len({q['id'] for q in m['current']})==len(m['current'])
        assert all(q['rule'] and q['category'] for q in m['current'])
        assert not any('30명'==q['title'] for q in m['current'])
    assert 'weekly_visits' in {q.get('key') for q in models[0]['current']}
    assert 'gpa' in {q.get('key') for q in models[1]['current']}
    assert 'long_term' not in {q.get('key') for q in models[1]['current']}
    assert 'age' in {q.get('key') for q in models[2]['current']}
    assert 'gpa' not in {q.get('key') for q in models[2]['current']}
    assert len({len(m['current']) for m in models})>1


@pytest.fixture
def app(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr('browser_draft.bootstrap',lambda:None)
    monkeypatch.setattr('browser_draft.save_browser',lambda:None)
    monkeypatch.setattr('team_access.team_gate',lambda *a,**kw:(None,None))
    def forbid(*a,**kw):raise AssertionError('UI navigation must not call Upstage')
    monkeypatch.setattr('upstage_client.run_agent',forbid)
    return AppTest.from_file(str(ROOT/'app.py')).run()


def load(at,name,screen=3):
    if 'notice' in at.session_state:at.button(key='entry_home').click().run();at.run()
    n,x=fixture(name)
    path=Path(x['source_file']);path=path if path.is_absolute() else ROOT/path
    if not path.exists():path=ROOT/'data'/path.name
    data=path.read_bytes()
    from workspaces import clear_active
    state=dict(at.session_state._state.filtered_state);clear_active(state)
    for key in list(at.session_state._state.filtered_state):
        if key not in state:del at.session_state[key]
    state.update(notice=n,raw_notice=n,pages=x['pages'],pdf=data,source_hash=fingerprint(data),
        source_filename=path.name,last_mode='실제 AI 분석',route='review',screen=screen)
    for key,value in state.items():at.session_state[key]=value
    return at.run()


@pytest.mark.parametrize('name',['routed_pdf13','evidence_scholarship21','evidence_hackathon21'])
def test_actual_notice_ui_and_preparation_use_latest_answers_without_api(app,name):
    at=load(app,name)
    assert not at.exception
    # Untouched defaults are not counted as answers, including after multiple reruns.
    for _ in range(2):
        assert progress(at.session_state.draft_answers['question_records'])[0]==0
        at.run()
    at.text_input(key='answer_other_facts').set_value('QA 마지막 입력')
    next(b for b in at.button if b.label=='준비 목록 확인하기 →').click().run()
    assert not at.exception and 'QA 마지막 입력' in at.session_state.draft_answers['other_facts']
    assert at.session_state.screen==4 and at.session_state.preparation['condition_rows']
    at.button(key='nav_3').click().run()
    assert at.text_input(key='answer_other_facts').value=='QA 마지막 입력'


def test_profile_unknown_and_numeric_edit_survive_profile_changes_and_restore(app):
    at=load(app,'evidence_hackathon21')
    c=next(c for c in atomic_conditions(at.session_state.notice) if c['field']=='age')
    scope=at.session_state.source_hash[:12];key=f'fact_{scope}_{c["id"]}_value'
    unknown=f'question_{scope}_'+fingerprint('profile_'+c['id']+':unknown')[:16]
    at.number_input(key=key).set_value(25).run()
    at.checkbox(key=unknown).check().run()
    at.session_state.common_profile={'age':{'state':'known','value':22,'period':'2026-10','scale':''}}
    at.run()
    assert at.number_input(key=key).value is None
    assert at.session_state.draft_answers['profile_facts'][c['id']]['value'] is None
    at.checkbox(key=unknown).uncheck().run()
    assert not at.number_input(key=key).disabled
    at.number_input(key=key).set_value(30).run()
    assert not any('15세' in text for text in at.session_state.draft_answers['question_answers'])
    from browser_draft import snapshot,restore
    restored=restore(snapshot(at.session_state._state.filtered_state))
    assert restored['profile_overrides'][c['id']]['value']==30
    assert restored['situation_responses']['profile_'+c['id']]['state']=='known'


def test_explicit_unknown_enrollment_is_not_overwritten_by_profile(app):
    at=load(app,'routed_pdf13')
    at.radio(key='answer_enrollment_status').set_value('모르겠어요').run()
    at.session_state.common_profile={'enrollment_status':{'state':'known','value':'재학','period':'2026-03'}}
    at.run();at.button(key='nav_4').click().run();at.button(key='nav_3').click().run()
    assert at.radio(key='answer_enrollment_status').value=='모르겠어요'
    assert at.session_state.draft_answers['enrollment_status'] is None


def test_selecting_gpa_scale_first_does_not_mark_unknown_or_disable_score(app):
    at=load(app,'evidence_scholarship21')
    scale=next(w for w in at.selectbox if w.label=='내 성적의 만점')
    scale.set_value('100').run()
    field=next(w for w in at.number_input if w.label=='성적 · 점')
    assert not field.disabled and field.value is None
    assert progress(at.session_state.draft_answers['question_records'])[0]==0
    field.set_value(80).run()
    assert next(f for f in at.session_state.draft_answers['profile_facts'].values() if f['field']=='gpa')['scale']=='100'


def test_conflict_is_preserved_with_unanswered_other_conditions(app):
    at=load(app,'routed_pdf13')
    at.number_input(key='answer_weekly_visits').set_value(1).run()
    at.button(key='nav_4').click().run()
    rows=at.session_state.preparation['condition_rows']
    assert any(r['status']=='불일치' and '방문' in r['label'] for r in rows)
    assert any(r['status']=='확인 필요' for r in rows)


def test_notice_switch_restore_and_hidden_center_answer(app):
    from browser_draft import single_snapshot
    from workspaces import activate
    at=load(app,'routed_pdf13')
    at.text_input(key='answer_selected_center').set_value('여명학교').run()
    at.text_input(key='answer_skills').set_value('QA 중국어 학습 경험').run()
    at.text_input(key='answer_selected_center').set_value('다른 기관').run()
    assert not any(w.key=='answer_skills' for w in at.text_input)
    assert 'skills' not in at.session_state.draft_answers
    saved=single_snapshot(at.session_state._state.filtered_state)
    load(at,'evidence_hackathon21')
    assert 'QA 중국어' not in str(at.session_state.draft_answers)
    from browser_draft import restore_single
    at.button(key='entry_home').click().run();at.run()
    state=dict(at.session_state._state.filtered_state);activate(state,saved)
    for key in list(at.session_state._state.filtered_state):
        if key not in state:del at.session_state[key]
    for key,value in state.items():at.session_state[key]=value
    at.run()
    at.text_input(key='answer_selected_center').set_value('여명학교').run()
    assert at.text_input(key='answer_skills').value=='QA 중국어 학습 경험'
    assert not at.exception


def test_composite_conditions_are_not_split_and_future_questions_are_separate():
    n,x=fixture('routed_hwpx13')
    m=build_questionnaire(n,x['pages'],{},'지원 검토 중')
    assert m['later']
    assert not {q['id'] for q in m['current']} & {q['id'] for q in m['later']}
    n,x=fixture('evidence_scholarship21')
    m=build_questionnaire(n,x['pages'],{},'지원 검토 중')
    assert any('특수대학원' in q['rule'] and '석·박사' in q['rule'] for q in m['current'])
    assert not any(q.get('key')=='remaining_terms' for q in m['current']) # no guessed integer from unrelated credits


def test_language_preference_is_not_a_major_and_social_question_is_scoped():
    n,x=fixture('routed_pdf13')
    assert not any(c['field']=='major' and '중국어' in c['quote'] for c in atomic_conditions(n))
    m=build_questionnaire(n,x['pages'],{},'지원 검토 중')
    social=next(q for q in m['current'] if q['kind']=='extra' and q['question']['kind']=='social_support')
    assert '사회적 배려' in social['rule'] and '중국어' not in social['rule']
    schedule=next(q for q in m['current'] if q.get('key')=='unavailable_dates')
    assert '면접' in schedule['display_rule'] and '서류 접수' not in schedule['display_rule']
