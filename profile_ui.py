"""Profile-first entry and explicit per-notice override controls."""
import json
from pathlib import Path
import streamlit as st
from profiles import LABELS,OPTIONS,NUMERIC,TIMED,clean_profile,atomic_conditions,applied_facts,profile_rows
from workspaces import checkpoint,activate,refresh_profile

def route(name):
    checkpoint(st.session_state);st.session_state.route=name
    st.session_state['_navigation_changed']=True

def start_upload():
    route('review');st.session_state.screen=1

def fact_input(key,label,initial,prefix):
    if key in OPTIONS:
        options=['모름']+OPTIONS[key]
        value=st.selectbox(label,options,index=options.index(initial) if initial in options else 0,key=prefix)
        return None if value=='모름' else value
    if key in NUMERIC:
        if key=='gpa':return st.number_input(label,min_value=0.0,max_value=100.0,value=float(initial) if initial is not None else None,step=0.1,key=prefix)
        return st.number_input(label,min_value=0,max_value=120,value=int(initial) if initial is not None else None,step=1,key=prefix)
    return st.text_input(label,value=str(initial or ''),key=prefix,max_chars=200) or None

def render_profile():
    st.header('내 정보 · 필요한 만큼만')
    st.caption('이 브라우저에만 저장합니다. 공고별 서류 준비·지원 단계는 별도로 보관합니다. 모르는 정보는 비워두세요.')
    current=clean_profile(st.session_state.get('common_profile',{}))
    with st.form('common_profile_form'):
        draft={}
        def draw(key):
            f=current.get(key,{})
            value=fact_input(key,LABELS[key],f.get('value'),'pf_'+key)
            period=st.text_input(LABELS[key]+' 기준 시점',value=f.get('period',''),key='pf_period_'+key,placeholder='공고와 같은 형식: 2026-03 또는 2026-1학기') if key in TIMED else ''
            scale=st.selectbox('성적 만점 기준',['모름','4.5','4.3','100'],index=['모름','4.5','4.3','100'].index(f.get('scale')) if f.get('scale') in ['4.5','4.3','100'] else 0) if key=='gpa' else ''
            draft[key]={'state':'known' if value is not None else 'unknown' if key in OPTIONS else 'unset','value':value,'period':period,'scale':scale if scale!='모름' else ''}
        for key in ('school','campus','enrollment_status','major','interests'):draw(key)
        with st.expander('공고 조건에 필요할 때 · 대학 유형·지역·학기·성적'):
            for key in ('college_type','region','remaining_terms','gpa','nationality','age'):draw(key)
        with st.expander('장학 조건에 필요할 때 · 선택 정보'):
            st.caption('공고에 필요한 경우에만 입력하세요. 대상 여부는 증빙 준비 상태와 다릅니다.')
            for key in ('income_band','social_support'):draw(key)
        if st.form_submit_button('내 정보 저장',type='primary'):
            st.session_state.common_profile=clean_profile(draft);refresh_profile(st.session_state)
            st.success('저장했습니다. 이번 공고에서 직접 수정한 답변은 유지합니다.')
    if st.button('공통 프로필만 삭제'):
        st.session_state.common_profile={};refresh_profile(st.session_state)
        for key in list(st.session_state):
            if key.startswith('pf_'):st.session_state.pop(key,None)
        st.rerun()

def render_fact_overrides(notice,base_answers):
    conditions=atomic_conditions(notice)
    if not conditions:return {}
    st.markdown('### 저장 정보로 확인할 조건')
    overrides=dict(st.session_state.get('profile_overrides',{}))
    scope=st.session_state.source_hash[:12]
    for c in conditions:
        key=c['field'];prefix='fact_'+scope+'_'+c['id'];existing=overrides.get(c['id'])
        if key in ('enrollment_status','remaining_terms','social_support'):continue
        with st.expander(LABELS[key]+' · '+c['rule'],expanded=False):
            st.caption('공고 기준: '+(c['period'] or '기준 시점 미확인')+(' / 만점 '+c['scale'] if c['scale'] else ''))
            mode=st.selectbox('답변 적용 방식',['프로필 사용','이번 공고에 직접 답변','이번 공고는 모름'],
                index=0 if existing is None else 1 if existing.get('state')=='known' else 2,key=prefix+'_mode')
            if mode=='프로필 사용':overrides.pop(c['id'],None)
            elif mode=='이번 공고는 모름':overrides[c['id']]={'state':'unknown','value':None}
            else:
                value=fact_input(key,'이번 공고의 '+LABELS[key],existing.get('value') if existing else None,prefix+'_value')
                scale=st.selectbox('이번 답변의 만점',['모름','4.5','4.3','100'],key=prefix+'_scale') if key=='gpa' else ''
                overrides[c['id']]={'state':'known' if value is not None else 'unknown','value':value,'scale':scale}
            st.text(c['quote']);st.caption('원문 '+(c['page'] or '?')+'쪽')
    st.session_state.profile_overrides=overrides
    facts=applied_facts(notice,st.session_state.get('common_profile',{}),overrides,base_answers,st.session_state.get('profile_provenance',{}))
    with st.expander('적용된 내 정보 확인'):
        for c in conditions:
            f=facts[c['id']];st.write(LABELS[c['field']]+' · '+str(f['value'] if f['value'] is not None else '확인 필요')+' · '+f['origin'])
    return facts

