"""Public, source-grounded closing events. Pure functions: no network or writes."""
import calendar
import datetime as dt
import re
from core import fingerprint

KST = dt.timezone(dt.timedelta(hours=9))
APPLICATION = re.compile(r'접수|신청|응모|모집\s*기간|모집\s*마감|(?:상시|수시)\s*모집|(?:서류|작품|지원서|제안서)\s*제출')
OTHER = re.compile(r'발표|면접|심사|활동\s*기간|활동\s*종료|문의|운영\s*시간|지원\s*자격|모집\s*대상|공모\s*분야|시상|모집\s*인원|모집\s*분야|선발\s*절차')
FULL_DATE = re.compile(r'(?<!\d)(20\d{2})\s*[년./-]\s*(\d{1,2})\s*[월./-]\s*(\d{1,2})(?:\s*일)?(?!\d)')
SHORT_DATE = re.compile(r'(?<!\d)(\d{1,2})\s*[월./-]\s*(\d{1,2})(?:\s*일)?(?!\d)')
TIME = re.compile(r'(?<!\d)([01]?\d|2[0-3])(?:\s*:\s*([0-5]\d)(?!\d)|\s*시(?:\s*([0-5]?\d)\s*분)?)(?!\d)')


def now_kst():
    return dt.datetime.now(KST)


def source_blocks(pages):
    """Use a local application section; never borrow a year from the title."""
    for page_no, page in enumerate(pages, 1):
        lines = page.splitlines()
        for i, line in enumerate(lines):
            if re.search(r'(?:신청|응모|지원|참가)\s*(?:자격|대상)|신청자\s|응모자\s',line):continue
            if not APPLICATION.search(line) or (OTHER.search(line) and not re.search(r'접수|신청|응모',line)):
                continue
            block = [line]
            for following in lines[i+1:i+5]:
                if OTHER.search(following) or APPLICATION.search(following): break
                block.append(following)
            text = '\n'.join(block).strip()
            # A flattened table may contain the next stage on the same line.
            boundary = re.search(r'(?:서류\s*심사|최종\s*결과|합격자|결과)\s*발표|면접\s*(?:심사|일정)',text)
            if boundary: text = text[:boundary.start()].strip()
            if text: yield text, str(page_no)


def dates_in(text):
    """Explicit dates plus a short range end with a local, explicit start year."""
    found=[]
    for match in FULL_DATE.finditer(text):
        try: date=dt.date(*map(int,match.groups()))
        except ValueError: continue
        found.append((match.start(),match.end(),date))
        tail=text[match.end():]
        connector=re.match(r'\s*\.?\s*(?:\([^)]{1,4}\))?\s*(?:[~～∼–-]|부터)\s*',tail)
        if connector:
            endtext=tail[connector.end():]
            short=SHORT_DATE.match(endtext)
            if short:
                try: end=dt.date(date.year,int(short[1]),int(short[2]))
                except ValueError: continue
                if end>=date: found.append((match.end()+connector.end(),match.end()+connector.end()+short.end(),end))
            else:
                day=re.match(r'(\d{1,2})\s*일',endtext)
                if day:
                    try: end=date.replace(day=int(day[1]))
                    except ValueError: continue
                    if end>=date: found.append((match.end()+connector.end(),match.end()+connector.end()+day.end(),end))
    return sorted(set(found))


def stage_name(text):
    round_=re.search(r'(?<!\d)(\d+\s*차)(?:\s*(?:모집|접수|신청))?',text)
    step='작품 제출' if re.search(r'작품\s*(?:제출|접수)',text) else '서류 제출' if re.search(r'서류\s*제출',text) else '신청·접수'
    return ((round_[1].replace(' ','')+' ') if round_ else '')+step+' 마감'


def zone_info(text):
    if re.search(r'한국\s*시간|\bKST\b|Asia/Seoul',text,re.I):return 'Asia/Seoul','원문에 한국 시간 명시'
    if re.search(r'\bUTC\b|\bGMT\b',text,re.I):
        offset=re.search(r'(?:UTC|GMT)\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?',text,re.I)
        if offset and int(offset[2])<=14 and int(offset[3] or 0)<60 and not (int(offset[2])==14 and int(offset[3] or 0)>0):
            return f'UTC{offset[1]}{int(offset[2]):02d}:{int(offset[3] or 0):02d}','원문 시간대'
        if not offset and not re.search(r'(?:UTC|GMT)\s*[+-]',text,re.I):return 'UTC+00:00','원문 시간대'
        return '', '원문 시간대 표기 확인 필요'
    if re.search(r'현지\s*시간|\b(?:EST|EDT|PST|PDT|CET|CEST|JST)\b|(?:미국|일본|영국|유럽)\s*시간',text,re.I):
        return '', '원문의 다른 시간대 확인 필요'
    return 'Asia/Seoul','서비스 기본: 한국 시간 (원문 시간대 미기재)'


