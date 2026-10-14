import json
from pathlib import Path
import pytest

from core import validate_payload, guard_review
from schema_builder import notice_schema, review_schema
from upstage_client import decode_steps, StudioError
from workflow_adapter import ground_notice
from planning import document_items, next_steps


def compact():
    # Values observed in Studio config20's public Tongyeong poster result.
    return {'공고명':'2026년 통영시 관광기념품 공모전', '주관_프로그램명':'통영시 관광기념품 공모전',
            '모집대상':'대한민국 국민 누구나','모집기간_시작일':'2026-08-26',
            '모집기간_종료일':'2026-08-28','지원방법':'방문접수, 우편접수','지원링크':'',
            '장학금_총액':5800000,'선발단계':[{'단계명':'접수','시작일시':'2026-08-26 09:00',
                '종료일시':'2026-08-28 18:00','진행방법':'방문접수 또는 우편접수'}]}


def step(model,data):
    return {'model':model,'content':[{'type':'output_text','text':json.dumps(data,ensure_ascii=False)}]}


def test_compact_schema_accepts_numbers_but_never_claims_unsupported_amount_or_documents():
    raw=decode_steps([step('Information Extract - 포스터',compact()),step('Instruct - 지시-2','참고 요약')])
    n=ground_notice(validate_payload(raw,notice_schema()),['대한민국 국민 누구나'])
    assert n['notice_type']=='대회·공모전' and n['_workflow_review']=='참고 요약'
    assert n['_schema_limits'] and n['_studio_compact']['장학금_총액']==5800000
    assert '5800000' not in n['benefits'] and not document_items(n,['대한민국 국민 누구나'])
    assert n['application_deadline']==''  # A title year alone isn't a dated application period.
    assert next_steps(n,{},[])[0]['title']=='원문의 제출서류·추가 조건 확인'
    card=next(c for c in guard_review(n,{}, {'documents_status':'일치'},[]) if c['key']=='documents')
    assert card['status']=='확인 필요'


def test_repeated_validation_keeps_limits_and_only_verbatim_source_can_ground_eligibility():
    raw=compact();raw['장학금_총액']=None
    n=validate_payload(validate_payload(raw,notice_schema()),notice_schema())
    n=ground_notice(n,['대한민국 국민 누구나\n접수기간 2026. 8. 26.(수) ~ 2026. 8. 28.(금) 09:00 ~ 18:00'])
    assert n['eligibility_page']=='1' and n['application_deadline']=='2026-08-28'
    assert n['_schema_limits'] and n['_studio_compact']==raw
    n=ground_notice(n,['다른 문서 원문'])
    assert n['eligibility_page']=='' and n['application_deadline']==''


def test_multiple_executed_extracts_keep_conflict_instead_of_last_value():
    one=compact();two={**one,'모집기간_종료일':'2026-09-01'}
    raw=decode_steps([step('Information Extract - 포스터',one),step('Information Extract - 포스터',two),
                     {'model':'Information Extract - 모집 안내','content':[],'status':'skipped'}])
    n=validate_payload(raw,notice_schema())
    assert not n['application_deadline']
    assert any('모집기간_종료일' in c for c in n['source_conflicts'])
    assert len(n['_studio_compact']['_extract_parts'])==2


def test_review_uses_final_instruct_and_removes_citations_without_changing_notice_page():
    initial={k:[] if s['type']=='array' else '' for k,s in review_schema()['properties'].items()}
    initial.update(summary='중간 결과',eligibility_status='일치')
    final={**initial,'summary':'마지막 검토','eligibility_status':'확인 필요[7](#citation-7)',
           'eligibility_page':'2【†10】','priority_actions':['추가 조건 확인【†2】']}
    raw=decode_steps([step('Information Extract',initial),step('Instruct - Decision-1','```json\n'+json.dumps(final,ensure_ascii=False)+'\n```')])
    actual=validate_payload(raw,review_schema())
    assert actual['summary']=='마지막 검토' and actual['eligibility_status']=='확인 필요'
    assert actual['eligibility_page']=='2' and actual['priority_actions']==['추가 조건 확인']


def test_invalid_final_instruct_does_not_silently_reuse_intermediate_decision():
    with pytest.raises(StudioError,match='JSON'):
        decode_steps([step('Information Extract',{'eligibility_status':'일치'}),step('Instruct','결과를 생성할 수 없습니다')])


def test_pinned_versions_match_actual_exports():
    root=Path(__file__).parents[1]
    settings=json.loads((root/'settings.json').read_text('utf-8'))
    for kind,version in [('notice',20),('review',4)]:
        export=json.loads((root/f'agent_configs/{kind}.config{version}.export.json').read_text('utf-8'))['exportedFrom']
        assert settings[f'{kind}_agent_id']==export['workflowId']
        assert settings[f'{kind}_config_id']==str(export['configVer'])


def test_verification_session_never_reads_or_writes_existing_browser_drafts(monkeypatch):
    from types import SimpleNamespace
    import browser_draft
    state={}
    fake=SimpleNamespace(session_state=state,query_params={'verification':'1'},info=lambda message:None)
    monkeypatch.setattr(browser_draft,'st',fake)
    def forbidden(**kwargs):raise AssertionError('Must not access existing browser storage')
    monkeypatch.setattr(browser_draft,'_bridge',forbidden)
    browser_draft.bootstrap();browser_draft.save_browser()
    fake.query_params={}
    browser_draft.bootstrap();browser_draft.save_browser()
    assert state['_verification_session']


def test_live_pdf20_regression_keeps_unsupported_document_list_unknown():
    fixture=json.loads((Path(__file__).parent/'fixtures/compact_pdf20.json').read_text('utf-8'))
    n=ground_notice(validate_payload(fixture['raw'],notice_schema()),fixture['pages'])
    assert n['application_deadline']=='2026-01-26' and n['eligibility_page']=='2'
    assert n['notice_type']=='대외활동·봉사' and n['_workflow_review']
    assert n['required_documents']==[] and n['_schema_limits']
    row=next(c for c in guard_review(n,{}, {'documents_status':'해당 없음'},fixture['pages']) if c['key']=='documents')
    assert row['status']=='확인 필요' and '설정에서' in row['reason']
