"""Isolated preparation regressions. Actual saved outputs and explicit synthetic edges."""
import json
from copy import deepcopy
from pathlib import Path
import pytest
from core import fingerprint
from preparation_model import document_rows,document_progress,preparation_actions,bucket,compare_sources,source_bundle,adopt_public_update
from workflow_adapter import ground_notice,adapt_notice
from source_context import CURRENT,FUTURE,AFTER,UNKNOWN

ROOT=Path(__file__).parents[1]


def actual(name):
    x=json.loads((ROOT/'tests/fixtures'/f'{name}.json').read_text('utf-8'))
    n=ground_notice(adapt_notice(x['raw']),x['pages'])
    return n,x


def bundle(n,pages,sha='a'*64,status='uploaded'):
    return dict(url='',documents=[dict(notice=n,pages=pages,sha256=sha,name='공고.pdf',url='',selected=True,config={})],
        status=status,inventory=[{'name':'공고.pdf','url':'','status':'ready'}],warnings=[],stale=False,changes=[],checked_at='')


@pytest.mark.parametrize('name',['routed_pdf13','evidence_scholarship21','evidence_hackathon21'])
def test_actual_documents_keep_sources_and_no_invented_links(name):
    n,x=actual(name);b=bundle(n,x['pages']);rows=document_rows(b,'지원 준비 중',{},{});progress=document_progress(rows,b)
    assert rows and all(r['source_name']=='공고.pdf' and r['storage_key'] and r['sources'] for r in rows)
    assert all(not r['requirements'] or r['requirement_verified'] for r in rows)
    assert progress['done']==0 and progress['partial'] # uploaded file is not all attachments
    assert all(r['bucket']!='현재 단계' for r in rows if r['stage'] in (FUTURE,AFTER,UNKNOWN))
    # Unchecked documents cannot become eligibility rejection.
    assert all(r['readiness']=='아직 확인하지 않음' for r in rows)


def test_empty_unknown_and_conditional_documents_never_show_complete():
    n,x=actual('evidence_hackathon21');n['_structured_notice']['제출서류']=[]
    b=bundle(n,x['pages']);assert document_progress([],b)==dict(done=0,total=0,partial=True,unknown=True)
    assert '제출서류 목록' in str(preparation_actions(b,[],[],{},False))


def test_stages_and_deadline_actions_are_distinct():
    assert bucket({'stage':CURRENT},'서류 제출 후')=='이전 단계'
    assert bucket({'stage':CURRENT},'선발 후·활동 중')=='이전 단계'
    assert bucket({'stage':FUTURE},'선발 후·활동 중')=='현재 단계'
    assert bucket({'stage':AFTER},'지원 검토 중')=='이후 단계'
    n,x=actual('evidence_hackathon21');b=bundle(n,x['pages']);rows=document_rows(b,'지원 준비 중',{}, {})
    steps=preparation_actions(b,rows,[],{'review_stage':'지원 준비 중'},expired=True)
    assert not any(a['target']=='document' for a in steps)


def test_checked_requirement_change_preserves_record_but_excludes_completion():
    n,x=actual('evidence_hackathon21');b=bundle(n,x['pages']);r=document_rows(b,'지원 준비 중',{}, {})[0]
    state={'prep_document_states':{r['storage_key']:{'done':True,'signature':r['signature'],'applicability':'해당'}}}
    same=document_rows(b,'지원 준비 중',state,{})[0];assert same['done'] and not same['needs_recheck']
    # Synthetic version change: same identity and source quote but changed requirement.
    changed=deepcopy(b);changed['documents'][0]['notice']['_structured_notice']['제출서류'][0]['제출설명']+=' 추가 확인'
    after=document_rows(changed,'지원 준비 중',state,{})[0]
    assert after['done'] and after['needs_recheck'] and after['readiness']!='준비 완료'
    assert state['prep_document_states'][r['storage_key']]['done']


def test_duplicates_and_conflicts_keep_source_scope():
    n,x=actual('evidence_hackathon21');b=bundle(n,x['pages']);b['url']='https://example.org/notice'
    original=document_rows(b,'지원 준비 중',{}, {})
    copy=deepcopy(b['documents'][0]);copy.update(url='https://example.org/attachment',selected=False,sha256='b'*64,name='첨부.pdf')
    b['documents'].append(copy)
    same=document_rows(b,'지원 준비 중',{},{});assert len(same)==len(original) and len(same[0]['sources'])==2
    copy['notice']['_structured_notice']['제출서류'][0]['필수여부']='선택'
    different=document_rows(b,'지원 준비 중',{},{});assert sum(bool(r.get('conflict')) for r in different)>=2


