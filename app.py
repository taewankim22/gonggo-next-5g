import datetime as dt
import html
import json
import os
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
from core import read_pdf, fingerprint, validate_payload, guard_review, action_list
from schema_builder import notice_schema, review_schema
from upstage_client import run_agent as studio_run_agent, StudioError
from team_access import team_gate, protected_call
from pdf_tools import comparison_pdf
from input_tools import inspect_input, parse_pages, map_image_page
from prepare_demo import sample_review
from browser_draft import bootstrap, save_browser, clear_draft
from planning import question_keys, document_items, additional_questions, checklist_snapshot, next_steps, preparation_text, PREP_STATES, STAGES
from conditions import bind_answers, BASIC, LABELS, SOCIAL_QUESTION, social_document, social_answer, has_social
from independent_review import condition_rows
from source_context import UNKNOWN as UNKNOWN_STAGE
from workspaces import checkpoint, clear_active, seed_basic, explicit_basic
from profile_ui import entry, render_fact_overrides, navigation
from ui_components import render_preparation_summary, render_conditions, status_badge
from profiles import applied_facts, RULE_VERSION

ROOT=Path(__file__).parent
load_dotenv(ROOT/'.env')
st.set_page_config(page_title='공고다음 · 5G',page_icon='✨',layout='wide',initial_sidebar_state='collapsed')
st.html('<style>'+(ROOT/'ui.css').read_text(encoding='utf-8')+'</style>')
st.markdown('<div class="brandline"><div class="brandword">공고다음<span>YOUR NEXT OPPORTUNITY</span></div></div>',unsafe_allow_html=True)

settings=json.loads((ROOT/'settings.json').read_text(encoding='utf-8')) if (ROOT/'settings.json').exists() else {}
team,team_ledger=team_gate(ROOT,required=settings.get('team_required',False),password_required=settings.get('team_password_required',True))
def run_agent(*args,**kwargs):
    # This trace is server-session state, never accepted from a browser backup.
    # The original submission already counted; resuming only retrieves its job.
    if (kwargs.get('trace') or {}).get('job_id'):
        return studio_run_agent(*args,**kwargs)
    return protected_call(team,st.session_state,team_ledger,studio_run_agent,*args,**kwargs)

# Authenticate before restoring any browser draft or rendering app controls.
# Retain inputs independently of Streamlit's cleanup for hidden widgets.
for state_key in list(st.session_state):
    if state_key.startswith(('answer_', 'question_', 'doc_', 'fact_', 'catalog_document_')) or state_key in ('profile_preset','schedule_state','show_later_questions','catalog_kind','catalog_status','catalog_search','catalog_view','calendar_month','calendar_day','discovery_kinds'):
        st.session_state[state_key] = st.session_state[state_key]
bootstrap()
st.session_state.setdefault('screen', 1)
def go(screen):
    # A text edit and navigation click can arrive together. Finish collecting
    # step 3's widget values before the destination consumes draft_answers.
    if st.session_state.get('screen')==3 and screen!=3:
        st.session_state['_next_screen']=screen
        return
    st.session_state.screen = screen
    st.session_state.route = 'review'

def clear_answers():
    st.session_state.pop('_draft_restored',None)
    st.session_state.pop('situation_responses',None)
    for key in list(st.session_state):
        if key.startswith(('answer_', 'question_', 'doc_')) or key in ('profile_preset','schedule_state','show_later_questions','draft_answers','preparation','result','review_hash','profile','raw_review'):
            st.session_state.pop(key, None)

with st.sidebar:
    navigation()

from search_ui import render_search_settings
national_search_config=render_search_settings()

