"""Regression cases grounded in the actual Hyundai Jump School notice."""
import json
from pathlib import Path
import pytest
from core import guard_review, fingerprint
from conditions import bind_answers, SOCIAL_QUESTION, social_document
from input_tools import parse_pages
from planning import question_keys, additional_questions, document_items, checklist_snapshot

ROOT=Path(__file__).parents[1]

def actual_case(social=None):
    data=json.loads((ROOT/'tests/fixtures/conditions_notice.json').read_text(encoding='utf-8'))
    n=data['notice'];pages=data['pages']
    a={'enrollment_status':'재학','remaining_terms':3,'selected_center':'다른 기관',
       'weekly_visits':2,'weekly_hours':4,'long_term':'가능','review_stage':'지원 준비 중',
       'unavailable_dates':'참석 불가 일정 없음','other_facts':''}
    items=document_items(n,pages);keys=question_keys(n,a)
    qs,_,_=additional_questions(n,keys,items,a['review_stage'])
    qa={q['text']:('서울 소재 4년제 재학, 통학 가능, 수료·졸업유예 아님' if q['condition_id']=='eligibility' else '') for q in qs}
    qa[SOCIAL_QUESTION]=social
    a.update(question_answers=qa,preference_facts={'social_support':social})
    a['condition_answers']=bind_answers(n,keys,qs,a,qa)
    a['document_checklist']=checklist_snapshot(items,{i['id']:{'applicability':social or '아직 모름','readiness':'아직 확인하지 않음'} for i in items},a['review_stage'])
    return n,pages,a

def cards(n,p,a,status='일치'):
    return {c['key']:c for c in guard_review(n,a,{k+'_status':status for k in ('eligibility','preference','commitment','documents','schedule')},p)}

def test_optional_unknown_does_not_contaminate_eligibility():
    n,p,a=actual_case()
    result=cards(n,p,a)
    assert result['eligibility']['status']=='일치'
    assert result['social_preference']['status']=='확인 필요'
    assert result['other_preference']['status']=='확인 필요'
    assert result['documents']['status']=='확인 필요'
    assert any(q['condition_id']=='eligibility' and '이동' in q['text'] for q in a['condition_answers'])
    assert not any('성적' in q['text'] for q in a['condition_answers'])

def test_missing_eligibility_only_downgrades_related_card():
    n,p,a=actual_case('해당 없음')
    next(q for q in a['condition_answers'] if '4년제' in q['text'])['answer']=''
    result=cards(n,p,a)
    assert result['eligibility']['status']=='확인 필요'
    assert result['social_preference']['status']=='해당 없음'

@pytest.mark.parametrize('value,expected',[(None,'확인 필요'),('해당','확인 필요'),('해당 없음','해당 없음')])
def test_social_subject_separate_from_unready_evidence(value,expected):
    n,p,a=actual_case(value);result=cards(n,p,a)
    assert result['social_preference']['status']==expected
    if value=='해당':assert '대상 여부: 해당' in result['social_preference']['reason']
    # Other-center exclusion must not exclude the independent social preference.
    assert result['preference']['status']=='해당 없음'
    assert result['documents']['status']=='확인 필요' # mandatory transcript still unready

def test_raw_na_without_explicit_applicability_is_unknown():
    n,p,a=actual_case();result=cards(n,p,a,'해당 없음')
    for key in ('eligibility','documents','commitment','schedule','social_preference'):
        assert result[key]['status']=='확인 필요'

def test_missing_answer_not_model_failure_but_real_conflict_remains():
    n,p,a=actual_case()
    next(q for q in a['condition_answers'] if '4년제' in q['text'])['answer']=None
    result=cards(n,p,a,'불일치')
    assert result['eligibility']['status']=='확인 필요'
    assert result['documents']['status']=='확인 필요'
    a['weekly_visits']=1
    # The old Extract quote is not continuous OCR text; use the actual page as verified evidence here.
    n['commitment_quote']=p[int(n['commitment_page'])-1]
    next(q for q in a['condition_answers'] if q['answer_key']=='weekly_hours')['answer']=None
    assert cards(n,p,a,'일치')['commitment']['status']=='불일치'

def test_unverified_social_quote_cannot_support_na():
    n,p,a=actual_case('해당 없음');n['preference_quote']='없는 원문 인용문'
    assert cards(n,p,a)['social_preference']['status']=='확인 필요'

def test_prepared_proof_is_only_a_self_report_match():
    n,p,a=actual_case('해당')
    for row in a['document_checklist']:
        if social_document(row):row['readiness']='준비 완료'
    result=cards(n,p,a)['social_preference']
    assert result['status']=='일치' and '인정 여부는 확인하지 않았습니다' in result['reason']

def test_subject_change_persists_and_updates_documents_in_real_app(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from browser_draft import snapshot,restore
    monkeypatch.setattr('browser_draft.bootstrap',lambda:None)
    monkeypatch.setattr('browser_draft.save_browser',lambda:None)
    # UI behavior is independent of deployment credentials; gate behavior has its own tests.
    monkeypatch.setattr('team_access.team_gate',lambda *args,**kwargs:(None,None))
    n,p,a=actual_case()
    at=AppTest.from_file(str(ROOT/'app.py')).run()
    original=(ROOT/'data/hyundai_jump_13.pdf').read_bytes()
    for key,value in dict(notice=n,raw_notice=n,pages=p,pdf=original,source_hash=fingerprint(original),source_filename='hyundai_jump_13.pdf',screen=3,last_mode='실제 AI 분석').items():
        at.session_state[key]=value
    at.run()
    widget='question_'+fingerprint(original)[:12]+'_'+fingerprint(SOCIAL_QUESTION)[:12]
    at.radio(key=widget).set_value('해당').run()
    at.button(key='nav_4').click().run()
    rows=at.session_state['preparation']['checklist']
    row=next(r for r in rows if social_document(r))
    assert row['applicability']=='해당' and row['readiness']=='아직 확인하지 않음'
    done='doc_'+fingerprint(original)[:12]+'_'+row['id']+'_done'
    at.checkbox(key=done).check().run()
    at.button(key='nav_3').click().run()
    assert at.radio(key=widget).value=='해당'
    at.radio(key=widget).set_value('해당 없음').run()
    at.button(key='nav_4').click().run()
    assert at.checkbox(key=done).disabled
    assert next(r for r in at.session_state['preparation']['checklist'] if social_document(r))['applicability']=='해당 없음'
    state=at.session_state._state.filtered_state
    restored=restore(snapshot(state))
    assert restored[widget]=='해당 없음' and restored[done] is True
    assert 'api_key' not in str(snapshot(state))
    assert not at.exception
