import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
import olefile
import pytest
from input_tools import inspect_input, map_image_page
from upstage_client import run_agent

FIXTURE = Path(__file__).parent/'fixtures/scholarship_notice.hwp'

def test_real_hwp_header_and_original_bytes():
    data = FIXTURE.read_bytes()
    info = inspect_input(data, 'announcement.HWP')
    assert info == {'mime':'application/x-hwp','pages':[], 'kind':'hangul'}
    assert map_image_page({'eligibility_quote':'공고문','eligibility_page':''},info)['eligibility_page']==''

def test_real_hwpx_container():
    data=(FIXTURE.parent/'ai_champion_notice.hwpx').read_bytes()
    assert inspect_input(data,'공고.hwpx')=={'mime':'application/hwp+zip','pages':[],'kind':'hangul'}

@pytest.mark.parametrize('data,name',[(b'broken','x.hwp'),(b'broken','x.hwpx'),(b'%PDF-1.7','x.hwp')])
def test_reject_fake_hangul(data,name):
    with pytest.raises(ValueError):inspect_input(data,name)

@pytest.mark.parametrize('flag',[2,4])
def test_reject_protected_hwp_before_upload(tmp_path,flag):
    p=tmp_path/'protected.hwp';p.write_bytes(FIXTURE.read_bytes())
    with olefile.OleFileIO(p,write_mode=True) as doc:
        header=bytearray(doc.openstream('FileHeader').read())
        header[36:40]=(int.from_bytes(header[36:40],'little')|flag).to_bytes(4,'little')
        doc.write_stream('FileHeader',bytes(header))
    with pytest.raises(ValueError,match='보호'):inspect_input(p.read_bytes(),p.name)

def make_hwpx(mime=b'application/hwp+zip',payload=b'<xml/>'):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('mimetype',mime)
        for name in ['header.xml','section0.xml','content.hpf']:z.writestr('Contents/'+name,payload)
    return out.getvalue()

def test_hwpx_container_not_inferred_as_pdf_or_single_page():
    assert inspect_input(make_hwpx(),'x.hwpx')=={'mime':'application/hwp+zip','pages':[],'kind':'hangul'}
    with pytest.raises(ValueError,match='형식'):inspect_input(make_hwpx(b'application/zip'),'x.hwpx')

def test_hwpx_expansion_limit():
    with pytest.raises(ValueError,match='너무 큽니다'):
        inspect_input(make_hwpx(payload=b'x'*(23*1024*1024)),'x.hwpx')

def test_agent_receives_original_hwp_mime_and_parse_trace(monkeypatch):
    import upstage_client
    data=FIXTURE.read_bytes(); calls={}
    class FakeClient:
        def __init__(self,**kwargs):
            self.files=SimpleNamespace(create=self.upload)
            self.responses=SimpleNamespace(create=self.response)
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def with_options(self,**kwargs):return self
        def upload(self,**kwargs):calls['upload']=kwargs;return SimpleNamespace(id='file-test')
        def response(self,**kwargs):
            calls['request']=kwargs
            return SimpleNamespace(status='completed',id='job-test',created_at=0,
                model_dump=lambda:{'output':[{'model':'extract','content':[{'type':'output_text','text':'{"notice_title":"공모전"}'}]}]})
    monkeypatch.setattr(upstage_client,'OpenAI',FakeClient)
    result=run_agent('test-only-key','agt_test','4',data,'공고.hwp',mime='application/x-hwp')
    assert calls['upload']['file']==('공고.hwp',data,'application/x-hwp')
    assert calls['request']['include']==['all']
    assert result['notice_title']=='공모전'
