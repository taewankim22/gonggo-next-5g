"""Adapt Studio's compact, routed schema without inventing missing evidence."""
import copy
import json
import re

LIMIT = ('현재 Studio 설정은 제출서류·우대조건·조건별 근거를 별도로 추출하지 않습니다. '
         '아래 결과만으로 준비 완료나 지원 가능 여부를 확정할 수 없습니다. 상세 공고를 함께 확인하세요.')
TYPES = {'모집_안내문':'대외활동·봉사', '대회_공고문':'대회·공모전',
         '장학금 신청':'장학금', '대회_포스터':'대회·공모전'}


def is_compact(data):
    return isinstance(data, dict) and '공고명' in data and any(
        k in data for k in ('모집대상', '모집기간_종료일', '주관_프로그램명')) and '공고유형' not in data


def merge_extracts(parts):
    """Keep all executed parts; conflicting facts must not be last-write-wins."""
    if len(parts) == 1:
        return parts[0]
    merged = {}; conflicts = []
    for key in dict.fromkeys(k for p in parts for k in p if not k.startswith('_')):
        values = []
        for part in parts:
            value = part.get(key)
            if value is not None and value != '' and value != [] and value not in values:
                values.append(value)
        if values and all(isinstance(v, list) for v in values):
            rows = []
            for group in values:
                for row in group:
                    if row not in rows: rows.append(row)
            merged[key] = rows
        elif len(values) <= 1:
            merged[key] = values[0] if values else parts[0].get(key, '')
        else:
            merged[key] = ''
            conflicts.append(key+' 값이 문서 구간마다 다릅니다: '+json.dumps(values, ensure_ascii=False))
    merged['_extract_parts'] = parts
    merged['_extract_conflicts'] = conflicts
    return merged


def normalize_compact(data, pages=()):
    from core import evidence
    from deadline_guard import explicit_date
    def value(key):
        v = data.get(key, '')
        if v is None: return ''
        if isinstance(v, bool) or not isinstance(v, (str, int, float)):
            raise ValueError('Studio 결과의 '+key+' 형식을 확인해주세요.')
        return str(v).strip()
    def quote(text):
        matches = [str(i) for i in range(1, len(pages)+1) if evidence(text, str(i), pages)]
        return {'근거원문':text, '근거페이지':matches[0] if len(matches)==1 else ''}
    def table(key):
        records=data.get(key) or []
        if not isinstance(records,list) or any(not isinstance(r,dict) for r in records):
            raise ValueError('Studio 결과의 '+key+' 표 형식을 확인해주세요.')
        return records
    raw = {k:'' for k in ('공고명','공고유형','주최주관','접수방법','접수링크','접수마감','접수마감설명','활동기간')}
    raw.update({k:[] for k in ('지원조건','제출서류','일정','혜택','문의처','주의사항')})
    raw.update(공고명=value('공고명'), 공고유형=TYPES.get(data.get('_classification',''), '기타'),
               주최주관=value('문의처_운영기관명'), 접수방법=value('지원방법'), 접수링크=value('지원링크'),
               접수마감=value('모집기간_종료일'))
    # Program names and contact organizations have different meanings.
    if raw['주최주관']: raw['주최주관'] += ' (문의 운영기관 · 주최 여부 확인 필요)'
    raw['활동기간']=' ~ '.join(v for v in (value('활동기간_시작일'),value('활동기간_종료일')) if v)
    target=value('모집대상')
    if target:
        raw['지원조건'].append({'분류':'지원자격','조건':target,'적용대상':'전체',
            '적용단계':'지원단계','대조항목':'','비교방법':'검토',**quote(target)})
    for r in table('활동내용'):
        text=str(r.get('활동 내용') or '')
        if text:raw['지원조건'].append({'분류':'활동의무','조건':text,'적용단계':'선발 후·활동 중',**quote(text)})
    for r in table('선발단계'):
        raw['일정'].append({dst:str(r.get(src) or '') for dst,src in
            {'일정명':'단계명','시작':'시작일시','종료':'종료일시','설명':'진행방법'}.items()})
    # Recover a date only from an explicitly dated application line/window.
    # No deadline year may be borrowed from the program title.
    deadline=raw['접수마감']
    for page_no,page in enumerate(pages,1):
        lines=page.splitlines()
        for i,line in enumerate(lines):
            if not re.search(r'접수|신청|지원서|응모|모집기간|모집 기간',line):continue
            window='\n'.join(lines[i:i+3])
            if explicit_date(deadline,window):
                raw['접수마감설명']=window
                raw['일정'].append({'일정명':'접수 마감 근거','종료':deadline,'근거원문':window,'근거페이지':str(page_no)})
                break
        if raw['접수마감설명']:break
    contact=' · '.join(value(k) for k in ('문의처_운영기관명','문의처_운영시간',
        '문의처_카카오톡채널아이디','문의처_이메일','문의처_홈페이지') if value(k))
    if contact:raw['문의처'].append({'내용':contact})
    # This numeric field drops amount scope and can add unlike awards incorrectly.
    # Keep its value in the raw result, never present it as a verified benefit.
    if value('장학금_총액'):
        raw['혜택'].append({'내용':'금액·지급 대상·지급 단위를 원문의 혜택 또는 시상표에서 확인해주세요.','금액범위':'미확인'})
    raw['주의사항']=[{'내용':LIMIT,'근거원문':'','근거페이지':''}]
    raw['주의사항'] += [{'내용':c,'근거원문':'','근거페이지':''} for c in data.get('_extract_conflicts',[])]
    raw['_workflow_review']=data.get('_workflow_review','')
    raw['_studio_compact']=copy.deepcopy(data)
    raw['_schema_limits']=LIMIT
    return raw