with st.sidebar.expander('설정 · 사용 모드와 Upstage 연결', expanded=False):
    st.markdown('### 공고다음')
    st.caption('5G · 나의 다음 기회')
    mode=st.radio('사용 모드',['실제 AI 분석','예시 화면 체험'],index=1 if st.session_state.get('last_mode')=='예시 화면 체험' else 0,help='예시는 사람이 작성한 조건 데이터와 고정 규칙을 사용합니다. API를 호출하지 않습니다.')
    if team:
        api_key=''
        notice_id,notice_version=team.notice_id,team.notice_version
        review_id,review_version=team.review_id,team.review_version
        st.info('운영자의 Upstage 연결을 사용합니다. API 키와 Agent 설정은 서버에서 관리합니다.')
        limit_note='하루 누적 호출 횟수 제한은 없습니다.' if team.daily_limit==0 else f'실패 요청 포함 하루 전체 {team.daily_limit}회로 제한합니다.'
        st.caption('공고 분석·맞춤 검토 각각 1회로 집계합니다. '+limit_note+' 동시 분석은 1건, 호출 간격은 10초입니다.'+(' 접속은 2시간 후 만료됩니다.' if team.require_password else ' 공개 테스트 중에는 암호 없이 이용할 수 있습니다.'))
    else:
        api_key=st.text_input('Upstage API 키',value='',type='password',help='현재 세션에서만 사용하며 파일에 저장하지 않습니다.')
        notice_id=st.text_input('공고 분석 Agent ID',value=os.getenv('NOTICE_AGENT_ID',settings.get('notice_agent_id','')))
        notice_version=st.text_input('공고 분석 설정 버전',value=os.getenv('NOTICE_CONFIG_ID',settings.get('notice_config_id','1')))
        review_id=st.text_input('맞춤 검토 Agent ID',value=os.getenv('REVIEW_AGENT_ID',settings.get('review_agent_id','')))
        review_version=st.text_input('맞춤 검토 설정 버전',value=os.getenv('REVIEW_CONFIG_ID',settings.get('review_config_id','1')))
        st.caption('키 값은 채팅·스크린샷에 포함하지 마세요. 입력한 키는 Upstage API 인증에만 사용됩니다.')
    if not team and os.getenv('GONGGO_DEVELOPER_TOOLS') == '1':
        with st.expander('공개 샘플 3건 실제 검증',expanded=False):
            st.caption('개발 검증용: 서로 다른 PDF·JPG·PNG 공개 자료와 가상 답변을 현재 두 Agent로 실행합니다. API 6회가 호출되며 비밀값 없는 실행 증거를 로컬 verification 폴더에 저장합니다. 예시 화면과 구분됩니다.')
            if st.button('현재 설정으로 3건 검증 시작'):
                try:
                    from verification_runner import run_public_checks
                    stage=st.empty()
                    st.session_state.batch_results=run_public_checks(api_key,notice_id,notice_version,review_id,review_version,stage.info)
                    stage.success('3건의 실제 분석과 맞춤검토가 완료되었습니다. 세부 결과와 원문을 확인하세요.')
                except (ValueError,StudioError) as exc:st.error(str(exc))
            for i,res in enumerate(st.session_state.get('batch_results',[]),1):
                info=inspect_input((ROOT/'data'/res['source_filename']).read_bytes(),res['source_filename'])
                source_pages=info['pages'] or parse_pages(res['notice_execution']['steps'])
                res['cards']=guard_review(res['notice'],res['answers'],res['raw_review'],source_pages)
                st.write(f'**샘플 {i} · {res["notice"]["notice_title"]}**')
                st.caption(f'공고 설정 {res["notice_execution"]["config_id"]} / 검토 설정 {res["review_execution"]["config_id"]} · {res["source_filename"]}')
                st.table([{'검토 항목':c['title'],'상태':c['status'],'인용 일치':c['verified'],'다음 행동':c['action']} for c in res['cards']])
                with st.expander(f'샘플 {i} 원문과 상세 근거'):
                    for c in res['cards']:
                        st.write(c['title']+' · '+c['reason']);st.text(c['quote'] or '문서에 조건이 명시되지 않음')
                        for extra in c.get('supporting_quotes',[]):st.text('추가 원문 '+extra['page']+'쪽: '+extra['quote'])
                    if res['source_filename'].lower().endswith(('.jpg','.png')):st.image(str(ROOT/'data'/res['source_filename']),use_container_width=True)
                    st.download_button(f'샘플 {i} 실행 결과 저장',json.dumps(res,ensure_ascii=False,indent=2),f'sample{i}.actual.json','application/json')
    st.divider()
    st.caption('공고 원본·추출 내용·답변·체크는 이 브라우저에 자동 저장합니다. 같은 주소로 다시 접속하면 복원됩니다. API 키와 팀 암호는 브라우저에 저장하지 않습니다. AI 상세 검토 결과도 자동 저장하지 않습니다. 공용 컴퓨터에서는 사용 후 지워주세요.')
    st.button('저장한 공고·답변·체크 지우기',on_click=clear_draft)
    st.caption('다른 기기·브라우저나 다른 사이트 주소로 자동 동기화하지 않습니다. 브라우저 데이터 삭제 시 저장 내용도 사라집니다.')
    st.caption('직접 올린 파일·답변은 서버의 공용 저장소에 기록하지 않습니다. 인터넷에서 가져온 공개 공고의 분석은 공용 목록에 저장합니다. 실제 분석 시 원본 파일과 답변이 Upstage로 전달됩니다.')
    st.caption('조건 검토 도구이며 지원 자격·선발 결과를 확정하지 않습니다.')

