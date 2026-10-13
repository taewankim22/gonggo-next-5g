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
from profile_ui import entry, render_fact_overrides
from profiles import applied_facts, RULE_VERSION

ROOT=Path(__file__).parent
load_dotenv(ROOT/'.env')
st.set_page_config(page_title='공고다음 · 5G',page_icon='✨',layout='wide')
st.markdown('''<style>
:root{--ink:#171717;--muted:#666;--line:#e8e8e8;--pink:#c92873;--insta:linear-gradient(120deg,#f6a13a 0%,#e33c68 42%,#bb2d9a 70%,#6c42ce 100%)}
.stApp{background:#fafafa;color:var(--ink)}
.block-container{max-width:980px;padding-top:4.5rem;padding-bottom:4rem}
header[data-testid="stHeader"]{background:#fafafaf0;border-bottom:1px solid var(--line)}
[data-testid="stSidebar"]{background:white;border-right:1px solid var(--line)}
h1,h2,h3{color:var(--ink);letter-spacing:-.055em}
h1{font-size:clamp(1.8rem,3.5vw,2.65rem)!important;line-height:1.3!important;font-weight:800!important}
h3{font-size:1.28rem!important;margin-top:1rem!important}
p,label{line-height:1.65}
a{color:#8430ac}
a:focus-visible,button:focus-visible{outline:3px solid #8430ac!important;outline-offset:4px}
.brandline{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 0 20px;margin-bottom:22px;border-bottom:1px solid var(--line)}
.brandword{font-size:1.45rem;font-weight:850;letter-spacing:-.08em;color:#161616}
.brandword span{display:block;font-size:.68rem;font-weight:600;letter-spacing:.11em;color:#666;margin-top:2px}
.brandnote{font-size:.75rem;color:#666;white-space:nowrap}
.story-nav{display:flex;justify-content:space-between;gap:12px;max-width:440px;margin:0 auto 26px}
.story-nav a{text-decoration:none;color:#333;text-align:center;font-size:.75rem;font-weight:650;min-width:58px}
.story-ring{display:grid;place-items:center;width:64px;height:64px;padding:3px;margin:0 auto 8px;border-radius:50%;background:var(--insta);transition:transform .15s ease}
.story-ring span{display:grid;place-items:center;width:100%;height:100%;border:3px solid white;border-radius:50%;background:#fff5f9;color:#9a235c;font-size:1rem;font-weight:800}
.story-nav a:hover .story-ring{transform:translateY(-3px)}
.hero{background:white;border:1px solid var(--line);border-radius:18px;overflow:hidden;margin-bottom:1.4rem}
.feed-header{display:flex;align-items:center;gap:10px;padding:15px 20px;border-bottom:1px solid #f0f0f0}
.avatar{display:grid;place-items:center;width:38px;height:38px;border-radius:50%;background:var(--insta);color:white;font-weight:850;font-size:.8rem;flex-shrink:0}
.feed-name{font-size:.85rem;font-weight:750;color:#171717}.feed-name small{display:block;font-size:.7rem;color:#777;font-weight:400;margin-top:1px}
.feed-tag{margin-left:auto;border:1px solid #eeddea;color:#9d347c;border-radius:20px;padding:4px 10px;font-size:.68rem;font-weight:700;white-space:nowrap}
.hero-body{padding:28px 26px 24px;background:linear-gradient(135deg,#fff7ec 0%,#fff3f7 50%,#f8f3ff 100%)}
.hero-body p{font-size:.94rem;color:#57505a;margin:14px 0 0;line-height:1.75}
.feed-footer{padding:12px 20px;color:#666;font-size:.76rem}.feed-footer b{color:#b12d77;font-weight:650}
.steps{color:#777;font-size:.8rem;margin-bottom:1.4rem}
[data-testid="stFileUploader"]{background:#fff;border:1px solid var(--line);border-radius:16px;padding:12px}
[data-testid="stFileUploaderDropzone"]{background:#fff8fb;border:1px dashed #d7adc5;border-radius:12px}
[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input{background:#fafafa!important;color:#171717!important}
[data-baseweb="select"]>div{background:#fff!important;border-color:#ddd!important;border-radius:10px!important;color:#171717!important}
[data-testid="stButton"] button,[data-testid="stDownloadButton"] button{border-radius:11px;transition:filter .15s ease;font-weight:650}
button[kind="primary"],[data-testid="stBaseButton-primary"]{background:linear-gradient(110deg,#c52a63,#a32b9c,#6940c9)!important;border:0!important;color:white!important;min-height:46px}
button[kind="primary"]:hover{filter:brightness(.94)}
button[kind="secondary"],[data-testid="stBaseButton-secondary"]{background:white;border-color:#dedede;color:#272727}
[data-testid="stExpander"]{background:white;border:1px solid var(--line);border-radius:12px}
[data-testid="stCaptionContainer"]{color:#6a6a6a}
.review-card{background:white;border:1px solid var(--line);border-radius:16px;padding:1.3rem;margin:.7rem 0;box-shadow:0 3px 14px #24112a05}
.badge{padding:4px 10px;border-radius:20px;font-size:.75rem;font-weight:700;float:right;color:#353035}
.review-card h3{font-size:1.08rem!important;margin:0 0 .8rem!important}.review-card p{line-height:1.75;font-size:.94rem;margin:.5rem 0}
.action{border-top:1px solid #f0e8ef;padding-top:.8rem;color:#98265f}.small{font-size:.78rem;color:#777}
[data-testid="stMetric"]{background:white;border:1px solid var(--line);border-radius:14px;padding:12px}
[data-testid="stMetricValue"]{color:#a42b75}
hr{border-color:var(--line)}
.st-key-wizard_nav button{min-height:48px;font-size:.85rem}
.st-key-wizard_nav button *{white-space:normal!important;overflow:visible!important;text-overflow:clip!important;font-size:inherit!important}
[data-testid="stCaptionContainer"] p{color:#666!important}
[data-testid="stCheckbox"] label{padding:8px 0;min-height:44px}
.review-card,.stMarkdown{overflow-wrap:anywhere}
.condition-row{display:grid;grid-template-columns:2fr 1.2fr 1fr;gap:12px;align-items:start;background:white;border:1px solid #e8e8e8;border-radius:12px;padding:14px;color:#252525}
.condition-row small{display:block;color:#555;margin-top:5px}.condition-row .badge{float:none;display:inline-block}
@media(max-width:640px){.condition-row{grid-template-columns:1fr}.condition-row small{font-size:.8rem}}
@media(max-width:640px){.st-key-wizard_nav [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:5px!important}.st-key-wizard_nav [data-testid="stColumn"]{min-width:0!important;flex:1!important}.st-key-wizard_nav button{padding:6px!important;font-size:.75rem!important}.block-container{padding-top:3.8rem}.brandline{margin-bottom:10px;padding-bottom:12px}}

@media(max-width:640px){.block-container{padding-left:1rem;padding-right:1rem}.hero-body{padding:23px 18px}.story-ring{width:54px;height:54px}.brandnote{display:none}.feed-tag{font-size:.62rem;padding:3px 8px}}
@media(prefers-reduced-motion:reduce){.story-ring,button{transition:none!important}}
</style>''',unsafe_allow_html=True)

