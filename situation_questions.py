"""Display model for notice-specific questions. No network calls or verdict generation."""
import re
from conditions import BASIC, BASIC_LABELS, link_question, missing
from planning import question_keys, additional_questions, document_items
from profiles import atomic_conditions, LABELS, NUMERIC, OPTIONS

GROUPS = ('지원 조건','우대 조건','참여 일정·활동 의무','추가 확인')
GROUP = {'eligibility':GROUPS[0],'preference':GROUPS[1], 'commitment':GROUPS[2],
         'schedule':GROUPS[2], 'documents':GROUPS[3], 'unlinked':GROUPS[3]}
UNITS = {'remaining_terms':'학기','weekly_visits':'회 / 주','weekly_hours':'시간 / 주',
         'age':'만 나이','income_band':'구간','gpa':'점'}
TITLES = {'enrollment_status':'공고 기준일의 학적','remaining_terms':'공고 기준일의 잔여학기',
          'selected_center':'희망 활동 기관','skills':'관련 경험이나 역량을 알려주세요',
          'weekly_visits':'일주일에 몇 번 참여할 수 있나요?',
          'weekly_hours':'일주일에 몇 시간 참여할 수 있나요?',
          'long_term':'안내된 활동 기간에 참여할 수 있나요?',
          'unavailable_dates':'참석하기 어려운 일정이 있나요?'}


def future(stage, current):
    return ((stage=='선발 후·활동 중' and current not in ('선발 후·활동 중','활동 종료 후'))
            or (stage=='활동 종료 후' and current!='활동 종료 후'))


def short_rule(rule):
    """Remove display prefixes only; never truncate exceptions or alternatives."""
    return re.sub(r'^(?:지원단계|선발 후·활동 중|활동 종료 후|시점 확인 필요)\s*·\s*(?:전체\s*·\s*)?', '', rule)


def extra_title(q):
    row=q.get('source_condition',{}); rule=row.get('조건') or q.get('rule','')
    if q['kind']=='social_support':return '사회적 배려 우대 대상인가요?'
    if not row:return q['text']
    if re.search(r'불가|제외|제한|않아야',rule):return '이 제한 조건과 관련된 상황을 알려주세요'
    if '팀' in rule:return '팀 구성·참가 조건을 확인해주세요'
    if q['condition_id']=='commitment':return '활동 조건에 대해 알려주세요'
    if q['condition_id']=='preference':return '이 우대 조건과 관련된 경험이 있나요?'
    return '이 지원 조건에 대해 알려주세요'


def build_questionnaire(notice, pages, answers, stage):
    keys=question_keys(notice,answers)
    extra,later,covered=additional_questions(notice,keys,document_items(notice,pages),stage)
    conditions=atomic_conditions(notice)
    current=[]; deferred=[]
    for key in keys:
        if key=='review_stage':continue
        source=notice.get('_basic_evidence',{}).get(key,{})
        related=[c for c in conditions if c['field']==key]
        record=link_question(notice,BASIC_LABELS[key],BASIC[key])
        if source:record.update(rule=source.get('조건',''),quote=source.get('근거원문',''),page=source.get('근거페이지',''))
        if key=='long_term':record['rule']=notice.get('activity_period','')
        q=dict(id='basic_'+key,kind='basic',key=key,category=BASIC[key],title=TITLES[key],
               rule=record['rule'],quote=record['quote'],page=record['page'],related=related,
               stage=source.get('적용단계','지원단계'),unit=UNITS.get(key,''),period=' / '.join(dict.fromkeys(c['period'] for c in related if c['period'])),
               input_type='number' if key in UNITS else 'choice' if key in ('enrollment_status','long_term','unavailable_dates') else 'text')
        if key=='unavailable_dates':
            events=[r for r in notice.get('_structured_notice',{}).get('일정',[]) if re.search(r'면접|사전교육|발대식|참석|출석|오리엔테이션|설명회|대면|현장',r.get('일정명',''))]
            q['display_rule']='\n'.join(' · '.join(r.get(k,'') for k in ('일정명','시작','종료','장소') if r.get(k)) for r in events) or '참석 일정은 아래 공고 근거에서 확인해주세요.'
        # Feasibility is useful before selection; completing later paperwork is not.
        if future(q['stage'],stage) and key in ('weekly_visits','weekly_hours'):
            q['title']='선발되면 '+q['title']
        current.append(q)
    basic_fields={q['key'] for q in current+deferred}
    for c in conditions:
        if c['field'] in basic_fields or (c['field']=='social_support' and any(q['kind']=='social_support' for q in extra)):continue
        current.append(dict(id='profile_'+c['id'],kind='profile',key=c['field'],category=c['category'],
            title=LABELS[c['field']],rule=c['rule'],quote=c['quote'],page=c['page'],period=c['period'],unit=UNITS.get(c['field'],''),
            stage='지원단계',condition=c,input_type='number' if c['field'] in NUMERIC else 'choice' if c['field'] in OPTIONS else 'text'))
    for q in extra+later:
        # A typed profile fact already asks this exact rule. Keep the existing
        # narrative answer as an optional companion, never infer a whole-rule yes.
        companion=next((v for v in current if v['kind']=='profile' and v['rule']==q['rule']),None)
        if companion and q['kind']!='social_support':
            companion.setdefault('companions',[]).append(q)
            continue
        row=q.get('source_condition',{})
        simple_membership=not row.get('예외') and bool(re.fullmatch(r'(?:교육\(수료\)생|재학생|휴학생|수료생|졸업생)',row.get('조건','')))
        model=dict(id=q['id'],kind='extra',category=q['condition_id'],title='공고의 대상에 해당하나요?' if simple_membership else extra_title(q),
                   rule=q['rule'],quote=q['quote'],page=q['page'],period=row.get('기준시점',''),unit='',
                   stage=row.get('적용단계','지원단계'),question=q,input_type='choice' if q['kind']=='social_support' or simple_membership else 'text')
        (deferred if q in later else current).append(model)
    for q in current+deferred:q['group']=GROUP.get(q['category'],GROUPS[3])
    return dict(current=current,later=deferred,keys=keys,extras=extra,later_extras=later,covered=covered)


def response_state(value, explicit=False):
    if not missing(value):return 'known'
    return 'unknown' if explicit else 'unset'


def progress(records):
    return sum(r['state']!='unset' for r in records),len(records)
