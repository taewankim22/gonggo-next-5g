import io
import json
from pathlib import Path
import pytest
from pypdf import PdfReader
from core import evidence, guard_review, read_pdf, validate_payload, fingerprint
from schema_builder import CATEGORIES, notice_schema
from prepare_demo import sample_review
from pdf_tools import comparison_pdf
from upstage_client import decode_output, StudioError

ROOT=Path(__file__).parents[1]
@pytest.fixture
def notice():return json.loads((ROOT/'data/demo_notice.json').read_text(encoding='utf-8'))
@pytest.fixture
def pages():return read_pdf((ROOT/'data/hyundai_jump_13.pdf').read_bytes())
def card(notice,pages,answers,key):
    return next(c for c in guard_review(notice,answers,sample_review(notice,answers),pages) if c['key']==key)

def test_all_fixture_quotes_really_exist(notice,pages):
    for key in CATEGORIES:assert evidence(notice[key+'_quote'],notice[key+'_page'],pages),key
@pytest.mark.parametrize('quote,page',[('만들어낸 조건 문장입니다','2'),('재학생 및 휴학생','0'),('재학생 및 휴학생','50'),('','2'),('재학생 및 휴학생','2,3')])
def test_invalid_evidence(quote,page,pages):assert not evidence(quote,page,pages)
def test_weekly_total_does_not_replace_visits(notice,pages):
    c=card(notice,pages,{'weekly_visits':1,'weekly_hours':4},'commitment')
    assert c['status']=='불일치' and '방문 횟수' in c['reason']
def test_unknown_not_fail(notice,pages):assert card(notice,pages,{},'commitment')['status']=='확인 필요'
def test_center_restriction(notice,pages):assert card(notice,pages,{'selected_center':'다른 기관','skills':'중국어'},'preference')['status']=='해당 없음'
def test_missing_center(notice,pages):assert card(notice,pages,{'skills':'중국어'},'preference')['status']=='확인 필요'
def test_invalid_quote_blocks_positive(notice,pages):
    notice['eligibility_quote']='전혀 없는 합격 보장 문구'
    raw=sample_review(notice,{});raw['eligibility_status']='일치'
    assert guard_review(notice,{},raw,pages)[0]['status']=='확인 필요'
def test_tampered_model_quote_not_used(notice,pages):
    raw=sample_review(notice,{});raw['preference_quote']='조작된 인용'
    assert guard_review(notice,{},raw,pages)[1]['quote']==notice['preference_quote']
def test_bad_pdf_rejected():
    with pytest.raises(ValueError):read_pdf(b'Not PDF')
def test_schema_type_rejected(notice):
    notice['question_keys']='wrong'
    with pytest.raises(ValueError):validate_payload(notice,notice_schema())
def test_comparison_pdf_korean_readable(notice):
    data=comparison_pdf(notice,{'selected_center':'여명학교','weekly_visits':1})
    text=''.join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)
    assert '여명학교' in text and 'USER_ANSWERS' in text
def test_answer_revision_changes_fingerprint():assert fingerprint({'visits':1})!=fingerprint({'visits':2})
def test_invalid_api_json_no_fallback():
    with pytest.raises(StudioError):decode_output('not json')
def test_single_node_wrapper():assert decode_output('{"Extract-1":{"notice_title":"title"}}')=={'notice_title':'title'}
