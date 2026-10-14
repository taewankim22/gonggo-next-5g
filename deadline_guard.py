"""Keep inferred recruitment years out of deadlines and ranking."""
import datetime as dt
import re


def explicit_date(date, text):
    """Require a complete date or a locally scoped, explicit-year date range."""
    try:
        value=dt.date.fromisoformat(date)
    except (ValueError,TypeError):
        return False
    y,m,d=value.year,value.month,value.day
    year=rf'(?<!\d){y}\s*[년./-]\s*'
    month=rf'0?{m}\s*[월./-]\s*'
    day=rf'0?{d}(?:\s*일)?(?!\d)'
    if re.search(year+month+day,text):return True
    # e.g. 2026.10.6.(화) ~ 10.26.(월), or 2026년 10월 6~26일.
    start=rf'{year}(?:0?[1-9]|1[0-2])\s*[월./-]\s*(?:0?[1-9]|[12]\d|3[01])\s*일?\.?\s*(?:\([^)]{{1,4}}\))?\s*[~～∼–-]\s*'
    if re.search(start+month+day,text):return True
    start_same=rf'{year}{month}(?:0?[1-9]|[12]\d|3[01])\s*일?\.?\s*(?:\([^)]{{1,4}}\))?\s*[~～∼–-]\s*'
    return bool(re.search(start_same+day,text))


def guard_deadline(raw,pages):
    """Mutate the copied structured result, never the original AI trace."""
    deadline=raw.get('접수마감','')
    if not deadline:return
    from core import evidence
    schedules=[r for r in raw.get('일정',[]) if re.search(r'접수|신청|지원서|응모',r.get('일정명',''))]
    quotes=[r.get('근거원문','') for r in schedules
            if evidence(r.get('근거원문',''),r.get('근거페이지',''),pages)]
    note=raw.get('접수마감설명','')
    if any(evidence(note,str(i+1),pages) for i in range(len(pages))):quotes.append(note)
    # Seeing a program year in the title does not establish its application year.
    if any(explicit_date(deadline,q) for q in quotes):return
    raw['접수마감']=''
    message='접수 마감의 연도·날짜를 원문 접수 일정에서 확인하지 못했습니다. 원문 확인 필요'
    if message not in note:raw['접수마감설명']=' · '.join(x for x in (note,message) if x)
    if not any(r.get('내용')==message for r in raw.get('주의사항',[])):
        raw.setdefault('주의사항',[]).append({'내용':message,'근거원문':'','근거페이지':''})
