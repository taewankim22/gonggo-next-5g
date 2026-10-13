"""Source-grounded submission scope, including headings across Parse pages."""
import re
from core import normalize

CURRENT='지원 단계'
FUTURE='선발 후·활동 중'
AFTER='활동 종료 후'
UNKNOWN='시점 확인 필요'

def phase(text):
    if re.search(r'사후서류|활동\s*종료\s*후',text):return AFTER
    if re.search(r'후속\s*연구|협약|선발된|선정된|선정되었|사전\s*심사\s*통과',text):return FUTURE
    if re.search(r'사전서류|모집\s*개요|참가\s*방법|참가\s*신청|접수\s*방법|신청\s*방법|접수[·ㆍ/ ]?사전\s*심사|지원서.*제출|모집\s*페이지',text):return CURRENT
    return None

def source_lines(pages):
    """Only actual numbered headings change scope; a body cross-reference does not."""
    root=None;child=None;output=[]
    for p,page in enumerate(pages,1):
        for line in page.splitlines():
            s=re.sub(r'^\s*#{1,6}\s*','',line).strip()
            main=re.match(r'^(\d{1,2})\.\s*([^\d].{0,65})$',s)
            sub=re.match(r'^(?:\d{1,2}\)|[가-힣][.)])\s*(.{1,90})$',s)
            if main:
                root={'title':s,'page':str(p),'stage':phase(s)};child=None
            elif sub:
                child={'title':s,'page':str(p),'stage':phase(s)}
            # A later-stage main section owns its subsections (e.g. application for funding).
            owner=root if root and root['stage'] in (FUTURE,AFTER) else child if child and child['stage'] else root
            output.append({'page':str(p),'line':line,'scope':dict(owner) if owner else None})
    return output

def locate_document(name,raw,pages):
    lines=source_lines(pages)
    anchors=[]
    primary=re.split(r'\(| - | 등 | 제출| 작성|를 |을 ',name)[0].strip()
    primary=re.sub(r'^(?:공통|필수|사전서류|사후서류)[,\s:]*','',primary)
    if len(normalize(primary))>=3:anchors.append(primary)
    # Fallback noun phrases are evidence candidates, never proof of obligation.
    anchors += re.findall(r'[가-힣A-Za-z]+(?:\s+[가-힣A-Za-z]+)?\s*(?:신고증|채용확인서|입증자료|재무제표|증명서|보고서|제안서)',name)
    anchors += re.findall(r'(?:입증자료|결산재무제표|채용확인서)',name)
    anchors += sorted(re.findall(r'[가-힣]+(?:의향서|확인서|신청서|신고증)',name),key=len,reverse=True)
    matches=[];used=''
    for anchor in dict.fromkeys(anchors):
        needle=normalize(anchor)
        for idx,record in enumerate(lines):
            # A name may wrap over two lines. Keep real source text and its heading.
            block=record['line']
            if needle not in normalize(block) and idx+1<len(lines) and lines[idx+1]['page']==record['page']:
                following=lines[idx+1]['line']
                if needle in normalize(following):continue
                block+='\n'+following
            if needle and needle in normalize(block):
                matches.append({**record,'quote':block})
        if matches:used=anchor;break
    if not matches:
        return dict(source_found=False,source_page='',source_quote='',stage=UNKNOWN,
                    stage_quote='',stage_page='',stage_reason='서류 이름과 제출 시점을 원문에서 연결하지 못했습니다.')
    if ':' in raw:
        subject=normalize(raw.split(':',1)[0])
        scoped=[m for m in matches if subject and subject in normalize(m['quote'])]
        if scoped:matches=scoped
    candidates=[]
    for m in matches:
        scope=m['scope']
        stage=scope['stage'] if scope else None
        # Explicit timing on the matched line overrides a neutral/current section.
        local=phase(m['quote'])
        if stage not in (FUTURE,AFTER) and local:stage=local
        if not stage and phase(raw) and normalize(raw.split(':')[0]) in normalize(m['quote']):stage=phase(raw)
        candidates.append(stage or UNKNOWN)
    unique=set(candidates)
    stage=next(iter(unique)) if len(unique)==1 else UNKNOWN
    m=matches[0];scope=m['scope'] or {}
    return dict(source_found=True,source_page=m['page'],source_quote=m['quote'],source_anchor=used,
                stage=stage,stage_quote=scope.get('title','') if scope.get('stage') else m['quote'],stage_page=scope.get('page',m['page']) if scope.get('stage') else m['page'],
                stage_reason=('원문 상위 절과 서류 구간의 시점을 연결했습니다.' if stage!=UNKNOWN else
                              '원문에 서로 다른 시점이 있거나 제출 시점을 확정하지 못했습니다. 현재 필수 누락으로 계산하지 않습니다.'))
