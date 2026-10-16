"""Native accessible Streamlit controls; all changes are local view state."""
import datetime as dt
import html
import streamlit as st
from deadline_calendar import now_kst,month_shift,month_days,event_status,group_status


def set_month(month):
    st.session_state.calendar_month=month
    st.session_state.calendar_day='전체 날짜'


def set_day(day):
    st.session_state.calendar_day=day


def filter_groups(groups,kind,status,interest):
    return [g for g in groups if
        (kind=='전체' or g['record']['kind']==kind) and
        (status=='전체' or group_status(g['record']['_calendar'])==status) and
        (not interest or interest.casefold() in (g['record']['title']+' '+str(g['record'].get('tags',[]))).casefold())]


def render_deadline_details(group):
    record=group['record'];details=record['_calendar']
    st.write('**'+group_status(details)+'**')
    for e in details['events']:
        st.write(f"**{e['stage']} · {e['date']} · {e['time'] or '마감 시간 미확인'}**")
        if e['delivery']:st.write(e['delivery'])
    with st.expander('마감 근거 · 마지막 확인'):
        st.write('원문 마지막 확인: '+(record.get('checked_at') or '확인 시점 미기록'))
        if not details['events']:st.write(details['category']+' · 날짜를 임의로 지정하지 않았습니다.')
        evidence=[]
        for event in details['events']:
            st.write(event['timezone_basis']+' · 달력 날짜는 원문 시간대의 날짜입니다.')
            evidence.extend(event['evidence'])
        if not evidence:evidence=details.get('evidence',[])
        seen=set()
        for e in evidence:
            key=(e['document_id'],e['quote'])
            if key in seen:continue
            seen.add(key)
            st.write(e['document_name']+' · '+e['page']+'쪽')
            st.text(e['quote'])
        if not evidence:st.write('분석한 원문에서 접수 마감의 연도·날짜를 확인하지 못했습니다. 원문을 확인해주세요.')


def render_calendar(groups,render_card):
    today=now_kst().date();current=today.strftime('%Y-%m')
    st.session_state.setdefault('calendar_month',current)
    month=st.session_state.calendar_month
    # Navigation is bounded by supported date objects, not by whether events exist.
    month_options=sorted({month_shift(current,i) for i in range(-24,25)}|{month}|
                        {e['date'][:7] for g in groups for e in g['record']['_calendar']['events']})
    with st.container(key='calendar_controls'):
        prev,select,today_button,next_=st.columns([1,3,1,1])
        with prev:st.button('← 이전 달',key='calendar_prev',on_click=set_month,args=(month_shift(month,-1),),use_container_width=True)
        with select:st.selectbox('표시 월',month_options,key='calendar_month',on_change=set_day,args=('전체 날짜',),label_visibility='collapsed')
        with today_button:st.button('오늘',key='calendar_today',on_click=set_month,args=(current,),use_container_width=True)
        with next_:st.button('다음 달 →',key='calendar_next',on_click=set_month,args=(month_shift(month,1),),use_container_width=True)
    month=st.session_state.calendar_month
    st.subheader(month.replace('-','년 ')+'월 마감')
    by_day={}
    undated=[]
    for group in groups:
        events=group['record']['_calendar']['events']
        if not events:undated.append(group)
        for date in sorted({e['date'] for e in events if e['date'].startswith(month)}):
            by_day.setdefault(date,[]).append(group)
    options=['전체 날짜']+sorted(by_day)
    if st.session_state.get('calendar_day') not in options:st.session_state.calendar_day='전체 날짜'
    with st.container(key='calendar_grid'):
        cols=st.columns(7)
        for col,label in zip(cols,['일','월','화','수','목','금','토']):col.markdown('**'+label+'**')
        for week in month_days(month):
            cols=st.columns(7)
            for col,day in zip(cols,week):
                with col:
                    date=day.isoformat();items=by_day.get(date,[])
                    with st.container(key='calendar_cell_'+date):
                        if date.startswith(month):
                            st.button(f'{day.day}일'+(f' · {len(items)}건' if items else ''),key='calendar_date_'+date,
                                type='primary' if date==st.session_state.calendar_day else 'secondary',
                                disabled=not items,on_click=set_day,args=(date,),use_container_width=True,
                                help=date+(' · 오늘' if day==today else '')+'에 마감하는 공고')
                            titles=''.join('<div class="cal-preview">'+html.escape(g['record']['title'][:28])+'</div>' for g in items[:2])
                            if len(items)>2:titles+=f'<div class="cal-more">외 {len(items)-2}건</div>'
                            st.markdown(titles,unsafe_allow_html=True)
    selected=st.selectbox('날짜 선택',options,key='calendar_day',
        format_func=lambda x:'이달 전체 날짜' if x=='전체 날짜' else f'{x} · {len(by_day[x])}개 공고')
    dates=sorted(by_day) if selected=='전체 날짜' else [selected]
    if not dates:st.info('이달에 마감하는 분석 공고가 없습니다. 다른 달이나 아래 일정 미확인 공고를 확인하세요.')
    for date in dates:
        st.markdown('### '+date+f' · {len(by_day[date])}개 공고')
        for group in by_day[date]:
            with st.expander(group['record']['title']):
                render_card(group,suffix=date)
    if undated:
        with st.expander(f'상시·마감일 확인 필요 · {len(undated)}개 공고',expanded=not by_day):
            for group in undated:render_card(group,suffix='undated')