settings=json.loads((ROOT/'settings.json').read_text(encoding='utf-8')) if (ROOT/'settings.json').exists() else {}
team,team_ledger=team_gate(ROOT,required=settings.get('team_required',False),password_required=settings.get('team_password_required',True))
def run_agent(*args,**kwargs):
    return protected_call(team,st.session_state,team_ledger,studio_run_agent,*args,**kwargs)

# Authenticate before restoring any browser draft or rendering app controls.
# Retain inputs independently of Streamlit's cleanup for hidden widgets.
for state_key in list(st.session_state):
    if state_key.startswith(('answer_', 'question_', 'doc_', 'fact_')) or state_key in ('profile_preset','schedule_state','show_later_questions'):
        st.session_state[state_key] = st.session_state[state_key]
bootstrap()
st.session_state.setdefault('screen', 1)
def go(screen):
    st.session_state.screen = screen
    st.session_state.route = 'review'

def clear_answers():
    st.session_state.pop('_draft_restored',None)
    for key in list(st.session_state):
        if key.startswith(('answer_', 'question_', 'doc_')) or key in ('profile_preset','schedule_state','show_later_questions','draft_answers','preparation','result','review_hash','profile','raw_review'):
            st.session_state.pop(key, None)

st.markdown('<div class="brandline"><div class="brandword">공고다음<span>YOUR NEXT OPPORTUNITY</span></div><div class="brandnote">나에게 맞는 기회, 준비하는 방법.</div></div>',unsafe_allow_html=True)

