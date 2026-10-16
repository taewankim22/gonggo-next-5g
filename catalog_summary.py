"""Public notice facts for browsing; no profile judgements or new AI calls."""
import re

from catalog import available_record
from core import normalize


def compact_text(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def public_summary(root, group):
    fields = {key: [] for key in ('organizer', 'audience', 'application', 'benefits')}
    seen = {key: set() for key in fields}
    tags = []
    for record in group['documents']:
        state = available_record(root, record)
        if not state:
            continue
        notice = state['notice']
        structured = notice.get('_structured_notice', {})
        # Live tags contain organizer/type, not subject areas. Never relabel
        # those as subjects or infer a subject from the title.
        excluded = {normalize(notice.get('organizer', '')), normalize(notice.get('notice_type', ''))}
        for tag in record.get('tags', []):
            if tag and (record.get('storage') != 'live' or normalize(tag) not in excluded):
                if tag not in tags:
                    tags.append(tag)
        audience = []
        for row in structured.get('지원조건', []):
            if row.get('분류') == '지원자격' and row.get('적용단계') == '지원단계':
                parts = [row.get('조건', '')]
                if row.get('적용대상') not in ('', '전체', '모든 지원자', '지원자 전체', None):
                    parts.append('대상: '+row['적용대상'])
                if row.get('예외'):parts.append('예외: '+row['예외'])
                audience.append(' · '.join(parts))
        benefit_rows = structured.get('혜택', [])
        benefits = [' · '.join(dict.fromkeys(row.get(k, '') for k in
                    ('종류', '내용', '금액표현', '금액범위', '대상', '지급단계') if row.get(k)))
                    for row in benefit_rows]
        values = {
            'organizer': [notice.get('organizer', '')],
            'audience': [' / '.join(dict.fromkeys(audience)) or notice.get('eligibility_rule', '')],
            # Preserve wording, including missing years and timezones. Only
            # the existing grounded calendar claims a confirmed calendar date.
            'application': [notice.get('deadline_note', '')],
            # workflow_adapter/studio_latest have already preserved scope and
            # blocked the compact schema's unsupported numeric total.
            'benefits': benefits or [notice.get('benefits', '')],
        }
        for key, entries in values.items():
            for value in entries:
                text = compact_text(value)
                if not text or normalize(text) in seen[key]:
                    continue
                seen[key].add(normalize(text))
                fields[key].append({'text': text, 'document': record.get('document_name', record['title'])})
    return {**fields, 'fields': ' · '.join(tags)}
