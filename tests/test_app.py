from pathlib import Path
from streamlit.testing.v1 import AppTest
import pytest

@pytest.fixture(autouse=True)
def browser_transport(monkeypatch):
    # AppTest has no JavaScript/IndexedDB. The real bridge is tested in-browser;
    # these tests exercise the application screens with transport disabled.
    monkeypatch.setattr('browser_draft.bootstrap',lambda:None)
    monkeypatch.setattr('browser_draft.save_browser',lambda:None)
    monkeypatch.setattr('team_access.team_gate',lambda *args,**kwargs:(None,None))

def test_routed_workflow_result_questions_and_checklist_survive_navigation():
    import json
    root=Path(__file__).parents[1]
    x=json.loads((root/'tests/fixtures/routed_pdf13.json').read_text(encoding='utf-8'))
    from workflow_adapter import ground_notice,adapt_notice
    at=AppTest.from_file(str(root/'app.py')).run()
    at.session_state.route='review';at.run()
    at.radio[0].set_value('예시 화면 체험').run()
    next(b for b in at.button if b.label=='예시 공고 살펴보기').click().run()
    n=ground_notice(adapt_notice(x['raw']),x['pages'])
    at.session_state.notice=n;at.session_state.raw_notice=n;at.session_state.pages=x['pages'];at.run()
    assert not at.exception
    assert any('AI가 짚은' in e.label for e in at.expander)
    at.button(key='nav_3').click().run()
    at.number_input(key='answer_weekly_visits').set_value(1).run()
    at.button(key='nav_4').click().run()
    assert not at.exception
    at.button(key='nav_3').click().run()
    assert at.number_input(key='answer_weekly_visits').value==1


def test_real_hwpx_duplicate_conditions_can_reach_preparation_without_widget_collision():
    import json
    from workflow_adapter import ground_notice,adapt_notice
    root=Path(__file__).parents[1]
    x=json.loads((root/'tests/fixtures/routed_hwpx13.json').read_text(encoding='utf-8'))
    at=AppTest.from_file(str(root/'app.py')).run()
    at.session_state.route='review';at.run()
    at.radio[0].set_value('예시 화면 체험').run()
    next(b for b in at.button if b.label=='예시 공고 살펴보기').click().run()
    n=ground_notice(adapt_notice(x['raw']),x['pages'])
    at.session_state.notice=n;at.session_state.raw_notice=n;at.session_state.pages=x['pages'];at.run()
    at.button(key='nav_3').click().run()
    assert not at.exception
    at.button(key='nav_4').click().run()
    assert not at.exception
    rows=at.session_state.preparation['checklist']
    certificate=next(r for r in rows if '전문사업연구자' in r['text'])
    assert certificate['later']


def test_condition_filter_is_display_only_and_sidebar_navigation_preserves_answers():
    from unittest.mock import patch
    from ui_components import required_progress
    at=AppTest.from_file(str(Path(__file__).parents[1]/'app.py')).run()
    at.session_state.route='review';at.run()
    at.radio[0].set_value('예시 화면 체험').run()
    next(b for b in at.button if b.label=='예시 공고 살펴보기').click().run()
    at.button(key='nav_3').click().run()
    at.selectbox(key='profile_preset').select('가상 B · 다른 기관 / 주 1회').run()
    at.button(key='nav_4').click().run()
    original=at.session_state.preparation['condition_rows']
    assert any(r['status']=='불일치' for r in original)
    with patch('upstage_client.run_agent',side_effect=AssertionError('UI must not call API')):
        filter_key='condition_filter_'+at.session_state.source_hash[:12]
        at.session_state[filter_key]='일치';at.run()
        assert at.session_state.preparation['condition_rows']==original
        doc=next(c for c in at.checkbox if str(c.key).endswith('_done'))
        key=doc.key;doc.check().run()
        assert required_progress(at.session_state.preparation['checklist'])[0]==1
        at.button(key='entry_home').click().run()
        at.button(key='entry_review').click().run()
        assert at.checkbox(key=key).value
        at.button(key='nav_3').click().run()
        assert at.number_input(key='answer_weekly_visits').value==1
        assert not any('확인하는 조건' in c.value or '적용한 ' in c.value for c in at.caption)
        assert not at.exception

def test_preset_survives_rerun_and_answer_change_invalidates_result():
    at=AppTest.from_file(str(Path(__file__).parents[1]/'app.py')).run()
    at.session_state.route='review'
    at.run()
    at.radio[0].set_value('예시 화면 체험').run()
    next(b for b in at.button if b.label=='예시 공고 살펴보기').click().run()
    at.button(key='nav_3').click().run()
    at.selectbox(key='profile_preset').select('가상 B · 다른 기관 / 주 1회').run()
    at.run()
    assert at.text_input(key='answer_selected_center').value=='다른 기관'
    assert at.selectbox(key='answer_enrollment_status').value=='재학'
    at.button(key='nav_4').click().run()
    next(b for b in at.button if b.label=='내 조건과 대조하기').click().run()
    assert not at.exception
    cards=at.session_state['result']
    assert next(c for c in cards if c['key']=='preference')['status']=='해당 없음'
    assert next(c for c in cards if c['key']=='commitment')['status']=='불일치'
    at.button(key='nav_3').click().run()
    at.number_input(key='answer_weekly_visits').set_value(2).run()
    assert 'result' not in at.session_state

