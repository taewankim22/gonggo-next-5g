"""Actual config21 exports plus explicitly synthetic failure cases. No paid calls."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

from core import fingerprint, validate_payload
from schema_builder import notice_schema
from workflow_adapter import ground_notice
from notice_overview import overview_model
from notice_facts import benefit_rows
from planning import document_items

FIXTURES = Path(__file__).parent/'fixtures'


def load(name='hackathon'):
    f=json.loads((FIXTURES/f'evidence_{name}21.json').read_text('utf-8'))
    return f, ground_notice(validate_payload({**f['raw'],'_classification':f['classification_from_executed_route']},notice_schema()),f['pages'])


def test_actual_hackathon_amounts_and_non_cash_survive_entire_adapter():
    f,n=load();m=overview_model(n,f['pages'])
    assert '총상금 · 500만원' in m['benefits']
    assert '대상 · 1팀 · 200만원' in m['benefits']
    assert '최우수상 · 1팀 · 150만원' in m['benefits']
    assert '우수상 · 2팀 · 150만원(1개 팀당 75만원)' in m['benefits']
    assert '150만원(1개 팀당 75만원) · 팀당' not in m['benefits']
    assert any('전문 멘토링' in r['display'] and r['verified'] for r in m['benefit_details'])
    assert '상금·혜택' not in m['pending'] and not n.get('_schema_limits')
    assert m['deadline']=='2026.10.20 · 23:59'
    assert '신청 주소' in m['pending']  # No invented application URL.


def test_actual_hackathon_documents_and_exclusions_reach_following_steps():
    f,n=load();rows=document_items(n,f['pages'])
    current=[r for r in rows if r['stage']=='지원단계']
    later=[r for r in rows if r['stage']=='선발 후·활동 중']
    assert len(current)==3 and len(later)==2
    assert any('참가신청서' in r['name'] for r in current)
    assert all('IR Deck' not in r['name'] and '시연 영상' not in r['name'] for r in current)
    assert len(n['_structured_notice']['지원조건'])==len(f['raw']['지원조건'])
    assert '허위' in n['eligibility_rule'] and '수상' in n['eligibility_rule']


def test_actual_poster_does_not_turn_top_prize_into_total_or_merged_cells_into_count():
    f,n=load('poster');m=overview_model(n,f['pages'])
    assert '300 만원' in m['benefits'] and '150만원' in m['benefits']
    assert '총상금' not in m['benefits'] and '5800000' not in m['benefits']
    assert '전통공예 1, 감성굿즈 1' not in m['benefits']
    assert '상금 지급 인원·단위' in m['pending']
    assert all(r['verified'] for r in m['benefit_details'])


def test_old_compact_results_recover_source_passages_without_reinterpreting_numeric_total():
    f,_=load();raw=copy.deepcopy(f['raw'])
    for key in ('지원조건','제출서류','혜택','일정','기본정보근거'):raw.pop(key)
    raw['장학금_총액']=99999999
    with patch('upstage_client.run_agent',side_effect=AssertionError('No calls')):
        n=ground_notice(validate_payload(raw,notice_schema()),f['pages'])
        m=overview_model(n,f['pages'])
    assert '99999999' not in m['benefits'] and '500만원' in n['benefits']
    assert n['_schema_limits'] and not n['required_documents']
    assert '제출서류' in m['pending'] and m['messages']


def test_correct_quote_cannot_validate_fabricated_amount_and_missing_stays_unknown():
    f,n=load();bad=copy.deepcopy(n)
    row=next(r for r in bad['_structured_notice']['혜택'] if r.get('혜택명')=='총상금')
    row['금액표현']='900만원'
    result=benefit_rows(bad,f['pages'])
    assert not next(r for r in result if r.get('혜택명')=='총상금')['verified']
    assert '900만원' not in overview_model(bad,f['pages'])['benefits']
    empty=overview_model({'notice_title':'합성 미기재 사례'},['공개 모집 안내'])
    assert empty['benefits']=='—' and empty['deadline']=='—'
    assert '상금·혜택' in empty['pending'] and '23:59' not in str(empty)


def test_browser_restore_preserves_actual_new_details_and_private_answers():
    from browser_draft import single_snapshot,restore_single
    f,n=load()
    # Synthetic bytes isolate the persistence contract, not an HWP reading test.
    data=b'isolated-persistence-fixture'
    state=dict(notice=n,pages=f['pages'],pdf=data,source_hash=fingerprint(data),
        source_filename='synthetic.hwp',last_mode='실제 AI 분석',screen=3,
        notice_config={'agent_id':'agt_test','config_id':'21'},answer_other_facts='테스트 답변')
    restored=restore_single(single_snapshot(state))
    assert restored['answer_other_facts']=='테스트 답변'
    assert restored['notice']['benefits']==n['benefits']
    assert restored['notice_config']==state['notice_config']
    assert single_snapshot(restored)['values']['notice']==n


def test_actual_scholarship_personal_semester_amounts_precede_whole_budget():
    f,n=load('scholarship');m=overview_model(n,f['pages'])
    assert '대학생 지원사업 · 장학금액 · 300명 · 학기당 300만 원' in m['benefits']
    assert '대학원생[석사] 지원사업 · 장학금액 · 20명 · 학기당 600만 원' in m['benefits']
    assert m['benefits'].index('학기당 300만')<m['benefits'].index('전체 지원 규모')
    assert '20.8억 원' in m['benefits'] and '연간 600' not in m['benefits']
    assert m['deadline']=='2026.09.28 · 18:00'
    assert 'http://www.kosaf.go.kr' in n['submission_method']
    # Unverified merged-table row amounts aren't promoted alongside grounded ones.
    assert any(not r['verified'] for r in m['benefit_details'])


def test_reanalysis_keeps_only_same_document_explicit_inputs_not_old_ai_results():
    from workspaces import retain_same_document_inputs
    state=dict(source_hash='same',answer_other_facts='테스트',question_one='모름',doc_done=True,
               notice={'old':True},result=['stale'],profile_overrides=['school'],answer_use_example=True)
    kept=retain_same_document_inputs(state,'same')
    assert kept==dict(answer_other_facts='테스트',question_one='모름',doc_done=True,profile_overrides=['school'])
    kept['profile_overrides'].append('other')
    assert state['profile_overrides']==['school']
    assert retain_same_document_inputs(state,'different')=={}


def test_explicit_abbreviated_year_and_range_clock_but_no_title_year_borrowing():
    from deadline_guard import explicit_date
    from deadline_calendar import document_deadlines,consolidate
    assert explicit_date('2026-09-28',"신청 마감 '26. 9. 28.(월) 18시")
    assert not explicit_date('2026-09-28','신청 마감 9. 28. 18시')
    text="신청 기간 '26. 9. 11.(금) 09시 ~ 9. 28.(월) 18시"
    dates=consolidate([document_deadlines({},[text],dict(id='test',source_url=''))])
    assert dates['events'][0]['date']=='2026-09-28'
    assert dates['events'][0]['time']=='18:00'


def test_latest_widget_edit_reaches_preparation_when_navigation_arrives_together(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr('browser_draft.bootstrap',lambda:None)
    monkeypatch.setattr('browser_draft.save_browser',lambda:None)
    monkeypatch.setattr('team_access.team_gate',lambda *a,**kw:(None,None))
    f,n=load();root=Path(__file__).parents[1];data=(root/f['source_file']).read_bytes()
    at=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    for k,v in dict(notice=n,pages=f['pages'],pdf=data,source_hash=fingerprint(data),
        source_filename='isolated.hwp',last_mode='실제 AI 분석',route='review',screen=3).items():at.session_state[k]=v
    at.run(timeout=20)
    field=next(w for w in at.text_input if w.label=='팀 구성·참가 조건을 확인해주세요')
    with patch('upstage_client.run_agent',side_effect=AssertionError('Navigation must not call API')):
        field.set_value('분리된 QA 답변')  # No intermediate rerun before clicking Next.
        next(b for b in at.button if b.label=='준비 목록 확인하기 →').click().run(timeout=20)
        assert at.session_state.screen==4 and not at.exception
        assert '분리된 QA 답변' in at.session_state.preparation['answers']['question_answers'].values()
        done=next(w for w in at.checkbox if '참가신청서' in w.label)
        key=done.key;done.check().run(timeout=20)
        for step in [2,3,4]:at.button(key=f'nav_{step}').click().run(timeout=20)
        assert at.checkbox(key=key).value
        assert '분리된 QA 답변' in at.session_state.preparation['answers']['question_answers'].values()