if st.session_state.get('last_mode')!=mode:
    checkpoint(st.session_state)
    for k in ['notice','raw_notice','result','pages','pdf','profile','source_hash','review_hash','review_pdf','source_info','source_filename','notice_trace','review_trace','raw_review','evidence_basis']:
        st.session_state.pop(k,None)
    clear_answers()
    st.session_state.screen=1
    st.session_state.pop('pending_file',None)
    st.session_state.pop('_notice_request',None)
    st.session_state.last_mode=mode

def discovery_runner(data,filename,info,progress,trace):
    return run_agent(team.api_key if team else api_key,notice_id,notice_version,data,filename,progress,mime=info['mime'],trace=trace)

if st.session_state.get('route')=='catalog':
    # Render browser persistence before a potentially long discovery batch.
    checkpoint(st.session_state)
    save_browser()
if entry(ROOT,{'enabled':mode=='실제 AI 분석' and bool(team or api_key),'agent_id':notice_id,'version':notice_version,'runner':discovery_runner,'search_config':national_search_config}):
    checkpoint(st.session_state)
    if st.session_state.get('route')!='catalog':save_browser()
    st.stop()

if 'notice' not in st.session_state:st.session_state.screen=1
screen=st.session_state.screen
labels=['공고 넣기','핵심 확인','내 상황','준비 목록']
if mode=='예시 화면 체험':st.caption('예시 체험 중 · API를 호출하지 않는 연습용 결과입니다.')
with st.container(key='wizard_nav'):
    for col,number,label in zip(st.columns(4),range(1,5),labels):
        col.button(f'{number:02d} {label}',key=f'nav_{number}',type='primary' if number==screen else 'secondary',use_container_width=True,
                   disabled=(number>1 and 'notice' not in st.session_state) or (number==4 and screen!=3 and 'draft_answers' not in st.session_state),on_click=go,args=(number,))
