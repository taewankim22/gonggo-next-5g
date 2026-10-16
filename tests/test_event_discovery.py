import pytest
from national_search import (DiscoveryStore,SearchConfig,REGIONS,search_plan,candidate,
                            discover_nationwide,discovery_kind)
from nationwide_notice import parse_public_article,file_name,attachment_links
from bs4 import BeautifulSoup
from copy import deepcopy
from public_network import Response


def test_selected_event_topics_cover_all_regions_without_private_queries(tmp_path):
    calls=[]
    def search(query):
        calls.append(query)
        return {'items':[]}
    _,stats=discover_nationwide(tmp_path,SearchConfig('not-a-real-key'),sources=(),
                               searcher=search,kinds=['해커톤','대회'])
    assert len(calls)==stats['queries_completed']==stats['queries_total']==36
    assert all(any(region in query for query in calls) for region in REGIONS)
    assert all('해커톤' in q or '경진대회' in q for q in calls)
    assert 'site:ac.kr' in calls[0] and 'site:or.kr' in calls[1]
    with pytest.raises(ValueError):
        discover_nationwide(tmp_path,SearchConfig('test'),sources=(),
                           searcher=lambda _:pytest.fail('No request for empty selection'),kinds=[])


def test_queue_balances_topics_and_rechecks_old_cached_secondary_pages(tmp_path):
    store=DiscoveryStore(tmp_path)
    rows=[candidate(f'https://school.ac.kr/{i}','장학생 모집 '+str(i),'기관') for i in range(20)]
    rows.extend([candidate('https://school.ac.kr/h','AI 해커톤 모집','기관'),
                 candidate('https://school.ac.kr/c','AI 경진대회 모집','기관'),
                 candidate('https://school.ac.kr/a','서포터즈 모집','기관'),
                 candidate('https://school.ac.kr/t','공모전 모집','기관')])
    # Stored before filtering rules were introduced.
    rows.extend([dict(url='https://news.nate.com/view/123',title='해커톤 참가자 모집',source_name='웹',needs_original=False),
                 dict(url='https://school.ac.kr/list',title='해커톤 공고 모음',source_name='기관'),
                 dict(url='https://school.ac.kr/results',title='경진대회 수상자 발표',source_name='기관')])
    store.remember(rows)
    queue=store.queue()
    assert {discovery_kind(c) for c in queue[:5]}=={'장학금','해커톤','대회','대외활동','공모전'}
    assert len(queue)==24
    assert [discovery_kind(c) for c in store.queue(kinds=['해커톤','대회'])]==['해커톤','대회']
    ordered=store.queue([rows[21]['url'],rows[20]['url']],kinds=['해커톤','대회'])
    assert [discovery_kind(c) for c in ordered]==['해커톤','대회']


def test_observed_ssu_recruitment_layout_excludes_adjacent_notices():
    body='<p>트랙2 신청기간 연장 ~10.14.(수) 오후2시까지. 트랙1 모집마감.</p>'*3
    html=f'''<div id="contents"><div class="col-lg-9"><div class="bg-white">
      <h1>2026 창업 경진대회 모집</h1><div>조회수</div><hr><div>{body}
      <a href="/download.php?id=1">모집공고.pdf</a></div></div></div>
      <div class="col-lg-3">다른 공고 장학금 1억원 12월31일</div></div>'''
    response=Response('https://scatch.ssu.ac.kr/notice',html.encode(),'text/html; charset=utf-8',200)
    title,parsed,_=parse_public_article(response,'fallback')
    assert title=='2026 창업 경진대회 모집'
    assert '트랙1 모집마감' in parsed.get_text() and '1억원' not in parsed.get_text()
    other=Response('https://unrecognized.org',html.encode(),'text/html; charset=utf-8',200)
    with pytest.raises(ValueError,match='본문 구조'):parse_public_article(other,'fallback')