def test_priority_keeps_eligibility_conflict_and_no_completion_action():
    n,x=actual('routed_pdf13');b=bundle(n,x['pages']);rows=document_rows(b,'지원 준비 중',{}, {})
    conditions=[dict(id='x',category='eligibility',status='불일치',verified=True,reason='학적 불일치'),
                dict(id='y',category='preference',status='확인 필요',label='우대 여부',reason='미입력')]
    a=preparation_actions(b,rows,conditions,{},False)
    assert a[0]['target']=='conditions' and any(x['target']=='question' for x in a)
    for r in rows:r.update(readiness='준비 완료',done=True)
    assert not any(x['target']=='document' for x in preparation_actions(b,rows,[],{},False))


def test_source_diff_requires_bytes_and_same_config():
    n,x=actual('evidence_hackathon21');old=dict(notice=n,pages=x['pages'])
    r=dict(id='x',source_url='https://example.org',checked_at='2026-10-17',sha256='a',config={'id':'21'})
    assert compare_sources(r,old,r,old)['status']=='unchanged'
    assert compare_sources(r,old,{**r,'sha256':'b','config':{'id':'22'}},old)=={
        'status':'source_and_config_changed','items':[],'previous_checked_at':'2026-10-17','checked_at':'2026-10-17','old_hash':'a','new_hash':'b'}


def test_source_retry_only_executes_requested_document_and_preserves_completed(tmp_path,monkeypatch):
    from tests.test_live_discovery import article,result
    from live_catalog import LiveCatalog,analyze_public
    from discovery_flow import refresh_latest
    a=article();a['documents'].append({**a['documents'][0],'document_url':a['url']+'&file=2','data':a['documents'][0]['data']+b'\n','name':'첨부.pdf'})
    calls=[]
    def runner(*args):calls.append(args[1]);return result()
    analyze_public(tmp_path,a,0,'agt_test','13',runner)
    monkeypatch.setattr('nationwide_notice.prepare_public_article',lambda *args:a)
    connection=dict(enabled=True,agent_id='agt_test',version='13',runner=runner)
    out=refresh_latest(tmp_path,connection,1,candidates=[dict(url=a['url'],title=a['title'])],national=True,document_urls={a['documents'][1]['document_url']})
    assert len(calls)==2 and out['analyzed']==1 and all(d['status']=='ready' for d in out['notices'][0]['documents'])
    again=refresh_latest(tmp_path,connection,1,candidates=[dict(url=a['url'],title=a['title'])],national=True,document_urls={a['documents'][1]['document_url']})
    assert len(calls)==2 and again['reused']==1
    state=LiveCatalog(tmp_path).state(LiveCatalog(tmp_path).records()[0]);joined=source_bundle(tmp_path,state)
    assert len(joined['documents'])==2 and joined['status']=='complete'


def test_failed_fetch_never_says_unchanged_or_merges_old_and_new(tmp_path,monkeypatch):
    from tests.test_live_discovery import article,result
    from live_catalog import LiveCatalog,analyze_public
    from discovery_flow import refresh_latest
    a=article();r,_=analyze_public(tmp_path,a,0,'agt_test','13',result);state=LiveCatalog(tmp_path).state(r)
    def fail(*a):raise ValueError('source unavailable')
    monkeypatch.setattr('nationwide_notice.prepare_public_article',fail)
    result=refresh_latest(tmp_path,dict(enabled=True,agent_id='agt_test',version='13',runner=fail),1,
        candidates=[dict(url=a['url'],title=a['title'])],national=True)
    b=source_bundle(tmp_path,state)
    assert result['failed']==1 and b['fetch_failed'] and b['stale']
    rows=document_rows(b,'지원 준비 중',{},{});assert document_progress(rows,b)['total']==0


def test_private_preparation_metadata_survives_backup_without_api_key():
    from browser_draft import single_snapshot,restore_single
    n,x=actual('evidence_hackathon21');path=ROOT/x['source_file'];data=path.read_bytes()
    state=dict(notice=n,pages=x['pages'],pdf=data,source_hash=fingerprint(data),source_filename=path.name,last_mode='실제 AI 분석',
        prep_document_states={'local':{'done':True,'signature':'abc'}},api_key='MUST_NOT_SAVE')
    payload=single_snapshot(state);assert 'MUST_NOT_SAVE' not in json.dumps(payload)
    assert restore_single(payload)['prep_document_states']==state['prep_document_states']