with st.expander('설정 · 사용 모드와 Upstage 연결', expanded=False):
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
    st.caption('파일·답변은 서버의 공용 저장소에 기록하지 않습니다. 실제 분석 시 원본 파일과 답변이 Upstage로 전달됩니다.')
    st.caption('조건 검토 도구이며 지원 자격·선발 결과를 확정하지 않습니다.')

if st.session_state.get('last_mode')!=mode:
    checkpoint(st.session_state)
    for k in ['notice','raw_notice','result','pages','pdf','profile','source_hash','review_hash','review_pdf','source_info','source_filename','notice_trace','review_trace','raw_review','evidence_basis']:
        st.session_state.pop(k,None)
    clear_answers()
    st.session_state.screen=1
    st.session_state.pop('pending_file',None)
    st.session_state.last_mode=mode

if entry(ROOT):
    checkpoint(st.session_state)
    save_browser()
    st.stop()

if 'notice' not in st.session_state:st.session_state.screen=1
screen=st.session_state.screen
labels=['공고 넣기','핵심 확인','내 상황','준비 목록']
st.caption(f'{screen} / 4 단계 · 단계 이동 시 파일과 입력을 유지합니다.')
if mode=='예시 화면 체험':st.caption('예시 체험 중 · API를 호출하지 않는 연습용 결과입니다.')
with st.container(key='wizard_nav'):
    for col,number,label in zip(st.columns(4),range(1,5),labels):
        col.button(f'{number:02d} {label}',key=f'nav_{number}',type='primary' if number==screen else 'secondary',use_container_width=True,
                   disabled=(number>1 and 'notice' not in st.session_state) or (number==4 and screen!=3 and 'draft_answers' not in st.session_state),on_click=go,args=(number,))
st.progress(screen/4)
if st.session_state.get('_draft_restored'):
    st.caption('저장된 준비 내용을 복원했습니다.' if team else '저장된 준비 내용을 복원했습니다. 새 AI 분석에는 API 키를 다시 입력하세요.')
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
        if st.button('공고에서 조건 찾기',type='primary',use_container_width=True,disabled=not data):
            # Replace the current notice only after a successful analysis.
            try:
                info=inspect_input(data,filename); pages=info['pages']; trace={}
                progress=st.empty()
                from catalog import cached_public
                cached=cached_public(ROOT,fingerprint(data),notice_id,notice_version)
                if cached:
                    n=cached['notice'];trace=cached.get('notice_trace',{});pages=cached['pages']
                    progress.info('동일한 공개 원문·설정 버전의 분석을 재사용했습니다.')
                else:n=run_agent(api_key,notice_id,notice_version,data,filename,progress.info,mime=info['mime'],trace=trace)
                n=validate_payload(n,notice_schema())
                ocr_pages=parse_pages(trace.get('steps',[]))
                if not any(pages) or (n.get('_structured_notice') and any(ocr_pages)):pages=ocr_pages
                from workflow_adapter import ground_notice
                n=ground_notice(n,pages)
                checkpoint(st.session_state);clear_active(st.session_state);clear_answers()
                st.session_state.update(notice=map_image_page(n,info),raw_notice=dict(n),pages=pages,pdf=data,source_hash=fingerprint(data),source_info=info,source_filename=filename,notice_trace=trace,evidence_basis='Studio Parse 변환 본문' if n.get('_structured_notice') and any(ocr_pages) else 'PDF 텍스트' if info['pages'] and any(info['pages']) else 'Studio Parse 변환 본문' if info['kind']=='hangul' else 'Studio Parse OCR')
                st.session_state.update(last_mode=mode,notice_config={'agent_id':notice_id,'config_id':notice_version})
                progress.empty();go(2);st.rerun()
            except (ValueError,StudioError) as exc: st.error(str(exc))
    if 'notice' in st.session_state:
        st.button('분석한 공고 계속 보기 →',on_click=go,args=(2,),use_container_width=True)

