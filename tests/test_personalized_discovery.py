import datetime as dt
import json
from pathlib import Path
from copy import deepcopy
import pytest
from catalog_ranking import priority,personalized_catalog
from discovery_flow import refresh_latest
from live_catalog import LiveCatalog,analyze_public
from catalog import load_catalog
from test_live_discovery import article,result,URL

ROOT=Path(__file__).parents[1]
TODAY=dt.date(2026,10,14)
RECORD={'title':'교육 장학금','deadline':'2026-10-30','tags':[]}
def row(status,category='eligibility',verified=True):return dict(status=status,category=category,verified=verified)
def rank(rows,**kw):return priority(kw.get('record',RECORD),{'rows':rows},kw.get('profile',{}),TODAY)

def test_unknowns_never_change_priority_or_erase_conflict():
    match=[row('일치')];conflict=[row('불일치')]
    assert rank(match)['key']==rank(match+[row('확인 필요')]*20)['key']
    assert rank(conflict)['label']==rank(conflict+[row('확인 필요')]*20)['label']=='자격 불일치 확인'
    assert rank(match)['key']<rank([])['key']<rank(conflict)['key']

def test_preference_document_and_unverified_conflicts_never_reject():
    for r in (row('불일치','preference'),row('불일치','documents'),row('불일치',verified=False)):
        assert rank([r])['label']=='확인 필요'
    assert rank([row('일치','preference')])['label']=='확인 필요'

def test_expired_goes_last_and_interest_is_not_eligibility():
    p={'interests':{'state':'known','value':'교육, 개발'}}
    assert rank([],profile=p)['label']=='확인 필요'
    assert rank([],profile=p)['key']<rank([])['key']
    assert rank([row('일치')],record={**RECORD,'deadline':'2026-10-13'})['key']>rank([row('불일치')])['key']

def connection(runner=result):return dict(enabled=True,agent_id='agt_test',version='13',runner=runner)

def test_batch_analyzes_all_documents_continues_failure_reuses_completed(monkeypatch,tmp_path):
    a=article();a['documents'].append({**a['documents'][0],'name':'첨부.pdf','document_url':URL+'&attachNo=1','filename':'attachment.pdf'})
    b=deepcopy(a);b.update(url=URL.replace('123','124'),title='가져오기 실패')
    c=deepcopy(a);c.update(url=URL.replace('123','125'),title='다음 공고')
    monkeypatch.setattr('discovery_flow.discover',lambda:[a,b,c])
    def prepare(candidate,*args):
        if candidate is b:raise ValueError('fetch failed')
        return candidate
    monkeypatch.setattr('discovery_flow.prepare_article',prepare)
    calls=[]
    def runner(data,name,*args):
        calls.append(name)
        if name=='attachment.pdf':raise ValueError('첨부 분석 실패')
        return result()
    summary=refresh_latest(tmp_path,connection(runner),3)
    assert summary['analyzed']==2 and summary['failed']==3
    assert all(not n['complete'] for n in summary['notices'])
    assert len(LiveCatalog(tmp_path).records())==2
    again=refresh_latest(tmp_path,connection(runner),3)
    assert again['reused']==2 and again['analyzed']==0
    assert calls.count('article.pdf')==2

def test_disabled_connection_never_fetches(monkeypatch,tmp_path):
    monkeypatch.setattr('discovery_flow.discover',lambda:pytest.fail('No network'))
    with pytest.raises(ValueError):refresh_latest(tmp_path,{'enabled':False})

def test_partial_or_changed_source_never_recommends_stale_analysis(monkeypatch,tmp_path):
    a=article();monkeypatch.setattr('discovery_flow.discover',lambda:[a])
    monkeypatch.setattr('discovery_flow.prepare_article',lambda *args:a)
    refresh_latest(tmp_path,connection(),1)
    assert personalized_catalog(tmp_path,load_catalog(tmp_path),{})[0]['documents']
    a['documents'][0]['data']+=b'\n'
    def fail(*args):raise ValueError('failed')
    refresh_latest(tmp_path,connection(fail),1)
    group=personalized_catalog(tmp_path,load_catalog(tmp_path),{})[0]
    assert not group['documents'] and group['priority']['label']=='분석 확인 필요'
    assert LiveCatalog(tmp_path).records() # historical cache retained

