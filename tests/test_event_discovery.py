import pytest
from national_search import (DiscoveryStore,SearchConfig,REGIONS,search_plan,candidate,
                            discover_nationwide,discovery_kind)
from nationwide_notice import parse_public_article
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