if screen==2:
    st.subheader('02 / 이 공고의 핵심')
    if 'notice' in st.session_state:
        if 'raw_notice' not in st.session_state:st.session_state.raw_notice=dict(st.session_state.notice)
        st.session_state.notice=map_image_page(st.session_state.notice,st.session_state.get('source_info',{}))
        n=st.session_state.notice
        st.write('**'+n['notice_title']+'**')
        if not any(st.session_state.pages):st.warning('대조할 원문 본문이 없습니다. 인용과 조건은 원본 파일에서 직접 확인해주세요.')
        if n['application_deadline']:
            st.caption('공고상 접수 마감: '+n['application_deadline'])
            try:
                if dt.date.fromisoformat(n['application_deadline'])<dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date():st.warning('마감된 공고입니다. 조건 검증·연습용으로 확인하세요.')
            except ValueError: st.warning('마감일 형식을 확인하지 못했습니다. 원문을 확인하세요.')
        with st.expander('원본과 추출된 조건',expanded=False):
            st.download_button('원본 다운로드',st.session_state.pdf,st.session_state.get('source_filename','공고원문.pdf'),st.session_state.get('source_info',{}).get('mime','application/pdf'))
            notice_export={'source_filename':st.session_state.get('source_filename'),'source_sha256':st.session_state.source_hash,'source_info':st.session_state.get('source_info',{}),'notice':n,'raw_notice':st.session_state.get('raw_notice'),'notice_execution':st.session_state.get('notice_trace',{}),'evidence_basis':st.session_state.get('evidence_basis','예시 데이터')}
            st.download_button('공고 추출 결과 저장 (JSON)',json.dumps(notice_export,ensure_ascii=False,indent=2),'5G_공고다음_공고추출.json','application/json')
            st.caption('추출값은 AI 또는 예시 데이터입니다. 원문 인용의 정확성은 검토 카드에서 따로 표시합니다.')
            for k in ('eligibility','preference','commitment','documents','schedule'):
                st.write(n[k+'_rule'])
            if st.session_state.get('source_info',{}).get('kind')=='hangul':
                st.caption('아래는 Studio Parse가 읽어낸 본문입니다. 표 배치와 페이지 번호는 원본과 다를 수 있습니다.')
                for page_number,page_text in enumerate(st.session_state.pages,1):
                    st.text(f'변환 본문 {page_number}페이지\n{page_text}')
        if n.get('_structured_notice') and n['source_conflicts']:
            with st.expander('원문 유의사항과 추후 공지',expanded=False):
                for conflict in n['source_conflicts']:st.write(conflict)
        else:
            for conflict in n['source_conflicts']: st.caption('확인할 점 · '+conflict)
        st.write('**지원 대상**')
        st.write(n.get('eligibility_rule') or '명시되지 않음 · 원문 확인')
        st.write('**제출 방법**')
        st.text(n.get('submission_method') or '원문 또는 운영기관에 확인')
        if n.get('_structured_notice'):
            st.write('**혜택과 지원 범위**')
            st.write(n.get('benefits') or '금액·혜택 미기재 · 상세 공고 확인')
            with st.expander('조건·서류·일정을 항목별로 확인',expanded=False):
                for title in ('지원조건','제출서류','일정','혜택'):
                    entries=n['_structured_notice'].get(title,[])
                    if entries:
                        st.write('**'+title+'**')
                        from core import evidence
                        checked=[{**r,'인용 대조':'본문에서 확인' if evidence(r.get('근거원문',''),r.get('근거페이지',''),st.session_state.pages) else '원문 직접 확인 필요'} for r in entries]
                        st.dataframe(checked,hide_index=True,use_container_width=True)
            if n.get('_workflow_review'):
                with st.expander('AI가 짚은 불일치와 다음 행동',expanded=True):
                    st.caption('공고 원문 검토 안내입니다. 개인의 지원 자격을 확정한 결과는 아닙니다.')
                    st.markdown(n['_workflow_review'])
        st.caption('다음 단계에서는 이 공고에 필요한 질문만 보여드립니다.')
        st.button('내 상황 입력하기 →',type='primary',on_click=go,args=(3,),use_container_width=True)
        st.button('← 공고 넣기로',on_click=go,args=(1,))

