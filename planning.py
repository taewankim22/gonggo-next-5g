"""Conservative preparation UI from existing Studio fields; no invented requirements."""
import re
from core import fingerprint, normalize
from conditions import link_question, has_social, SOCIAL_QUESTION, missing

PREP_STATES = ['아직 확인하지 않음', '준비 전', '준비 중', '준비 완료', '제출 완료']
STAGES = ['지원 검토 중', '지원 준비 중', '서류 제출 전', '서류 제출 후', '면접 준비 중', '선발 후·활동 중', '활동 종료 후']

def has_attendance(notice):
    return bool(re.search(r'면접|사전교육|발대식|참석|출석|오리엔테이션|설명회|대면|현장', notice.get('schedule_rule','')))

def question_keys(notice, answers=None):
    answers=answers or {}; keys=[]
    if notice.get('allowed_statuses'):keys.append('enrollment_status')
    if notice.get('minimum_remaining_terms'):keys.append('remaining_terms')
    center=notice.get('preference_center','')
    valid_center=bool(center and '분야' not in center)
    if valid_center:keys.append('selected_center')
    if notice.get('preference_skill') and (not center or (valid_center and normalize(answers.get('selected_center',''))==normalize(center))):
        keys.append('skills')
    for key in ('weekly_visits','weekly_hours'):
        if notice.get('minimum_'+key):keys.append(key)
    if notice.get('activity_period'):keys.append('long_term')
    if notice.get('documents_rule') or notice.get('required_documents'):keys.append('review_stage')
    if has_attendance(notice):keys.append('unavailable_dates')
    return keys

def document_items(notice, pages):
    items=[];seen=set()
    for raw in notice.get('required_documents',[]):
        if not raw.strip() or normalize(raw) in seen:continue
        seen.add(normalize(raw))
        stage='활동 종료 후' if re.search(r'사후|활동\s*종료|결과보고서',raw) else '선발 후·활동 중' if re.search(r'선발된|통과|중간\s*심사|최종\s*결과물|협약|선정되|후속연구',raw) else '지원 단계'
        category='선택' if '선택' in raw else '해당자만' if re.search(r'해당자|경우|희망\s*시|영리기관|대상자|채용예정',raw) else '필수' if re.search(r'필수|공통|사전서류|사후서류',raw) else '대상·필수 여부 확인'
        # Use the extracted item as-is. A composite item stays composite; no guessed split.
        name=raw.split(':',1)[-1].strip()
        anchor=re.split(r'\(| - | 등 | 제출| 작성|를 |을 ',name)[0].strip()
        anchor=re.sub(r'^(?:공통|필수|사전서류|사후서류)[,\s:]*','',anchor)
        matches=[]
        if len(normalize(anchor))>=2:
            for number,page in enumerate(pages,1):
                # Match across line breaks, then retain an exact surrounding source excerpt.
                pattern=r'\s*'.join(re.escape(c) for c in normalize(anchor))
                hit=re.search(pattern,page)
                if hit:matches.append((number,page[max(0,hit.start()-100):min(len(page),hit.end()+170)]))
        page,quote=matches[0] if matches else ('','')
        items.append({'id':fingerprint(raw)[:12],'text':raw,'name':name,'category':category,'stage':stage,
                      'source_page':str(page),'source_quote':quote,'source_found':bool(matches)})
    return items

def later_item(item,stage):
    if item['stage']=='활동 종료 후':return stage!='활동 종료 후'
    if item['stage']=='선발 후·활동 중':return stage not in ('선발 후·활동 중','활동 종료 후')
    return False

def additional_questions(notice, keys, items, stage):
    active=[];later=[];covered=[]
    chunks=re.split(r'\?\s*[,，]\s*|\n+',notice.get('other_questions',''))
    for chunk in chunks:
        q=chunk.strip(' ,，');q=q if q.endswith('?') else q+'?'
        if len(q)<3:continue
        if has_social(notice) and '사회적배려' in normalize(q):
            covered.append(q)
            continue
        # Duplicates are only removed when the whole question is represented elsewhere.
        compound=bool(re.search(r'지역|소재|4년제|국적|외국인|초과학기|기준일|이동|통학|언어',q))
        duplicate=(('remaining_terms' in keys and '잔여학기' in q and not compound)
            or ('selected_center' in keys and ('희망 활동' in q or '여명학교' in q) and not compound)
            or ('enrollment_status' in keys and re.fullmatch(r'(?:공고 기준일의 )?(?:재학생|휴학생|수료생|졸업예정자|재학|휴학|수료|졸업)[^?]{0,20}\?',q) is not None))
        doc_question=bool(re.search(r'준비|제출|작성|다운로드',q))
        doc_covered=doc_question and any(len(i['name'].split('(')[0].strip())>=2 and normalize(re.split(r'\(| - | 등 | 제출',i['name'])[0]) in normalize(q) for i in items)
        mixed=bool(re.search(r'대상자|자격|학적|국적|학기|연구체계|요건|부도|체납|개인\(',q))
        if items and re.fullmatch(r'(?:참가 시 )?제출이 필요한 자료를 준비할 수 있나요\?',q):doc_covered=True
        # A named group explicitly permitted in eligibility is not a required membership.
        terms=re.findall(r'\(([A-Z]{2,10})\)',q)
        permitted=any(re.search(r'\('+re.escape(term)+r'\).{0,6}(?:도지원가능|지원가능|포함)',normalize(notice.get('eligibility_rule',''))) for term in terms)
        if permitted:covered.append(q);continue
        skill=notice.get('preference_skill','')
        if skill and ('중국어' in q or '한반도' in q) and all(word in skill for word in re.findall(r'중국어|한반도',q)):
            # Named-center preference is handled by center + skill fields, including no selection.
            if notice.get('preference_center') and '분야' not in notice['preference_center']:covered.append(q);continue
        if duplicate or (doc_covered and not mixed):covered.append(q);continue
        record=link_question(notice,q)
        if stage not in ('선발 후·활동 중','활동 종료 후') and re.search(r'후속연구|협약|정부지원연구개발비|채용|결산|부도|체납|참여제한|25\.11\.30',q):later.append(record)
        else:active.append(record)
    # Preserve all omitted questions for an explicit audit/view; hidden never means satisfied.
    if notice.get('commitment_rule') and not notice.get('minimum_weekly_hours') and not notice.get('minimum_weekly_visits'):
        text='활동 의무 중 이행이 어렵거나 아직 확인하지 못한 항목이 있나요?'
        active.append({**link_question(notice,text,'commitment'),'context':notice['commitment_rule']})
    if has_social(notice):
        active.append(link_question(notice,SOCIAL_QUESTION,'preference','social_support'))
    return active,later,covered