def document_deadlines(notice,pages,record):
    events=[];rolling='';ambiguous=False
    for quote,page in source_blocks(pages):
        if re.search(r'예산\s*소진',quote):rolling='예산 소진 시 종료'
        elif re.search(r'상시\s*(?:모집|접수|신청)|수시\s*(?:접수|모집)',quote):rolling=rolling or '상시 모집'
        dates=dates_in(quote)
        if not dates:continue
        # Multiple labeled rounds on one line must not be collapsed to the last date.
        if len(set(re.findall(r'\d+\s*차',quote)))>1:
            ambiguous=True;continue
        if len({v[2] for v in dates})>2:
            ambiguous=True;continue
        if len(dates)>1:
            between=quote[dates[0][1]:dates[-1][0]]
            if not re.search(r'[~～∼–-]|부터',between):
                ambiguous=True;continue
        elif not re.search(r'마감|까지|종료|도착|소인|접수\s*일|신청\s*일|제출\s*기한',quote):
            # A lone start date is not a closing date.
            ambiguous=True;continue
        start,end,date=dates[-1]
        time_text=re.sub(r'(?:UTC|GMT)\s*[+-]\s*\d{1,2}(?::?\d{2})?','',quote[end:],flags=re.I)
        times=list(TIME.finditer(time_text))
        clock=''
        if len(times)==1:clock=f'{int(times[0][1]):02d}:{int(times[0][2] or times[0][3] or 0):02d}'
        elif len(times)==2 and re.search(r'[~～∼–-]',time_text[times[0].end():times[1].start()]):
            clock=f'{int(times[-1][1]):02d}:{int(times[-1][2] or times[-1][3] or 0):02d}'
        elif len(times)>1:ambiguous=True;continue
        if clock:
            marker=time_text[max(0,times[-1].start()-5):times[-1].start()]
            hour,minute=map(int,clock.split(':'))
            if '오후' in marker and 1<=hour<12:hour+=12
            elif '오전' in marker and hour==12:hour=0
            clock=f'{hour:02d}:{minute:02d}'
        zone,basis=zone_info(quote)
        delivery='우편 도착분 기준' if '도착' in quote else '우편 소인분 기준' if '소인' in quote else ''
        events.append(dict(date=date.isoformat(),time=clock,timezone=zone,timezone_basis=basis,
            stage=stage_name(quote),quote=quote,page=page,document_id=record['id'],
            document_name=record.get('document_name',record.get('filename','')),source_url=record['source_url'],
            checked_at=record.get('checked_at',''),delivery=delivery,date_verified=True,time_verified=bool(clock)))
    # A pre-existing AI date that differs from source-derived dates needs review.
    proposed=notice.get('application_deadline','')
    if proposed and events and proposed not in {e['date'] for e in events}:ambiguous=True
    return dict(events=events,rolling=rolling,ambiguous=ambiguous)


def consolidate(results, unavailable=False):
    all_events=[e for r in results for e in r['events']]
    if unavailable:return dict(events=[],category='원문 갱신 확인 필요',evidence=all_events)
    if any(r['ambiguous'] for r in results):return dict(events=[],category='마감일 확인 필요',evidence=all_events)
    unique={}
    # Same application date across a poster and its postal-method paragraph is one event.
    for e in all_events:
        key=(e['stage'],e['date'])
        if key not in unique:unique[key]={**e,'evidence':[e]}
        else:
            prior=unique[key];prior['evidence'].append(e)
            if prior['time'] and e['time'] and (prior['time'],prior['timezone'])!=(e['time'],e['timezone']):
                return dict(events=[],category='문서 간 마감 충돌',evidence=all_events)
            if not prior['time'] and e['time']:
                for field in ('time','timezone','timezone_basis','time_verified'):prior[field]=e[field]
            prior['delivery']=prior['delivery'] or e['delivery']
    stages={}
    for stage,date in unique:stages.setdefault(stage,set()).add(date)
    if any(len(dates)>1 for dates in stages.values()):return dict(events=[],category='문서 간 마감 충돌',evidence=all_events)
    events=list(unique.values())
    for e in events:e['id']=fingerprint([e['stage'],e['date'],e['time']])[:16]
    rolling=next((r['rolling'] for r in results if r['rolling']),'')
    if rolling and events:return dict(events=[],category='마감 조건 확인 필요',evidence=all_events)
    return dict(events=events,category='날짜 확인' if events else rolling or '마감일 확인 필요',evidence=all_events)


def group_deadlines(root,documents,scan=None):
    from catalog import available_record
    results=[]
    for record in documents:
        state=available_record(root,record)
        if state:results.append(document_deadlines(state['notice'],state['pages'],record))
    unavailable=not documents or bool(scan and (scan.get('fetch_failed') or not scan.get('complete')))
    return consolidate(results,unavailable)


def event_status(event,now=None):
    now=now or now_kst()
    if isinstance(now,dt.date) and not isinstance(now,dt.datetime):now=dt.datetime.combine(now,dt.time(),KST)
    if now.tzinfo is None:now=now.replace(tzinfo=KST)
    date=dt.date.fromisoformat(event['date']);zone=event['timezone']
    if not zone:return '시간대 확인 필요'
    tz=KST
    if zone.startswith('UTC'):
        sign=1 if zone[3]=='+' else -1
        tz=dt.timezone(sign*dt.timedelta(hours=int(zone[4:6]),minutes=int(zone[7:9])))
    local=now.astimezone(tz)
    if event['time']:
        close=dt.datetime.combine(date,dt.time.fromisoformat(event['time']),tz)
        return '마감' if local>=close else '마감 전 · 시작일 확인'
    if date<local.date():return '마감'
    if date==local.date():return '오늘 마감 · 시간 확인 필요'
    return '마감 전 · 시작일 확인'


def group_status(details,now=None):
    if not details['events']:return details['category']
    statuses={event_status(e,now) for e in details['events']}
    for label in ('마감 전 · 시작일 확인','오늘 마감 · 시간 확인 필요','시간대 확인 필요'):
        if label in statuses:return label
    return '마감'


def month_shift(month,delta):
    date=dt.date.fromisoformat(month+'-01');n=date.year*12+date.month-1+delta
    return f'{n//12:04d}-{n%12+1:02d}'


def month_days(month):
    year,number=map(int,month.split('-'))
    return calendar.Calendar(firstweekday=6).monthdatescalendar(year,number)
