import json
from pathlib import Path
from core import validate_payload,guard_review
from schema_builder import notice_schema,review_schema
from workflow_adapter import adapt_notice,ground_notice
from planning import document_items,additional_questions,checklist_snapshot,next_steps
from upstage_client import decode_steps
from conditions import bind_answers

ROOT=Path(__file__).parents[1]


def test_identical_questions_are_deduplicated_but_distinct_stages_stay_separate():
    from workflow_adapter import structured_questions
    current={'분류':'지원자격','조건':'연구팀 구성이 필요함','적용대상':'전체','적용단계':'지원단계'}
    future={**current,'적용대상':'우수팀','적용단계':'선발 후·활동 중'}
    n={'_structured_notice':{'지원조건':[current,dict(current),future]}}
    active,later,_=structured_questions(n,'지원 검토 중')
    assert len(active)==len(later)==1
    assert active[0]['id']!=later[0]['id'] and active[0]['text']!=later[0]['text']

def raw_notice():
    return {'공고명':'공개 시험 공고','공고유형':'대회·공모전','주최주관':'','접수방법':'','접수링크':'',
            '접수마감':'','접수마감설명':'','활동기간':'','지원조건':[],'제출서류':[],
            '일정':[],'혜택':[],'문의처':[],'주의사항':[]}

def test_selects_executed_branch_not_last_skipped_extract_and_decodes_instruct():
    raw=raw_notice()
    result=decode_steps([
        {'model':'Information Extract - 대회','content':[{'type':'output_text','text':json.dumps(raw)}]},
        {'model':'Information Extract - 기타','content':[],'status':'skipped'},
        {'model':'Instruct - 대회','content':[{'type':'output_text','text':json.dumps('검토\n총 규모 (3쪽)【†9】')}]}
    ])
    assert result['공고유형']=='대회·공모전'
    assert result['_workflow_review']=='검토\n총 규모 (3쪽)'

def test_future_docs_and_unknown_values_never_become_current_required_or_zero():
    raw=raw_notice();quote='협약 시 영리기관은 결산재무제표를 제출해야 함'
    raw['제출서류']=[{'서류명':'결산재무제표','필수여부':'해당자만','적용대상':'영리기관',
        '제출단계':'선발 후·활동 중','제출설명':'협약 시','근거원문':quote,'근거페이지':'1'},
        {'서류명':'필수서류 및 제출서류','제출단계':'지원단계'}]
    raw['혜택']=[{'종류':'연구지원','내용':'후속연구','금액표현':'최대 60억원','금액범위':'전체총규모'}]
    n=validate_payload(raw,notice_schema());items=document_items(n,[quote])
    assert n['activity_period']=='' and n['minimum_weekly_hours']==''
    assert '전체총규모' in n['benefits']
    assert len(items)==1
    rows=checklist_snapshot(items,{},'지원 준비 중')
    assert rows[0]['later'] and rows[0]['applicability']=='아직 모름'
    assert not any(a['title']=='준비할 제출물' for a in next_steps(n,{},rows))

def test_unique_verbatim_evidence_relocates_page_but_ambiguous_quote_does_not():
    raw=raw_notice();quote='본 대학의 4년제 재학생만 지원 가능합니다'
    raw['지원조건']=[{'분류':'지원자격','조건':'4년제 재학','적용대상':'전체','적용단계':'지원단계',
        '대조항목':'대학유형','비교방법':'같음','기준값':'4년제','근거원문':quote,'근거페이지':'1'}]
    n=ground_notice(adapt_notice(raw),['표지',quote]);assert n['eligibility_page']=='2'
    n=ground_notice(adapt_notice(raw),['표지',quote,quote]);assert n['eligibility_page']=='1'

