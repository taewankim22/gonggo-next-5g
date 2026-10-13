"""Presentation only: preparation counts never determine eligibility."""
import html
import re
from collections import Counter
from urllib.parse import urlsplit

import streamlit as st
from conditions import LABELS
from source_context import UNKNOWN


def esc(value):
    return html.escape(str(value or ''))


def required_progress(rows):
    current = [r for r in rows if not r.get('later') and r.get('stage') != UNKNOWN
               and r.get('category') == '필수']
    done = sum(r.get('readiness') in ('준비 완료', '제출 완료') for r in current)
    return done, len(current)


def submission_url(text):
    # Only explicitly present web links; never turn an inferred institution into a URL.
    for value in re.findall(r'https?://[^\s<>"\[\]]+', text or ''):
        value = value.rstrip(').,;。')
        try:
            if urlsplit(value).hostname:
                return value
        except ValueError:
            continue
    return None


def status_badge(status):
    tone = {'불일치': 'conflict', '확인 필요': 'pending', '일치': 'match',
            '해당 없음': 'neutral', '이후 단계': 'neutral', '준비 완료': 'match'}.get(status, 'neutral')
    return f'<span class="status-badge {tone}">{esc(status)}</span>'


def render_preparation_summary(notice, rows, steps):
    done, total = required_progress(rows)
    with st.container(key='prep_metrics'):
        deadline, submission, progress = st.columns(3)
        with deadline, st.container(border=True, key='metric_deadline'):
            value = notice.get('application_deadline') or '확인 필요'
            st.markdown(f'<div class="metric-label">접수 마감</div><div class="metric-value">{esc(value)}</div>', unsafe_allow_html=True)
            with st.popover('마감 안내', use_container_width=True):
                st.write(notice.get('deadline_note') or '정확한 마감 시각과 접수 상태를 원문에서 확인해주세요.')
        with submission, st.container(border=True, key='metric_submission'):
            method = notice.get('submission_method') or '원문에서 확인'
            brief = method.split('\n')[0]
            brief = brief[:36] + '…' if len(brief) > 36 else brief
            st.markdown(f'<div class="metric-label">제출 경로</div><div class="metric-value method">{esc(brief)}</div>', unsafe_allow_html=True)
            with st.popover('제출 방법 보기', use_container_width=True):
                st.write(method)
                url = submission_url(method)
                if url:
                    st.link_button('접수 사이트 열기 ↗', url)
        with progress, st.container(border=True, key='metric_progress'):
            value = f'{done} / {total} 완료' if total else '필수 목록 확인'
            st.markdown(f'<div class="metric-label">현재 단계 필수 서류</div><div class="metric-value">{value}</div>', unsafe_allow_html=True)
            st.progress(done / total if total else 0)
            with st.popover('집계 기준', use_container_width=True):
                st.write('현재 단계의 필수 제출물만 셉니다. 이후 단계·제출 시점 미확인·선택 서류는 제외합니다. 완료는 본인의 체크이며, 서류 검증이나 접수 완료를 뜻하지 않습니다.')
                if not total:
                    st.write('확인된 필수 서류 목록이 없습니다. 제출서류가 필요 없다는 뜻은 아닙니다.')
    st.markdown('### 지금 할 일')
    content = []
    for i, step in enumerate(steps, 1):
        condition = step['title'] in ('조건이 다른 항목 확인', '아직 답하지 않은 조건')
        target, label = ('conditions', '판정표 보기') if condition else ('checklist', '체크리스트로')
        content.append(f'<div class="next-action"><span class="action-number">{i}</span>'
                       f'<div class="action-copy"><strong>{esc(step["title"])}</strong><p>{esc(step["detail"])}</p></div>'
                       f'<a class="jump-link" href="#{target}" target="_self">{label}<span aria-hidden="true"> ↗</span></a></div>')
    st.markdown('<div class="action-list">' + ''.join(content) + '</div>', unsafe_allow_html=True)


def render_conditions(rows, scope):
    current = [r for r in rows if r['status'] != '이후 단계']
    future = [r for r in rows if r['status'] == '이후 단계']
    counts = Counter(r['status'] for r in current)
    st.markdown('<div id="conditions" class="section-anchor"></div>', unsafe_allow_html=True)
    st.markdown('### 조건별 판정')
    options = ['전체'] + [s for s in ('불일치', '확인 필요', '일치', '해당 없음') if counts[s]]
    key = 'condition_filter_' + scope
    if st.session_state.get(key) not in options:
        st.session_state[key] = '전체'
    choice = st.pills('판정 필터', options, selection_mode='single', required=True,
                      format_func=lambda s: f'{s} {len(current) if s == "전체" else counts[s]}',
                      key=key, label_visibility='collapsed')

    def draw(row, index, prefix):
        answer = '미입력' if row['answer'] in (None, '') else str(row['answer'])
        with st.container(key=f'condition_row_{prefix}_{index}'):
            title, my_answer, status, source = st.columns([3, 1.4, 1.5, .8], vertical_alignment='center')
            title.markdown(f'<div class="condition-title">{esc(row["label"])}</div><div class="condition-meta">{esc(LABELS.get(row["category"], row["category"]))} · {esc(row["stage"])}</div>', unsafe_allow_html=True)
            my_answer.markdown(f'<div class="mobile-label">내 답변</div><div class="condition-answer {"empty-answer" if answer == "미입력" else ""}">{esc(answer)}</div>', unsafe_allow_html=True)
            status.markdown(status_badge(row['status']), unsafe_allow_html=True)
            with source, st.popover('근거', help=row['label'] + ' · 판정 이유와 원문', use_container_width=True):
                st.markdown('**' + row['label'] + '**')
                st.write(row['reason'])
                st.caption(row['basis'] + ' · ' + (row['page'] or '미확인') + '쪽 · ' + ('인용 확인' if row['verified'] else '근거 직접 확인 필요'))
                st.text(row['quote'] or '연결된 원문 없음')
                if row.get('stage_quote'):
                    st.caption('시점 근거 ' + (row.get('stage_page') or '미확인') + '쪽')
                    st.text(row['stage_quote'])

    if current:
        with st.container(border=True, key='condition_table'):
            st.markdown('<div class="condition-head"><span>조건</span><span>내 답변</span><span>판정</span><span>근거</span></div>', unsafe_allow_html=True)
            order = {'불일치': 0, '확인 필요': 1, '일치': 2, '해당 없음': 3}
            for index, row in enumerate(sorted(current, key=lambda r: order.get(r['status'], 4))):
                if choice == '전체' or row['status'] == choice:
                    draw(row, index, 'current')
    else:
        st.info('개별 판정을 위한 조건이 추출되지 않았습니다. 원문과 AI 검토를 확인하세요.')
    if future:
        with st.expander(f'이후 단계 조건 {len(future)}개'):
            for index, row in enumerate(future):
                draw(row, index, 'future')
    with st.expander('판정 기준 보기'):
        st.write('조건마다 따로 판정합니다. 미입력은 확인 필요로 남고, 다른 조건의 불일치를 지우지 않습니다. 자유서술 답변은 입력만으로 일치 판정하지 않습니다. 각 항목의 근거에서 이유를 확인하세요.')
