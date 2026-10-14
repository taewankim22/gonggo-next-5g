"""Search credentials stay in server secrets or the current session only."""
import streamlit as st
from national_search import search_config


def render_search_settings():
    try:values=dict(st.secrets.get('search',{}))
    except (FileNotFoundError,KeyError):values={}
    config=search_config(values)
    with st.sidebar.expander('전국 검색 연결 · Tavily',expanded=False):
        if config.enabled:
            st.success('서버의 전국 웹 검색 연결을 사용합니다.')
        else:
            st.write('Tavily 무료 계정의 API 키로 전국 웹 검색을 연결합니다.')
            st.link_button('Tavily 검색 키 발급','https://app.tavily.com/')
            api_key=st.text_input('Tavily API 키',type='password',key='_tavily_api_key')
            config=search_config({'api_key':api_key})
            st.write('입력한 키는 현재 세션에서만 사용합니다. 내 정보·브라우저 저장·공개 목록에는 포함하지 않습니다.')
            if config.enabled:st.info('입력됨 · 검색 실행 시 연결을 확인합니다.')
        st.write('팀 공용 연결은 Streamlit Secrets의 [search]에 api_key를 추가하면 됩니다. 전체 검색은 기본 54크레딧이며 15분 이내 같은 검색은 재사용합니다.')
    return config
