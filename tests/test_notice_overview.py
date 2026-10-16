import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

from core import validate_payload
from schema_builder import notice_schema
from workflow_adapter import ground_notice
from notice_overview import overview_model
from test_latest_studio import compact
from test_calendar_ui import app

NOW = dt.datetime(2026, 8, 28, 17, 30, tzinfo=dt.timezone(dt.timedelta(hours=9)))


def test_verified_time_is_not_warned_and_unscoped_compact_prize_stays_unknown():
    pages = ['대한민국 국민 누구나\n접수기간 2026. 8. 26.(수) ~ 2026. 8. 28.(금) 09:00 ~ 18:00']
    notice = ground_notice(validate_payload(compact(), notice_schema()), pages)
    before = json.dumps(notice, ensure_ascii=False)
    model = overview_model(notice, pages, now=NOW)
    assert model['deadline'] == '2026.08.28 · 18:00'
    assert '마감 시간' not in model['pending']
    assert '세부 지원 자격' not in model['pending']
    assert model['benefits'] == '—'
    assert {'상금·혜택', '제출서류', '우대조건'} <= set(model['pending'])
    assert json.dumps(notice, ensure_ascii=False) == before


def test_unknown_time_link_and_benefits_are_centralized_without_invented_values():
    notice = dict(notice_title='해커톤', application_deadline='2026-08-28', submission_method='온라인',
                  benefits='금액·지급 대상·지급 단위를 원문의 혜택 또는 시상표에서 확인해주세요. · 미확인')
    model = overview_model(notice, ['신청 마감 2026-08-28'], now=NOW)
    assert model['deadline'] == '2026.08.28' and model['benefits'] == '—'
    assert {'마감 시간', '신청 주소', '상금·혜택'} <= set(model['pending'])
    assert any('오늘 마감' in m for m in model['messages'])
    assert '23:59' not in str(model)


def test_source_conflict_or_missing_year_extension_cannot_pick_a_deadline():
    model = overview_model({'application_deadline':'2026-10-12'},
                           ['신청 마감 2026-10-12 13:00\n모집기간 연장 ~10/14 14:00까지'], now=NOW)
    assert model['deadline'] == '—'
    assert '접수 마감·모집 차수' in model['pending']


def test_real_poster_keeps_known_amounts_and_expired_status():
    fixture = json.loads((Path(__file__).parent/'fixtures/public_sample3.json').read_text('utf-8'))
    model = overview_model(fixture['notice'], fixture['pages'], now=NOW.replace(hour=19))
    assert '300' in model['benefits'] and model['deadline'] == '2026.08.28 · 18:00'
    assert any('마감된 공고' in m for m in model['messages'])
    assert '제출서류' in model['pending']  # Product restrictions aren't a verified submission checklist.
    assert '신청 주소' not in model['pending']  # Postal/visit submissions don't require a URL.


def test_overview_keeps_navigation_downloads_and_saved_answers_without_calls(app):
    at = app
    with patch('upstage_client.run_agent', side_effect=AssertionError('No API calls')):
        at.text_input(key='catalog_search').set_value('통영').run(timeout=20)
        next(b for b in at.button if b.label=='이 공고 검토하기').click().run(timeout=20)
        assert at.session_state.screen == 2
        assert [e.label for e in at.expander if e.label in ('원문과 근거 확인','상세 조건 확인')] == ['원문과 근거 확인','상세 조건 확인']
        assert not any(e.label in ('원본과 추출된 조건','조건·서류·일정을 항목별로 확인') for e in at.expander)
        assert len(at.get('download_button')) == 2
        next(b for b in at.button if b.label=='내 상황 입력하기 →').click().run(timeout=20)
        assert at.session_state.screen == 3
        at.session_state.answer_other_facts = '분리된 테스트 답변'
        at.button(key='nav_2').click().run(timeout=20)
        assert at.session_state.answer_other_facts == '분리된 테스트 답변'
        next(b for b in at.button if b.label=='← 공고 넣기로').click().run(timeout=20)
        assert at.session_state.screen == 1 and at.session_state.pdf
        assert not at.exception
