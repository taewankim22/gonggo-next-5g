import json
from copy import deepcopy
from pathlib import Path
import pytest
from national_search import (REGIONS,SearchConfig,SearchError,DiscoveryStore,discover_nationwide,
    candidate,search_plan,board_candidates,tavily_search)
from nationwide_notice import prepare_public_article,parse_public_article
from public_network import Response,canonical_url
from live_catalog import LiveCatalog,analyze_public
from catalog_ranking import personalized_catalog
from catalog import load_catalog
from discovery_flow import refresh_latest
from test_live_discovery import article,result,URL


def test_nationwide_plan_covers_every_region_and_category():
    plans=search_plan(2026)
    assert len(plans)==90
    assert {p['region'] for p in plans}==set(REGIONS)|{'전국'}
    assert all(len([p for p in plans if p['region']==r])==5 for r in REGIONS)
    assert all('2026' not in p['query'] for p in plans if p['region']=='전국' and 'site:' not in p['query'])


def test_search_partial_failure_keeps_other_regions_and_cache(tmp_path):
    calls=[]
    def search(query):
        calls.append(query)
        if '대구' in query:raise SearchError('테스트 장애')
        return {'items':[{'link':'https://example.org/notice/2026?utm_source=x','title':'<b>2026</b> 장학생 모집'}]}
    config=SearchConfig('PRIVATE_SECRET')
    found,stats=discover_nationwide(tmp_path,config,searcher=search,sources=())
    assert stats['queries_completed']==85 and len(stats['errors'])==5 and len(found)==1
    assert '제주' in DiscoveryStore(tmp_path).items()[0]['regions']
    assert 'PRIVATE' not in str(DiscoveryStore(tmp_path).items())+str(stats)
    again,next_stats=discover_nationwide(tmp_path,config,searcher=search,sources=())
    assert next_stats['query_cache_hits']==85 and len(calls)==95


def test_missing_credentials_never_claim_national_search(tmp_path):
    found,stats=discover_nationwide(tmp_path,None,searcher=lambda q:pytest.fail(),sources=())
    assert stats['queries_completed']==0 and stats['errors'] and not found


def test_bad_credentials_stop_without_repeated_requests(tmp_path):
    calls=[]
    def fail(q):calls.append(q);raise SearchError('인증 오류',True)
    _,s=discover_nationwide(tmp_path,SearchConfig('test-key'),searcher=fail,sources=())
    assert len(calls)==1 and s['queries_completed']==0


def test_search_http_errors_do_not_leak_secret(monkeypatch):
    import urllib.error
    class Broken:
        def open(self,*args,**kwargs):raise urllib.error.HTTPError('url',401,'SECRET_BAD',{},None)
    monkeypatch.setattr('national_search.urllib.request.build_opener',lambda *args:Broken())
    with pytest.raises(SearchError) as error:tavily_search(SearchConfig('SECRET_BAD'),'공모전')
    assert 'SECRET_BAD' not in str(error.value) and error.value.fatal


def test_candidate_identity_and_distinct_rounds(tmp_path):
    store=DiscoveryStore(tmp_path)
    x=candidate('https://example.org/view?idx=1&page=2&utm_source=a','2026 1차 장학','기관')
    y=candidate('https://example.org/view?idx=1&page=3&utm_source=b','2026 1차 장학','기관')
    z=candidate('https://example.org/view?idx=2','2026 2차 장학','기관')
    store.remember([x,y,z])
    assert len(store.items())==2
    assert '%EA' in canonical_url('https://example.org/공고 첨부.pdf')
    assert canonical_url(canonical_url('https://example.org/공고 첨부.pdf'))==canonical_url('https://example.org/공고 첨부.pdf')


def test_aggregators_are_candidates_not_originals(tmp_path):
    c=candidate('https://www.wevity.com/?c=find&s=1&idx=1','공모전 모집','검색')
    store=DiscoveryStore(tmp_path);store.remember([c])
    assert c['needs_original'] and not store.queue()
    with pytest.raises(ValueError,match='모음 사이트'):prepare_public_article(c,tmp_path)


def test_exact_content_reused_across_sources_but_changes_reanalyzed(tmp_path):
    a=article();calls=[]
    def run(*args):calls.append(1);return result()
    first,reused=analyze_public(tmp_path,a,0,'agt_test','13',run)
    b=deepcopy(a);b['url']='https://different.ac.kr/view/1';b['documents'][0]['document_url']=b['url']
    second,reused=analyze_public(tmp_path,b,0,'agt_test','13',run)
    assert reused and calls==[1] and first['source_url']!=second['source_url']
    b['documents'][0]['data']+=b'\n'
    analyze_public(tmp_path,b,0,'agt_test','13',run)
    analyze_public(tmp_path,b,0,'agt_test','14',run)
    assert calls==[1,1,1]


