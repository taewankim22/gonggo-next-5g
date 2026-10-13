import io
import json
from pathlib import Path
import pytest
from PIL import Image
from input_tools import inspect_input, parse_pages, map_image_page
from core import guard_review, normalize, read_pdf
from pdf_tools import comparison_pdf

def image_bytes(fmt='PNG', size=(300,300)):
    b=io.BytesIO();Image.new('RGB',size,'white').save(b,fmt);return b.getvalue()

@pytest.mark.parametrize('fmt,extension,mime',[('PNG','png','image/png'),('JPEG','jpg','image/jpeg'),('JPEG','jpeg','image/jpeg')])
def test_original_image_types(fmt,extension,mime):
    assert inspect_input(image_bytes(fmt),'poster.'+extension)['mime']==mime

@pytest.mark.parametrize('data,name',[(b'broken','x.png'),(image_bytes(),'x.jpg'),(image_bytes(size=(50,50)),'x.png'),(b'','x.pdf')])
def test_reject_invalid_inputs(data,name):
    with pytest.raises(ValueError):inspect_input(data,name)

def test_missing_and_unreadable_not_nonapplicable():
    for presence in ('미기재','판독불가'):
        n={'documents_presence':presence}
        result=guard_review(n,{}, {'documents_status':'해당 없음'},[])
        card=next(c for c in result if c['key']=='documents')
        assert card['status']=='확인 필요'
        assert ('판독' if presence=='판독불가' else '문서에서') in card['reason']

def test_explicit_no_conflict_different_from_unknown():
    n={'schedule_rule':'교육에 참석해야 합니다','schedule_quote':'교육에 참석해야 합니다','schedule_page':'1','schedule_presence':'명시'}
    raw={'schedule_status':'일치'}
    known=guard_review(n,{'unavailable_dates':'참석 불가 일정 없음'},raw,['교육에 참석해야 합니다'])[-1]
    unknown=guard_review(n,{},raw,['교육에 참석해야 합니다'])[-1]
    assert known['status']=='일치' and unknown['status']=='확인 필요'

def test_comparison_preserves_punctuation():
    n={'preference_quote':'북한·한반도 관련 분야에 관심이 있는 학생 → 여명학교 선택'}
    text=''.join(read_pdf(comparison_pdf(n,{})))
    assert normalize(n['preference_quote']) in normalize(text)

def test_parse_uses_only_parse_nodes():
    payload=json.dumps({'elements':[{'page':1,'content':{'html':'<p>포스터 작은 각주</p>'}}]})
    assert parse_pages([{'model':'step_1_parse','content':[{'text':payload}]}])==[' 포스터 작은 각주 ']
    assert parse_pages([{'model':'step_2_extract','content':[{'text':payload}]}])==[]

def test_actual_parse_shape():
    p=Path(__file__).parents[1]/'tests/fixtures/public_parse.json'
    if not p.exists():pytest.skip('local actual trace not included')
    data=json.loads(p.read_text(encoding='utf-8'))
    pages=parse_pages(data['notice_execution']['steps'])
    assert len(pages)==4 and '현대점프스쿨' in pages[0]

def test_image_page_mapping_is_separate_from_ai_value():
    n={'eligibility_quote':'단일 포스터에 적힌 조건','eligibility_page':'','preference_quote':'','preference_page':''}
    mapped=map_image_page(n,{'kind':'image'})
    assert mapped['eligibility_page']=='1' and n['eligibility_page']==''
    assert mapped['preference_page']==''

def test_final_export_matches_schema():
    from schema_builder import notice_schema,review_schema
    root=Path(__file__).parents[1]
    for name,fn in [('notice',notice_schema),('review',review_schema)]:
        p=root/f'agent_configs/{name}.mission2.export.json'
        if not p.exists():pytest.skip('final exported workflow unavailable')
        d=json.loads(p.read_text(encoding='utf-8'))
        actual=d['workflowConfig']['informationExtractConfiguration']['schemas'][0]['json_schema']['schema']['properties']
        assert actual==fn()['properties']