if screen==1:
    st.markdown('<div class="hero"><div class="hero-body"><h1>발견한 기회를,<br>나의 다음으로.</h1><p>공고를 올리면 필요한 조건과 준비할 서류를 정리해 드려요.</p></div><div class="feed-footer">PDF · HWP · HWPX · JPG · PNG</div></div>',unsafe_allow_html=True)
    st.subheader('01 / 어떤 공고가 궁금한가요?')
    if mode=='예시 화면 체험':
        st.info('API 호출 없는 예시입니다. 사람이 작성한 조건 데이터와 고정 규칙을 사용합니다.')
        data=(ROOT/'data/hyundai_jump_13.pdf').read_bytes()
        filename='hyundai_jump_13.pdf'
        st.write('**2026 현대점프스쿨 13기** · 마감된 평가용 공고')
        if st.button('예시 공고 살펴보기',type='primary',use_container_width=True):
            checkpoint(st.session_state);clear_active(st.session_state)
            st.session_state.update(notice=json.loads((ROOT/'data/demo_notice.json').read_text(encoding='utf-8')),
              pages=read_pdf(data),pdf=data,source_hash=fingerprint(data),source_filename=filename,last_mode=mode)
            clear_answers();go(2);st.rerun()
    else:
        upload=st.file_uploader('공고문 PDF·한글(HWP/HWPX) 또는 포스터 이미지',type=['pdf','hwp','hwpx','jpg','jpeg','png'],key='notice_upload_'+str(st.session_state.get('_upload_generation',0)),help='15MB 이하. PDF 30페이지 이하. 한글은 암호·배포용 보호 없는 HWP 5.x/HWPX. 이미지는 가로·세로 200px 이상, 3천만 화소 이하. 공개 문서 또는 분석 권한이 있는 파일만 사용하세요.')
        if upload is not None:
            st.session_state.pending_file={'data':upload.getvalue(),'name':upload.name}
        saved=st.session_state.get('pending_file')
        # Existing analyzed originals remain available when the uploader is unmounted.
        if not saved and st.session_state.get('pdf'):
            saved={'data':st.session_state.pdf,'name':st.session_state.get('source_filename','공고원문.pdf')}
        use_example=st.checkbox('공개 평가용 공고 사용: 현대점프스쿨 13기',value=False,key='answer_use_example')
        data=(ROOT/'data/hyundai_jump_13.pdf').read_bytes() if use_example else saved['data'] if saved else None
        filename='hyundai_jump_13.pdf' if use_example else saved['name'] if saved else ''
        if data:st.caption('선택한 파일: '+filename)
        if upload is not None and not use_example and filename.lower().endswith(('.hwp','.hwpx')):
            st.info('한글 파일 원본을 Upstage로 전달해 분석합니다. 분석 후 읽어낸 본문을 확인할 수 있습니다. 원본 배치는 한글에서 확인해주세요. 긴 문서는 필요한 공고 페이지만 PDF로 저장하면 더 빠르게 분석할 수 있습니다.')
        if upload is not None and not use_example and filename.lower().endswith(('.jpg','.jpeg','.png')):
            try:
                inspect_input(data,filename)
                st.image(data,caption='업로드한 원본 포스터',use_container_width=True)
            except ValueError as exc:st.error(str(exc))
        st.caption('공개 예시 공고는 2026년 1월 마감 자료로, 분석 검증에 사용합니다.')
        requested=st.button('공고에서 조건 찾기',type='primary',use_container_width=True,disabled=not data)
        pending=st.session_state.get('_notice_request')
        if requested or pending:
            # Replace the current notice only after a successful analysis.
            try:
                if pending:
                    data,filename=pending['data'],pending['filename']
                    notice_id,notice_version=pending['agent_id'],pending['config_id']
                info=inspect_input(data,filename); pages=info['pages']; trace=pending['trace'] if pending else {}
                progress=st.empty()
                from catalog import cached_public
                cached=None if pending else cached_public(ROOT,fingerprint(data),notice_id,notice_version)
                if cached:
                    n=cached['notice'];trace=cached.get('notice_trace',{});pages=cached['pages']
                    progress.info('동일한 공개 원문·설정 버전의 분석을 재사용했습니다.')
                else:
                    if not pending:
                        st.session_state['_notice_request']={'data':data,'filename':filename,'agent_id':notice_id,'config_id':notice_version,'trace':trace}
                    n=run_agent(api_key,notice_id,notice_version,data,filename,progress.info,mime=info['mime'],trace=trace)
                n=validate_payload(n,notice_schema())
                ocr_pages=parse_pages(trace.get('steps',[]))
                if not any(pages) or (n.get('_structured_notice') and any(ocr_pages)):pages=ocr_pages
                from workflow_adapter import ground_notice
                n=ground_notice(n,pages)
                from workspaces import retain_same_document_inputs
                retained=retain_same_document_inputs(st.session_state,fingerprint(data))
                checkpoint(st.session_state);clear_active(st.session_state);clear_answers()
                st.session_state.update(notice=map_image_page(n,info),raw_notice=dict(n),pages=pages,pdf=data,source_hash=fingerprint(data),source_info=info,source_filename=filename,notice_trace=trace,evidence_basis='Studio Parse 변환 본문' if n.get('_structured_notice') and any(ocr_pages) else 'PDF 텍스트' if info['pages'] and any(info['pages']) else 'Studio Parse 변환 본문' if info['kind']=='hangul' else 'Studio Parse OCR')
                st.session_state.update(last_mode=mode,notice_config={'agent_id':notice_id,'config_id':notice_version})
                from datetime import datetime,timezone
                st.session_state.catalog_source={'analyzed_at':cached.get('catalog_source',{}).get('analyzed_at','') if cached else datetime.now(timezone.utc).isoformat()}
                st.session_state.update(retained)
                go(2);st.session_state.pop('_notice_request',None);st.rerun()
            except (ValueError,StudioError) as exc:
                st.session_state.pop('_notice_request',None)
                st.error(str(exc))
    if 'notice' in st.session_state:
        st.button('분석한 공고 계속 보기 →',on_click=go,args=(2,),use_container_width=True)

if screen in (2,3,4) and st.session_state.get('notice'):
    from workflow_adapter import ground_notice
    st.session_state.notice = ground_notice(st.session_state.notice,st.session_state.get('pages',[]))

if screen==3 and st.session_state.get('notice',{}).get('_schema_limits'):
        st.warning(st.session_state.notice['_schema_limits'])