def test_documents_grouped_by_notice_and_date_disagreement_is_unknown(tmp_path):
    a=article();r,_=analyze_public(tmp_path,a,0,'agt_test','13',result)
    a['documents'][0]['document_url']+='&attachNo=1'
    s,_=analyze_public(tmp_path,a,0,'agt_test','13',result)
    s['deadline']='2026-11-30'
    with LiveCatalog(tmp_path).connect() as db:
        db.execute('UPDATE records SET record=? WHERE id=?',(json.dumps(s),s['id']))
    groups=personalized_catalog(tmp_path,load_catalog(tmp_path),{})
    assert len(groups)==1 and len(groups[0]['documents'])==2
    assert groups[0]['record']['deadline']=='' and any('마감일이 다릅니다' in c for c in groups[0]['cautions'])

def test_real_public_notices_change_order_by_profile_and_keep_unknowns():
    records=[r for r in load_catalog(ROOT) if r['id'] in ('notice1','notice3')]
    def fact(value):return dict(state='known',value=value)
    four={'college_type':fact('4년제'),'nationality':fact('대한민국')}
    college={'college_type':fact('전문대'),'nationality':fact('대한민국')}
    a=personalized_catalog(ROOT,records,four,TODAY)
    b=personalized_catalog(ROOT,records,college,TODAY)
    c=personalized_catalog(ROOT,records,{},TODAY)
    assert a[0]['record']['id']=='notice1' and b[0]['record']['id']=='notice3'
    mismatch=next(g for g in b if g['record']['id']=='notice1')
    assert mismatch['priority']['label']=='자격 불일치 확인' and mismatch['result']['unknowns']
    assert all(g['priority']['label']=='확인 필요' for g in c)
    assert all(r['status']=='확인 필요' for g in c for r in g['result']['rows'])

def test_unmapped_extracted_conditions_remain_visible(tmp_path):
    from catalog import card_review
    raw=result();condition={'분류':'지원자격','조건':'본인 확인 면담에 참석해야 함','적용단계':'지원단계','대조항목':'',
                           '근거원문':'면담 참석 필수','근거페이지':'1','비교방법':'검토'}
    raw['지원조건'].append(condition)
    r,_=analyze_public(tmp_path,article(),0,'agt_test','13',lambda *args:raw)
    review=card_review(tmp_path,r,{})
    added=next(row for row in review['rows'] if row.get('rule')==condition['조건'])
    assert added['status']=='확인 필요' and added['answer'] is None

def test_save_and_search_ui_one_action_keeps_private_data_out_of_catalog(monkeypatch,tmp_path):
    from streamlit.testing.v1 import AppTest
    import live_catalog
    monkeypatch.setattr('browser_draft.bootstrap',lambda:None)
    monkeypatch.setattr('browser_draft.save_browser',lambda:None)
    monkeypatch.setattr('team_access.team_gate',lambda *args,**kwargs:(None,None))
    original=LiveCatalog
    monkeypatch.setattr(live_catalog,'LiveCatalog',lambda root:original(tmp_path))
    monkeypatch.setattr('discovery_flow.LiveCatalog',lambda root:original(tmp_path))
    monkeypatch.setattr('catalog_ranking.LiveCatalog',lambda root:original(tmp_path))
    monkeypatch.setattr('discovery_flow.discover',lambda:[{'url':URL,'title':'실제 스키마 테스트'}])
    monkeypatch.setattr('discovery_flow.prepare_article',lambda *args:article())
    calls=[]
    def run(*args,**kwargs):calls.append(1);return result()
    monkeypatch.setattr('upstage_client.run_agent',run)
    at=AppTest.from_file(str(ROOT/'app.py')).run()
    next(t for t in at.text_input if t.label=='Upstage API 키').input('test-only').run()
    at.button(key='entry_profile').click().run()
    at.text_input(key='pf_school').input('테스트비공개대학')
    next(b for b in at.button if b.label=='저장하고 최신 공고 찾기').click().run(timeout=30)
    assert not at.exception and at.session_state.route=='catalog' and calls==[1]
    assert at.session_state.common_profile['school']['value']=='테스트비공개대학'
    with original(tmp_path).connect() as db:
        shared=str(db.execute('SELECT record,analysis FROM records').fetchall())+str(db.execute('SELECT manifest FROM scans').fetchall())
    assert '테스트비공개대학' not in shared and 'test-only' not in shared
    at.button(key='discovery_latest').click().run(timeout=30)
    assert not at.exception and calls==[1] and at.session_state['_discovery_batch_summary']['reused']==1
    at.button(key='catalog_edit_profile').click().run()
    at.text_input(key='pf_school').input('다른비공개대학')
    next(b for b in at.button if b.label=='내 정보 저장').click().run()
    at.button(key='entry_catalog').click().run()
    assert not at.exception and calls==[1]
