import json
from pathlib import Path
from types import SimpleNamespace
import pytest


def test_completed_job_is_retrieved_after_ui_interrupt_without_resubmission(monkeypatch):
    import upstage_client as client
    calls=[]
    trace={}
    class UiRerun(BaseException):pass
    output=[{'model':'Information Extract','content':[{'type':'output_text','text':'{"title":"done"}'}]}]
    queued=SimpleNamespace(id='job_saved',status='queued')
    completed=SimpleNamespace(id='job_saved',status='completed',created_at=1,output_text='',model_dump=lambda:{'output':output})
    def upload(**kwargs):calls.append('upload');return SimpleNamespace(id='file_saved')
    def submit(**kwargs):calls.append('submit');return queued
    def retrieve(job,**kwargs):assert job=='job_saved';calls.append('retrieve');return completed
    class Connection:
        files=SimpleNamespace(create=upload)
        responses=SimpleNamespace(create=submit,retrieve=retrieve)
        def __init__(self,**kwargs):pass
        def with_options(self,**kwargs):
            assert kwargs=={'max_retries':2}
            return self
        def __enter__(self):return self
        def __exit__(self,*args):pass
    monkeypatch.setattr(client,'OpenAI',Connection)
    def progress(message):
        if trace.get('job_id'):raise UiRerun()
    with pytest.raises(UiRerun):
        client.run_agent('unit-test','agt_test','13',b'file',progress=progress,trace=trace)
    assert trace['job_id']=='job_saved'
    result=client.run_agent('unit-test','agt_test','13',b'file',trace=trace)
    assert result=={'title':'done'} and calls==['upload','submit','retrieve']
    with pytest.raises(client.StudioError,match='설정이 다릅니다'):
        client.run_agent('unit-test','agt_test','14',b'file',trace=trace)
    assert calls==['upload','submit','retrieve']


def test_app_resumes_pending_notice_after_rerun_and_counts_submission_once(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from streamlit.runtime.scriptrunner import RerunException,RerunData
    root=Path(__file__).parents[1]
    raw=json.loads((root/'tests/fixtures/routed_pdf13.json').read_text(encoding='utf-8'))['raw']
    calls=[];charged=[]
    def runner(*args,**kwargs):
        trace=kwargs['trace'];calls.append(bool(trace.get('job_id')))
        if not trace.get('job_id'):
            trace.update(job_id='job_pending',agent_id=args[1],config_id=args[2],file_id='file_test')
            raise RerunException(RerunData())
        return raw
    def protected(config,state,ledger,run,*args,**kwargs):
        charged.append(1);return run(*args,**kwargs)
    monkeypatch.setattr('upstage_client.run_agent',runner)
    monkeypatch.setattr('team_access.protected_call',protected)
    monkeypatch.setattr('team_access.team_gate',lambda *a,**k:(None,None))
    monkeypatch.setattr('catalog.cached_public',lambda *a:None)
    monkeypatch.setattr('browser_draft.bootstrap',lambda:None)
    monkeypatch.setattr('browser_draft.save_browser',lambda:None)
    at=AppTest.from_file(str(root/'app.py')).run()
    at.session_state.route='review';at.run()
    next(c for c in at.checkbox if c.label.startswith('공개 평가용')).check().run()
    next(b for b in at.button if b.label=='공고에서 조건 찾기').click().run()
    assert not at.exception
    assert calls==[False,True] and charged==[1]
    assert at.session_state.screen==2 and '_notice_request' not in at.session_state
    assert at.session_state.notice_trace['job_id']=='job_pending'
