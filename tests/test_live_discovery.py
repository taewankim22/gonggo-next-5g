import json
from pathlib import Path
from copy import deepcopy
import pytest

from core import fingerprint, read_pdf
from live_catalog import LiveCatalog, analyze_public
from web_notice import parse_article, source_pdf, article_url

ROOT=Path(__file__).parents[1]
URL='https://www.sejong.ac.kr/kor/intro/notice7.do?articleNo=123&mode=view'


def article():
    return dict(title='테스트 공고',url=URL,checked_at='2026-10-14T00:00:00Z',attachments=[],warnings=[],body_text='공고 본문',
                documents=[dict(name='게시글 본문과 포스터',filename='article.pdf',document_url=URL,
                                data=(ROOT/'data/hyundai_jump_13.pdf').read_bytes(),basis='재구성 PDF')])


def result(*args):
    return json.loads((ROOT/'tests/fixtures/routed_pdf13.json').read_text(encoding='utf-8'))['raw']


def test_real_schema_publishes_across_instances_and_deduplicates(tmp_path):
    a=article();calls=[]
    def runner(*args):calls.append(1);return result()
    r,reused=analyze_public(tmp_path,a,0,'agt_test','13',runner)
    assert not reused and len(LiveCatalog(tmp_path).records())==1
    assert LiveCatalog(tmp_path).state(r)['source_hash']==fingerprint(a['documents'][0]['data'])
    same,reused=analyze_public(tmp_path,a,0,'agt_test','13',runner)
    assert reused and calls==[1] and same['id']==r['id']
    analyze_public(tmp_path,a,0,'agt_test','14',runner)
    assert len(calls)==2 and len(LiveCatalog(tmp_path).records())==1
    a['documents'][0]['data']+=b'\n'
    analyze_public(tmp_path,a,0,'agt_test','14',runner)
    assert len(calls)==3


def test_failure_never_publishes_or_removes_existing_notice(tmp_path):
    r,_=analyze_public(tmp_path,article(),0,'agt_test','13',result)
    a=article();a['url']=URL.replace('123','124')
    with pytest.raises(ValueError):analyze_public(tmp_path,a,0,'agt_test','13',lambda *args:{'bad':'json'})
    assert LiveCatalog(tmp_path).records()==[r]


def test_cross_user_lock_and_ambiguous_submit_never_resubmits(tmp_path):
    cache=LiveCatalog(tmp_path)
    cache.claim('same',now=1000)
    with pytest.raises(ValueError,match='분석 중'):LiveCatalog(tmp_path).claim('same',now=1001)
    cache.save_trace('same',{'submission_started':True});cache.release('same')
    with pytest.raises(ValueError,match='불명확'):cache.claim('same')


def test_failed_poll_resumes_same_job_and_publishes(tmp_path):
    calls=[]
    def runner(data,name,info,progress,trace):
        calls.append(bool(trace.get('job_id')))
        if not trace.get('job_id'):
            trace.update(submission_started=True,job_id='job_existing',file_id='file_existing')
            raise ValueError('temporary network failure')
        return result()
    with pytest.raises(ValueError):analyze_public(tmp_path,article(),0,'agt_test','13',runner)
    assert not LiveCatalog(tmp_path).records()
    analyze_public(tmp_path,article(),0,'agt_test','13',runner)
    assert calls==[False,True]


def test_source_scope_and_personal_data_not_in_shared_records(tmp_path):
    a=article();a['documents'].append({**a['documents'][0],'name':'첨부.hwp'})
    a['private_profile']={'api_key':'SECRET','school':'개인대학'}
    r,_=analyze_public(tmp_path,a,0,'agt_test','13',result)
    assert '별도 확인' in r['coverage_note']
    with LiveCatalog(tmp_path).connect() as db:
        text=str(db.execute('SELECT record,analysis FROM records').fetchall())
    assert 'SECRET' not in text and '개인대학' not in text


