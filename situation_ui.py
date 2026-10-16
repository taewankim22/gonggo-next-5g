"""Step 3: evidence-linked cards over the existing answer contract."""
import html
import streamlit as st
from core import fingerprint, evidence
from conditions import bind_answers, SOCIAL_QUESTION, has_social
from planning import STAGES
from profiles import OPTIONS, NUMERIC, applied_facts, profile_fact
from workspaces import seed_basic, explicit_basic
from situation_questions import build_questionnaire, GROUPS, short_rule, response_state, progress


def _mark(q, widget, unknown_widget=None):
    state=st.session_state
    unknown=bool(unknown_widget and state.get(unknown_widget))
    if unknown:state[widget]=None
    value=state.get(widget)
    value=None if value in ('모름','모르겠어요','아직 모름') else value
    records=dict(state.get('situation_responses',{}))
    records[q['id']]={'state':response_state(value,True),'value':value}
    state.situation_responses=records
    if q['kind']=='basic':explicit_basic(state,q['key'])
    if q['kind']=='profile':
        overrides=dict(state.get('profile_overrides',{}))
        overrides[q['condition']['id']]={'state':'known' if value is not None else 'unknown','value':value,
            'scale':state.get(widget.removesuffix('_value')+'_scale','')}
        state.profile_overrides=overrides
    if q['kind']=='extra' and q['question']['kind']=='social_support':explicit_basic(state,'social_support')
    for key in ('result','review_hash','raw_review','preparation'):state.pop(key,None)


def _reset_profile(q,widget,unknown_widget):
    st.session_state.get('profile_overrides',{}).pop(q['condition']['id'],None)
    st.session_state.get('situation_responses',{}).pop(q['id'],None)
    for key in (widget,unknown_widget,widget.removesuffix('_value')+'_scale'):
        st.session_state.pop(key,None)
    for key in ('result','review_hash','raw_review','preparation'):st.session_state.pop(key,None)


def _mark_scale(q,widget):
    # Choosing a score scale before entering a score is not an explicit "unknown".
    if st.session_state.get(widget) is not None:
        _mark(q,widget)
        return
    overrides=dict(st.session_state.get('profile_overrides',{}))
    prior=overrides.get(q['condition']['id'],{})
    overrides[q['condition']['id']]={'state':prior.get('state','unset'),'value':None,
        'scale':st.session_state.get(widget.removesuffix('_value')+'_scale','')}
    st.session_state.profile_overrides=overrides
    for key in ('result','review_hash','raw_review','preparation'):st.session_state.pop(key,None)


def _source(q,pages):
    with st.expander('공고 근거 보기'):
        st.write(q['rule'] or '연결할 조건을 확인하지 못했습니다.')
        if q.get('related'):
            for c in q['related']:
                if c['rule']!=q['rule']:st.write(short_rule(c['rule']))
                if c['quote']!=q['quote']:st.text(c['quote'])
        if q['quote']:st.text(q['quote'])
        st.write((q['page']+'쪽 · ' if q['page'] else '')+('원문 인용 확인' if evidence(q['quote'],q['page'],pages) else '원문 근거 확인 필요'))
        if q['stage'] not in ('지원단계',''):st.write('적용 시점: '+q['stage'])


def _choice(label,options,widget,q,unknown_label='모름'):
    # index=None distinguishes no response from an explicit unknown selection.
    if widget in st.session_state and st.session_state[widget] not in options:
        st.session_state[widget]=None
    return st.radio(label,options,index=None,key=widget,horizontal=True,
        format_func=lambda x:unknown_label if x in ('모르겠어요','아직 모름','모름') else '해당하지 않음' if x=='해당 없음' else x,
        on_change=_mark,args=(q,widget))