def checklist_snapshot(items, states, stage):
    rows=[]
    for item in items:
        state=states.get(item['id'],{})
        rows.append({**item,'readiness':state.get('readiness',PREP_STATES[0]),
                     'applicability':state.get('applicability','아직 모름') if item['category'] in ('해당자만','선택','대상·필수 여부 확인') else '해당',
                     'later':later_item(item,stage)})
    return rows

def next_steps(notice, answers, rows, cards=None):
    actions=[]
    def add(title,detail):actions.append({'title':title,'detail':detail})
    conflicts=[c for c in (cards or []) if c['status']=='불일치' and c.get('presence')=='명시']
    if conflicts:add('조건이 다른 항목 확인', ' / '.join(c['title']+': '+c['action'] for c in conflicts))
    current=[r for r in rows if not r['later'] and r['applicability']!='해당 없음']
    pending=[r['name']+(' (선택 · 제출하려는 경우)' if r['category']=='선택' else '') for r in current if r['readiness'] not in ('준비 완료','제출 완료') and r['applicability']=='해당' and r['source_found']]
    unclear=[r['name'] for r in current if r['applicability']=='아직 모름' or not r['source_found']]
    if pending:add('준비할 제출물', ' · '.join(pending)+' — 체크리스트에서 준비 상태를 갱신하세요.')
    if unclear:add('적용 대상·원문 확인', ' · '.join(unclear)+' — 원문 근거와 적용 대상을 확인하세요. 모든 사람의 필수서류라는 뜻은 아닙니다.')
    labels={'enrollment_status':'공고 기준일의 학적','remaining_terms':'잔여학기','selected_center':'희망 활동 기관','skills':'명시된 우대 역량','weekly_visits':'활동 횟수','weekly_hours':'활동 시간','long_term':'전체 활동 기간 참여 가능 여부','unavailable_dates':'참석 일정'}
    unanswered=[labels[k] for k in question_keys(notice,answers) if k in labels and (answers.get(k) is None or answers.get(k)=='')]
    unanswered += [q for q,a in answers.get('question_answers',{}).items() if missing(a)]
    if unanswered:add('아직 답하지 않은 조건', unanswered[0]+(f' 외 {len(unanswered)-1}개' if len(unanswered)>1 else '')+' — 모르면 확인 필요로 남겨두세요.')
    documents=next((c for c in (cards or []) if c['key']=='documents' and c['verified'] and c['presence']=='명시'),None)
    if documents and documents.get('action'):add('제출 전 함께 확인',documents['action'])
    if not rows:add('제출서류 목록 확인','문서에서 구체적인 서류 목록을 찾지 못했습니다. 서류가 필요 없다는 뜻은 아닙니다. 상세 공고나 운영기관을 확인하세요.')
    if not actions:add('준비한 내용과 제출 경로 확인','체크는 본인이 표시한 준비 상태입니다. 서류 내용·발급일·제출 완료 여부를 원문과 직접 확인하세요.')
    return actions[:3]

def preparation_text(notice,answers,rows,actions):
    lines=[notice.get('notice_title','공고'),'', '접수 마감: '+(notice.get('application_deadline') or '미기재'),
           '마감 상세: '+(notice.get('deadline_note') or '미기재'),
           '제출 방법: '+(notice.get('submission_method') or '미기재'),'', '다음 행동']
    lines += [f'{i}. {a["title"]}: {a["detail"]}' for i,a in enumerate(actions,1)]
    lines += ['', '제출물 체크리스트 (사용자 자기 확인이며 서류 내용 검증 아님)']
    lines += [f'- [{r["readiness"]}] {r["text"]} / {r["category"]} / {r["stage"]} / 적용: {r["applicability"]} / 원문: {r["source_page"] or "미확인"}쪽' for r in rows]
    lines += ['', '내 답변']+[f'- {q} {a or "미입력"}' for q,a in answers.get('question_answers',{}).items()]
    labels={'review_stage':'지원 단계','enrollment_status':'학적','remaining_terms':'잔여학기','selected_center':'활동 기관','skills':'관련 역량','weekly_visits':'주당 방문 횟수','weekly_hours':'주당 시간','long_term':'전체 활동기간 참여','unavailable_dates':'참석 불가 일정'}
    lines += [f'- {label}: {answers[key] if answers[key] is not None else "미입력"}' for key,label in labels.items() if key in answers]
    lines += ['', '지원 자격·선발 여부를 확정하지 않습니다. 원문과 최신 공지를 확인하세요.']
    return '\n'.join(lines)