if screen==2:
    if 'notice' in st.session_state:
        if 'raw_notice' not in st.session_state:st.session_state.raw_notice=dict(st.session_state.notice)
        st.session_state.notice=map_image_page(st.session_state.notice,st.session_state.get('source_info',{}))
        n=st.session_state.notice
        from notice_overview import render_overview
        overview=render_overview(n,st.session_state.pages,st.session_state.get('catalog_source'))
        with st.container(key='overview_next'):
            st.button('내 상황 입력하기 →',type='primary',on_click=go,args=(3,),use_container_width=True)
        st.button('← 공고 넣기로',on_click=go,args=(1,))
        with st.expander('원문과 근거 확인',expanded=False):
            st.download_button('원본 다운로드',st.session_state.pdf,st.session_state.get('source_filename','공고원문.pdf'),st.session_state.get('source_info',{}).get('mime','application/pdf'))
            notice_export={'source_filename':st.session_state.get('source_filename'),'source_sha256':st.session_state.source_hash,'source_info':st.session_state.get('source_info',{}),'notice':n,'raw_notice':st.session_state.get('raw_notice'),'notice_execution':st.session_state.get('notice_trace',{}),'evidence_basis':st.session_state.get('evidence_basis','예시 데이터')}
            st.download_button('공고 추출 결과 저장 (JSON)',json.dumps(notice_export,ensure_ascii=False,indent=2),'5G_공고다음_공고추출.json','application/json')
            st.caption('추출값은 AI 또는 예시 데이터입니다. 원문 인용의 정확성은 검토 카드에서 따로 표시합니다.')
            source=st.session_state.get('catalog_source',{})
            if source.get('url'):st.link_button('공고 원문 보기',source['url'])
            if source.get('checked_at'):st.write('원문 마지막 확인: '+source['checked_at'])
            if source.get('coverage_note'):st.write(source['coverage_note'])
            if not any(st.session_state.pages):st.write('대조할 원문 본문이 없습니다. 원본 파일에서 직접 확인해주세요.')
            if overview['dates']['evidence']:
                st.markdown('**접수 일정 근거**')
                for event in overview['dates']['evidence']:
                    st.write(event['stage']+' · '+event['page']+'쪽')
                    st.text(event['quote'])
                    st.write(event['timezone_basis'])
            if n.get('deadline_note'):st.write(n['deadline_note'])
            if n.get('_schema_limits'):st.write(n['_schema_limits'])
            conflicts=[c for c in n.get('source_conflicts',[]) if not n.get('_schema_limits') or not c.startswith(n['_schema_limits'])]
            if conflicts:
                st.markdown('**원문 유의사항과 추후 공지**')
                for conflict in conflicts:st.write(conflict)
            if st.session_state.get('source_info',{}).get('kind')=='hangul':
                st.caption('아래는 Studio Parse가 읽어낸 본문입니다. 표 배치와 페이지 번호는 원본과 다를 수 있습니다.')
                for page_number,page_text in enumerate(st.session_state.pages,1):
                    st.text(f'변환 본문 {page_number}페이지\n{page_text}')
        with st.expander('상세 조건 확인',expanded=False):
            if n.get('_structured_notice'):
                for title in ('지원조건','제출서류','일정','혜택'):
                    entries=n['_structured_notice'].get(title,[])
                    if entries:
                        st.write('**'+title+'**')
                        from core import evidence
                        checked=[{**r,'인용 대조':'본문에서 확인' if evidence(r.get('근거원문',''),r.get('근거페이지',''),st.session_state.pages) else '원문 직접 확인 필요'} for r in entries]
                        if title=='혜택':
                            from notice_facts import benefit_rows
                            checked=[{**r,'검토 상태':'금액·근거 확인 / 지급 인원·단위 추가 확인' if r['verified'] and r['scope_pending'] else '본문 대조 완료' if r['verified'] else '금액·인용 대조 필요'} for r in benefit_rows(n,st.session_state.pages)]
                        st.dataframe(checked,hide_index=True,use_container_width=True)
            else:
                for k,label in [('eligibility','지원 대상'),('preference','우대조건'),('commitment','활동 의무'),('documents','제출서류'),('schedule','일정')]:
                    st.markdown('**'+label+'**');st.write(n.get(k+'_rule') or '원문 확인 필요')
            if n.get('_workflow_review'):
                st.markdown('**AI 요약 · 원문 대조 필요**')
                st.caption('AI 요약의 날짜·금액·자격은 원문과 대조해주세요. 개인의 지원 자격을 확정한 결과는 아닙니다.')
                st.markdown(n['_workflow_review'])