def test_article_isolates_body_keeps_table_footnote_and_stable_pdf():
    raw='<script>BAD</script><nav>메뉴</nav><p class="b-title">지원 공고</p><div class="b-content-box"><div class="fr-view"><p>2026년 10월 30일까지 신청</p><table><tr><td rowspan="2">지원대상</td><td>재학생</td></tr><tr><td>휴학생 제외</td></tr></table><p>※ 학점 2.0 이상. 예외 조건 확인</p></div></div>'
    title,body=parse_article(raw)
    data=source_pdf(title,body,URL,{})
    text='\n'.join(read_pdf(data))
    assert all(word in text for word in ('재학생','휴학생 제외','예외 조건','10월 30일'))
    assert '메뉴' not in text and 'BAD' not in text
    assert data==source_pdf(title,body,URL,{})
    with pytest.raises(ValueError):parse_article('<html>로그인 페이지</html>')


def test_source_allowlist_and_missing_image_fail_closed():
    assert article_url(URL+'&title=abc')==URL
    for url in ('http://127.0.0.1/x','https://evil.example/?mode=view&articleNo=123',URL.replace('123','abc')):
        with pytest.raises(ValueError):article_url(url)
    title,body=parse_article('<p class="b-title">포스터</p><div class="b-content-box"><div class="fr-view"><img src="/poster.png"></div></div>')
    with pytest.raises(ValueError,match='이미지가 누락'):source_pdf(title,body,URL,{})


def test_total_terms_never_become_remaining_term_comparison():
    from workflow_adapter import adapt_notice,ground_notice
    from profiles import atomic_conditions
    raw=result()
    raw['지원조건']=[{'분류':'지원자격','조건':'정규 수업연한 8학기 이내','적용대상':'전체','적용단계':'지원단계',
                    '대조항목':'잔여학기','비교방법':'이하','기준값':'8','근거원문':'standard number(8 semester for a four-year program) of semesters',
                    '근거페이지':'1','예외':'','기준시점':'2026-2학기','만점':''}]
    n=ground_notice(adapt_notice(raw),[raw['지원조건'][0]['근거원문']])
    assert not any(c['field']=='remaining_terms' for c in atomic_conditions(n))
    assert n['_structured_notice']['지원조건'][0]['조건']=='정규 수업연한 8학기 이내'


def test_catalog_integration_preserves_static_and_live(tmp_path):
    from catalog import load_catalog,available_record,card_review
    r,_=analyze_public(tmp_path,article(),0,'agt_test','13',result)
    assert load_catalog(tmp_path)==[r]
    assert available_record(tmp_path,r)
    assert card_review(tmp_path,r,{})['rows']
    corrupt={**r,'sha256':'wrong'}
    assert available_record(tmp_path,corrupt) is None


def test_ui_fetch_prepare_analyze_filter_failure_without_background_calls(monkeypatch,tmp_path):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    import catalog,live_catalog
    monkeypatch.setattr('browser_draft.bootstrap',lambda:None)
    monkeypatch.setattr('browser_draft.save_browser',lambda:None)
    monkeypatch.setattr('team_access.team_gate',lambda *args,**kwargs:(None,None))
    # Keep this integration test's shared storage separate from the developer's cache.
    original=LiveCatalog
    monkeypatch.setattr(live_catalog,'LiveCatalog',lambda root:original(tmp_path))
    monkeypatch.setattr('discovery_ui.discover',lambda:[{'title':'테스트 공고','url':URL}])
    monkeypatch.setattr('discovery_ui.prepare_article',lambda *args:article())
    calls=[]
    def runner(*args,**kwargs):calls.append(1);return result()
    monkeypatch.setattr('upstage_client.run_agent',runner)
    at=AppTest.from_file(str(ROOT/'app.py')).run()
    at.button(key='entry_catalog').click().run()
    assert not at.exception and not calls
    next(t for t in at.text_input if t.label=='Upstage API 키').input('test-only').run()
    at.button(key='discovery_fetch').click().run()
    at.button(key='discovery_prepare').click().run()
    assert not calls
    at.button(key='discovery_analyze').click().run()
    assert not at.exception and calls==[1] and at.success
    r=original(tmp_path).records()[0]
    assert at.button(key='catalog_'+r['id'])
    at.button(key='discovery_analyze').click().run()
    assert calls==[1]
    at.text_input(key='catalog_search').input('없는검색어').run()
    assert any('필터에 맞는' in x.value for x in at.info)
    at.text_input(key='catalog_search').input('').run()
    at.button(key='catalog_'+r['id']).click().run()
    assert not at.exception and at.session_state.screen==2
    assert '분석 범위' in at.session_state.catalog_source['coverage_note']
