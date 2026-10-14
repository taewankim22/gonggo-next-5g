"""Evidence validation and conservative review guards (no selection decision)."""
import hashlib
import io
import json
import re
import unicodedata
from pypdf import PdfReader
from schema_builder import CATEGORIES, QUESTION_KEYS

STATUSES = ('일치', '불일치', '확인 필요', '해당 없음')

def fingerprint(value):
    blob = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()

def read_pdf(data):
    if not data.startswith(b'%PDF-'):
        raise ValueError('PDF 파일을 선택해주세요.')
    if len(data) > 15 * 1024 * 1024:
        raise ValueError('15MB 이하 PDF를 사용해주세요.')
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError('암호가 없는 PDF가 필요합니다.')
        if not 1 <= len(reader.pages) <= 30:
            raise ValueError('1~30페이지 PDF를 사용해주세요.')
        return [p.extract_text() or '' for p in reader.pages]
    except ValueError:
        raise
    except Exception:
        raise ValueError('PDF를 읽을 수 없습니다. 파일이 손상되지 않았는지 확인해주세요.') from None

def normalize(text):
    # OCR often normalizes typographic quotes/arrows. Do not remove words or numbers.
    text = unicodedata.normalize('NFKC', text or '').translate(str.maketrans({'‘':"'",'’':"'",'“':'"','”':'"','➔':'→'}))
    return re.sub(r'\s+', '', text)

def evidence(quote, page, pages):
    try:
        n = int(page)
    except (TypeError, ValueError):
        return False
    def evidence_text(text):
        # Parse emits Markdown table separators; they are layout, not source words.
        text=re.sub(r'(?m)^\s*\|([^\n]+)\|\s*$',lambda m:m[1].replace('|',' '),text or '')
        return normalize(text)
    q = evidence_text(quote)
    return bool(len(q) >= 8 and 1 <= n <= len(pages) and q in evidence_text(pages[n - 1]))

def validate_payload(data, schema):
    if not isinstance(data, dict):
        raise ValueError('분석 결과가 JSON 객체가 아닙니다. 워크플로우 설정을 확인해주세요.')
    from studio_latest import is_compact
    if 'notice_title' in schema['properties'] and ('공고유형' in data or is_compact(data)):
        from workflow_adapter import adapt_notice
        data=adapt_notice(data)
    clean = {}
    for key, spec in schema['properties'].items():
        value = data.get(key)
        if spec['type'] == 'array':
            if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
                raise ValueError(f'결과 형식 오류: {key} (문자열 배열이 필요합니다)')
            clean[key] = value
        else:
            if not isinstance(value, str):
                raise ValueError(f'결과 형식 오류: {key} (문자열이 필요합니다)')
            clean[key] = value
    if 'question_keys' in clean:
        clean['question_keys'] = [k for k in QUESTION_KEYS if k in clean['question_keys']]
        for key in ('_structured_notice','_workflow_review','_basic_evidence','_studio_compact','_schema_limits'):
            if key in data:clean[key]=data[key]
    return clean

def numeric(value):
    if value is None or value == '' or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if 0 <= result <= 1000 else None
    except (ValueError, TypeError):
        return None