def _numeric(q,widget,unknown_widget):
    if st.session_state.get(unknown_widget):st.session_state[widget]=None
    cols=st.columns([4,1],vertical_alignment='bottom')
    with cols[0]:
        floating=q.get('key') in ('gpa','weekly_hours')
        value=st.session_state.get(widget)
        if value is not None:st.session_state[widget]=float(value) if floating else int(value)
        out=st.number_input(q['title']+(' · '+q['unit'] if q['unit'] and q['unit'] not in q['title'] else ''),min_value=0.0 if floating else 0,
            value=None,step=0.1 if floating else 1,key=widget,placeholder='숫자를 입력하세요',
            disabled=bool(st.session_state.get(unknown_widget)),on_change=_mark,args=(q,widget))
    with cols[1]:
        st.checkbox('모름',key=unknown_widget,on_change=_mark,args=(q,widget,unknown_widget))
    return None if st.session_state.get(unknown_widget) else out


def render_situation(notice,pages,mode,go):
    state=st.session_state;scope=state.source_hash[:12];profile=state.get('common_profile',{})
    seed_basic(state,notice,profile)
    st.markdown('<div class="situation-heading"><h1>내 조건을 확인해요</h1><p>모르는 답변은 건너뛰어도 괜찮아요.</p></div>',unsafe_allow_html=True)
    summary=st.empty()
    answers={};qa={};records=[];active_keys=[]
    initial=build_questionnaire(notice,pages,{'selected_center':state.get('answer_selected_center','')},state.get('answer_review_stage',STAGES[0]))
    if mode=='예시 화면 체험':
        def preset():
            choice=state.get('profile_preset','직접 입력')
            if choice=='직접 입력':return
            values={'enrollment_status':'휴학' if 'A' in choice else '재학','remaining_terms':3,
                'selected_center':'여명학교' if 'A' in choice else '다른 기관','skills':'중국어 가능, 교육 현장 활용 의사 있음',
                'weekly_visits':2 if 'A' in choice else 1,'weekly_hours':4,'long_term':'가능','review_stage':'지원 준비 중'}
            for k,v in values.items():state['answer_'+k]=v;explicit_basic(state,k)
            state.pop('result',None)
        st.selectbox('답변 시작하기',['직접 입력','가상 A · 여명학교 / 주 2회','가상 B · 다른 기관 / 주 1회'],key='profile_preset',on_change=preset)
    if 'review_stage' in initial['keys']:
        if state.get('answer_review_stage') not in STAGES:state.answer_review_stage=STAGES[0]
        answers['review_stage']=st.selectbox('현재 지원 단계',STAGES,key='answer_review_stage')
    stage=answers.get('review_stage',STAGES[0])
    model=build_questionnaire(notice,pages,{'selected_center':state.get('answer_selected_center','')},stage)

    def draw_extra(q,optional=False):
        widget='question_'+scope+'_'+q['id'];source=q['question']
        if source['kind']=='social_support':
            if state.get('profile_provenance',{}).get('social_support')!='이번 공고 답변':
                value,origin=profile_fact(profile,'social_support')
                if widget not in state or 'social_support' in state.get('profile_seeded',{}):
                    state[widget]=value if value in ('해당','해당 없음') else None
                    state.setdefault('profile_seeded',{})['social_support']=state[widget]
                    state.setdefault('profile_provenance',{})['social_support']=origin
                if origin=='공통 프로필':badge()
            v=_choice(q['title'],['해당','해당 없음','아직 모름'],widget,q)
        elif q.get('input_type')=='choice' and state.get(widget) in (None,'','해당','해당하지 않음','아직 모름'):
            v=_choice(q['title'],['해당','해당하지 않음','아직 모름'],widget,q)
        else:
            v=st.text_input(q['title'] if not optional else '이 조건의 추가 설명 (선택)',key=widget,max_chars=700,placeholder='아는 내용만 입력하세요',on_change=_mark,args=(q,widget))
        value=None if v in ('모름','모르겠어요','아직 모름') else v
        if not optional or value not in (None,''):
            qa[source['text']]=value
        return value

    def badge():st.markdown('<span class="situation-profile">내 정보 적용</span>',unsafe_allow_html=True)

    def draw(q,count=True):
        widget='answer_'+q['key'] if q['kind']=='basic' else 'fact_'+scope+'_'+q['condition']['id']+'_value' if q['kind']=='profile' else 'question_'+scope+'_'+q['id']
        unknown_widget='question_'+scope+'_'+fingerprint(q['id']+':unknown')[:16]
        origin='이번 공고 답변';profile_unknown=False
        if q['kind']=='profile':
            c=q['condition'];override=state.get('profile_overrides',{}).get(c['id'])
            if override is None:
                v,origin=profile_fact(profile,c['field'],c['period'])
                state[widget]=v
                profile_unknown=origin=='프로필에서 모름'
                if c['field']=='gpa':state[widget.removesuffix('_value')+'_scale']=profile.get('gpa',{}).get('scale','') or '모름'
            else:
                if widget not in state:state[widget]=override.get('value') if override.get('state')=='known' else None
                profile_unknown=override.get('state')=='unknown'
            if profile_unknown and c['field'] in NUMERIC and unknown_widget not in state:state[unknown_widget]=True
        elif q['kind']=='basic':origin=state.get('profile_provenance',{}).get(q['key'],'')
        with st.container(key='situation_item_'+q['id']):
            if origin=='공통 프로필':badge()
            context=' · '.join(v for v in (q.get('period'),q['condition'].get('scale','')+'점 만점' if q['kind']=='profile' and q['condition'].get('scale') else '') if v)
            if context:st.markdown('**기준: '+context+'**')
            if q['kind'] in ('profile','extra') or q.get('key') in ('long_term','unavailable_dates'):
                st.markdown('<div class="situation-rule">'+html.escape(short_rule(q.get('display_rule',q['rule'])))+'</div>',unsafe_allow_html=True)
            if q['kind']=='extra':value=draw_extra(q)
            elif q['input_type']=='number':value=_numeric(q,widget,unknown_widget)
            elif q['kind']=='basic' and q['key']=='unavailable_dates':
                schedule_q={**q,'id':q['id']}
                choice=st.radio(q['title'],['참석 불가 일정 없음','참석 불가 일정 있음','아직 확인하지 않음'],key='schedule_state',index=None,horizontal=True,
                    format_func=lambda x:{'참석 불가 일정 없음':'모두 가능','참석 불가 일정 있음':'어려운 일정 있음','아직 확인하지 않음':'모름'}[x],on_change=_mark,args=(schedule_q,'schedule_state'))
                value=st.text_input('어려운 날짜·시간',key=widget,max_chars=700) if choice=='참석 불가 일정 있음' else '참석 불가 일정 없음' if choice=='참석 불가 일정 없음' else None
            elif q['input_type']=='choice':
                options=(['재학','휴학','수료','졸업','모르겠어요'] if q.get('key')=='enrollment_status' else ['가능','어려움','모르겠어요'] if q.get('key')=='long_term' else OPTIONS[q['key']]+['모름'])
                # Existing explicit unknowns retain their semantic value after upgrade.
                if profile_unknown:state[widget]=options[-1]
                selected=_choice(q['title'],options,widget,q)
                value=None if selected in ('모름','모르겠어요') else selected
            else:value=st.text_input(q['title'],key=widget,max_chars=700,placeholder='아는 내용만 입력하세요',on_change=_mark,args=(q,widget))
            if q['kind']=='profile':
                if q['key']=='gpa':
                    scale_widget=widget.removesuffix('_value')+'_scale'
                    if state.get(scale_widget) not in ('모름','4.5','4.3','100'):state[scale_widget]='모름'
                    st.selectbox('내 성적의 만점',['모름','4.5','4.3','100'],key=scale_widget,on_change=_mark_scale,args=(q,widget))
                with st.popover('답변 적용'):
                    st.write('수정한 답변은 이번 공고에만 적용됩니다.')
                    st.button('내 정보 다시 적용',key='reset_'+q['id'],on_click=_reset_profile,args=(q,widget,unknown_widget))
            elif q['kind']=='basic':answers[q['key']]=value;active_keys.append(q['key'])
            _source(q,pages)
            for companion in q.get('companions',[]):
                with st.expander('이 조건의 추가 설명 (선택)'):
                    draw_extra(dict(id=companion['id'],kind='extra',question=companion,title=companion['text']),True)
        explicit=state.get('situation_responses',{}).get(q['id'],{}).get('state')=='unknown' or profile_unknown
        if q['kind']=='basic' and origin=='이번 공고 답변' and value is None:explicit=True
        if count:records.append({'id':q['id'],'state':response_state(value,explicit),'origin':origin,'value':value,
            'condition':q['rule'],'quote':q['quote'],'page':q['page'],'stage':q['stage'],'input_type':q['input_type'],
            'period':q.get('period',''),'unit':q.get('unit','')})

    for group in GROUPS:
        questions=[q for q in model['current'] if q['group']==group]
        if not questions:continue
        with st.container(border=True,key='situation_group_'+str(GROUPS.index(group))):
            st.markdown('### '+group)
            for q in questions:draw(q)
    if not model['current']:st.info('현재 분석에서 연결할 질문을 찾지 못했습니다. 원문의 지원 조건을 확인해주세요.')
    if model['later']:
        with st.expander(f'이후 단계에서 확인할 조건 · {len(model["later"])}개'):
            st.write('현재 응답 수에 포함하지 않습니다.')
            # Preserve existing drafts even while the inputs are not mounted.
            if st.checkbox('이후 단계 질문에도 지금 답하기',key='show_later_questions'):
                for q in model['later']:draw(q,False)
            else:
                for q in model['later']:st.write(short_rule(q['rule']))
    with st.expander('추가로 알려줄 내용'):
        extra=st.text_input('그 밖에 알려줄 내용 (선택)',key='answer_other_facts',max_chars=1000)
    answers['active_question_keys']=active_keys
    answers['profile_facts']=applied_facts(notice,profile,state.get('profile_overrides',{}),answers,state.get('profile_provenance',{}))
    answers['answer_provenance']=dict(state.get('profile_provenance',{}));answers['profile_revision']=fingerprint(profile)
    current_texts={q['text'] for q in model['extras']}
    current_qa={k:v for k,v in qa.items() if k in current_texts}
    answers['question_answers']=current_qa
    answers['condition_answers']=bind_answers(notice,active_keys,model['extras'],answers,current_qa)
    answers['preference_facts']={'social_support':qa.get(SOCIAL_QUESTION)} if has_social(notice) else {}
    for fact in answers['profile_facts'].values():
        if fact['field']=='social_support' and has_social(notice):fact.update(value=qa.get(SOCIAL_QUESTION),origin=state.get('profile_provenance',{}).get('social_support','이번 공고 답변'))
    answers['deferred_questions']=[q['rule'] for q in model['later']]
    answers['other_facts']='\n'.join([q+' '+(v or '미입력') for q,v in current_qa.items()]+([extra] if extra else []))
    answers['question_records']=records
    done,total=progress(records)
    summary.markdown(f'<div class="situation-progress"><span>답변 <strong>{done} / {total}</strong></span><progress aria-label="응답 진행도" value="{done}" max="{max(total,1)}"></progress></div>',unsafe_allow_html=True)
    if state.get('draft_answers')!=answers:
        for key in ('result','review_hash','raw_review','preparation'):state.pop(key,None)
    state.draft_answers=answers
    with st.container(key='situation_next'):
        st.button('준비 목록 확인하기 →',type='primary',on_click=go,args=(4,),use_container_width=True)
    st.button('← 핵심 확인',on_click=go,args=(2,))
