import datetime as dt
import json
from pathlib import Path
import pytest
from deadline_calendar import (document_deadlines,consolidate,event_status,group_status,
                               month_shift,month_days,KST,group_deadlines)

ROOT=Path(__file__).parents[1]
RECORD=dict(id='test',source_url='https://example.org/notice',checked_at='2026-10-16T00:00:00Z')

def parse(text,date=''):
    return document_deadlines({'application_deadline':date},[text],RECORD)

def detail(text,date=''):
    return consolidate([parse(text,date)])

def test_actual_public_three_documents_reuse_saved_parse_and_ai_results():
    expected=[('2026-01-26',''),('2026-05-29',''),('2026-08-28','18:00')]
    for i,want in enumerate(expected,1):
        data=json.loads((ROOT/f'data/catalog/notice{i}.json').read_text('utf-8'))
        result=consolidate([document_deadlines(data['notice'],data['pages'],RECORD)])
        assert result['category']=='날짜 확인'
        assert [(e['date'],e['time']) for e in result['events']]==[want]
        assert all(e['quote'] in data['pages'][int(e['page'])-1] for e in result['events'][0]['evidence'])
    assert result['events'][0]['delivery']=='우편 도착분 기준'

def test_missing_time_not_borrowed_from_results_or_contact():
    data=detail('서류 접수 2026.10.1 ~ 2026.10.16\n합격자 발표 2026.10.20 18:00\n문의 09:00~18:00')
    e=data['events'][0];assert e['time']==''
    assert event_status(e,dt.datetime(2026,10,16,23,30,tzinfo=KST))=='오늘 마감 · 시간 확인 필요'
    assert event_status(e,dt.datetime(2026,10,17,tzinfo=KST))=='마감'
    assert detail('접수기간 2026.10.1 ~ 2026.10.16 문의 09:00~18:00')['events'][0]['time']==''
    assert detail('접수기간 2026.10.1 ~ 2026.10.16 결과 발표 2026.10.20 18:00')['events'][0]['time']==''

def test_exact_time_midnight_month_and_year_boundaries():
    e=detail('접수 마감 2026-12-31 18:00 KST')['events'][0]
    assert event_status(e,dt.datetime(2026,12,31,17,59,tzinfo=KST)).startswith('마감 전')
    assert event_status(e,dt.datetime(2026,12,31,18,tzinfo=KST))=='마감'
    assert month_shift('2026-12',1)=='2027-01'
    assert month_shift('2026-01',-1)=='2025-12'
    assert len([d for week in month_days('2028-02') for d in week if d.month==2])==29
    midnight=detail('신청 마감 2027-01-01 00:00')['events'][0]
    assert midnight['date']=='2027-01-01' and midnight['time']=='00:00'

def test_explicit_foreign_timezone_and_unknown_timezone():
    e=detail('신청 마감 2026-10-16 18:00 UTC+00:00')['events'][0]
    assert event_status(e,dt.datetime(2026,10,17,2,59,tzinfo=KST)).startswith('마감 전')
    assert event_status(e,dt.datetime(2026,10,17,3,tzinfo=KST))=='마감'
    e=detail('신청 마감 2026-10-16 18:00 미국 현지 시간')['events'][0]
    assert event_status(e)=='시간대 확인 필요'
    e=detail('신청 마감 2026-10-16 18:00 UTC+09:30')['events'][0]
    assert e['timezone']=='UTC+09:30'
    assert event_status(e,dt.datetime(2026,10,16,17,30,tzinfo=KST))=='마감'
    e=detail('신청 마감 2026-10-16 18:00 UTC+25:00')['events'][0]
    assert event_status(e)=='시간대 확인 필요'

@pytest.mark.parametrize('text',[
    '2026년 장학금 공고\n접수기간 10.1 ~ 10.16',
    '합격자 발표 2026-10-16 18:00',
    '활동 기간 2026-10-01 ~ 2026-10-16',
    '모집기간 2026-10-01',
    '신청 마감 2026-02-30',
    '신청기간 2026-10-01 ~ 10-32까지',
    '신청기간 2026-10-16 ~ 2026-10-01까지',
    '응모 자격: 2026-10-16까지 만 18세가 되는 사람',
    '신청자 2026-10-16까지 재학한 사람',
    '1차 접수 마감 2026-10-16 / 2차 접수 마감 2026-11-16',
])
def test_no_invented_year_or_other_stage_or_ambiguous_date(text):
    assert not detail(text)['events']

def test_rolling_missing_and_budget_are_visible_separately():
    assert detail('상시 모집')['category']=='상시 모집'
    assert detail('신청 접수: 예산 소진 시까지')['category']=='예산 소진 시 종료'
    assert detail('날짜 없음')['category']=='마감일 확인 필요'

def test_same_source_multiple_attachments_dates_and_clocks_conflicts():
    a=parse('접수 마감 2026-10-16 18:00')
    b=parse('접수 마감 2026-10-17 18:00')
    assert consolidate([a,b])['category']=='문서 간 마감 충돌'
    assert len(consolidate([a,a])['events'])==1
    assert consolidate([a,parse('접수 마감 2026-10-16 17:00')])['category']=='문서 간 마감 충돌'
    assert not consolidate([a],unavailable=True)['events']
    # A stale model date is not allowed to override a source extension.
    assert not detail('접수 마감 2026-10-30','2026-10-16')['events']
    assert detail('접수 마감 2026-10-30','2026-10-30')['events'][0]['date']=='2026-10-30'

def test_rounds_and_document_stages_remain_separate():
    d=detail('1차 신청 마감 2026-10-16\n2차 신청 마감 2026-11-16')
    assert len(d['events'])==2 and d['events'][0]['stage'].startswith('1차')
    d=detail('서류 제출 마감 2026-10-16\n작품 제출 마감 2026-10-20')
    assert len(d['events'])==2

def test_postmark_wording_and_false_timestamp_not_hidden():
    e=detail('우편 접수 마감 2026-10-16 18:00 소인분까지')['events'][0]
    assert e['delivery']=='우편 소인분 기준'
    assert e['timezone_basis'].startswith('서비스 기본')
    assert detail('접수 마감 2026-10-16 오후 6시')['events'][0]['time']=='18:00'
    assert detail('접수 마감 2026-10-16 오전 12시')['events'][0]['time']=='00:00'
    assert detail('접수 마감 2026-10-16 오후 6시 5분')['events'][0]['time']=='18:05'
    assert detail('접수 마감 2026-10-16 18:')['events'][0]['time']==''

def test_read_failure_blocks_calendar_even_with_old_analysis(tmp_path,monkeypatch):
    monkeypatch.setattr('catalog.available_record',lambda *args:dict(notice={},pages=['신청 마감 2026-10-16']))
    result=group_deadlines(tmp_path,[RECORD],{'complete':False,'fetch_failed':True})
    assert not result['events'] and result['category']=='원문 갱신 확인 필요'