def test_unauthenticated_live_call_has_no_fake_result(monkeypatch):
    monkeypatch.setattr('catalog.cached_public',lambda *args:None)
    at=AppTest.from_file(str(Path(__file__).parents[1]/'app.py')).run()
    at.session_state.route='review'
    at.run()
    next(c for c in at.checkbox if c.label.startswith('공개 평가용')).check().run()
    next(b for b in at.button if b.label=='공고에서 조건 찾기').click().run()
    assert 'notice' not in at.session_state
    assert at.error

def test_document_rules_always_offer_review_stage_even_if_agent_omits_question():
    import json
    root=Path(__file__).parents[1]
    at=AppTest.from_file(str(root/'app.py')).run()
    at.session_state.route='review'
    at.run()
    at.radio[0].set_value('예시 화면 체험').run()
    next(b for b in at.button if b.label=='예시 공고 살펴보기').click().run()
    at.button(key='nav_3').click().run()
    notice=json.loads((root/'data/demo_notice.json').read_text(encoding='utf-8'))
    notice['question_keys']=[]
    at.session_state['notice']=notice
    at.run()
    assert at.selectbox(key='answer_review_stage').label=='현재 지원 단계'
    assert not at.exception

def test_actual_hwp_checklist_state_updates_and_invalidates_ai_result():
    import json
    root=Path(__file__).parents[1]
    d=json.loads((root/'tests/fixtures/public_hwp.json').read_text(encoding='utf-8'))
    from input_tools import parse_pages
    from planning import document_items
    at=AppTest.from_file(str(root/'app.py')).run()
    at.session_state.route='review'
    at.run()
    at.radio[0].set_value('예시 화면 체험').run()
    next(b for b in at.button if b.label=='예시 공고 살펴보기').click().run()
    at.button(key='nav_3').click().run()
    at.session_state['notice']=d['notice'];at.session_state['raw_notice']=d['notice']
    pages=d['pages'];at.session_state['pages']=pages
    at.run()
    assert not at.exception
    assert not any(x.label=='개인 일정 확인 상태' for x in at.selectbox)
    scope=at.session_state['source_hash'][:12]
    item=next(i for i in document_items(d['notice'],pages) if '발표자료' in i['name'])
    widget='doc_'+scope+'_'+item['id']+'_done'
    at.button(key='nav_4').click().run()
    next(b for b in at.button if b.label=='내 조건과 대조하기').click().run()
    assert 'result' in at.session_state
    at.checkbox(key=widget).check().run()
    assert not at.exception and 'result' not in at.session_state
    actions=at.session_state['preparation']['next_actions']
    assert '발표자료' not in str(actions) and '결과보고서' not in str(actions)
    assert '공모전 지원금 신청서' in str(actions)


def test_four_screens_preserve_answers_file_checklist_and_review_without_api():
    from unittest.mock import patch
    at=AppTest.from_file(str(Path(__file__).parents[1]/'app.py')).run()
    at.session_state.route='review'
    at.run()
    at.radio[0].set_value('예시 화면 체험').run()
    next(b for b in at.button if b.label=='예시 공고 살펴보기').click().run()
    original=at.session_state['pdf']
    assert at.session_state['screen']==2
    assert not at.number_input
    at.button(key='nav_3').click().run()
    at.selectbox(key='profile_preset').select('가상 B · 다른 기관 / 주 1회').run()
    at.text_input(key='answer_other_facts').set_value('왕복 통학 1시간').run()
    at.button(key='nav_4').click().run()
    done=next(c for c in at.checkbox if str(c.key).endswith('_done'))
    doc_key=done.key
    done.check().run()
    applies=next(c for c in at.selectbox if str(c.key).endswith('_applies'))
    apply_key=applies.key
    applies.select('해당').run()
    next(b for b in at.button if b.label=='내 조건과 대조하기').click().run()
    assert 'result' in at.session_state
    with patch('upstage_client.run_agent',side_effect=AssertionError('Navigation must not call API')):
        for step in [1,2,3]:at.button(key=f'nav_{step}').click().run()
        assert at.text_input(key='answer_other_facts').value=='왕복 통학 1시간'
        assert at.text_input(key='answer_selected_center').value=='다른 기관'
        assert at.number_input(key='answer_weekly_visits').value==1
        assert at.selectbox(key='answer_enrollment_status').value=='재학'
        at.button(key='nav_4').click().run()
        assert at.checkbox(key=doc_key).value is True
        assert at.selectbox(key=apply_key).value=='해당'
        assert at.session_state['pdf']==original
        assert 'result' in at.session_state
        assert not at.exception


def test_live_original_retained_when_upload_widget_hidden():
    from unittest.mock import patch
    from core import fingerprint
    import json
    root=Path(__file__).parents[1]
    at=AppTest.from_file(str(root/'app.py')).run()
    original=(root/'data/hyundai_jump_13.pdf').read_bytes()
    at.session_state['notice']=json.loads((root/'data/demo_notice.json').read_text(encoding='utf-8'))
    at.session_state['pdf']=original
    at.session_state['pages']=[]
    at.session_state['source_hash']=fingerprint(original)
    at.session_state['source_filename']='내가_올린_공고.pdf'
    with patch('upstage_client.run_agent',side_effect=AssertionError('No automatic API call')):
        at.run()
        for step in [2,3,4,1]:at.button(key=f'nav_{step}').click().run()
        assert any('내가_올린_공고.pdf' in c.value for c in at.caption)
        assert at.session_state['pdf']==original
        assert 'notice' in at.session_state
        assert not at.exception
