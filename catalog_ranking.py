"""Explainable local prioritization, never a probability of eligibility."""
import re
from catalog import available_record, card_review, status_label
from core import normalize
from live_catalog import LiveCatalog
from profiles import clean_profile


def priority(record, review, profile, today=None):
    rows=review['rows']
    eligibility=[r for r in rows if r.get('category')=='eligibility' and r.get('verified')]
    preferences=[r for r in rows if r.get('category')=='preference' and r.get('verified')]
    conflict=any(r['status']=='불일치' for r in eligibility)
    matched=any(r['status']=='일치' for r in eligibility)
    preferred=any(r['status']=='일치' for r in preferences)
    fact=clean_profile(profile).get('interests',{})
    words=re.split(r'[,，/;\n]+',str(fact.get('value') or '')) if fact.get('state')=='known' else []
    text=normalize(record['title']+' '+' '.join(str(x) for x in record.get('tags',[])))
    interest=any(len(normalize(w))>=2 and normalize(w) in text for w in words)
    from deadline_calendar import group_status
    expired=(group_status(record['_calendar'],today)=='마감' if '_calendar' in record
             else status_label(record,today)=='과거 검증 사례')
    label='자격 불일치 확인' if conflict else '조건 일부 일치' if matched else '확인 필요'
    reasons=[]
    if expired:reasons.append('마감일이 지난 공고')
    if conflict:reasons.append('확인된 자격 불일치가 있어 뒤에 표시')
    elif matched:reasons.append('원문과 일치한 지원 자격이 있어 우선 표시')
    else:reasons.append('지원 자격을 확정할 정보가 부족함')
    if preferred:reasons.append('일치한 우대 조건 있음')
    if interest:reasons.append('제목·분류에 관심 분야 키워드 포함')
    # Unknown counts, document readiness and preference conflicts are NOT an
    # eligibility rejection. No private values are written into the catalogue.
    key=(expired,conflict,not matched,not preferred,not interest,
         status_label(record,today)=='접수 상태 확인 필요',record.get('deadline') or '9999-12-31',record['title'])
    return dict(key=key,label=label,reasons=reasons)


def personalized_catalog(root, records, profile, today=None):
    from national_search import aggregator,RESULT_NOTICE,NON_RECRUITMENT
    scans=LiveCatalog(root).scans();groups={}
    for record in records:
        # Apply source rules to legacy analyses too. Keep their stored evidence
        # and discovery candidates, but do not present press/list pages as a
        # recruitment announcement that a student can apply to.
        if (record.get('storage')=='live' and (aggregator(record['source_url'])
                or RESULT_NOTICE.search(record['title']) or NON_RECRUITMENT.search(record['title']))):continue
        groups.setdefault(record['source_url'],[]).append(record)
    out=[]
    for url,documents in groups.items():
        scan=scans.get(url)
        valid=[];cautions=[]
        if scan:
            cautions.extend(scan['warnings'])
            for doc in scan['documents']:
                match=next((r for r in documents if r.get('document_url')==doc['url'] and r.get('sha256')==doc['sha256'] and r.get('config')==scan['config']),None)
                if match and available_record(root,match):valid.append(match)
                else:cautions.append(doc['name']+' · 확인 필요 (분석 미완료)')
        else:
            valid=[r for r in documents if available_record(root,r)]
            if any(r.get('attachment_count') or r.get('warnings') for r in documents):
                cautions.append('첨부 전체의 분석 완료 여부를 확인해주세요. 최신 공고 찾기로 갱신할 수 있습니다.')
        if not valid:
            # Preserve the old card for transparency, but never rank stale facts.
            representative=dict(documents[0]);review={'rows':[],'matches':[],'unknowns':[],'conflicts':[]}
            cautions.append('최신 원문 분석을 완료하지 못해 조건 우선순위에서 제외했습니다.')
        else:
            representative=dict(next((r for r in valid if r.get('document_url')==url),valid[0]))
            rows=[]
            for r in valid:
                rows.extend({**row,'document_name':r.get('document_name',r['title']),'record_id':r['id']}
                            for row in card_review(root,r,profile)['rows'])
            review={key:[r for r in rows if r['status']==status] for key,status in
                    [('matches','일치'),('unknowns','확인 필요'),('conflicts','불일치')]}
            review['rows']=rows
            dates={r['deadline'] for r in valid if r.get('deadline')}
            if len(dates)>1:
                representative['deadline']='';cautions.append('문서 간 마감일이 다릅니다. 적용되는 접수 일정을 원문에서 확인해주세요.')
            elif dates:representative['deadline']=next(iter(dates))
        from deadline_calendar import group_deadlines
        representative['_calendar']=group_deadlines(root,valid,scan)
        order=priority(representative,review,profile,today)
        if not valid:order.update(label='분석 확인 필요',key=(True,True,True,True,True,True,'9999-12-31',representative['title']))
        out.append(dict(record=representative,documents=valid,result=review,priority=order,cautions=cautions))
    # Collapse proven complete reposts only. A title alone, shared blank form or
    # overlapping attachment cannot establish that two notices are the same.
    unique=[];identical={}
    for group in out:
        record=group['record'];scan=scans.get(record['source_url'],{})
        signature=None
        if scan.get('complete') and group['documents'] and not group['cautions']:
            signature=(normalize(record['title']),tuple(sorted((r['sha256'],str(r.get('config'))) for r in group['documents'])))
        if signature and signature in identical:
            previous=identical[signature]
            previous.setdefault('source_aliases',[]).append(record['source_url'])
        else:
            unique.append(group)
            if signature:identical[signature]=group
    return sorted(unique,key=lambda x:x['priority']['key'])