def test_unknown_answers_keep_own_condition_and_future_questions_separate():
    raw=raw_notice()
    raw['지원조건']=[{'분류':'지원자격','조건':'팀 구성이 필요함','적용대상':'전체','적용단계':'지원단계','근거원문':'지원자는 연구팀 구성이 반드시 필요합니다','근거페이지':'1'},
        {'분류':'지원자격','조건':'후속연구 법인 구성','적용대상':'선발팀','적용단계':'선발 후·활동 중','근거원문':'후속연구 지원은 법인 연구체계 구성이 필수입니다','근거페이지':'2'}]
    n=adapt_notice(raw);active,later,_=additional_questions(n,[],[],'지원 준비 중')
    assert len(active)==len(later)==1 and active[0]['page']=='1' and later[0]['page']=='2'
    assert bind_answers(n,[],active,{}, {active[0]['text']:''})[0]['answer']==''

def test_forbidden_enrollment_not_added_as_allowed():
    raw=raw_notice()
    raw['지원조건']=[{'분류':'지원자격','조건':'수료생 및 졸업예정자 지원불가','적용단계':'지원단계',
        '대조항목':'학적','근거원문':'수료생 및 졸업예정자 지원불가','근거페이지':'1'}]
    assert not adapt_notice(raw)['allowed_statuses']

def test_nested_output_survives_legacy_validation_twice():
    n=validate_payload(raw_notice(),notice_schema())
    assert validate_payload(n,notice_schema())['_structured_notice']==n['_structured_notice']

def test_table_delimiters_do_not_hide_a_real_numeric_conflict():
    from core import evidence
    from independent_review import condition_rows
    raw=raw_notice();quote='대학생-청소년 멘토링 주 2회, 4시간 방문 멘토링'
    raw['지원조건']=[{'분류':'활동의무','조건':'주 2회 방문','적용단계':'선발 후·활동 중','근거원문':quote,'근거페이지':'1'}]
    pages=['| 대학생-청소년 멘토링 | 주 2회, 4시간 방문 멘토링 |']
    n=ground_notice(adapt_notice(raw),pages)
    rows=condition_rows(n,{'weekly_visits':1},pages)
    assert next(r for r in rows if r['label']=='주당 방문 횟수')['status']=='불일치'
    assert not evidence('대학생-청소년 멘토링 주 2회, 방문 멘토링','1',pages)

def test_actual_public_pdf_keeps_conflict_and_unanswered_separately():
    from independent_review import condition_rows
    x=json.loads((ROOT/'tests/fixtures/routed_pdf13.json').read_text(encoding='utf-8'))
    n=ground_notice(adapt_notice(x['raw']),x['pages'])
    rows=condition_rows(n,{'weekly_visits':1,'remaining_terms':3},x['pages'])
    assert any(r['label']=='주당 방문 횟수' and r['status']=='불일치' for r in rows)
    assert any(r['status']=='확인 필요' for r in rows)
    assert n['preference_center']=='여명학교'

def test_poster_does_not_promote_ungrounded_award_to_per_person_payment():
    x=json.loads((ROOT/'tests/fixtures/routed_poster13.json').read_text(encoding='utf-8'))
    n=ground_notice(adapt_notice(x['raw']),x['pages'])
    assert n['_structured_notice']['혜택'][0]['금액범위']=='미확인'
    assert not n['activity_period'] and not document_items(n,x['pages'])

def test_actual_hwpx_source_heading_overrides_incorrect_current_stage():
    x=json.loads((ROOT/'tests/fixtures/routed_hwpx13.json').read_text(encoding='utf-8'))
    n=ground_notice(adapt_notice(x['raw']),x['pages'])
    rows=checklist_snapshot(document_items(n,x['pages']),{},'지원 준비 중')
    assert next(r for r in rows if r['name']=='전문사업연구자 신고증')['later']
    assert all(r['later'] for r in rows if '재무제표' in r['name'] or '채용확인서' in r['name'])
    assert not next(r for r in rows if r['name']=='구현제안서')['later']
    assert any(a['title']=='추가 제출자료 공지 확인' for a in next_steps(n,{},rows))
    assert '전체 지원 규모' in n['benefits'] and '장학금' not in n['benefits']
