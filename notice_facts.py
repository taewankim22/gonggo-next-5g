"""Source-backed benefit display. No model calls, arithmetic, or title-specific rules."""
import re
from core import evidence, normalize


def exclusion_context(row,pages):
    """A source exclusion heading takes precedence over the model's category.

    Preserve the contiguous heading+list so the negation has visible evidence.
    Never infer exclusion merely from words such as '수상' in an isolated line.
    """
    quote=row.get('근거원문','')
    if not quote:return row
    for page_no,page in enumerate(pages,1):
        pattern=r'(?m)^[^\n]*?(?:참여 제한 대상|지원 제외 대상|신청 제외 대상)[^\n]*\n(?:(?![□❒]|\d+\.\s).*(?:\n|$))+'
        for match in re.finditer(pattern,page):
            block=match.group().strip()
            if normalize(quote) not in normalize(block):continue
            row=dict(row)
            text=row.get('조건','')
            if not text.startswith('참여 제한 대상에 해당하지 않아야 함:'):
                text='참여 제한 대상에 해당하지 않아야 함: '+text
            row.update(분류='지원자격',조건=text,대조항목='',비교방법='검토',기준값='',
                       근거원문=block,근거페이지=str(page_no))
            return row
    return row


def relocate(row, pages):
    row = dict(row)
    # Studio's table IDs are annotations, not words printed in the document.
    quote = re.sub(r'(?m)^\s*s_\d+_i_\d+\s*(?=\|)', '', row.get('근거원문', ''))
    row['근거원문'] = quote
    if not evidence(quote, row.get('근거페이지'), pages):
        matches = [str(i) for i in range(1, len(pages)+1) if evidence(quote, str(i), pages)]
        if len(matches) == 1:row['근거페이지'] = matches[0]
    return row


def recover_benefits(pages):
    """Old compact results: expose original benefit passages, never a generated total.

    Keep table rows verbatim (including counts and units) rather than interpreting
    their columns. The UI labels this as source text, not newly executed AI.
    """
    found = []
    for page_no, page in enumerate(pages, 1):
        lines = page.splitlines()
        active = False
        for i, line in enumerate(lines):
            text = line.strip()
            if re.search(r'(?:지원|활동|참가)\s*(?:내용|혜택)|시상\s*(?:내역|규모|내용)|총\s*상금', text):
                active = True
            elif re.match(r'^\s*(?:#{1,4}\s*)?\d+[.)]\s*[^\d]', text) and not re.search('지원|시상|혜택',text):
                active = False
            money = re.search(r'\d[\d,.]*\s*(?:억|만|천)?\s*원|(?:USD|KRW|\$)\s*\d', text)
            direct = bool(re.search(r'장학금|상금|활동비|수당|시상금', text) and money)
            supported = active and (money or re.search(r'멘토링|특강|교육|수료증', text))
            if not (direct or supported) or len(normalize(text)) < 8:continue
            # Do not mislabel an application fee as a benefit.
            if re.search(r'참가비|접수비|신청비|수강료|반환|환수', text):continue
            row = {'종류':'원문 혜택', '내용':text, '금액표현':'', '금액범위':'원문표현',
                   '근거원문':text, '근거페이지':str(page_no)}
            if evidence(text,str(page_no),pages) and normalize(text) not in {normalize(r['내용']) for r in found}:
                found.append(row)
    return found


def benefit_rows(notice, pages):
    rows = notice.get('_structured_notice',{}).get('혜택',[])
    result = []
    for original in rows:
        row = relocate(original,pages)
        quote = row.get('근거원문','')
        verified = evidence(quote,row.get('근거페이지'),pages)
        # A correct quote alone does not validate an invented amount/name/count.
        for key in ('금액표현', '혜택명'):
            value = row.get(key,'').strip()
            if value and normalize(value) not in normalize(quote):verified = False
        # An isolated table number is not a monetary value without its unit.
        if row.get('금액표현') and not re.search(r'원|KRW|USD|달러|엔|유로|[$€¥₩]',row['금액표현'],re.I):verified=False
        count = row.get('지급인원','')
        count_verified = bool(count and normalize(count) in normalize(quote))
        title = row.get('혜택명') or row.get('내용','')
        if row.get('금액표현'):
            text = ' · '.join(v for v in (title,count if count_verified else '',row.get('금액표현')) if v)
            unit = row.get('금액범위','')
            if unit in ('개인당','팀당') and re.search(r'(?:1\s*인|1\s*개?\s*팀|인|팀|개인)\s*당',quote) and not re.search(r'당',row['금액표현']):text += ' · '+unit
            if unit=='전체총규모' and re.search(r'총\s*지원\s*규모|전체\s*사업\s*예산|사업규모|사업비|지원규모',quote):text='전체 지원 규모 · '+text
            # Preserve the nearest explicit type heading (e.g. undergraduate vs
            # graduate), rather than applying one group's amount to everyone.
            if unit=='개인당' and row.get('근거페이지','').isdigit():
                page=pages[int(row['근거페이지'])-1] if 0<int(row['근거페이지'])<=len(pages) else ''
                headings=re.findall(r'(?m)^\s*(\[[^\]\n]*유형\][^\n]+)',page)
                if len(headings)==1:text=headings[0].strip()+' · '+text
        else:
            text = row.get('내용') or title
            if normalize(text) not in normalize(quote):text = quote
        if text:
            result.append({**row,'display':text,'verified':verified,
                           'scope_pending':bool(row.get('금액표현') and (row.get('금액범위')=='미확인' or (count and not count_verified)))})
    return result


def benefit_summary(notice, pages):
    rows = benefit_rows(notice,pages)
    verified = [r for r in rows if r['verified']]
    if not rows:
        return '', rows
    # Personal benefits precede programme budgets; contest totals remain first.
    verified.sort(key=lambda r:(0 if r.get('금액범위')=='개인당' else 1 if '총상금' in r['display'] else 2 if r.get('금액표현') and r.get('금액범위')!='전체총규모' else 3 if not r.get('금액표현') else 4))
    lines = list(dict.fromkeys(r['display'] for r in verified))
    # Keep each fact intact; expanded details carry all remaining rows.
    summary = '\n'.join(lines[:4])
    if len(lines)>4:summary += f'\n외 {len(lines)-4}개 혜택 · 아래 상세보기'
    return summary, rows