if screen==3:
    from situation_ui import render_situation
    render_situation(st.session_state.notice,st.session_state.pages,mode,go)
    if '_next_screen' in st.session_state:
        st.session_state.screen=st.session_state.pop('_next_screen')
        st.session_state.route='review'
        st.rerun()

if screen==4:
        from preparation_ui import render_preparation
        n=st.session_state.notice
        a,rows,steps,prepared_text=render_preparation(ROOT,{'enabled':mode=='실제 AI 분석' and bool(team or api_key),
            'agent_id':notice_id,'version':notice_version,'runner':discovery_runner},go)
        current=fingerprint({'logic_version':RULE_VERSION,'source':st.session_state.source_hash,'answers':a,'mode':mode,'review_agent':review_id,'version':review_version})
        if st.session_state.get('review_hash')!=current:st.session_state.pop('result',None)
        with st.expander('추가 AI 검토·준비 목록 저장'):
            st.download_button('내 준비 목록 저장 (TXT)',prepared_text,'5G_공고다음_준비목록.txt','text/plain')
            st.write('추가 AI 검토 시 현재 문서의 조건과 답변·준비 상태를 Upstage로 전달합니다. 자료별 근거와 함께 확인해주세요.')
            if st.button('AI로 추가 검토하기',key='prep_ai_review',use_container_width=True):
                st.session_state.pop('result',None)
                try:
                    from preparation_model import selected_review_answers
                    a=selected_review_answers(a,n,st.session_state.pages,st.session_state.draft_answers.get('other_facts',''))
                    if mode=='예시 화면 체험':raw=sample_review(n,a)
                    else:
                        pdf=comparison_pdf(n,a);st.session_state.review_pdf=pdf
                        progress=st.empty();review_trace={}
                        raw=run_agent(api_key,review_id,review_version,pdf,'comparison.pdf',progress.info,trace=review_trace)
                        st.session_state.review_trace=review_trace
                        raw=validate_payload(raw,review_schema());progress.empty()
                    cards=guard_review(n,a,raw,st.session_state.pages)
                    st.session_state.update(result=cards,profile=a,review_hash=current,raw_review=raw)
                    st.rerun()
                except (ValueError,StudioError) as exc:st.error(str(exc))

