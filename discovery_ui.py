"""Nationwide discovery, explicit pending queue and shared document analysis."""
import streamlit as st
from discovery_flow import refresh_latest
from live_catalog import LiveCatalog
from national_search import DiscoveryStore, SOURCES, SEARCH_KINDS, search_plan, discover_nationwide, candidate
from upstage_client import StudioError


def show_summary(summary):
    message=f'공고 {summary["selected"]}개 원문 확인 · 새 분석 {summary["analyzed"]}문서 · 재사용 {summary["reused"]}문서'
    if not summary['selected']:
        st.info('자동 분석할 모집 원문을 확보하지 못했습니다. 발견한 후보에서 주최기관 원문을 연결해주세요.')
    elif summary['failed'] or any(not n['complete'] for n in summary['notices']):
        st.warning(message+f' · 미완료 {summary["failed"]}건 (첨부 경고 포함 상세 확인)')
    else:st.success(message+' · 내 정보로 목록을 정렬했습니다.')
    with st.expander('이번 분석 내역'):
        for notice in summary['notices']:
            st.write('**'+notice['title']+'**')
            for doc in notice['documents']:
                st.write(doc['name']+' · '+('분석 완료' if doc['status']=='ready' else '확인 필요'))
                if doc.get('error'):st.warning(doc['error'])
            for warning in notice['warnings']:st.warning(warning)


def run_batch(root,connection,limit,queue):
    status=st.empty()
    try:
        summary=refresh_latest(root,connection,limit,status.info,queue,national=True)
        st.session_state['_discovery_batch_summary']=summary
        return summary
    except (ValueError,OSError,StudioError):
        st.error('원문 분석을 완료하지 못했습니다. 완료된 분석과 대기 후보는 유지됩니다.')
    finally:status.empty()


def render_discovery(root, connection):
    connection=connection or {}
    config=connection.get('search_config')
    search_ready=bool(config and config.enabled)
    ai_ready=bool(connection.get('enabled'))
    with st.container(border=True):
        st.subheader('전국 최신 공고 찾기')
        st.write('전국·17개 시도의 장학금·공모전·대외활동·해커톤·대회를 검색하고, **저장한 내 정보**로 분석한 공고를 정렬합니다.')
        kinds=st.multiselect('검색할 공고 종류',list(SEARCH_KINDS),default=list(SEARCH_KINDS),key='discovery_kinds')
        with st.expander('수집 출처 · 분석 방식'):
            total=len(search_plan(kinds=kinds)) if kinds else 0
            st.write(f'전국 공통 + 17개 시도 × 선택한 {len(kinds)}개 종류, 총 {total}개 검색어로 웹 검색합니다. 검색어별 최대 20개 링크를 확인하며, 검색에 잡히지 않는 공고도 있습니다.')
            st.write('최근 한 달 게시·수정 검색을 사용합니다. 날짜를 알 수 없는 결과도 포함될 수 있어 실제 접수 일정은 원문으로 확인합니다. 알려진 공고 모음·블로그는 검색에서 제외합니다.')
            st.write('해커톤·대회는 기관·대학의 모집 공고를 우선 찾고, 지역별 검색으로 기업·행사 사이트도 확인합니다. 보도·모음 페이지는 주최기관 원문 연결이 필요합니다.')
            st.write('지역은 검색 범위입니다. 실제 지원 가능 지역·학교는 원문 분석으로 확인합니다. 개인 프로필은 검색 API에 전달하지 않습니다.')
            for _,name,url in SOURCES:st.link_button(name,url)
            st.write('공고 모음 사이트에서 발견한 링크는 주최기관 원문이 필요합니다. 본문·포스터와 읽을 수 있는 첨부 최대 10개를 분석하고 누락·실패를 표시합니다.')
            st.write('같은 문서·설정은 출처가 달라도 분석을 재사용합니다. 원문이 바뀌면 이전 조건을 새 판정에 섞지 않습니다.')
            limit=st.selectbox('한 번에 원문 분석할 공고 수',[10,20,50,100,3,1],key='discovery_batch_size',format_func=lambda n:f'{n}개 공고')
            st.write('수집 범위와 별개인 처리 묶음입니다. 나머지 후보는 아래 목록에 남고 이어서 분석할 수 있습니다.')
            st.write('선택한 종류별로 번갈아 분석합니다. 해당 종류의 원문 후보를 확보하지 못하면 다른 종류를 계속 처리합니다.')
        if not search_ready:st.info('전국 웹 검색을 사용하려면 메뉴 → 전국 검색 연결 · Tavily에서 연결해주세요.')
        if not ai_ready:st.info('원문 분석에는 실제 AI 분석 모드와 Upstage 연결이 필요합니다.')
        pending=st.session_state.pop('_discovery_auto_requested',False)
        clicked=st.button('최신 공고 찾기',key='discovery_latest',type='primary',disabled=not (search_ready and ai_ready and kinds),use_container_width=True)
        if not kinds:st.info('검색할 공고 종류를 하나 이상 선택해주세요.')
        if (clicked or pending) and search_ready and ai_ready and kinds:
            status=st.empty()
            try:
                found,stats=discover_nationwide(root,config,status.info,kinds=kinds)
                st.session_state['_national_search_summary']=stats
                queue=DiscoveryStore(root).queue([c['url'] for c in found],kinds=kinds)
                run_batch(root,connection,limit,queue)
                st.session_state['catalog_kind']='전체';st.session_state['catalog_status']='전체';st.session_state['catalog_search']=''
            except (ValueError,OSError,StudioError):st.error('검색을 완료하지 못했습니다. 저장된 후보와 완료 분석은 유지됩니다. 아래 목록에서 다시 시도해주세요.')
            finally:status.empty()
        elif pending:st.info('내 정보는 저장했습니다. 전국 검색 연결과 Upstage 연결을 확인한 뒤 최신 공고 찾기를 눌러주세요.')
        stats=st.session_state.get('_national_search_summary')
        if stats:
            st.write(f'웹 검색 {stats["queries_completed"]}/{stats["queries_total"]}개 완료 · 이번에 발견한 공고 후보 {stats["found"]}개')
            with st.expander('출처별 수집 결과'):
                st.table(stats['sources'])
                for error in stats['errors']:st.warning(error)
                st.write(f'최근 검색 재사용 {stats["query_cache_hits"]}개 · 검색 결과 캐시 15분, 원문은 분석 전에 다시 확인합니다.')
        if st.session_state.get('_discovery_batch_summary'):show_summary(st.session_state['_discovery_batch_summary'])
    render_manual_discovery(root,connection)


