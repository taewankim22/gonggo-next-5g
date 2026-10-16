"""Stable browsing categories, compatible with older Studio classifications."""
import re

KINDS = ('전체', '장학금', '장학연계활동', '대외활동·봉사', '해커톤', '대회', '공모전', '기타')
HACKATHON = re.compile(r'해커톤|hack[\s-]*a[\s-]*thon', re.I)
CONTEST = re.compile(r'공모전|공모\s*(?:대회|전)', re.I)
COMPETITION = re.compile(r'대회|경진|챔피언십|competition|championship', re.I)


def catalog_kind(record):
    """Display classification only; never rewrite saved analysis or eligibility."""
    kind = str(record.get('kind') or '').strip()
    title = str(record.get('title') or '')
    # A grant for participating in a contest is still a grant, not the contest.
    if kind in ('장학금', '장학연계활동'):
        return kind
    if HACKATHON.search(kind) or HACKATHON.search(title):
        return '해커톤'
    if CONTEST.search(title):
        return '공모전'
    if COMPETITION.search(title):
        return '대회'
    if kind == '공모전':
        return '공모전'
    if kind in ('대회', '경진대회', '대회·공모전', '공모전·대회'):
        # The old combined label is a broad competition category. Do not
        # invent a hackathon subtype when the title does not identify one.
        return '대회'
    if kind in ('대외활동', '봉사', '대외활동·봉사'):
        return '대외활동·봉사'
    return '기타'


def matches_kind(record, kind):
    return kind == '전체' or catalog_kind(record) == kind