if screen==4 and 'result' in st.session_state:
    st.session_state.result=guard_review(st.session_state.notice,st.session_state.profile,st.session_state.raw_review,st.session_state.pages)
    st.divider(); st.subheader('AI 상세 검토 · 원문 근거')
    cards=st.session_state.result
    cols=st.columns(3)
    for col,(title,status) in zip(cols,[('먼저 조정할 조건','불일치'),('추가 확인할 조건','확인 필요'),('원문에서 찾은 인용',None)]):
        col.metric(title,sum(c['status']==status for c in cards) if status else f"{sum(c['verified'] for c in cards)} / {len(cards)}")
    st.caption('‘일치’는 해당 항목만의 대조 결과입니다. 전체 지원 자격이나 선발 가능성을 뜻하지 않습니다.')
    st.caption('위 지금 할 일과 함께 확인하세요. AI 대조 후 답변이나 체크 상태를 바꾸면 이전 대조 결과는 숨겨집니다.')
    for c in cards:
        def esc(value):
            text=str(value)
            for key,label in {'USER_ANSWERS':'내 답변','NOTICE':'공고','document_checklist':'제출물 체크리스트','question_answers':'질문별 답변','condition_answers':'조건별 답변','condition_id':'연결된 조건','preference_facts':'우대 대상 답변','social_support':'사회적 배려 대상 여부','deferred_questions':'이후 단계 질문','readiness':'준비 상태','applicability':'적용 대상','enrollment_status':'학적','other_facts':'추가 답변','review_stage':'지원 단계','unavailable_dates':'참석 불가 일정'}.items():text=text.replace(key,label)
            return html.escape(text)
        color={'불일치':'#f9e8df','확인 필요':'#f8f1d9','일치':'#e2efdf','해당 없음':'#edf0ed'}[c['status']]
        st.markdown(f'<div class="review-card"><span class="badge" style="background:{color}">{esc(c["status"])}</span><h3>{esc(c["title"])}</h3><p>{esc(c["reason"])}</p><p class="action">다음 행동 · {esc(c["action"])}</p></div>',unsafe_allow_html=True)
        with st.expander(f'{c["title"]} — 원문 근거 {"확인됨" if c["verified"] else "직접 확인 필요"}'):
            st.caption(f'원본 {c["page"] or "미확인"}페이지 · {st.session_state.get("evidence_basis","PDF 텍스트")}와 대조. OCR·인용 일치는 의미의 정확성을 보장하지 않습니다.')
            if st.session_state.get('source_info',{}).get('kind')=='image':st.caption('단일 이미지 원본은 앱이 1페이지로 연결합니다. Agent가 추출한 페이지 번호와 구분해 저장합니다.')
            if not c['verified'] and c['quote']:st.caption('아래는 AI의 인용 후보이며, 원문의 연속 문장으로 확인되지 않았습니다.')
            st.text(c['quote'] or '인용문이 없습니다.')
            for question in c.get('linked_questions',[]):
                st.caption('연결된 질문 · '+question['text']+' / 답변: '+str(question.get('answer') if question.get('answer') not in (None,'') else '미입력 · 확인 필요'))
            for extra in c.get('supporting_quotes',[]):
                st.caption('추가 원문 구간 · '+extra['page']+'페이지 · '+extra['basis']);st.text(extra['quote'])
            if c.get('model_quote_changed'):st.caption('맞춤검토가 재출력한 인용과 차이가 있어 최초 공고 추출 인용을 표시합니다.')
            try:
                import pypdfium2 as pdfium
                if st.session_state.get('source_info',{}).get('kind')=='image':
                    st.image(st.session_state.pdf,caption='원본 포스터 · 인식한 글자를 직접 확인하세요',use_container_width=True)
                elif st.session_state.get('source_info',{}).get('kind')=='hangul':
                    st.caption('한글 원본 미리보기는 지원하지 않습니다. 위 원본 다운로드로 배치를 확인하세요. 아래는 Studio 변환 본문이며 원본 페이지와 다를 수 있습니다.')
                    if c['page'].isdigit() and 1<=int(c['page'])<=len(st.session_state.pages):
                        st.text(st.session_state.pages[int(c['page'])-1])
                elif c['page'].isdigit() and 1<=int(c['page'])<=len(st.session_state.pages):
                    doc=pdfium.PdfDocument(st.session_state.pdf)
                    page=doc[int(c['page'])-1]; bitmap=page.render(scale=1.4)
                    st.image(bitmap.to_pil(),caption='원본 공고',use_container_width=True)
                    bitmap.close();page.close();doc.close()
            except Exception:st.caption('미리보기를 열지 못했습니다. 원본 파일을 다운로드해 확인하세요.')
    exported={'mode':mode,'source_sha256':st.session_state.source_hash,'notice':st.session_state.notice,'raw_notice':st.session_state.get('raw_notice'),'answers':st.session_state.profile,'cards':cards,'preparation':st.session_state.get('preparation',{}),'next_actions':st.session_state.get('preparation',{}).get('next_actions',[]),'raw_review':st.session_state.get('raw_review'), 'notice_execution':st.session_state.get('notice_trace',{}),'review_execution':st.session_state.get('review_trace',{}),'evidence_basis':st.session_state.get('evidence_basis','PDF 텍스트'),'page_mapping':'단일 이미지의 빈 페이지 번호는 앱에서 1로 연결' if st.session_state.get('source_info',{}).get('kind')=='image' else 'Agent 추출 번호'}
    st.download_button('내 검토 결과 저장 (JSON)',json.dumps(exported,ensure_ascii=False,indent=2),'5G_공고다음_검토결과.json','application/json')
if screen==4:
    st.button('← 내 상황 수정하기',on_click=go,args=(3,),use_container_width=True)
st.divider(); st.caption('공고다음 · 공고 속 조건을, 내 다음 행동으로. | 5G 해커톤 프로토타입')


# Scroll only on screen changes, never while editing a field or checkbox.
if st.session_state.get('rendered_screen') != screen:
    st.html("""<script>
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const main = document.querySelector('[data-testid="stMain"]');
      if (main) main.scrollTo({top: 0, behavior: 'instant'});
    }));
    </script>""", unsafe_allow_javascript=True)
    st.session_state.rendered_screen=screen

if screen in (3,4):
    from ui_focus import render_focus
    render_focus()
checkpoint(st.session_state)
save_browser()