def render_manual_discovery(root,connection):
    store=DiscoveryStore(root)
    with st.expander('발견한 공고 · 분석 대기 목록',expanded=False):
        st.write('검색에서 발견한 후보이며 지원 자격·마감일은 아직 확정하지 않았습니다. 분석 실패도 목록에 남습니다.')
        if st.button('등록 기관 게시판만 새로 확인',key='discovery_fetch'):
            status=st.empty()
            try:
                _,stats=discover_nationwide(root,None,status.info)
                st.session_state['_national_search_summary']=stats
            except (ValueError,OSError):st.error('기관 게시판 수집에 실패했습니다. 기존 후보는 유지됩니다.')
            finally:status.empty()
        items=store.items()
        with st.form('public_source_url'):
            url=st.text_input('주최기관 공고·원본 파일 URL',placeholder='https://…')
            title=st.text_input('공고 제목',placeholder='원문에 표시된 공고명')
            add=st.form_submit_button('원문 후보에 추가')
            if add:
                try:
                    if not title.strip():raise ValueError('공고 제목을 입력해주세요.')
                    store.remember([candidate(url,title,'직접 연결한 공개 원문')]);st.rerun()
                except ValueError as exc:st.error(str(exc))
        if not items:st.info('아직 발견한 공고가 없습니다. 전국 검색 또는 원문 URL 연결을 사용해주세요.');return
        st.write(f'저장된 공고 후보 {len(items)}개')
        keyword=st.text_input('발견한 후보에서 검색',key='candidate_filter')
        shown=[c for c in items if keyword in c['title']]
        if not shown:st.info('검색어와 일치하는 후보가 없습니다.');return
        selected=st.selectbox('확인할 공고',shown,format_func=lambda c:c['title']+' · '+c['source_name'],key='discovery_candidate_national')
        st.link_button('수집 출처 원문',selected['url'])
        scans=LiveCatalog(root).scans()
        scan=scans.get(selected['url'])
        if scan:
            st.write('마지막 처리: '+scan['checked_at']+' · '+('분석 완료' if scan['complete'] else '일부 미완료 · 확인 필요'))
            for warning in scan['warnings']:st.warning(warning)
            for doc in scan['documents']:
                if doc.get('error'):st.warning(doc['name']+' · '+doc['error'])
        if selected.get('needs_original'):
            st.info('모음 사이트에서 발견했습니다. 주최기관 원문 URL을 위에 추가하면 분석할 수 있습니다.')
        if selected.get('notice_purpose') in ('결과·후속 안내','목록·운영 안내'):
            st.info('모집 원문이 아닌 결과·목록·운영 안내로 보입니다. 자동 모집 분석에서는 제외하고 직접 확인할 수 있습니다.')
        if st.button('이 공고 원문 확인·분석',key='discovery_analyze',disabled=not connection.get('enabled') or selected.get('needs_original',False)):
            summary=run_batch(root,connection,1,[selected])
            if summary:show_summary(summary)
        if st.button('분석 대기 공고 이어서 처리',key='discovery_continue',disabled=not connection.get('enabled')):
            kinds=st.session_state.get('discovery_kinds')
            queue=[c for c in store.queue(kinds=kinds or None) if not scans.get(c['url'],{}).get('complete')]
            if not queue:st.info('저장된 후보의 분석을 마쳤습니다. 최신 공고 찾기로 원문 변경 여부를 확인하세요.')
            else:
                summary=run_batch(root,connection,st.session_state.get('discovery_batch_size',10),queue)
                if summary:show_summary(summary)
