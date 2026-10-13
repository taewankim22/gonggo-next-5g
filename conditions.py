"""Explicit question-to-condition links; unknown never means not applicable."""
import re
from core import fingerprint, normalize, evidence

LABELS={'eligibility':'지원 자격','preference':'우대 조건','commitment':'활동 의무',
        'documents':'제출서류','schedule':'참석 일정','unlinked':'조건 연결 확인 필요'}
BASIC={'enrollment_status':'eligibility','remaining_terms':'eligibility',
       'selected_center':'preference','skills':'preference','weekly_visits':'commitment',
       'weekly_hours':'commitment','long_term':'commitment','review_stage':'documents',
       'unavailable_dates':'schedule'}
BASIC_LABELS={'enrollment_status':'공고 기준일의 학적','remaining_terms':'공고 기준일의 잔여학기',
              'selected_center':'희망 활동 기관','skills':'명시된 우대와 관련된 역량',
              'weekly_visits':'주당 방문 횟수','weekly_hours':'주당 활동 시간','long_term':'전체 활동 기간 참여',
              'review_stage':'현재 지원 단계','unavailable_dates':'참석 일정'}
SOCIAL_QUESTION='공고에 명시된 사회적 배려 대상에 해당하나요?'
UNKNOWN=(None,'','아직 모름','모르겠어요','아직 확인하지 않음')

def missing(value):
    return value in UNKNOWN or (isinstance(value,str) and not value.strip())

def has_social(notice):
    return '사회적배려' in normalize(notice.get('preference_rule',''))

def link_question(notice,text,category=None,kind='text'):
    if category is None:
        # Keep ambiguous questions unlinked instead of silently treating them as eligibility.
        patterns={'eligibility':r'지역|소재|4년제|이동|통학|학과 재학생|초과학기|수료|졸업|국적|외국인|나이|연령|재학|휴학|잔여학기',
                  'preference':r'사회적\s*배려|우대|전공|특기|중국어|한반도|역량',
                  'documents':r'증명서|서류|자료.*준비|제출.*준비',
                  'commitment':r'활동 의무|시간|방문|이행|콘텐츠|후속연구|협약|연구체계',
                  'schedule':r'면접|참석|일정|교육.*참여'}
        hits=[key for key,pattern in patterns.items() if re.search(pattern,text) and notice.get(key+'_rule')]
        category=hits[0] if len(hits)==1 else 'unlinked'
    return {'id':fingerprint(text)[:12],'text':text,'condition_id':category,
            'condition_label':LABELS[category],'kind':kind,
            'rule':notice.get(category+'_rule',''),'quote':notice.get(category+'_quote',''),
            'page':notice.get(category+'_page','')}

def bind_answers(notice,keys,questions,answers,qa):
    links=[]
    for key in keys:
        if key in BASIC:
            record=link_question(notice,BASIC_LABELS[key],BASIC[key]);record.update(answer_key=key,answer=answers.get(key))
            links.append(record)
    for q in questions:
        if q['text'] in qa:
            links.append({**q,'answer_key':'question_answers.'+q['id'],'answer':qa[q['text']]})
    return links

def social_answer(answers):
    return answers.get('preference_facts',{}).get('social_support')

def social_document(item):
    return '사회적배려' in normalize(item.get('text',''))

def social_card(notice,answers,pages):
    quote,page=notice.get('preference_quote',''),notice.get('preference_page','')
    verified=evidence(quote,page,pages) and '사회적배려' in normalize(quote)
    value=social_answer(answers)
    status='확인 필요'
    reason='사회적 배려 대상 여부를 아직 답하지 않았습니다. 증빙서류 준비 여부와 별도로 확인하세요.'
    action='3단계에서 대상 여부를 확인하세요. 모르면 확인 필요로 남겨두세요.'
    if not verified:
        reason='사회적 배려 우대의 원문 근거를 확인하지 못했습니다.'
        action='원문에서 우대 대상과 인정 증빙을 확인하세요.'
    elif value=='해당 없음':
        status='해당 없음';reason='본인이 사회적 배려 대상이 아니라고 답했습니다. 지원 자격 미달을 뜻하지 않습니다.'
        action='다른 우대 조건과 필수 제출서류를 확인하세요.'
    elif value=='해당':
        docs=[r for r in answers.get('document_checklist',[]) if social_document(r) and not r.get('later')]
        ready=bool(docs) and all(r.get('readiness') in ('준비 완료','제출 완료') and r.get('applicability')=='해당' and r.get('source_found') for r in docs)
        status='일치' if ready else '확인 필요'
        reason='우대 대상 여부: 해당(본인 답변). 증빙서류: '+('준비 완료(본인 확인).' if ready else '준비·제출 여부 확인 필요.')+' 실제 증빙 내용과 인정 여부는 확인하지 않았습니다.'
        action='원문에 맞는 증빙 종류·내용을 확인하세요.' if ready else '4단계에서 증빙서류 준비 상태와 제출 의사를 별도로 확인하세요. 미준비를 비대상으로 판단하지 않습니다.'
    return dict(key='social_preference',title='사회적 배려 우대 · 대상과 증빙',status=status,reason=reason,action=action,
                quote=quote,page=page,verified=verified,presence=notice.get('preference_presence','명시'),
                rule=notice.get('preference_rule',''),model_status=None,model_quote_changed=False,supporting_quotes=[])
