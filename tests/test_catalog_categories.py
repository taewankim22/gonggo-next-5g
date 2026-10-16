from pathlib import Path

import pytest

from calendar_ui import filter_groups
from catalog import load_catalog
from catalog_categories import KINDS, catalog_kind
from national_search import SearchConfig, discover_nationwide


@pytest.mark.parametrize('title,kind,expected', [
    ('2026 Document Agent 해커톤 모집', '대회·공모전', '해커톤'),
    ('AI Hackathon 2026', '기타', '해커톤'),
    ('학생 AI 경진대회', '기타', '대회'),
    ('2026 인공지능 챔피언 대회', '대회·공모전', '대회'),
    ('2026년 통영시 관광기념품 공모전', '기타', '공모전'),
    ('공모전 프로그램장학금 지원금 안내', '장학금', '장학금'),
    ('해커톤 참가 지원 장학금', '장학금', '장학금'),
    ('학생 봉사자 모집', '대외활동', '대외활동·봉사'),
    ('일반 공고', '기타', '기타'),
    ('일반 공고', '대회·공모전', '대회'),
])
def test_current_and_legacy_categories(title, kind, expected):
    record={'title':title,'kind':kind}
    assert catalog_kind(record)==expected
    assert record['kind']==kind


def test_real_poster_is_in_contest_filter_without_reanalysis():
    root=Path(__file__).parents[1]
    record=next(r for r in load_catalog(root) if r['id']=='notice3')
    group={'record':record}
    assert filter_groups([group],'공모전','전체','통영')==[group]
    assert filter_groups([group],'해커톤','전체','')==[]
    assert record['kind']=='기타'
    assert {'해커톤','대회','공모전'}<=set(KINDS)


def test_hackathon_and_competition_search_candidates_are_not_discarded(tmp_path):
    titles=['AI Hackathon 2026','2026 인공지능 챔피언 대회','2026 대학생 해커톤']
    def search(query):
        return {'items':[{'link':f'https://example.org/notice/{i}','title':t} for i,t in enumerate(titles)]}
    found,stats=discover_nationwide(tmp_path,SearchConfig('test'),searcher=search,sources=())
    assert {r['title'] for r in found}==set(titles)
    assert stats['queries_completed']==54
