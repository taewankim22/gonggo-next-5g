"""Keep routed Korean facts intact while supporting existing personal review screens."""
import json
import re
from schema_builder import notice_schema, CATEGORIES

CATEGORY={'지원자격':'eligibility','우대':'preference','활동의무':'commitment','출품작제한':'documents'}
FIELDS={'학교':'school','캠퍼스':'campus','학적':'enrollment_status','전공':'major','대학유형':'college_type',
        '대학지역':'region','잔여학기':'remaining_terms','성적':'gpa','소득구간':'income_band',
        '사회적배려':'social_support','국적':'nationality','나이':'age'}
STAGES=('지원단계','선발 후·활동 중','활동 종료 후','시점 확인 필요')

def rows(data,key):
    value=data.get(key,[])
    if not isinstance(value,list) or any(not isinstance(v,dict) or any(not isinstance(x,str) for x in v.values()) for v in value):
        raise ValueError('분석 결과의 '+key+' 표 형식을 확인해주세요.')
    return value

def scoped(row,text='조건',stage='적용단계'):
    return ' · '.join(x for x in (row.get(stage),row.get('적용대상'),row.get(text),row.get('예외')) if x)

def adapt_notice(data):
    from studio_latest import is_compact, normalize_compact
    if is_compact(data):data=normalize_compact(data)
    for key in ('공고명','공고유형','주최주관','접수방법','접수링크','접수마감','접수마감설명','활동기간'):
        if not isinstance(data.get(key),str):raise ValueError('분석 결과의 '+key+' 형식을 확인해주세요.')
    tables={key:rows(data,key) for key in ('지원조건','제출서류','일정','혜택','문의처','주의사항')}
    n={k:[] if v['type']=='array' else '' for k,v in notice_schema()['properties'].items()}
    for dst,src in {'notice_title':'공고명','notice_type':'공고유형','organizer':'주최주관','application_deadline':'접수마감',
                    'deadline_note':'접수마감설명','activity_period':'활동기간'}.items():n[dst]=data[src]
    n['submission_method']=' · '.join(dict.fromkeys(v for v in (data['접수방법'],data['접수링크']) if v))
    n['_structured_notice']={k:v for k,v in data.items() if not k.startswith('_')}
    n['_workflow_review']=str(data.get('_workflow_review',''))
    n['_basic_evidence']={}
    for meta in ('_studio_compact','_schema_limits'):
        if meta in data:n[meta]=data[meta]
    groups={key:[] for key in CATEGORIES}
    profiles=[]
    for row in tables['지원조건']:
        category=CATEGORY.get(row.get('분류'))
        if not category:continue
        groups[category].append((scoped(row),row))
        field=FIELDS.get(row.get('대조항목'))
        if field and category in ('eligibility','preference') and row.get('적용단계')=='지원단계':
            scope=row.get('적용대상','')
            scope='' if scope in ('전체','모든 지원자','지원자 전체') else scope
            complex_rule=bool(row.get('예외') or scope or row.get('비교방법')=='검토')
            value=row.get('기준값','')
            if field in ('remaining_terms','gpa','income_band','age') and re.fullmatch(r'\d+(?:\.\d+)?\s*(?:학기|점|구간|세)?',value):value=re.match(r'\d+(?:\.\d+)?',value)[0]
            profiles.append({'field':field,'category':category,'rule':scoped(row),'quote':row.get('근거원문',''),
                'page':row.get('근거페이지',''),'operator':{'같음':'eq','이상':'gte','이하':'lte'}.get(row.get('비교방법'),'review'),
                'value':value,'period':row.get('기준시점',''),'scale':row.get('만점',''),
                'logic':'complex' if complex_rule else 'single','scope':scope})
        # Fixed numeric questions only when the actual quoted text carries the threshold.
        quote=row.get('근거원문',''); compact=re.sub(r'\s+','',quote)
        matches={}
        if row.get('적용단계')=='지원단계' and category=='eligibility':
            m=re.search(r'잔여학기[^\d]{0,12}(\d+)학기(?:이상)?',compact)
            if m:matches['remaining_terms']=m[1]
            if '학적' in row.get('대조항목','') and not re.search(r'불가|제외|아니',row.get('조건','')):
                statuses=[v for v,word in [('재학','재학생'),('휴학','휴학생'),('수료','수료생'),('졸업','졸업생')] if word in quote and word in row.get('조건','')]
                n['allowed_statuses']=list(dict.fromkeys(n['allowed_statuses']+statuses))
                if statuses:n['_basic_evidence']['enrollment_status']=row
        if category=='commitment':
            for key,pattern in [('weekly_visits',r'주(?:당)?(\d+)회'),('weekly_hours',r'(?:주(?:당)?(?:\d+회)?,?(?:총)?|총)(\d+(?:\.\d+)?)시간')]:
                m=re.search(pattern,compact)
                if m:matches[key]=m[1]
        if category=='preference':
            scope=row.get('적용대상','')
            centers=re.findall(r"['‘’\"]([^'‘’\"]+(?:학교|센터))['‘’\"]",scope)
            if not centers:centers=[v for v in re.findall(r'[가-힣A-Za-z0-9]+(?:학교|센터)',scope) if v not in ('학교','학습센터','활동센터')]
            if len(set(centers))==1 and centers[0] in row.get('근거원문',''):
                n['preference_center']=centers[0];n['preference_skill']=row.get('조건','')
                n['_basic_evidence']['skills']=row;n['_basic_evidence']['selected_center']=row
        for key,value in matches.items():
            n['minimum_'+key]=value;n['_basic_evidence'][key]=row
    for row in tables['제출서류']:
        text=' · '.join(row.get(k,'') for k in ('필수여부','서류명','적용대상','제출단계','제출설명') if row.get(k))
        n['required_documents'].append(text);groups['documents'].append((text,row))
    for row in tables['일정']:
        text=' · '.join(row.get(k,'') for k in ('일정명','시작','종료','장소','확정상태','설명') if row.get(k))
        groups['schedule'].append((text,row))
    for key,items in groups.items():
        n[key+'_rule']='\n'.join(text for text,row in items)
        n[key+'_presence']='명시' if items else '미기재'
        if items:
            representative=next((row for text,row in items if row.get('적용단계',row.get('제출단계'))=='지원단계'),items[0][1])
            n[key+'_quote']=representative.get('근거원문','');n[key+'_page']=representative.get('근거페이지','')
    n['benefits']='\n'.join(' · '.join(dict.fromkeys(row.get(k,'') for k in ('혜택명','내용','지급인원','금액표현','금액범위','대상','지급단계','조건') if row.get(k))) for row in tables['혜택'])
    n['contact_information']='\n'.join(' · '.join(row.values()) for row in tables['문의처'])
    n['source_conflicts']=[f"{r.get('내용','')} ({r.get('근거페이지','미확인')}쪽)" for r in tables['주의사항']]
    n['profile_conditions_json']=json.dumps(profiles,ensure_ascii=False)
    return n

