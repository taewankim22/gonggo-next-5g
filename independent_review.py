"""Independent, evidence-bound checks. Never copy a category verdict to its parts."""
import re
from core import evidence, fingerprint, normalize, numeric

def condition_rows(notice,answers,pages):
    from conditions import BASIC, BASIC_LABELS, missing, bind_answers
    from planning import question_keys,additional_questions,document_items
    links=answers.get('condition_answers')
    if links is None:
        keys=question_keys(notice,answers)
        qs,_,_=additional_questions(notice,keys,document_items(notice,pages),answers.get('review_stage','지원 검토 중'))
        links=bind_answers(notice,keys,qs,answers,answers.get('question_answers',{}))
    rows=[]
    for q in links:
        category=q.get('condition_id','unlinked');key=q.get('answer_key','');value=q.get('answer')
        if key=='review_stage':continue # workflow context, not an eligibility requirement
        quote=q.get('quote','');page=q.get('page','');verified=evidence(quote,page,pages)
        row=dict(id=q['id'],category=category,label=q['text'],rule=q.get('rule',''),answer=value,
                 status='확인 필요',reason='답변이 없습니다.',quote=quote,page=page,verified=verified,
                 stage=answers.get('review_stage') or '지원 검토 중',basis='미입력',action='이 조건의 답변을 확인하세요.')
        if not missing(value):
            row.update(reason='답변은 입력됐습니다. 자유서술 조건은 원문과 개별 대조가 필요합니다.',basis='답변 입력 · 개별 판단 미확정',action='원문과 답변을 대조하세요. 아래 AI 범주 검토도 참고할 수 있습니다.')
        if category=='unlinked':
            row.update(reason='질문이 어느 원문 조건에 속하는지 확인하지 못했습니다.',basis='연결 미확정')
        if not verified:
            row.update(reason='판정에 필요한 원문 인용과 페이지를 확인하지 못했습니다.',basis='근거 미확인')
        if verified and not missing(value):
            number_specs={'remaining_terms':('minimum_remaining_terms',r'잔여\s*학기[^\n。]{0,35}?(\d+)\s*학기\s*이상','잔여학기'),
                          'weekly_visits':('minimum_weekly_visits',r'주\s*(\d+)\s*회','방문 횟수'),
                          'weekly_hours':('minimum_weekly_hours',r'(?:주|총)\s*(\d+)\s*시간','활동 시간')}
            if key in number_specs:
                field,pattern,label=number_specs[key];required=numeric(notice.get(field));actual=numeric(value)
                found=[numeric(x) for x in re.findall(pattern,quote)]
                if required is not None and actual is not None and required in found:
                    row.update(status='불일치' if actual<required else '일치',reason=f'{label}: 공고 최소 {required:g}, 내 답변 {actual:g}.',basis='원문 수치 대조',action='이 조건을 충족할 수 있는지 먼저 확인하세요.' if actual<required else '다른 조건의 결과도 각각 확인하세요.')
            elif key=='enrollment_status':
                allowed=notice.get('allowed_statuses',[])
                if str(value) in ('수료','졸업') and re.search(re.escape(str(value))+r'(?:생|예정자)?[^\n]{0,8}(?:지원\s*)?(?:불가|불허)',quote):
                    row.update(status='불일치',reason='내 학적이 원문에서 지원 불가로 명시된 상태입니다.',basis='명시된 학적 대조')
                elif str(value) in ('재학','휴학') and any(str(value) in s for s in allowed) and str(value) in quote:
                    row.update(status='일치',reason='학적 항목만 공고와 일치합니다. 지역·잔여학기 등은 별도입니다.',basis='명시된 학적 대조')
            elif key=='long_term' and notice.get('activity_period') and str(value) in ('가능','어려움'):
                row.update(status='불일치' if value=='어려움' else '일치',reason='전체 활동 기간 참여 '+str(value)+'(본인 답변).',basis='기간 참여 자기 확인')
        rows.append(row)
    for item in answers.get('document_checklist',[]):
        later=item.get('later',False);unknown=item.get('stage')=='시점 확인 필요'
        applicable=item.get('applicability');ready=item.get('readiness');verified=bool(item.get('source_found'))
        status='이후 단계' if later else '확인 필요'
        reason='현재 준비할 서류가 아닙니다. 해당 단계에서 다시 확인하세요.' if later else '준비 여부 또는 적용 대상을 확인하세요.'
        if not later and not unknown and verified:
            if applicable=='해당 없음' and item.get('category')!='필수':status,reason='해당 없음','본인이 적용 대상이 아니라고 답했습니다.'
            elif applicable=='해당' and ready in ('준비 완료','제출 완료'):status,reason='일치','준비 완료라는 본인 확인입니다. 서류 내용·진위 검증은 아닙니다.'
        if unknown:reason=item.get('stage_reason','제출 시점을 원문에서 확인하세요.')
        rows.append(dict(id='doc_'+item['id'],category='documents',label=item['name'],rule=item['text'],
                         answer=f'{applicable} / {ready}',status=status,reason=reason,quote=item.get('source_quote',''),
                         page=item.get('source_page',''),verified=verified,stage=item.get('stage'),basis='제출 시점·자기 확인',
                         action='해당 단계에서 확인하세요.' if later else '시점과 적용 대상부터 확인하세요.' if unknown else '이 서류의 준비 상태를 확인하세요.',
                         stage_quote=item.get('stage_quote',''),stage_page=item.get('stage_page',''),optional=item.get('category')=='선택'))
    return rows

def apply_independent_checks(cards,rows):
    for card in cards:
        parts=[r for r in rows if r['category']==card['key']]
        card['condition_rows']=parts
        conflicts=[r for r in parts if r['status']=='불일치' and r['verified']]
        unknown=[r for r in parts if r['status']=='확인 필요']
        if conflicts:
            card.update(status='불일치',reason=' / '.join(r['reason'] for r in conflicts)+(f' 별도로 확인할 조건 {len(unknown)}개가 있습니다.' if unknown else ''),
                        action='확인된 불일치: '+' / '.join(r['label'] for r in conflicts)+' — 미입력과 별도로 먼저 확인하세요.')
    return cards