if screen==3:
        st.subheader('03 / 나에게 필요한 질문')
        n=st.session_state.notice
        items=document_items(n,st.session_state.pages)
        scope=st.session_state.source_hash[:12]
        keys=question_keys(n,{'selected_center':st.session_state.get('answer_selected_center','')})
        seed_basic(st.session_state,n,st.session_state.get('common_profile',{}))
        st.caption('모르는 항목은 건너뛰세요. 비어 있는 답변은 조건 불일치가 아니라 확인 필요로 남깁니다.')
        def apply_preset():
            chosen=st.session_state.get('profile_preset')
            if chosen is None or 'notice' not in st.session_state:return
            values={'enrollment_status':'휴학' if 'A' in chosen else '재학','remaining_terms':3,'selected_center':'여명학교' if 'A' in chosen else '다른 기관','skills':'중국어 가능, 교육 현장 활용 의사 있음','weekly_visits':2 if 'A' in chosen else 1,'weekly_hours':4,'long_term':'가능','review_stage':'지원 준비 중','other_facts':'4년제 대학, 지역·통학 조건은 미확인'} if chosen!='직접 입력' else {}
            for item in keys:
                default=None if item in ('remaining_terms','weekly_visits','weekly_hours') else '모르겠어요' if item in ('enrollment_status','long_term') else '지원 검토 중' if item=='review_stage' else ''
                st.session_state['answer_'+item]=values.get(item,default)
            st.session_state.pop('result',None)
        if mode=='예시 화면 체험':
            st.selectbox('답변 시작하기',['직접 입력','가상 A · 여명학교 / 주 2회','가상 B · 다른 기관 / 주 1회'],key='profile_preset',on_change=apply_preset)
        a={}
        if 'review_stage' in keys:
            if st.session_state.get('answer_review_stage') not in STAGES:st.session_state['answer_review_stage']=STAGES[0]
            a['review_stage']=st.selectbox('현재 지원 단계',STAGES,key='answer_review_stage')
        stage=a.get('review_stage',STAGES[0])
        for key in keys:
            widget='answer_'+key
            if key=='review_stage':continue
            if key in ('remaining_terms','weekly_visits','weekly_hours'):
                label={'remaining_terms':'공고 기준일의 잔여학기','weekly_visits':'주당 방문 가능한 횟수','weekly_hours':'주당 총 활동 가능한 시간'}[key]
                a[key]=st.number_input(label,min_value=0,max_value=100,value=None,step=1,key=widget,placeholder='모르면 비워두세요',on_change=explicit_basic,args=(st.session_state,key))
            elif key in ('enrollment_status','long_term'):
                label,options={'enrollment_status':('공고 기준일의 학적',['모르겠어요','재학','휴학','수료','졸업']),
                 'long_term':('공고의 전체 활동 기간에 참여할 수 있나요?',['모르겠어요','가능','어려움'])}[key]
                if key=='long_term':st.caption('활동 기간: '+n.get('activity_period',''))
                value=st.selectbox(label,options,key=widget,on_change=explicit_basic,args=(st.session_state,key))
                a[key]=None if value=='모르겠어요' else value
            elif key=='unavailable_dates':
                st.caption('참석 일정: '+n.get('schedule_rule',''))
                schedule_state=st.selectbox('개인 일정 확인 상태',['아직 확인하지 않음','참석 불가 일정 없음','참석 불가 일정 있음'],key='schedule_state')
                a[key]=None if schedule_state=='아직 확인하지 않음' else '참석 불가 일정 없음' if schedule_state=='참석 불가 일정 없음' else st.text_input('참석하기 어려운 날짜·시간',key=widget,max_chars=700)
            else:
                label={'selected_center':'희망 활동 기관','skills':'명시된 우대와 관련된 내 역량'}[key]
                a[key]=st.text_input(label,max_chars=700,key=widget)
        for key,origin in st.session_state.get('profile_provenance',{}).items():
            label={'enrollment_status':'학적','remaining_terms':'잔여학기','social_support':'사회적 배려 대상'}.get(key,'저장 정보')
            st.caption('적용한 '+label+' · '+origin)
        a['profile_facts']=render_fact_overrides(n,a)
        a['answer_provenance']=st.session_state.get('profile_provenance',{})
        a['profile_revision']=fingerprint(st.session_state.get('common_profile',{}))
        questions,later_questions,covered=additional_questions(n,keys,items,stage)
        qa={}
        def draw_question(question):
            if question.get('context'):st.caption('공고의 활동 의무: '+question['context'])
            widget='question_'+scope+'_'+question['id']
            if question.get('kind')=='social_support':
                if st.session_state.get('profile_provenance',{}).get('social_support')!='이번 공고 답변':
                    from profiles import profile_fact
                    pv,origin=profile_fact(st.session_state.get('common_profile',{}),'social_support')
                    if widget not in st.session_state or 'social_support' in st.session_state.get('profile_seeded',{}):
                        st.session_state[widget]=pv if pv in ('해당','해당 없음') else '아직 모름'
                        st.session_state.setdefault('profile_seeded',{})['social_support']=st.session_state[widget]
                        st.session_state.setdefault('profile_provenance',{})['social_support']=origin
                value=st.selectbox(question['text'],['아직 모름','해당','해당 없음'],key=widget,on_change=explicit_basic,args=(st.session_state,'social_support'))
                qa[question['text']]=None if value=='아직 모름' else value
                st.caption('대상 여부만 답하세요. 증빙 준비 상태는 다음 단계에서 별도로 확인합니다. 답변을 원하지 않으면 아직 모름으로 두세요.')
            else:
                qa[question['text']]=st.text_input(question['text'],key=widget,max_chars=700,placeholder='모르면 비워두세요')
            with st.expander('질문에 연결된 공고 조건 · '+question['condition_label']):
                st.write(question['rule'] or '연결할 조건을 자동으로 확정하지 못했습니다. 원문에서 직접 확인하세요.')
                st.caption('추출 근거 후보 · '+(question['page'] or '미확인')+'쪽')
                st.text(question['quote'] or '인용문 없음')
        for question in questions:draw_question(question)
        if later_questions:
            with st.expander(f'선발 후·후속연구 단계의 질문 {len(later_questions)}개'):
                st.caption('지금 답하지 않아도 됩니다. 숨긴 조건을 충족했다고 판단하지 않으며, 관련 단계에서는 다시 확인해야 합니다.')
                if st.checkbox('이후 단계 질문에도 지금 답하기',key='show_later_questions'):
                    for question in later_questions:draw_question(question)
                else:
                    for question in later_questions:st.write('• '+question['text'])
        with st.expander('추가 설명 또는 질문 정리 기준 보기'):
            extra=st.text_input('그 밖에 알려줄 내용 (선택)',key='answer_other_facts',max_chars=1000)
            st.caption('공고 추출값에 명시된 조건으로 기본 질문을 고릅니다. 서류 준비 질문은 아래 체크리스트로 옮겼습니다. 질문이 보이지 않는다고 해당 조건을 충족한 것은 아닙니다.')
            for q in covered:st.caption('중복 질문·허용 안내로 정리: '+q)
        a['question_answers']=qa
        a['condition_answers']=bind_answers(n,keys,questions+later_questions,a,qa)
        a['preference_facts']={'social_support':qa.get(SOCIAL_QUESTION)} if has_social(n) else {}
        for fact in a.get('profile_facts',{}).values():
            if fact['field']=='social_support' and has_social(n):
                fact.update(value=qa.get(SOCIAL_QUESTION),origin=st.session_state.get('profile_provenance',{}).get('social_support','이번 공고 답변'))
        a['deferred_questions']=[q['text'] for q in later_questions if q['text'] not in qa]
        a['other_facts']='\n'.join([q+' '+(v or '미입력') for q,v in qa.items()]+([extra] if extra else []))
        if st.session_state.get('draft_answers') != a:
            st.session_state.pop('result',None)
        st.session_state.draft_answers=a
        st.button('준비 목록과 다음 행동 보기 →',type='primary',on_click=go,args=(4,),use_container_width=True)
        st.button('← 핵심 확인으로',on_click=go,args=(2,))