def test_repost_cards_only_merge_complete_identical_notices(monkeypatch,tmp_path):
    a=article();b=deepcopy(a);b['url']='https://different.ac.kr/notice/2026';b['documents'][0]['document_url']=b['url']
    monkeypatch.setattr('nationwide_notice.prepare_public_article',lambda c,*args:c)
    conn=dict(enabled=True,agent_id='agt_test',version='13',runner=result)
    refresh_latest(tmp_path,conn,10,candidates=[a,b],national=True)
    cards=personalized_catalog(tmp_path,load_catalog(tmp_path),{})
    assert len(cards)==1 and len(cards[0]['source_aliases'])==1
    b['title']='2027 다른 회차'
    refresh_latest(tmp_path,conn,1,candidates=[b],national=True)
    assert len(personalized_catalog(tmp_path,load_catalog(tmp_path),{}))==2


def test_original_fetch_failure_does_not_abort_following_notice(monkeypatch,tmp_path):
    a=article();bad={**a,'url':'https://wevity.com/?idx=1'}
    monkeypatch.setattr('nationwide_notice.prepare_public_article',lambda c,*args:c)
    conn=dict(enabled=True,agent_id='agt_test',version='13',runner=result)
    summary=refresh_latest(tmp_path,conn,10,candidates=[bad,a],national=True)
    assert summary['failed']==1 and summary['analyzed']==1


def test_missing_poster_and_attachment_remain_visible(monkeypatch,tmp_path):
    url='https://institution.org/notice/1'
    html='<h1>공모전</h1><article>'+('<p>대학생 신청 공고 조건. </p>'*8)+'<img src="/poster.png"><a href="/notice.hwp">공고.hwp</a></article>'
    def fetch(source,*args,**kwargs):
        if source==url:return Response(url,html.encode(),'text/html; charset=utf-8',200)
        raise ValueError('다운로드 실패')
    monkeypatch.setattr('nationwide_notice.fetch',fetch)
    output=prepare_public_article(candidate(url,'공모전 모집','기관'),tmp_path)
    assert len(output['documents'])==1 and len(output['warnings'])==2
    assert output['attachments'][0]['status']=='failed'


def test_unrecognized_page_never_uses_navigation_as_evidence():
    response=Response('https://example.org',b'<html><nav>login home school</nav></html>','text/html',200)
    with pytest.raises(ValueError,match='본문 구조'):parse_public_article(response,'공모전')


def test_profile_backup_never_contains_search_credentials():
    from browser_draft import snapshot
    value=snapshot({'common_profile':{'school':{'state':'known','value':'테스트대학'}},'_tavily_api_key':'SECRET_VALUE'})
    assert 'SECRET' not in json.dumps(value)


def test_search_request_uses_fixed_basic_budget_and_only_returns_source_metadata(monkeypatch):
    class Reply:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return json.dumps({'results':[{'url':'https://example.org/n','title':'장학 모집','content':'검색요약은 근거가 아님'}],'usage':{'credits':1}}).encode()
    class Opener:
        def open(self,request,**kwargs):
            payload=json.loads(request.data)
            assert request.full_url=='https://api.tavily.com/search'
            assert payload['search_depth']=='basic' and payload['max_results']==20
            assert payload['time_range']=='month' and 'wevity.com' in payload['exclude_domains']
            assert not payload['auto_parameters'] and not payload['include_answer']
            assert 'school' not in payload
            return Reply()
    monkeypatch.setattr('national_search.urllib.request.build_opener',lambda *args:Opener())
    data=tavily_search(SearchConfig('test-key'),'전국 장학금')
    assert data=={'items':[{'link':'https://example.org/n','title':'장학 모집'}],'credits':1}


def test_result_notices_do_not_consume_automatic_recruitment_analysis(tmp_path):
    s=DiscoveryStore(tmp_path)
    result=candidate('https://example.org/n/1','2026 장학생 면접 대상자 발표일 안내','기관')
    recruitment=candidate('https://example.org/n/2','2027 장학생 선발 안내','기관')
    s.remember([result,recruitment])
    assert len(s.items())==2 and s.queue()==[recruitment]


def test_actual_asan_program_year_is_not_an_application_year():
    from workflow_adapter import ground_notice,adapt_notice
    x=json.loads((Path(__file__).parent/'fixtures/national_asan13.json').read_text(encoding='utf-8'))
    assert x['raw']['접수마감']=='2027-10-26'
    n=ground_notice(adapt_notice(x['raw']),x['pages'])
    assert n['application_deadline']=='' and '원문 확인 필요' in n['deadline_note']
    assert '10월 26일' in n['deadline_note']
    assert ground_notice(n,x['pages'])==n


@pytest.mark.parametrize('quote,date,expected',[
    ('접수 2026년 10월 26일 마감','2026-10-26',True),
    ('접수 2026.10.6.(화) ~ 10.26.(월)','2026-10-26',True),
    ('접수 2026년 10월 6~26일','2026-10-26',True),
    ('2027년 장학생 모집, 접수 10월 6일~10월 26일','2027-10-26',False),
    ('접수 2026년 10월 26일','2027-10-26',False),
])
def test_only_explicit_application_dates_can_be_ranked(quote,date,expected):
    from deadline_guard import explicit_date
    assert explicit_date(date,quote)==expected