def test_public_pdf_header_recovers_korean_filename_without_changing_document():
    expected='공고문_2026뉴스빅데이터해커톤.pdf'
    broken=expected.encode('utf-8').decode('latin-1').encode('utf-8').decode('latin-1')
    for header in (broken,expected):
        r=Response('https://culture.go.kr/fileDown.do',b'%PDF-original','application/pdf',200,
                   {'content-disposition':f'attachment; filename="{header}"'})
        assert file_name(r)==expected and r.body==b'%PDF-original'


def test_footer_certificate_is_not_a_recruitment_attachment():
    html='''<div class="board-view-content"><a href="/notice.pdf">공고문.pdf</a></div>
    <ul class="file-list"><li><a href="/apply.hwp">신청서.hwp</a></li></ul>
    <div id="footer-wrap"><div id="footer"><div class="marks-list">
      <a href="/ko/_Data/silla_wa_2022.pdf" title="새창열기">새창열기</a>
    </div></div></div><nav><a href="/site-guide.pdf">이용 안내.pdf</a></nav>'''
    links=attachment_links(BeautifulSoup(html,'html.parser'),'https://www.silla.ac.kr/ko/')
    assert links==[('https://www.silla.ac.kr/notice.pdf','공고문.pdf'),
                   ('https://www.silla.ac.kr/apply.hwp','신청서.hwp')]


def test_empty_extract_title_uses_only_verified_main_page_title(tmp_path):
    from live_catalog import analyze_public,LiveCatalog
    from test_live_discovery import article
    from test_latest_studio import compact
    from workflow_adapter import ground_notice
    a=article();a['source_title_verified']=True
    raw=compact();raw['공고명']='';raw['_extract_conflicts']=['공고명 값이 문서 구간마다 다릅니다.']
    record,_=analyze_public(tmp_path,a,0,'agt_test','20',lambda *args:deepcopy(raw))
    state=LiveCatalog(tmp_path).state(record)
    assert state['notice']['notice_title']==a['title']
    assert not state['notice']['_studio_compact']['공고명']
    assert state['notice']['source_conflicts']
    assert ground_notice(state['notice'],state['pages'])['notice_title']==a['title']
    for index,modified in enumerate([{'source_title_verified':False},{'url':a['url']+'&different=1'}]):
        b={**a,**modified};b['documents']=deepcopy(a['documents'])
        b['documents'][0]['data']+=str(index).encode()  # Isolated analysis, no cache reuse.
        with pytest.raises(ValueError,match='공고 제목'):
            analyze_public(tmp_path,b,0,'agt_test','20',lambda *args:deepcopy(raw))


def test_legacy_press_analysis_stays_stored_but_is_not_a_recruitment_card(tmp_path):
    from live_catalog import analyze_public,LiveCatalog
    from test_live_discovery import article,result
    from catalog_ranking import personalized_catalog
    a=article();a['url']='https://biz.chosun.com/it-science/notice'
    a['title']='SK하이닉스 AI 해커톤 개최 - 조선비즈'
    analyze_public(tmp_path,a,0,'agt_test','13',result)
    stored=LiveCatalog(tmp_path).records()
    assert stored and personalized_catalog(tmp_path,stored,{})==[]
    ds=DiscoveryStore(tmp_path)
    ds.remember([dict(url=a['url'],title=a['title'],source_name='웹 검색',needs_original=False)])
    assert ds.items()[0]['needs_original'] and not ds.queue()
    assert LiveCatalog(tmp_path).records()==stored


def test_ssu_short_extension_blocks_previous_attachment_deadline():
    from deadline_calendar import document_deadlines,consolidate
    r={'id':'body','source_url':'https://scatch.ssu.ac.kr/notice'}
    body=document_deadlines({},['2026년 창업아이디어 경진대회\n□ 신청기간 : ~ 10. 14.(수) 오후 2시까지 모집연장\n트랙2 모집연장, 트랙1 모집마감'],r)
    attached=document_deadlines({},['신청기간 : 2026. 9. 1. ~ 2026. 10. 12. 13:00까지'],{**r,'id':'pdf'})
    assert body['ambiguous'] and not body['events']
    assert attached['events'][0]['date']=='2026-10-12'
    combined=consolidate([body,attached])
    assert combined['category']=='마감일 확인 필요' and not combined['events']