if screen==4:
        n=st.session_state.notice
        a=dict(st.session_state.draft_answers)
        a['profile_facts']=applied_facts(n,st.session_state.get('common_profile',{}),st.session_state.get('profile_overrides',{}),a,st.session_state.get('profile_provenance',{}))
        for fact in a.get('profile_facts',{}).values():
            if fact['field']=='social_support' and has_social(n):fact.update(value=social_answer(a),origin=st.session_state.get('profile_provenance',{}).get('social_support','이번 공고 답변'))
        if a.get('profile_revision')!=fingerprint(st.session_state.get('common_profile',{})):
            st.warning('공통 프로필이 바뀌었습니다. 3단계에서 적용 답변을 다시 확인해주세요. 이전 AI 결과는 표시하지 않습니다.')
            st.session_state.pop('result',None)
        stage=a.get('review_stage',STAGES[0])
        items=document_items(n,st.session_state.pages)
        scope=st.session_state.source_hash[:12]
        st.subheader('04 / 나의 지원 준비')
        summary=st.container()
        condition_panel=st.container()
        st.markdown('### 제출서류 체크리스트')
        st.caption('체크는 본인이 표시한 준비 상태입니다. 서류 내용·유효성·실제 접수 여부를 검증한 것이 아닙니다. 분류는 공고 추출 문구 기준이므로 원문과 함께 확인하세요.')
        states={}
        def draw_document(item):
            value={}
            prefix='doc_'+scope+'_'+item['id']
            # Migrate prior multi-state preparation values into a simple checkbox.
            if prefix+'_done' not in st.session_state:
                st.session_state[prefix+'_done']=st.session_state.get(prefix+'_ready') in ('준비 완료','제출 완료')
            linked_social=has_social(n) and social_document(item) and item['category']!='필수'
            applicability=(social_answer(a) or '아직 모름') if linked_social else st.session_state.get(prefix+'_applies','아직 모름') if item['category']!='필수' else '해당'
            done=st.checkbox(item['name']+' · 준비 완료',key=prefix+'_done',disabled=applicability=='해당 없음')
            st.caption(item['category']+' · '+item['stage'])
            if linked_social:
                value['applicability']=applicability
                st.caption('연결된 우대 대상 답변 · '+('확인 필요' if applicability=='아직 모름' else applicability)+' — 대상 여부는 3단계에서 수정하세요. 선택서류는 필수서류가 아닙니다.')
            elif item['category'] in ('해당자만','선택','대상·필수 여부 확인'):
                value['applicability']=st.selectbox('적용 대상 확인 · '+item['name'],['아직 모름','해당','해당 없음'],key=prefix+'_applies')
            else:value['applicability']='해당'
            value['readiness']='준비 완료' if done and applicability!='해당 없음' else '아직 확인하지 않음'
            st.caption('준비 상태 · '+('해당 없음 (대상 아님)' if applicability=='해당 없음' else '준비 완료 (본인 확인)' if done else '확인 필요 — 체크하지 않은 상태를 준비 완료나 비대상으로 판단하지 않습니다.'))
            states[item['id']]=value
            with st.expander('근거 확인 · '+item['name']):
                if item['source_found']:
                    st.caption('문서에서 제출물 이름을 찾은 '+item['source_page']+'쪽 주변 구간입니다. 적용 대상·필수 여부까지 자동 검증한 것은 아닙니다.')
                    st.text(item['source_quote'])
                else:st.warning('추출된 제출물 이름을 원문에서 자동으로 찾지 못했습니다. 원문과 운영기관 안내를 확인하세요.')
                st.caption('제출 시점 근거 · '+(item.get('stage_page') or '미확인')+'쪽')
                st.text(item.get('stage_quote') or '제출 시점을 확정할 근거 없음')
                st.caption(item.get('stage_reason',''))
        from planning import later_item
        for item in items:
            if not later_item(item,stage) and item['stage']!=UNKNOWN_STAGE:draw_document(item)
        uncertain_items=[i for i in items if i['stage']==UNKNOWN_STAGE]
        if uncertain_items:
            with st.expander(f'제출 시점 확인 필요 {len(uncertain_items)}개 — 현재 필수 누락으로 계산하지 않음'):
                for item in uncertain_items:draw_document(item)
        later_items=[i for i in items if later_item(i,stage)]
        if later_items:
            with st.expander(f'이후 단계 제출물 {len(later_items)}개 — 지금 누락으로 계산하지 않음'):
                for item in later_items:draw_document(item)
        if not items:st.info('구체적인 제출서류 목록이 추출되지 않았습니다. 서류가 필요 없다는 뜻은 아닙니다. 상세 공고를 확인하세요.')
        rows=checklist_snapshot(items,states,stage)
        a['document_checklist']=rows
        a['independent_conditions']=condition_rows(n,a,st.session_state.pages)
        # Pass all readiness states to Studio as user assertions, never as verified documents.
        a['other_facts']+='\n제출물 준비 상태(본인 확인):\n'+'\n'.join(r['text']+' / 적용: '+r['applicability']+' / 상태: '+r['readiness']+' / 제출 단계: '+r['stage'] for r in rows)
        current=fingerprint({'logic_version':RULE_VERSION,'source':st.session_state.source_hash,'answers':a,'mode':mode,'review_agent':review_id,'version':review_version})
        if st.session_state.get('review_hash')!=current:st.session_state.pop('result',None)
        steps=next_steps(n,a,rows,st.session_state.get('result'))
        with condition_panel:
            st.markdown('### 조건별 독립 판정표')
            st.caption('한 조건의 미입력은 다른 조건의 불일치를 지우지 않습니다. 수치·명시된 학적·준비 상태를 개별 확인하며, 자유서술 답변은 입력만으로 일치 판정하지 않습니다.')
            current_conditions=[r for r in a['independent_conditions'] if r['status']!='이후 단계']
            order={'불일치':0,'확인 필요':1,'일치':2,'해당 없음':3}
            def draw_condition(r):
                color={'불일치':'#f9e8df','확인 필요':'#f8f1d9','일치':'#e2efdf','해당 없음':'#edf0ed','이후 단계':'#edf0ed'}[r['status']]
                answer='미입력' if r['answer'] in (None,'') else str(r['answer'])
                st.markdown('<div class="condition-row"><div><strong>'+html.escape(r['label'])+'</strong><small>'+html.escape(LABELS.get(r['category'],r['category']))+' · '+html.escape(r['stage'])+'</small></div><div>내 답변<small>'+html.escape(answer)+'</small></div><div><span class="badge" style="background:'+color+'">'+r['status']+'</span><small>'+html.escape(r['basis'])+'</small></div></div>',unsafe_allow_html=True)
                with st.expander('판정 이유·원문 · '+r['label']):
                    st.write(r['reason']);st.caption('근거 '+(r['page'] or '미확인')+'쪽 · '+('인용 확인' if r['verified'] else '근거 직접 확인 필요'))
                    st.text(r['quote'] or '연결된 원문 없음')
                    if r.get('stage_quote'):st.caption('시점 근거 '+r['stage_page']+'쪽');st.text(r['stage_quote'])
            for r in sorted(current_conditions,key=lambda r:order.get(r['status'],4)):draw_condition(r)
            future_conditions=[r for r in a['independent_conditions'] if r['status']=='이후 단계']
            if future_conditions:
                with st.expander(f'이후 단계 조건 {len(future_conditions)}개'):
                    for r in future_conditions:draw_condition(r)
            if not current_conditions:st.info('개별 판정을 위한 조건이 추출되지 않았습니다. 원문과 아래 AI 검토를 확인하세요.')
        with summary:
            st.markdown('### 지금 할 일')
            st.caption('준비 상태를 바꾸면 이 목록은 바로 갱신됩니다. 상세 AI 대조는 아래 버튼을 누를 때만 실행합니다.')
            if n.get('application_deadline'):st.write('**접수 마감:** '+n['application_deadline']+' · '+(n.get('deadline_note') or '시각은 원문 확인'))
            st.write('**제출 경로**')
            st.text(n.get('submission_method') or '원문 또는 운영기관에 확인')
            for i,step in enumerate(steps,1):
                st.markdown(f'<div class="review-card"><strong>{i}. {html.escape(step["title"])}</strong><p>{html.escape(step["detail"])}</p></div>',unsafe_allow_html=True)
        st.session_state.preparation={'answers':a,'checklist':rows,'condition_rows':a['independent_conditions'],'next_actions':steps}
        st.download_button('내 준비 목록 저장 (TXT)',preparation_text(n,a,rows,steps),'5G_공고다음_준비목록.txt','text/plain')
        st.caption('실제 AI 대조 시 답변과 체크리스트의 준비 상태를 Upstage로 전달합니다.')
        if st.button('내 조건과 대조하기',type='primary',use_container_width=True):
            st.session_state.pop('result',None)
            try:
                if mode=='예시 화면 체험':raw=sample_review(n,a)
                else:
                    pdf=comparison_pdf(n,a); st.session_state.review_pdf=pdf
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

checkpoint(st.session_state)
save_browser()
