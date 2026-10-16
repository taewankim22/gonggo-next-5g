from pathlib import Path
from unittest.mock import patch
import pytest
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).parents[1]

@pytest.fixture
def app(monkeypatch,tmp_path):
    from live_catalog import LiveCatalog
    from national_search import DiscoveryStore
    monkeypatch.setattr('browser_draft.bootstrap',lambda:None)
    monkeypatch.setattr('browser_draft.save_browser',lambda:None)
    monkeypatch.setattr('team_access.team_gate',lambda *a,**kw:(None,None))
    for module in ['live_catalog','catalog_ranking','discovery_ui']:
        monkeypatch.setattr(module+'.LiveCatalog',lambda root:LiveCatalog(tmp_path))
    monkeypatch.setattr('discovery_ui.DiscoveryStore',lambda root:DiscoveryStore(tmp_path))
    at=AppTest.from_file(str(ROOT/'app.py')).run(timeout=20)
    at.button(key='entry_catalog').click().run(timeout=20)
    assert not at.exception
    return at


def test_list_filter_review_return_and_no_calls(app):
    at=app
    with patch('upstage_client.run_agent',side_effect=AssertionError('No paid calls')), \
         patch('national_search.tavily_search',side_effect=AssertionError('No searches')), \
         patch('national_search.board_candidates',side_effect=AssertionError('No network')):
        # An existing session that last used the calendar must still show cards.
        at.session_state.catalog_view='캘린더 보기'
        at.text_input(key='catalog_search').set_value('통영').run(timeout=20)
        assert not any(r.key=='catalog_view' for r in at.radio)
        assert not any(s.key in ('calendar_month','calendar_day') for s in at.selectbox)
        assert any('18:00' in m.value for m in at.markdown)
        next(b for b in at.button if b.label=='이 공고 검토하기').click().run(timeout=20)
        assert at.session_state.route=='review'
        at.button(key='nav_3').click().run(timeout=20)
        at.session_state.answer_other_facts='테스트 답변 유지'
        at.button(key='entry_catalog').click().run(timeout=20)
        assert at.text_input(key='catalog_search').value=='통영'
        assert at.session_state.answer_other_facts=='테스트 답변 유지'
        assert any(b.label=='이 공고 검토하기' for b in at.button)
        assert not at.exception


def test_category_filters_stay_available_with_zero_results_and_no_api(app,monkeypatch):
    at=app
    with patch('upstage_client.run_agent',side_effect=AssertionError('No paid calls')), \
         patch('national_search.tavily_search',side_effect=AssertionError('No searches')):
        at.selectbox(key='catalog_kind').set_value('해커톤').run(timeout=20)
        assert any('아직 분석을 마친 해커톤' in i.value for i in at.info)
        assert at.selectbox(key='catalog_kind').value=='해커톤'
        at.selectbox(key='catalog_kind').set_value('공모전').run(timeout=20)
        assert at.selectbox(key='catalog_kind').value=='공모전'
        next(b for b in at.button if b.label=='이 공고 검토하기').click().run(timeout=20)
        at.button(key='entry_catalog').click().run(timeout=20)
        assert at.selectbox(key='catalog_kind').value=='공모전'
        monkeypatch.setattr('catalog.load_catalog',lambda root:[])
        at.selectbox(key='catalog_kind').set_value('대회').run(timeout=20)
        assert any('아직 분석을 마친 대회' in i.value for i in at.info)
        assert not at.exception


def test_multiple_events_same_day_and_unknowns_keep_filtering(app,monkeypatch):
    from copy import deepcopy
    from catalog import load_catalog
    from catalog_ranking import personalized_catalog
    groups=personalized_catalog(ROOT,[r for r in load_catalog(ROOT) if r['id']=='notice3'],{})
    base=groups[0];many=[]
    for i in range(5):
        g=deepcopy(base);g['record']['id']='fake'+str(i);g['record']['title']='분리된 화면 테스트 '+str(i)
        many.append(g)
    unknown=deepcopy(base);unknown['record'].update(id='unknown',title='일정 미기재 테스트')
    unknown['record']['_calendar']={'events':[],'category':'마감일 확인 필요','evidence':[]}
    many.append(unknown)
    monkeypatch.setattr('catalog_ranking.personalized_catalog',lambda *a:many)
    at=app
    at.run(timeout=20)
    assert len([b for b in at.button if b.label=='이 공고 검토하기'])==6
    at.selectbox(key='catalog_status').set_value('마감일 확인 필요').run(timeout=20)
    assert len([b for b in at.button if b.label=='이 공고 검토하기'])==1
    assert any(h.value=='일정 미기재 테스트' for h in at.subheader)
    assert not at.exception