def guard_review(notice, answers, raw, pages):
    """Never promote an AI conclusion. Downgrade unverifiable claims; flag numeric conflict."""
    from planning import has_attendance
    from conditions import missing as unanswered_value, has_social, social_card, social_answer, social_document
    cards = []
    for key, label in CATEGORIES.items():
        quote, page = notice.get(key+'_quote', ''), notice.get(key+'_page', '')
        verified = evidence(quote, page, pages)
        status = raw.get(key+'_status', '확인 필요')
        reason = raw.get(key+'_reason', '')
        action = raw.get(key+'_action', '') or '원문과 운영기관 안내를 확인해주세요.'
        supporting_quotes=[]
        known_conflict=False
        if status not in STATUSES:
            status, reason = '확인 필요', 'AI 결과의 상태값을 해석하지 못했습니다.'
        if status=='해당 없음':
            status,reason='확인 필요','비적용을 확인할 답변과 조건 연결이 부족합니다. 미입력은 해당 없음으로 판단하지 않습니다.'
            action='이 항목의 질문에 답하거나 원문에서 적용 대상을 확인하세요.'
        presence=notice.get(key+'_presence','명시' if notice.get(key+'_rule') else '미기재')
        if presence=='미기재':
            status,reason,action='확인 필요','문서에서 이 조건을 찾지 못했습니다. 비적용이나 충족을 뜻하지 않습니다.','상세 모집요강이나 운영기관에서 이 조건의 적용 여부를 확인하세요.'
            if notice.get('_schema_limits'):
                reason='현재 Studio 설정에서 이 조건을 추출하지 않았습니다. 원문에 없거나 적용되지 않는다는 뜻은 아닙니다.'
        elif presence=='판독불가':
            status,reason,action='확인 필요','원본의 이 부분을 판독하지 못했습니다.','더 선명한 원본이나 상세 모집요강을 확인하세요.'
        elif not verified:
            status, reason = '확인 필요', '인용문과 페이지를 원문 텍스트에서 확인하지 못했습니다. 스캔·표 또는 추출 오류일 수 있습니다.'
        if key == 'eligibility' and verified and presence=='명시':
            if (notice.get('allowed_statuses') and not answers.get('enrollment_status')) or (notice.get('minimum_remaining_terms') and answers.get('remaining_terms') is None):
                status, reason = '확인 필요', '학적 또는 잔여학기 답변이 비어 있습니다. 지역·대학 유형 등 나머지 조건도 확인해야 합니다.'
            if status=='일치' and 'condition_answers' not in answers and notice.get('other_questions') and not answers.get('other_facts'):
                status,reason='확인 필요','공고의 추가 지원 조건에 대한 답변이 없습니다. '+notice['other_questions']
            if status=='일치' and notice.get('minimum_remaining_terms') and '잔여학기' not in normalize(quote):
                status,reason='확인 필요','잔여학기 판단을 뒷받침하는 인용이 부족합니다. 모집대상 각주를 확인하세요.'
        if key == 'preference' and verified and presence=='명시':
            center = notice.get('preference_center', '')
            if center:
                label='기관별 우대조건'
                for source_page,source_text in enumerate(pages,1):
                    at=source_text.rfind(center)
                    if at>=0:
                        start=source_text.rfind('\n',0,max(0,at-160))+1
                        stop=source_text.find('\n',at+len(center)+70)
                        supporting_quotes.append({'page':str(source_page),'quote':source_text[start:stop if stop>=0 else len(source_text)],'basis':'원문에서 기관명이 있는 연속 구간을 코드로 찾아 표시'})
                        break
            if center and not answers.get('selected_center'):
                status, reason = '확인 필요', '선택할 기관이 정해지지 않아 기관별 우대 적용을 확인할 수 없습니다.'
            elif center and normalize(center) != normalize(answers.get('selected_center', '')):
                if supporting_quotes:
                    status, reason = '해당 없음', f'{center} 선택자에게 적용되는 기관별 우대는 해당하지 않습니다. 사회적 배려 등 다른 우대의 적용 여부는 이 카드에서 확정하지 않습니다.'
                else:
                    status,reason='확인 필요','기관별 적용을 뒷받침하는 원문 구간을 확인하지 못했습니다.'
            if center and '분야' in center:
                label='명시된 우대조건'
                status,reason='확인 필요','AI가 활동 분야를 우대 적용 기관으로 추출했습니다. 선발 우대와 활동 후 추가 혜택을 원문에서 구분해 확인해야 합니다.'
                action='우대사항인지 활동 후 추가 혜택인지 원문과 상세 안내를 확인하세요.'
        if key == 'commitment' and verified and presence=='명시':
            pairs = [('weekly_visits', 'minimum_weekly_visits', '방문 횟수'), ('weekly_hours', 'minimum_weekly_hours', '총시간')]
            missing, conflicts = [], []
            for user_key, rule_key, name in pairs:
                required, actual = numeric(notice.get(rule_key)), numeric(answers.get(user_key))
                if required is not None and actual is None:
                    missing.append(name)
                elif required is not None and actual < required:
                    conflicts.append(f'{name}: 내 답변 {actual:g}, 공고의 추출값 {required:g}')
            if conflicts:
                known_conflict=True
                status, reason = '불일치', ' / '.join(conflicts) + '. 추출값은 원문에서 다시 확인해주세요.'
                action = '시간 합계와 별개로 필요한 방문 횟수를 확보할 수 있는지 확인하세요.'
            elif missing:
                status, reason = '확인 필요', ', '.join(missing) + ' 답변이 비어 있습니다.'
            if notice.get('activity_period') and answers.get('long_term')=='어려움':
                known_conflict=True
                status,reason='불일치','공고의 전체 활동 기간 참여가 어렵다고 답했습니다: '+notice['activity_period']
            elif notice.get('activity_period') and not answers.get('long_term') and status=='일치':
                status,reason='확인 필요','전체 활동 기간 참여 가능 여부가 입력되지 않았습니다.'
        if key == 'documents' and presence=='명시' and not answers.get('review_stage'):
            status, reason = '확인 필요', '현재 지원 단계를 알려주면 서류를 준비해야 하는 시점을 대조할 수 있습니다.'
        if key == 'schedule' and presence=='명시' and not answers.get('unavailable_dates') and ('question_answers' not in answers or has_attendance(notice)):
            status, reason = '확인 필요', '개인 일정이 입력되지 않았습니다. 참여 가능 요일·시간을 확정할 수 없습니다.'
        if key=='schedule' and 'question_answers' in answers and not has_attendance(notice) and presence=='명시' and status!='불일치':
            label='접수·발표 일정'
            status,reason,action='확인 필요','추출된 일정에서 참석 일정이 확인되지 않아 개인 참석 가능 시간은 묻지 않았습니다. 접수·발표 날짜와 변경 공지는 원문에서 확인하세요.','접수 마감과 제출 경로를 확인하고 제출할 시점을 정하세요.'
        if 'condition_answers' in answers:
            linked=[q for q in answers['condition_answers'] if q.get('condition_id')==key and q.get('kind')!='social_support']
            unanswered=[q for q in linked if unanswered_value(q.get('answer'))]
            # Center-specific preference may be explicitly out of scope; do not re-open its hidden skills question.
            if unanswered and status in ('일치','불일치') and not known_conflict:
                status,reason='확인 필요','이 조건에 연결된 답변이 비어 있습니다: '+', '.join(q['text'] for q in unanswered)+'. 다른 조건의 빈 답변과 구분합니다.'
                action='이 조건의 미입력 질문을 확인하세요. 답변이 없다는 이유로 충족·미충족을 확정하지 않습니다.'
        elif key=='eligibility' and status=='일치':
            from conditions import link_question
            if any(unanswered_value(v) and link_question(notice,q)['condition_id']=='eligibility' for q,v in answers.get('question_answers',{}).items()):
                status,reason='확인 필요','지원 자격에 연결된 답변이 비어 있습니다.'
        if key=='documents' and status in ('일치','불일치') and 'document_checklist' in answers:
            pending=[r for r in answers['document_checklist'] if not r.get('later') and r.get('stage')!='시점 확인 필요' and r.get('applicability')!='해당 없음' and (r.get('readiness') not in ('준비 완료','제출 완료') or r.get('applicability')=='아직 모름' or not r.get('source_found'))]
            if pending:status,reason='확인 필요','준비 상태나 적용 대상을 확인하지 않은 제출물이 남아 있습니다. 체크리스트를 확인하세요.'
        if key=='documents' and 'document_checklist' in answers:
            invalid_na=[r for r in answers['document_checklist'] if not r.get('later') and r.get('applicability')=='해당 없음' and (r.get('category')=='필수' or (social_document(r) and social_answer(answers)!='해당 없음'))]
            if invalid_na:status,reason='확인 필요','필수서류 또는 대상 여부가 확인되지 않은 증빙을 해당 없음으로 처리할 수 없습니다.'
        cards.append(dict(key=key, title=label, status=status, reason=reason, action=action,
                          quote=quote, page=page, verified=verified, presence=presence, rule=notice.get(key+'_rule',''),
                          model_status=raw.get(key+'_status'), model_quote_changed=raw.get(key+'_quote','')!=quote))
        cards[-1]['supporting_quotes']=supporting_quotes
        cards[-1]['linked_questions']=[q for q in answers.get('condition_answers',[]) if q.get('condition_id')==key]
    if has_social(notice):cards.append(social_card(notice,answers,pages))
    extra_preferences=[q for q in answers.get('condition_answers',[]) if q.get('condition_id')=='preference' and q.get('kind')!='social_support' and q.get('answer_key','').startswith('question_answers.')]
    if notice.get('preference_center') and extra_preferences:
        quote,page=notice.get('preference_quote',''),notice.get('preference_page','')
        cards.append(dict(key='other_preference',title='그 밖의 우대 조건',status='확인 필요',reason='기관별 우대의 해당 없음과 별도로 확인합니다. '+' / '.join(q['text']+' 답변: '+('미입력' if unanswered_value(q.get('answer')) else str(q['answer'])) for q in extra_preferences),action='희망 기관이 인정하는 전공·역량 범위를 원문 또는 운영기관에서 확인하세요.',quote=quote,page=page,verified=evidence(quote,page,pages),presence=notice.get('preference_presence','명시'),rule=notice.get('preference_rule',''),supporting_quotes=[],linked_questions=extra_preferences))
    unlinked=[q for q in answers.get('condition_answers',[]) if q.get('condition_id')=='unlinked']
    if unlinked:
        cards.append(dict(key='unlinked',title='연결을 확인할 추가 조건',status='확인 필요',reason='어느 조건을 판단하는 질문인지 자동으로 확정하지 못했습니다: '+' / '.join(q['text'] for q in unlinked),action='질문과 원문 조건을 직접 대조하세요. 답변이 있어도 충족으로 확정하지 않습니다.',quote='',page='',verified=False,presence='미확인',rule='',supporting_quotes=[],linked_questions=unlinked))
    from independent_review import condition_rows, apply_independent_checks
    return apply_independent_checks(cards,condition_rows(notice,answers,pages))

def action_list(cards):
    ordered = sorted(cards, key=lambda c: {'불일치':0, '확인 필요':1, '일치':2, '해당 없음':3}[c['status']])
    return list(dict.fromkeys(c['action'] for c in ordered if c['status'] != '해당 없음'))[:3]
