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
        saved=st.form_submit_button('내 정보 저장')
        search=st.form_submit_button('저장하고 최신 공고 찾기',type='primary')
        if saved or search:
            st.session_state.common_profile=clean_profile(draft);refresh_profile(st.session_state)
            st.success('저장했습니다. 이번 공고에서 직접 수정한 답변은 유지합니다.')
            if search:
                route('catalog');st.session_state['_discovery_auto_requested']=True
                st.rerun()
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

def entry(root,connection=None):
    if st.session_state.pop('_navigation_changed',False):
        # A menu selection should reveal the destination on small screens too.
        st.html('''<script>requestAnimationFrame(() => {
          document.querySelector('[data-testid="stSidebar"][aria-expanded="true"] [data-testid="stSidebarCollapseButton"] button')?.click();
          document.querySelector('[data-testid="stMain"]')?.scrollTo({top:0,behavior:'instant'});
        });</script>''',unsafe_allow_javascript=True)
    view=st.session_state.get('route','review' if st.session_state.get('notice') else 'home')
    if view=='review':return False
    if view=='profile':render_profile()
    elif view=='catalog':render_catalog(root,connection)
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

def render_catalog(root,connection=None):
    from catalog import load_catalog
    from catalog_ranking import personalized_catalog
    st.header('공고 찾기')
    from discovery_ui import render_discovery
    render_discovery(root,connection)
    from calendar_ui import filter_groups,render_calendar
    st.subheader('분석한 공고')
    catalog=load_catalog(root)
    if not catalog:st.info('아직 원문 분석을 마친 공고가 없습니다.');return
    groups=personalized_catalog(root,catalog,st.session_state.get('common_profile',{}))
    kinds=['전체']+sorted({r['kind'] for r in catalog})
    if st.session_state.get('catalog_kind') not in kinds:st.session_state.catalog_kind='전체'
    statuses=['전체','마감 전 · 시작일 확인','오늘 마감 · 시간 확인 필요','마감','시간대 확인 필요','상시 모집','예산 소진 시 종료','마감일 확인 필요','문서 간 마감 충돌','마감 조건 확인 필요','원문 갱신 확인 필요']
    if st.session_state.get('catalog_status') not in statuses:st.session_state.catalog_status='전체'
    with st.container(key='catalog_filters'):
        cols=st.columns([1,1.5,2])
        with cols[0]:kind=st.selectbox('종류',kinds,key='catalog_kind')
        with cols[1]:status=st.selectbox('접수 상태',statuses,key='catalog_status')
        with cols[2]:interest=st.text_input('관심 분야 검색',placeholder='교육, 장학, 공모전 등',key='catalog_search')
    view=st.radio('공고 보기',['목록 보기','캘린더 보기'],horizontal=True,key='catalog_view',label_visibility='collapsed')
    selected=filter_groups(groups,kind,status,interest)
    st.write(f'필터에 맞는 공고 {len(selected)}개 · 저장된 분석 결과 기준')
    st.button('내 정보 수정',on_click=route,args=('profile',),key='catalog_edit_profile')
    def draw(group,suffix=''):
        render_catalog_card(root,group,suffix)
    if view=='캘린더 보기':render_calendar(selected,draw)
    else:
        for group in selected:draw(group)
    if not selected:st.info('현재 필터에 맞는 분석 공고가 없습니다. 검색어 또는 접수 상태를 바꿔보세요.')


def render_catalog_card(root,group,suffix=''):
    import html
    from catalog import available_record
    from catalog_summary import public_summary
    from calendar_ui import render_deadline_details
    record=group['record']
    summary=public_summary(root,group)
    def fact(label,value):
        st.markdown('<p><strong>'+html.escape(label)+'</strong> · '+html.escape(value)+'</p>',unsafe_allow_html=True)
    def preview(key,limit=180):
        items=summary[key]
        if not items:return '원문 확인 필요'
        value=items[0]['text']
        if len(value)>limit:value=value[:limit].rstrip()+'…'
        if len(items)>1:value+=f' · 문서별 안내 {len(items)}건'
        return value
    with st.container(border=True):
        st.subheader(record['title'])
        for caution in group['cautions']:st.warning(caution)
        if not group['documents']:
            st.warning('원문 확보 또는 분석 미완료')
            st.link_button('공고 원문 보기',record['source_url'])
            return
        fact('관련 분야',summary['fields'] or '분야 정보 확인 필요')
        fact('주최·주관',preview('organizer'))
        fact('모집 대상 요약',preview('audience'))
        if summary['application']:fact('신청·접수 안내',preview('application',260))
        render_deadline_details(group)
        st.markdown('**상금·장학금·혜택**')
        if not summary['benefits']:
            st.write('금액·혜택 정보 확인 필요')
        for item in summary['benefits'][:2]:
            # Preserve amount scopes, recipient restrictions and payment stages.
            st.write(item['text'])
        if len(summary['benefits'])>2:st.write(f'혜택 안내 외 {len(summary["benefits"])-2}건 · 아래 상세에서 확인')
        with st.expander('기본 정보 자세히 · 출처'):
            for label,key in [('주최·주관','organizer'),('모집 대상','audience'),('신청·접수 안내','application'),('상금·장학금·혜택','benefits')]:
                for item in summary[key]:
                    fact(label,item['text'])
                    if len(group['documents'])>1:st.write('분석 문서: '+item['document'])
            st.write('원문 마지막 확인: '+(record.get('checked_at') or '확인 시점 미기록'))
            if record.get('coverage_note'):st.write(record['coverage_note'])
            for alias in group.get('source_aliases',[]):st.link_button('동일 문서를 게시한 다른 출처',alias)
        st.link_button('공고 원문 보기',record['source_url'])
        selected=record
        if len(group['documents'])>1:
            selected=st.selectbox('자세히 검토할 문서',group['documents'],format_func=lambda r:r.get('document_name',r['title']),key='catalog_document_'+record['id']+suffix)
        if st.button('이 공고 검토하기',key='catalog_'+record['id']+suffix,type='primary'):
            from browser_draft import single_snapshot
            state=available_record(root,selected)
            saved=st.session_state.get('workspaces',{}).get(state['source_hash'])
            activate(st.session_state,saved or single_snapshot(state))
            # Keep saved personal answers, while using the current public
            # grounding rules and server-owned execution trace for this hash.
            for field in ('notice','raw_notice','pages','notice_trace','notice_config','catalog_source','evidence_basis'):
                if field in state:st.session_state[field]=state[field]
            st.rerun()