def navigation():
    view=st.session_state.get('route','review' if st.session_state.get('notice') else 'home')
    st.markdown('### 공고다음')
    st.caption('둘러보기')
    with st.container(key='entry_nav'):
        for label,target in zip(['홈','내 정보','공고 찾기','현재 공고'],['home','profile','catalog','review']):
            st.button(label,on_click=route,args=(target,),key='entry_'+target,use_container_width=True,type='primary' if view==target else 'secondary')
    st.caption('바로 시작')
    st.button('공고 직접 확인하기',on_click=start_upload,key='menu_upload',use_container_width=True)
    st.button('나에게 맞는 공고 보기',on_click=route,args=('catalog',),key='menu_catalog',use_container_width=True)
    st.divider()

def resume_notices():
    saved=st.session_state.get('workspaces',{})
    with st.popover('저장한 공고 이어보기',icon=':material/bookmark:'):
        if st.session_state.get('notice'):
            st.button('현재 공고 이어보기',on_click=route,args=('review',),use_container_width=True)
        if not saved and not st.session_state.get('notice'):
            st.write('아직 저장한 공고가 없습니다. 공고를 확인하면 여기에 보관됩니다.')
        for key,record in saved.items():
            if st.button(record['values']['notice']['notice_title'],key='resume_'+key,use_container_width=True):
                activate(st.session_state,record);st.rerun()

def entry(root):
    if st.session_state.pop('_navigation_changed',False):
        # A menu selection should reveal the destination on small screens too.
        st.html('''<script>requestAnimationFrame(() => {
          document.querySelector('[data-testid="stSidebar"][aria-expanded="true"] [data-testid="stSidebarCollapseButton"] button')?.click();
          document.querySelector('[data-testid="stMain"]')?.scrollTo({top:0,behavior:'instant'});
        });</script>''',unsafe_allow_javascript=True)
    view=st.session_state.get('route','review' if st.session_state.get('notice') else 'home')
    if view=='review':return False
    if view=='profile':render_profile()
    elif view=='catalog':render_catalog(root)
    else:
        with st.container(key='home_hero'):
            title,resume=st.columns([3,1.4],vertical_alignment='bottom')
            with title:
                st.markdown('<div class="hero-eyebrow">장학금 · 대외활동 · 공모전</div><h1>나의 정보로,<br>다음 기회를 준비해요.</h1>',unsafe_allow_html=True)
            with resume:resume_notices()
        with st.container(key='home_primary'):
            st.button('공고 직접 확인하기',on_click=start_upload,type='primary',use_container_width=True,help='공고 파일을 올리고 바로 조건 확인')
    if view in ('profile','catalog'):resume_notices()
    return True

def render_catalog(root):
    from catalog import load_catalog,card_review,available_record,status_label
    st.header('나에게 맞는 공고 보기')
    st.caption('공식 원문을 확보한 제한된 공개 목록입니다. 전체 장학금 검색이나 지원 자격 확정이 아닙니다. 목록 조회·필터는 AI를 호출하지 않습니다.')
    catalog=load_catalog(root)
    if not catalog:st.info('아직 원문 분석을 마친 공고가 없습니다.');return
    kind=st.selectbox('종류',['전체']+sorted({r['kind'] for r in catalog}))
    status=st.selectbox('접수 상태',['전체','마감 전 · 시작일 확인','과거 검증 사례','접수 상태 확인 필요'])
    interest=st.text_input('관심 분야 검색',placeholder='교육, 장학, 공모전 등')
    st.caption('목록 순서는 마감일 기준이며, 미확인 항목 수로 지원 가능성을 계산하지 않습니다.')
    count=0
    for record in sorted(catalog,key=lambda r:r.get('deadline',''),reverse=True):
        label=status_label(record)
        if kind!='전체' and kind!=record['kind']:continue
        if status!='전체' and status!=label:continue
        if interest and interest not in record['title']+' '+str(record.get('tags',[])):continue
        count+=1
        with st.container(border=True):
            st.subheader(record['title']);st.caption(label+' · 마감 '+(record.get('deadline') or '미확인'))
            st.link_button('공식 원문',record['source_url']);st.caption('원문 확인 '+record['checked_at'])
            if not available_record(root,record):
                st.warning('원문 확보 또는 분석 미완료 · 조건 추천에서 제외했습니다.');continue
            result=card_review(root,record,st.session_state.get('common_profile',{}))
            for title,key in [('확인된 일치','matches'),('추가 확인','unknowns'),('확인된 불일치','conflicts')]:
                st.write('**'+title+'** · '+(' / '.join(dict.fromkeys(r['label'] for r in result[key])) or '없음'))
            st.caption('확인된 불일치가 없어도 전체 지원 자격을 충족한다는 뜻은 아닙니다. 추출되지 않은 조건은 원문에서 확인하세요.')
            with st.expander('추천 이유와 원문 근거'):
                for row in result['rows']:
                    st.write(row['label']+' · '+row['status']+' · '+row['reason']);st.text(row['quote']);st.caption(str(row['page'])+'쪽')
            if st.button('이 공고 검토하기',key='catalog_'+record['id'],type='primary'):
                from browser_draft import single_snapshot
                state=available_record(root,record)
                saved=st.session_state.get('workspaces',{}).get(state['source_hash'])
                activate(st.session_state,saved or single_snapshot(state));st.rerun()
