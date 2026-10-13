"""Private profile facts and conservative, source-backed atomic comparisons."""
import json
import re
from core import fingerprint, evidence, normalize

LABELS = {'school':'학교','campus':'캠퍼스','enrollment_status':'학적','major':'전공',
 'interests':'관심 분야','college_type':'대학 유형','region':'대학 소재지역',
 'remaining_terms':'잔여학기','gpa':'성적','income_band':'학자금 지원구간',
 'social_support':'사회적 배려 대상','nationality':'국적','age':'만 나이'}
TIMED = {'enrollment_status','remaining_terms','gpa','income_band','age'}
OPTIONS = {'enrollment_status':['재학','휴학','수료','졸업'],
 'college_type':['4년제','전문대','대학원','기타'], 'social_support':['해당','해당 없음']}
NUMERIC = {'remaining_terms','gpa','income_band','age'}
RULE_VERSION='profile-v1'

def clean_profile(profile):
    if not isinstance(profile,dict):return {}
    out={}
    for key in LABELS:
        f=profile.get(key)
        if not isinstance(f,dict) or f.get('state') not in ('known','unknown','unset'):continue
        v=f.get('value')
        if v is not None and not isinstance(v,(str,int,float)):continue
        out[key]={'state':f['state'],'value':v if f['state']=='known' else None,
                  'period':str(f.get('period',''))[:80],'scale':str(f.get('scale',''))[:20]}
    return out

def atomic_conditions(notice):
    raw=notice.get('profile_conditions_json','')
    try:items=json.loads(raw) if isinstance(raw,str) and raw else []
    except (ValueError,TypeError):items=[]
    if not isinstance(items,list):items=[]
    out=[]
    for item in items[:40]:
        if not isinstance(item,dict) or item.get('field') not in LABELS:continue
        c={k:str(item.get(k,''))[:2000] for k in ('field','rule','quote','page','operator','value','period','scale','logic','scope')}
        c['quote']=re.sub(r'<br\s*/?>','\n',c['quote'],flags=re.I)
        c['category']='preference' if item.get('category')=='preference' else 'eligibility'
        c['id']=fingerprint(c)[:12];out.append(c)
    return out

def profile_fact(profile,key,period=''):
    f=clean_profile(profile).get(key,{})
    if f.get('state')!='known':return None,'미입력' if f.get('state')!='unknown' else '프로필에서 모름'
    if key in TIMED and (not period or normalize(f.get('period',''))!=normalize(period)):
        return None,'기준 시점 확인 필요'
    return f.get('value'),'공통 프로필'

def applied_facts(notice,profile,overrides,base_answers=None,provenance=None):
    out={}
    for c in atomic_conditions(notice):
        key=c['field'];override=overrides.get(c['id'])
        if key in ('enrollment_status','remaining_terms') and base_answers is not None and key in base_answers:
            value=base_answers[key];origin=(provenance or {}).get(key,'이번 공고 답변');scale=''
        elif isinstance(override,dict):
            value=override.get('value') if override.get('state')=='known' else None
            origin='이번 공고 답변' if value is not None else '이번 공고에서 모름'
            scale=override.get('scale','')
        else:
            value,origin=profile_fact(profile,key,c['period']);scale=profile.get(key,{}).get('scale','')
        out[c['id']]={'value':value,'origin':origin,'field':key,'scale':scale,'period':c['period']}
    return out

def profile_rows(notice,answers,pages):
    rows=[]
    for c in atomic_conditions(notice):
        f=answers.get('profile_facts',{}).get(c['id'],{})
        value=f.get('value');verified=evidence(c['quote'],c['page'],pages)
        if not verified and c['field'] in NUMERIC and len(normalize(c['quote']))>=5:
            try:verified=1<=int(c['page'])<=len(pages) and normalize(c['quote']) in normalize(pages[int(c['page'])-1])
            except (ValueError,TypeError):pass
        row=dict(id='profile_'+c['id'],category=c['category'],label=LABELS[c['field']],rule=c['rule'],
            answer=value,status='확인 필요',reason='미입력',quote=c['quote'],page=c['page'],verified=verified,
            stage='조건 검토',basis=f.get('origin','미입력'),action='원문 조건과 기준 시점을 확인하세요.')
        row['reason']='원문 근거 확인 필요' if not verified else f.get('origin','미입력') if value is None else '문장 의미·예외·적용 대상 확인 필요'
        # Never flatten OR / exceptions / scoped preferences into a global rejection.
        comparable=verified and value is not None and c['logic']=='single' and not c['scope']
        if comparable:
            result=None;op=c['operator'];q=normalize(c['quote']);expected=c['value']
            if op in ('gte','lte') and c['field'] in NUMERIC:
                try:
                    threshold=float(expected);actual=float(value)
                    threshold_text=re.escape(format(threshold,'g'))
                    sign='이상' if op=='gte' else '이하'
                    grounded=bool(re.search(threshold_text+r'(?:점|학기|세|구간)?'+sign,q))
                    same_scale=c['field']!='gpa' or (c['scale'] and str(f.get('scale'))==c['scale'] and c['scale'] in c['quote'])
                    if grounded and same_scale:result=actual>=threshold if op=='gte' else actual<=threshold
                except (TypeError,ValueError):pass
            elif op=='eq' and expected and normalize(expected) in q and c['field'] in ('college_type','nationality','school'):
                def canonical(v):
                    v=normalize(str(v))
                    if c['field']=='college_type':return {'4년제대학교':'4년제','4년제대학':'4년제','전문대학교':'전문대','전문대학':'전문대'}.get(v,v)
                    if c['field']=='nationality':return {'대한민국국민':'대한민국','대한민국국적':'대한민국','한국':'대한민국'}.get(v,v)
                    return v
                result=canonical(value)==canonical(expected)
            if result is not None:
                row.update(status='일치' if result else '불일치',reason='원문 단일 조건과 '+f.get('origin','답변')+'을 대조했습니다.',action='증빙과 나머지 조건을 확인하세요.' if result else '이 조건의 예외 또는 대상을 운영기관에 확인하세요.')
        rows.append(row)
    return rows
