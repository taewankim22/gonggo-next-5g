"""Presentation of existing notice facts; never changes stored extraction or decisions."""
import base64
import datetime as dt
import re

import streamlit as st

from catalog_categories import catalog_kind
from core import evidence
from deadline_calendar import document_deadlines, consolidate, event_status, now_kst
from ui_components import esc, submission_url


def fact_text(value):
    text = str(value or '').strip()
    if not text or re.fullmatch(r'[-—]|미확인|미기재|확인 필요|명시되지 않음', text):
        return ''
    if text.startswith(('금액·지급 대상·지급 단위를 원문', '금액·혜택 미기재',
                        '원문 또는 운영기관에 확인', '명시되지 않음 · 원문 확인')):
        return ''
    return text


def overview_model(notice, pages, source=None, now=None):
    source = source or {}
    now = now or now_kst()
    pending = []
    messages = []
    structured = notice.get('_structured_notice') or {}
    record = dict(id='current', source_url=source.get('url', ''), checked_at=source.get('checked_at', ''))
    parsed = document_deadlines(notice, pages, record)
    dates = consolidate([parsed])
    events = dates['events']
    deadline = ''
    if events:
        # Preserve distinct stages instead of choosing an arbitrary earliest date.
        lines = []
        for event in events:
            value = event['date'].replace('-', '.')
            if event['time']:value += ' · ' + event['time']
            if event['time'] and event['timezone'] not in ('', 'Asia/Seoul'):
                value += ' ' + event['timezone']
            if len(events) > 1:value = event['stage'] + '\n' + value
            lines.append(value)
        deadline = '\n'.join(lines)
        if any(not e['time'] for e in events):pending.append('마감 시간')
        if any(not e['timezone'] for e in events):pending.append('마감 시간대')
        if all(event_status(e, now) == '마감' for e in events):
            messages.append('마감된 공고입니다. 조건 검증·연습용으로 확인하세요.')
        elif any(event_status(e, now) == '오늘 마감 · 시간 확인 필요' for e in events):
            messages.append('오늘 마감하는 공고입니다. 정확한 마감 시간을 원문에서 확인하세요.')
    elif dates['category'] in ('상시 모집', '예산 소진 시 종료'):
        deadline = dates['category']
        pending.append('현재 접수 여부')
    else:
        # Keep the existing extracted date visible when no conflicting source
        # candidate exists, but disclose that its source/time needs checking.
        proposed = notice.get('application_deadline', '')
        try:
            date = dt.date.fromisoformat(proposed)
            if not parsed['ambiguous'] and not dates['evidence']:
                deadline = date.strftime('%Y.%m.%d')
                pending.extend(['접수 마감 근거', '마감 시간'])
                if date < now.astimezone(dt.timezone(dt.timedelta(hours=9))).date():
                    messages.append('추출된 마감일이 지난 공고입니다. 접수 상태는 원문에서 확인하세요.')
        except (ValueError, TypeError):
            pass
        if not deadline:pending.append('접수 마감·모집 차수' if dates['evidence'] or parsed['ambiguous'] else '접수 마감')

    def grounded(category, table=None, condition_type=None):
        if table and table in structured:
            rows = structured[table]
            if condition_type:rows = [r for r in rows if r.get('분류') == condition_type]
            return bool(rows) and all(evidence(r.get('근거원문'), r.get('근거페이지'), pages) for r in rows)
        return evidence(notice.get(category + '_quote'), notice.get(category + '_page'), pages)

    audience = fact_text(notice.get('eligibility_rule'))
    audience = re.sub(r'(?m)^지원단계 · 전체 · ', '', audience)
    if not audience or not grounded('eligibility', '지원조건', '지원자격'):pending.append('세부 지원 자격')
    method = fact_text(notice.get('submission_method'))
    if not method:pending.append('신청 방법')
    elif re.search(r'온라인|홈페이지|웹|구글|폼|사이트', method) and not submission_url(method):pending.append('신청 주소')
    benefits = fact_text(notice.get('benefits'))
    if not benefits or ('혜택' in structured and not grounded('', '혜택')):pending.append('상금·혜택')
    if notice.get('_schema_limits') or not grounded('documents', '제출서류'):pending.append('제출서류')
    if notice.get('_schema_limits') or not grounded('preference', '지원조건', '우대'):pending.append('우대조건')
    conflicts = [c for c in notice.get('source_conflicts', []) if not notice.get('_schema_limits') or not c.startswith(notice['_schema_limits'])]
    if conflicts:pending.append('원문 유의사항·조건 충돌')
    if not any(pages):pending.append('원문 본문')
    if source.get('coverage_note'):pending.append('분석한 문서 범위')
    return dict(title=notice.get('notice_title') or '공고 핵심 정보',
                kind=catalog_kind({'title':notice.get('notice_title'), 'kind':notice.get('notice_type')}),
                deadline=deadline or '—', audience=audience or '—', method=method or '—', benefits=benefits or '—',
                pending=list(dict.fromkeys(pending)), messages=messages, dates=dates)


ICONS = {
    'deadline':'<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4m8-4v4M4 11h16"/>',
    'audience':'<circle cx="12" cy="7" r="3"/><path d="M5 21v-3a7 7 0 0 1 14 0v3M4 5a3 3 0 0 0 0 6m16-6a3 3 0 0 1 0 6"/>',
    'method':'<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/>',
    'benefits':'<rect x="4" y="10" width="16" height="11" rx="1"/><path d="M3 6h18v4H3zm9 0v15"/><path d="M12 6C3 6 5 0 9 3l3 3c9 0 7-6 3-3z"/>',
}


def render_overview(notice, pages, source=None):
    model = overview_model(notice, pages, source)
    cards = []
    for key, label in [('deadline','접수 마감'), ('audience','지원 대상'), ('method','신청 방법'), ('benefits','상금·혜택')]:
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#c92873" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' + ICONS[key] + '</svg>'
        # Streamlit sanitizes inline SVG; a fixed, local data image needs no network.
        icon = '<img alt="" aria-hidden="true" src="data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode() + '">'
        cards.append(f'<section class="overview-card overview-{key}" aria-label="{label}"><div class="overview-icon">{icon}</div>'
                     f'<div class="overview-copy"><div class="overview-label">{label}</div><div class="overview-value">{esc(model[key])}</div></div></section>')
    st.html('<div class="notice-overview"><div class="overview-eyebrow">' + esc(model['kind']) + '</div>'
            '<h1 class="overview-title">' + esc(model['title']) + '</h1><div class="overview-grid">' + ''.join(cards) + '</div></div>')
    if model['pending'] or model['messages']:
        items = '<p class="overview-pending">' + esc(' · '.join(model['pending'])) + '</p>' if model['pending'] else ''
        messages = ''.join('<p class="overview-important">' + esc(m) + '</p>' for m in model['messages'])
        title = '원문 확인이 필요한 정보' if model['pending'] else '접수 상태 안내'
        st.html('<aside class="overview-caution" role="note" aria-label="공고 확인 안내"><span class="overview-warning-icon" aria-hidden="true">!</span>'
                '<div><strong>' + title + '</strong>' + items + messages +
                '<p class="overview-disclaimer">현재 요약만으로 지원 가능 여부를 확정할 수 없어요.</p></div></aside>')
    return model
