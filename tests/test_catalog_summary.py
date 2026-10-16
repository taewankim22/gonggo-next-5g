from pathlib import Path

from catalog import load_catalog
from catalog_summary import public_summary
from core import validate_payload
from schema_builder import notice_schema
from workflow_adapter import ground_notice
from test_latest_studio import compact

ROOT = Path(__file__).parents[1]


def test_saved_public_notices_preserve_award_scope_and_dates():
    records = {r['id']: r for r in load_catalog(ROOT) if r['id'].startswith('notice')}
    summaries = {key: public_summary(ROOT, {'documents': [record]}) for key, record in records.items()}
    assert '관광' in summaries['notice3']['fields']
    prize = summaries['notice3']['benefits'][0]['text']
    assert '대상 300 만원' in prize and '금 상 150만원' in prize and '장려상 30 만원' in prize
    scholarship = summaries['notice5']['benefits'][0]['text']
    assert '18억 원' in scholarship and '300명 × 학기당 300만 원 × 2개 학기' in scholarship
    assert '활동 종료 후 40만원' in summaries['notice2']['benefits'][0]['text']
    assert summaries['notice4']['application'][0]['text'] == '2026년 5월 1일부터 상시 가능(~12/30)'


def test_missing_fields_and_unscoped_compact_total_are_not_invented(monkeypatch):
    notice = ground_notice(validate_payload(compact(), notice_schema()), ['대한민국 국민 누구나'])
    monkeypatch.setattr('catalog_summary.available_record', lambda *a: {'notice': notice})
    record = {'title': '테스트', 'storage': 'live', 'tags': ['', notice['notice_type']]}
    result = public_summary(ROOT, {'documents': [record]})
    assert result['fields'] == '' and result['organizer'] == []
    assert '5800000' not in str(result) and '5,800,000' not in str(result)
    assert '확인' in result['benefits'][0]['text']


def test_multi_document_benefits_deduplicate_without_adding_amounts(monkeypatch):
    texts = {'a': '대상 300만원 · 1팀', 'b': '대상 300만원 · 1팀', 'c': '총상금 1,000만원'}
    monkeypatch.setattr('catalog_summary.available_record', lambda root, r: {'notice': {'benefits': texts[r['id']]}})
    records = [{'id': key, 'title': key} for key in texts]
    result = public_summary(ROOT, {'documents': records})
    assert [r['text'] for r in result['benefits']] == ['대상 300만원 · 1팀', '총상금 1,000만원']
    assert result['benefits'][1]['document'] == 'c'
    assert public_summary(ROOT, {'documents': []})['benefits'] == []