def ground_notice(notice,pages):
    """Relocate only verbatim quotes with exactly one matching source page."""
    if not notice.get('_structured_notice'):return notice
    import copy
    from core import evidence
    if notice.get('_studio_compact'):
        from studio_latest import normalize_compact
        raw=normalize_compact(notice['_studio_compact'],pages)
    else:
        raw=copy.deepcopy(notice['_structured_notice'])
    for row in raw.get('지원조건',[]):
        from notice_facts import exclusion_context
        row.update(exclusion_context(row,pages))
        # A language skill or interest area is not the applicant's degree major.
        if row.get('대조항목')=='전공' and not re.search(r'전공|학과|major|department',row.get('근거원문',''),re.I):
            row.update(대조항목='',비교방법='검토',기준값='')
        # A quoted number is not enough: total/enrolled terms are not remaining terms.
        # Preserve the full rule as a question, but don't compare it to the user's
        # remaining_terms profile unless that specific concept is in the source.
        if row.get('대조항목')=='잔여학기' and not re.search(r'잔여\s*학기|남은\s*학기|remaining\s+(?:\w+\s+){0,2}(?:semester|term)',row.get('근거원문',''),re.I):
            row.update(대조항목='',비교방법='검토',기준값='')
        if row.get('대조항목')=='성적':
            quote=row.get('근거원문','');value=row.get('기준값','').strip();scale=row.get('만점','').strip()
            # Earned credits and GPA are different quantities. Never compare 18
            # credits against a GPA of 4.0 simply because both came from one line.
            if value and re.search(re.escape(value)+r'\s*(?:학점|credits?)',quote,re.I) and not re.search(r'(?:평점|GPA)\s*(?:of\s*)?'+re.escape(value)+r'(?![\d.])',quote,re.I):
                row.update(대조항목='',비교방법='검토',기준값='',만점='')
            elif scale and not re.search(re.escape(scale)+r'\s*(?:점\s*)?(?:만점|scale)|(?:만점|out of|/)\s*'+re.escape(scale),quote,re.I):
                # A maximum score is not implied just by seeing that score earned.
                row['만점']=''
            if re.search(r'(?:이전|직전)\s*\d+\s*개?\s*학기|\d+\s*개?\s*학기.*(?:평균|각\s*평점)|previous\s+(?:two|three|\d+)\s+(?:semester|term)',row.get('조건',''),re.I):
                row.update(비교방법='검토',기준시점='')
    for key in ('지원조건','제출서류','일정','혜택','주의사항','기본정보근거'):
        for row in raw.get(key,[]):
            from notice_facts import relocate
            row.update(relocate(row,pages))
            quote=row.get('근거원문','');old=row.get('근거페이지','')
            if evidence(quote,old,pages):continue
            candidates=[str(i) for i in range(1,len(pages)+1) if evidence(quote,str(i),pages)]
            if len(candidates)==1:row['근거페이지']=candidates[0]
    for row in raw.get('혜택',[]):
        # Do not present a per-person/team payment when the quoted table is not grounded.
        if row.get('금액범위') in ('개인당','팀당') and not evidence(row.get('근거원문',''),row.get('근거페이지',''),pages):
            row['금액범위']='미확인'
            suffix=' (원문 표의 금액·지급 단위 확인 필요)'
            if not row.get('내용','').endswith(suffix):row['내용']=row.get('내용','')+suffix
    from deadline_guard import guard_deadline
    guard_deadline(raw,pages)
    raw['_workflow_review']=notice.get('_workflow_review','')
    result=adapt_notice(raw)
    from notice_facts import benefit_rows
    result['benefits']='\n'.join(dict.fromkeys(r['display'] for r in benefit_rows(result,pages) if r['verified']))
    return result

