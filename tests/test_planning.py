import json
from pathlib import Path
from planning import *
from input_tools import parse_pages
from core import guard_review

ROOT=Path(__file__).parents[1]
def actual(name):
    path=ROOT/'tests/fixtures'/('public_'+name+'.json')
    d=json.loads(path.read_text(encoding='utf-8'))
    return d['notice'],d['pages']

def test_hwp_has_four_pre_documents_and_one_later_document():
    n,pages=actual('hwp');items=document_items(n,pages)
    assert len(items)==5 and all(i['source_found'] for i in items)
    assert [i['name'] for i in items if later_item(i,'지원 준비 중')]==['결과보고서(학과 메일 jyelee@korea.ac.kr 제출)']
    assert 'unavailable_dates' not in question_keys(n)
    q,l,c=additional_questions(n,question_keys(n),items,'지원 준비 중')
    assert [x['text'] for x in q]==['본 학과 재학생인가요?','초과학기가 아닌가요?']

def test_optional_document_not_promoted_to_required():
    n,pages=actual('sample1');items=document_items(n,pages)
    assert [i['category'] for i in items]==['필수','선택']
    rows=checklist_snapshot(items,{items[1]['id']:{'applicability':'해당 없음'}},'지원 준비 중')
    actions=next_steps(n,{},rows)
    assert '성적 증명서' in actions[0]['detail']
    assert not any('사회적 배려' in x['detail'] for x in actions)

def test_weak_ocr_names_stay_unverified():
    items=document_items({'required_documents':['필수: 상상의 증명서']},['제출서류는 추후 공지'])
    assert not items[0]['source_found']
    actions=next_steps({}, {}, checklist_snapshot(items,{},'지원 준비 중'))
    assert actions[0]['title']=='적용 대상·원문 확인'

def test_checking_ready_updates_actions_without_ai_and_later_not_missing():
    n,pages=actual('hwp');items=document_items(n,pages)
    states={i['id']:{'readiness':'준비 완료'} for i in items if '발표자료' not in i['name'] and '결과보고서' not in i['name']}
    actions=next_steps(n,{},checklist_snapshot(items,states,'지원 준비 중'))
    assert '발표자료' in actions[0]['detail'] and '결과보고서' not in str(actions)
    states[next(i['id'] for i in items if '발표자료' in i['name'])]={'readiness':'준비 완료'}
    assert next_steps(n,{'enrollment_status':'재학'},checklist_snapshot(items,states,'지원 준비 중'))[0]['title']=='준비한 내용과 제출 경로 확인'
    assert any('결과보고서' in a['detail'] for a in next_steps(n,{},checklist_snapshot(items,states,'활동 종료 후')))

def test_empty_document_list_does_not_mean_no_documents_required():
    n,pages=actual('sample3')
    assert document_items(n,pages)==[] and 'unavailable_dates' not in question_keys(n)
    assert '필요 없다는 뜻은 아닙니다' in next_steps(n,{},[])[0]['detail']

def test_only_attendance_schedule_asks_unavailable_dates():
    assert not has_attendance({'schedule_rule':'7월 1일 접수, 7월 5일 합격자 발표'})
    assert has_attendance({'schedule_rule':'7월 5일 필수 면접'})

def test_center_specific_skill_not_asked_for_other_center():
    n,_=actual('sample1')
    assert 'skills' not in question_keys(n,{'selected_center':'다른 기관'})
    assert 'skills' in question_keys(n,{'selected_center':n['preference_center']})

def test_future_research_questions_deferred_and_retained():
    n,pages=actual('hwpx');items=document_items(n,pages)
    q,l,c=additional_questions(n,question_keys(n),items,'지원 준비 중')
    assert l and any('후속연구' in x['text'] for x in l)
    _,l2,_=additional_questions(n,question_keys(n),items,'선발 후·활동 중')
    assert not l2

def test_unready_checklist_cannot_become_documents_match():
    n,pages=actual('hwp')
    answers={'review_stage':'지원 준비 중','document_checklist':checklist_snapshot(document_items(n,pages),{},'지원 준비 중')}
    card=next(c for c in guard_review(n,answers,{'documents_status':'일치'},pages) if c['key']=='documents')
    assert card['status']=='확인 필요'

def test_preparation_download_preserves_unknown_and_original_item():
    n,pages=actual('sample1');rows=checklist_snapshot(document_items(n,pages),{},'지원 준비 중')
    text=preparation_text(n,{},rows,next_steps(n,{},rows))
    assert '아직 모름' in text and '선택' in text and '서류 내용 검증 아님' in text