def test_refresh_preserves_unchanged_answers_and_archives_previous_source():
    n,x=actual('evidence_hackathon21');data=(ROOT/x['source_file']).read_bytes()
    state=dict(notice=n,pages=x['pages'],pdf=data,source_hash=fingerprint(data),source_filename='old.hwp',last_mode='실제 AI 분석',
        draft_answers={'review_stage':'지원 준비 중'},prep_document_states={'a':{'done':True,'signature':'x'}},answer_other_facts='기록')
    old=state['source_hash'];new={k:deepcopy(v) for k,v in state.items() if k not in ('draft_answers','prep_document_states','answer_other_facts')}
    new.update(pdf=data+b'\n',source_hash=fingerprint(data+b'\n'))
    adopt_public_update(state,new)
    assert old in state['workspaces'] and state['prep_document_states']['a']['done']
    assert state['screen']==3 and state['source_hash']!=old


def test_browser_backup_preserves_checked_actual_document(monkeypatch):
    from tests.test_situation import load
    from streamlit.testing.v1 import AppTest
    from browser_draft import snapshot,restore
    monkeypatch.setattr('browser_draft.bootstrap',lambda:None)
    monkeypatch.setattr('browser_draft.save_browser',lambda:None)
    monkeypatch.setattr('team_access.team_gate',lambda *a,**kw:(None,None))
    at=load(AppTest.from_file(str(ROOT/'app.py')).run(),'evidence_hackathon21')
    at.button(key='nav_4').click().run()
    cb=next(c for c in at.checkbox if c.label.startswith('[붙암1]'));key=cb.key
    cb.check().run()
    assert at.session_state.preparation['progress']['done']==1
    restored=restore(snapshot(at.session_state._state.filtered_state))
    fresh=AppTest.from_file(str(ROOT/'app.py')).run()
    for restored_key,value in restored.items():fresh.session_state[restored_key]=value
    fresh.run()
    assert not fresh.exception and fresh.checkbox(key=key).value
    assert fresh.session_state.preparation['progress']['done']==1


def test_ai_review_does_not_mix_other_document_evidence():
    from preparation_model import selected_review_answers
    n,x=actual('evidence_hackathon21');rows=document_rows(bundle(n,x['pages']),'지원 검토 중',{}, {})
    supplemental={**rows[0],'id':'other','source_selected':False,'text':'OTHER_DOCUMENT_ONLY'}
    a={'document_checklist':rows+[supplemental],'other_facts':'OTHER_DOCUMENT_ONLY'}
    result=selected_review_answers(a,n,x['pages'],'사용자 입력')
    assert 'OTHER_DOCUMENT_ONLY' not in json.dumps(result,ensure_ascii=False)


def test_invented_requirement_is_not_displayed_as_verified():
    n,x=actual('evidence_hackathon21')
    n['_structured_notice']['제출서류'][0]['제출설명']='발급 7일 이내 PDF 필수'
    r=document_rows(bundle(n,x['pages']),'지원 검토 중',{}, {})[0]
    assert not r['requirements'] and not r['requirement_verified']
    assert '7일' not in r['text']


def test_public_revision_archives_only_changed_source_and_safe_reanalysis_keeps_preparation(tmp_path):
    from tests.test_live_discovery import article,result
    from live_catalog import LiveCatalog,analyze_public
    from workspaces import retain_same_document_inputs
    a=article();store=LiveCatalog(tmp_path)
    first,_=analyze_public(tmp_path,a,0,'agt_test','13',result)
    again,_=analyze_public(tmp_path,a,0,'agt_test','13',result)
    assert again['source_changes']['status']=='baseline'
    # Synthetic file revision, not a claim that this real public notice changed.
    a['documents'][0]['data']+=b'\n'
    changed,_=analyze_public(tmp_path,a,0,'agt_test','13',result)
    assert changed['source_changes']['status']=='source_changed'
    with store.connect() as db:
        revisions=db.execute('SELECT previous FROM revisions').fetchall()
    assert len(revisions)==1 and json.loads(revisions[0][0])['record']['sha256']==first['sha256']
    state={'source_hash':'same','prep_document_states':{'doc':{'done':True,'signature':'old'}}}
    assert retain_same_document_inputs(state,'same')['prep_document_states']==state['prep_document_states']
    assert not retain_same_document_inputs(state,'other')
