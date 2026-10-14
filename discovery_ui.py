"""Explicit fetch -> source choice -> actual Studio analysis, before publication."""
from pathlib import Path
import streamlit as st
from collect_notices import BOARD, discover
from live_catalog import analyze_public, now_iso
from public_network import AgentError
from upstage_client import StudioError
from web_notice import SOURCE_NAME, prepare_article


def render_discovery(root, connection):
    with st.container(border=True):
        st.subheader('인터넷에서 새 공고 가져오기')
        st.write('연결된 출처: **'+SOURCE_NAME+'**')
        with st.expander('검색 범위와 저장 방식'):
            st.write('이 게시판 첫 페이지의 공고를 가져옵니다. 전국 공고 통합 검색은 아닙니다. 마감 여부는 분석 후 원문과 함께 확인합니다.')
            st.link_button('수집 대상 게시판 열기',BOARD)
            st.write('공식 게시글과 첨부만 수집합니다. 개인 프로필·답변·API 키는 공개 목록에 저장하지 않습니다. 새 분석 결과는 이 서버 이용자에게 공유되며, 서버 재배포·초기화 시 사라질 수 있습니다. 검토 중인 공고와 답변은 기존 브라우저 저장 방식을 따릅니다.')
            st.write('목록 조회에는 AI를 사용하지 않습니다. 분석 버튼을 누르면 선택한 문서를 Upstage에 전달합니다. 동일한 문서·설정의 완료 결과는 재사용합니다.')
        if st.button('최신 공고 불러오기',key='discovery_fetch',use_container_width=True):
            try:
                with st.spinner('공식 게시판에서 공고를 가져오는 중…'):
                    candidates=discover()
                st.session_state['_discovery_candidates']=candidates
                st.session_state['_discovery_checked_at']=now_iso()
                st.session_state.pop('_discovery_article',None)
                st.session_state.pop('_discovery_success',None)
                if not candidates:st.info('가져올 수 있는 공고가 없습니다. 공식 게시판을 확인해주세요.')
            except (AgentError,ValueError,OSError):
                st.error('공식 게시판을 가져오지 못했습니다. 기존 분석 목록은 유지됩니다. 잠시 후 다시 시도하거나 공고 파일을 직접 올려주세요.')
        candidates=st.session_state.get('_discovery_candidates',[])
        if not candidates:return
        st.write(f'가져온 공고 **{len(candidates)}건**')
        selected=st.selectbox('가져올 공고',options=[c['url'] for c in candidates],
                              format_func=lambda url:next(c['title'] for c in candidates if c['url']==url),key='discovery_candidate')
        candidate=next(c for c in candidates if c['url']==selected)
        st.link_button('선택한 공고 원문',selected)
        if st.button('이 공고 원문 가져오기',key='discovery_prepare'):
            st.session_state.pop('_discovery_article',None)
            st.session_state.pop('_discovery_success',None)
            try:
                with st.spinner('본문·포스터·첨부를 확인하는 중…'):
                    st.session_state['_discovery_article']=prepare_article(candidate,Path(root)/'runtime/collected')
            except (ValueError,OSError,StudioError):
                st.error('원문을 온전히 준비하지 못했습니다. 본문·이미지·첨부 형식을 확인하거나 공고 파일을 직접 올려주세요.')
        article=st.session_state.get('_discovery_article')
        if not article or article['url']!=selected:return
        index=st.selectbox('분석할 문서',range(len(article['documents'])),format_func=lambda i:article['documents'][i]['name'],
                           key='discovery_document_'+selected)
        doc=article['documents'][index]
        st.write('이번 분석 범위: **'+doc['name']+'**')
        if len(article['documents'])>1 or article['warnings'] or article.get('attachment_limit_reached'):
            st.info('선택한 문서만 분석합니다. 다른 본문·첨부의 조건은 각각 확인해주세요.')
        for warning in article['warnings']:st.warning(warning)
        if article.get('attachment_limit_reached'):st.warning('첨부가 많아 처음 5개만 가져왔습니다. 나머지는 공식 원문에서 확인해주세요.')
        with st.expander('가져온 원문 확인'):
            st.download_button('분석할 문서 내려받기',doc['data'],doc['filename'],key='discovery_download')
            st.write(doc['basis'])
            st.text(article['body_text'][:12000])
        enabled=bool(connection and connection.get('enabled'))
        if not enabled:st.info('설정에서 실제 AI 분석 모드와 Upstage 연결을 확인해주세요.')
        if st.button('Upstage로 분석하고 목록에 추가',key='discovery_analyze',type='primary',disabled=not enabled,use_container_width=True):
            progress=st.empty()
            try:
                record,reused=analyze_public(root,article,index,connection['agent_id'],connection['version'],connection['runner'],progress.info)
                progress.empty()
                st.session_state['_discovery_success']=(record['title'],reused)
                # Reveal the newly added record even if old list filters were active.
                st.session_state['catalog_kind']='전체';st.session_state['catalog_status']='전체';st.session_state['catalog_search']=''
            except (ValueError,StudioError) as exc:
                progress.empty();st.error(str(exc))
            except OSError:
                progress.empty();st.error('서버 저장 중 오류가 발생했습니다. 기존 목록은 유지됩니다.')
        if st.session_state.get('_discovery_success'):
            title,reused=st.session_state['_discovery_success']
            st.success(('기존 분석을 재사용해 목록에 반영했습니다: ' if reused else '실제 Upstage 분석을 완료해 아래 목록에 추가했습니다: ')+title)
