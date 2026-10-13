import json
from pathlib import Path
import pytest
from core import guard_review
from independent_review import condition_rows
from input_tools import parse_pages
from planning import document_items,checklist_snapshot,next_steps,preparation_text,later_item
from source_context import locate_document,UNKNOWN,FUTURE,CURRENT
from test_conditions import actual_case

ROOT=Path(__file__).parents[1]

@pytest.mark.parametrize('model_status',['일치','불일치','확인 필요'])
def test_remaining_terms_conflict_survives_missing_region(model_status):
    n,p,a=actual_case()
    a['remaining_terms']=1
    for q in a['condition_answers']:
        if q['answer_key']=='remaining_terms':q['answer']=1
        if '4년제' in q['text']:q['answer']=''
    rows=condition_rows(n,a,p)
    assert next(r for r in rows if r['label']=='공고 기준일의 잔여학기')['status']=='불일치'
    assert next(r for r in rows if '4년제' in r['label'])['status']=='확인 필요'
    card=next(c for c in guard_review(n,a,{'eligibility_status':model_status},p) if c['key']=='eligibility')
    assert card['status']=='불일치' and '내 답변 1' in card['reason'] and '별도로' in card['reason']
    a['independent_conditions']=rows
    assert next_steps(n,a,a['document_checklist'])[0]['title']=='조건이 다른 항목 확인'
    assert '[불일치]' in preparation_text(n,a,a['document_checklist'],[])

def test_independent_threshold_boundary_and_missing_are_distinct():
    n,p,a=actual_case()
    for val,expected in [(2,'일치'),(0,'불일치'),(None,'확인 필요')]:
        a['remaining_terms']=val
        next(q for q in a['condition_answers'] if q['answer_key']=='remaining_terms')['answer']=val
        assert next(r for r in condition_rows(n,a,p) if r['label']=='공고 기준일의 잔여학기')['status']==expected

def test_neither_unverified_number_nor_free_text_gets_independent_pass():
    n,p,a=actual_case()
    n['minimum_remaining_terms']='99'
    q=next(q for q in a['condition_answers'] if q['answer_key']=='remaining_terms');q['answer']=1
    rows=condition_rows(n,a,p)
    assert next(r for r in rows if r['id']==q['id'])['status']=='확인 필요'
    assert next(r for r in rows if '4년제' in r['label'])['status']=='확인 필요'

def test_missing_quote_does_not_generate_a_confirmed_conflict():
    n,p,a=actual_case()
    q=next(q for q in a['condition_answers'] if q['answer_key']=='remaining_terms')
    q['quote']='존재하지 않는 최소 2학기';q['answer']=1
    r=next(r for r in condition_rows(n,a,p) if r['id']==q['id'])
    assert r['status']=='확인 필요' and not r['verified']

def test_actual_hwpx_current_list_excludes_future_evidence():
    d=json.loads((ROOT/'tests/fixtures/independent_hwpx.json').read_text(encoding='utf-8'))
    pages=d['pages'];items=document_items(d['notice'],pages)
    rows=checklist_snapshot(items,{},'지원 준비 중')
    current=[r for r in rows if not r['later'] and r['stage']!=UNKNOWN]
    assert len(current)==1 and '구현제안서' in current[0]['name']
    for term in ('신고증','입증자료','최근년도 결산재무제표'):
        item=next(i for i in items if term in i['name'])
        assert item['stage']==FUTURE and '후속연구' in item['stage_quote'] and item['stage_page']
        assert later_item(item,'지원 준비 중') and not later_item(item,'선발 후·활동 중')
    a={'review_stage':'지원 준비 중','document_checklist':rows}
    independent=condition_rows(d['notice'],a,pages)
    assert sum(r['status']=='이후 단계' for r in independent)==10
    actions=str(next_steps(d['notice'],a,rows))
    assert '신고증' not in actions and '결산재무제표' not in actions and '입증자료' not in actions

def test_scope_cross_page_reference_and_new_heading_reset():
    pages=['7. 참가 방법\n※ 8. 후속연구 관련 안내 참조\n신청 방법: 지원서를 제출\n8. 후속연구 관련 안내',
           '가. 신청 방법\n재무제표를 제출\n9. 참가 방법\n신청 방법: 지원서를 제출']
    future=locate_document('재무제표','재무제표',pages)
    assert future['stage']==FUTURE and future['stage_page']=='1'
    current=locate_document('지원서','지원서',pages)
    assert current['stage']==CURRENT

def test_ambiguous_timing_is_never_current_missing():
    pages=['1. 참가 방법\n신청 방법: 재무제표를 제출\n2. 후속연구 안내\n재무제표를 제출']
    n={'required_documents':['필수: 재무제표']};items=document_items(n,pages)
    assert items[0]['stage']==UNKNOWN
    rows=checklist_snapshot(items,{},'지원 준비 중');actions=next_steps(n,{},rows)
    assert actions[0]['title']=='서류 제출 시점 확인' and '현재 필수 누락으로 계산하지 않았습니다' in actions[0]['detail']

def test_report_name_alone_does_not_make_it_a_future_document():
    result=locate_document('결과보고서','필수: 결과보고서',['1. 참가 방법\n지난 활동의 결과보고서를 제출'])
    assert result['stage']==CURRENT

def test_new_app_table_keeps_answers_across_navigation_and_invalidates_ai(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from core import fingerprint
    monkeypatch.setattr('browser_draft.bootstrap',lambda:None)
    monkeypatch.setattr('browser_draft.save_browser',lambda:None)
    monkeypatch.setattr('team_access.team_gate',lambda *args,**kwargs:(None,None))
    n,p,a=actual_case();original=(ROOT/'data/hyundai_jump_13.pdf').read_bytes()
    at=AppTest.from_file(str(ROOT/'app.py')).run()
    for key,val in dict(notice=n,raw_notice=n,pages=p,pdf=original,source_hash=fingerprint(original),source_filename='hyundai.pdf',screen=3,last_mode='실제 AI 분석').items():at.session_state[key]=val
    at.run();at.number_input(key='answer_remaining_terms').set_value(1).run();at.button(key='nav_4').click().run()
    r=at.session_state['preparation']['condition_rows']
    assert any(x['status']=='불일치' and '잔여학기' in x['label'] for x in r)
    assert any(x['status']=='확인 필요' and '4년제' in x['label'] for x in r)
    at.session_state['result']=[{'status':'불일치'}]
    at.button(key='nav_3').click().run();assert at.number_input(key='answer_remaining_terms').value==1
    at.number_input(key='answer_remaining_terms').set_value(2).run();at.button(key='nav_4').click().run()
    assert 'result' not in at.session_state and not at.exception
    assert next(x for x in at.session_state['preparation']['condition_rows'] if '잔여학기' in x['label'])['status']=='일치'