def structured_documents(notice,pages):
    from core import fingerprint,evidence,normalize
    from source_context import locate_document,UNKNOWN,FUTURE,AFTER
    result=[];seen=set()
    for row in notice['_structured_notice'].get('제출서류',[]):
        name=row.get('서류명','').strip()
        if not name:continue
        if re.fullmatch(r'(?:(?:필수|선택|제출|관련)서류|서류)(?:\s*(?:및|등|,|·)\s*(?:(?:필수|선택|제출|관련)서류|서류))*',name):continue
        ident=fingerprint([name,row.get('제출단계'),row.get('적용대상')])[:12]
        if ident in seen:continue
        seen.add(ident)
        text=' · '.join(row.get(k,'') for k in ('서류명','적용대상','제출설명') if row.get(k))
        quote,page=row.get('근거원문',''),row.get('근거페이지','')
        located=locate_document(name,text,pages)
        stage=row.get('제출단계')
        stage=stage if stage in STAGES else UNKNOWN
        # A source heading can move an item later; never promote an unverified stage.
        if located['stage'] in (FUTURE,AFTER):stage=located['stage']
        verified=evidence(quote,page,pages) and normalize(name) in normalize(quote)
        if not verified:stage=located['stage'] if located['source_found'] else UNKNOWN
        category=row.get('필수여부')
        if category not in ('필수','해당자만','선택'):category='대상·필수 여부 확인'
        description=row.get('제출설명','')
        description_verified=verified and bool(description) and normalize(description) in normalize(quote)
        text=' · '.join(v for v in (name,row.get('적용대상',''),description if description_verified else '') if v)
        result.append({'id':ident,'text':text,'name':name,'category':category,'stage':stage,
            'target':row.get('적용대상',''),'requirements':description if description_verified else '',
            'requirements_candidate':description,'category_verified':verified,'requirement_verified':description_verified,
            'source_page':page if verified else located['source_page'],'source_quote':quote if verified else located['source_quote'],
            'stage_quote':located.get('stage_quote','') or quote,'stage_page':located.get('stage_page','') or page,
            'source_found':verified or located['source_found'],'stage_reason':'원문 근거와 제출 단계 확인' if verified else located.get('stage_reason','원문 확인 필요')})
    return result

def structured_questions(notice,stage):
    from conditions import link_question,SOCIAL_QUESTION,LABELS
    active=[];later=[];seen=set()
    for row in notice['_structured_notice'].get('지원조건',[]):
        category=CATEGORY.get(row.get('분류'))
        if not category or not row.get('조건'):continue
        # Profiles already render questions for their linked current conditions.
        if row.get('대조항목') in FIELDS and row.get('비교방법') in ('같음','이상','이하') and not row.get('예외') and row.get('적용단계')=='지원단계' and category in ('eligibility','preference'):continue
        # The same quoted sentence may be extracted for several profile fields.
        # Ask an identical scoped question once, but preserve different targets
        # and stages in both the widget identity and the answer mapping.
        text=LABELS[category]+' · '+scoped(row)+' — 해당 조건을 충족하거나 이행할 수 있나요?'
        q=link_question(notice,text,category)
        if q['id'] in seen:continue
        seen.add(q['id'])
        q.update(rule=scoped(row),quote=row.get('근거원문',''),page=row.get('근거페이지',''),context=scoped(row),
                 source_condition=dict(row))
        if (row.get('적용단계')=='선발 후·활동 중' and stage not in ('선발 후·활동 중','활동 종료 후')) or (row.get('적용단계')=='활동 종료 후' and stage!='활동 종료 후'):later.append(q)
        else:active.append(q)
    if '사회적' in notice.get('preference_rule',''):
        q=link_question(notice,SOCIAL_QUESTION,'preference','social_support')
        source=next((r for r in notice['_structured_notice']['지원조건'] if r.get('대조항목')=='사회적배려'),{})
        if source:q.update(rule=scoped(source),context=scoped(source),quote=source.get('근거원문',''),page=source.get('근거페이지',''),source_condition=dict(source))
        active.append(q)
    return active,later,[]
