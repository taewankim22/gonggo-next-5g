"""Step four: source coverage, actionable preparation, and conservative review."""
import re
import base64
from collections import Counter
from copy import deepcopy
import streamlit as st
from core import fingerprint
from planning import STAGES,preparation_text
from profiles import applied_facts
from independent_review import condition_rows
from conditions import has_social,social_answer,bind_answers
from ui_components import esc,status_badge,render_conditions,submission_url
from preparation_model import source_bundle,document_rows,document_progress,preparation_actions,adopt_public_update


def prep_icon(kind):
    paths={
        'date':'<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4m8-4v4M4 11h16"/>',
        'link':'<path d="m10 13 4-4m-6 7-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 1 1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0"/>',
        'file':'<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8m-8 4h5"/>',
    }
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="'+('#c92873' if kind=='date' else '#243044')+'" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'+paths[kind]+'</svg>'
    return '<span class="prep-icon '+kind+'"><img alt="" src="data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode()+'"></span>'


def prep_badge(label):
    tone='required' if label=='필수' else 'done' if label=='준비 완료' else 'pending' if any(s in label for s in ('확인','차이')) else 'neutral'
    return '<span class="prep-pill '+tone+'">'+esc(label)+'</span>'


def metric_heading(kind,label,value):
    st.markdown('<div class="prep-metric-main">'+prep_icon(kind)+'<div class="prep-metric-copy"><div class="prep-metric-label">'+esc(label)+'</div><div class="prep-metric-value">'+esc(value).replace('\n','<br>')+'</div></div></div>',unsafe_allow_html=True)


def jump(target):
    st.session_state['_prep_focus']=target


def change_stage():
    a=dict(st.session_state.get('draft_answers',{}));a['review_stage']=st.session_state.answer_review_stage
    st.session_state.draft_answers=a
    for key in ('result','review_hash','raw_review'):st.session_state.pop(key,None)


def render_sources(root,bundle,connection,go):
    state=st.session_state
    statuses={'ready':'분석 완료','pending':'아직 분석하지 않음','failed':'분석 실패',
              'download_failed':'가져오기 실패','unsupported':'지원하지 않는 형식'}
    with st.expander('분석 범위·원문 확인',expanded=state.get('_prep_focus')=='sources'):
        if bundle['url']:st.link_button('공고 원문 열기 ↗',bundle['url'])
        if state.get('pdf'):
            st.download_button('현재 원본 내려받기',state.pdf,state.get('source_filename','notice.pdf'),key='prep_original')
        for i,doc in enumerate(bundle['inventory']):
            st.write('**'+doc['name']+'** · '+statuses.get(doc.get('status'),'처리 기록 확인 필요'))
            if doc.get('status') in ('failed','pending','download_failed') and doc.get('url'):
                label='다시 가져오기·분석' if doc['status']=='download_failed' else '이 자료만 분석하기'
                if st.button(label,key='prep_retry_'+fingerprint(doc['url'])[:12],disabled=not connection.get('enabled')):
                    state['_prep_refresh_targets']=[doc['url']];state['_prep_refresh_requested']=True;st.rerun()
            if doc.get('status')=='unsupported':
                st.write('원문에서 내려받아 PDF 등 지원 형식으로 준비해주세요.')
        for warning in bundle['warnings']:st.write(warning)
        if bundle['status']=='uploaded':st.write('직접 올린 파일 1건의 결과예요. 다른 첨부가 있는지는 원문에서 확인해주세요.')
        st.write('원문 마지막 확인: '+(bundle['checked_at'] or '기록 없음'))
        for doc in bundle['documents']:
            st.write(doc['name']+' · 분석 시각: '+(doc.get('analyzed_at') or '기록 없음'))
            if not doc.get('selected'):
                if st.button('이 자료의 조건 검토하기',key='prep_open_'+doc['record_id']):
                    from catalog import available_record
                    from browser_draft import single_snapshot
                    from workspaces import activate
                    new=available_record(root,doc['record'])
                    if new:
                        saved=state.get('workspaces',{}).get(new['source_hash'])
                        activate(state,saved or single_snapshot(new));st.rerun()
        if bundle['url']:
            st.write('원문을 다시 가져오고 바뀐 자료만 분석합니다. 변경된 파일은 AI 호출이 필요할 수 있어요.')
            if st.button('원문 변경 확인·분석',key='prep_refresh',disabled=not connection.get('enabled')):
                state['_prep_refresh_targets']=None;state['_prep_refresh_requested']=True;st.rerun()
        if st.button('파일 직접 올리기',key='prep_upload'):
            # Preserve this workspace; the upload path replaces it only on success.
            go(1);st.rerun()


def refresh(root,bundle,connection,targets):
    from discovery_flow import refresh_latest
    from catalog import load_catalog,available_record
    from upstage_client import StudioError
    state=st.session_state
    current_doc=bundle['documents'][0]['url']
    before={d['url']:d['sha256'] for d in bundle['documents']}
    try:
        with st.status('원문을 확인하고 있어요.',expanded=True) as status:
            result=refresh_latest(root,connection,1,status.write,[{'url':bundle['url'],'title':state.notice.get('notice_title','공고')}],
                                  national=True,document_urls=targets)
            status.update(label='완료된 자료는 유지했습니다.' if result['failed'] else '원문 확인을 마쳤습니다.',state='complete')
        manifest=result['notices'][0]
        refresh_result={'failed':bool(result['failed'] or manifest.get('fetch_failed')),
            'analyzed':result['analyzed'],'reused':result['reused'],'checked_at':manifest['checked_at'],
            'unchanged':not result['failed'] and bool(before) and all(before.get(d['url'])==d.get('sha256') for d in manifest['documents'])}
        current=next((d for d in manifest['documents'] if d['url']==current_doc and d.get('status')=='ready'),None)
        if current:
            record=next((r for r in load_catalog(root) if r['id']==current['record_id']),None)
            new=available_record(root,record) if record else None
            if new:adopt_public_update(state,new)
        state['_prep_refresh_result']=refresh_result
        st.rerun()
    except (ValueError,OSError,StudioError):
        st.error('원문 확인·분석을 완료하지 못했습니다. 이전 준비 기록은 유지돼요. 원문에서 확인하거나 파일을 직접 올려주세요.')


def draw_document(item,scope):
    state=st.session_state
    key=item['prefix'];store=state.setdefault('prep_document_states',{})
    # Keep the existing checkbox keys so old browser drafts remain usable.
    state.setdefault(key+'_done',item['done'])
    state.setdefault(key+'_applies',item['applicability'])
    with st.container(key='prep_document_'+item['storage_key']):
        focus=state.get('_prep_focus')=='document:'+item['id']
        check,content=st.columns([.35,9],gap='small')
        with check:
            done=st.checkbox(item['name']+' · 준비 완료',key=key+'_done',disabled=item['applicability']=='해당 없음',label_visibility='collapsed')
        tags=[item['category']]
        if item['needs_recheck']:tags.append('다시 확인 필요')
        elif item.get('conflict'):tags.append('자료 간 안내 차이')
        elif item.get('stale'):tags.append('최신 원문 확인 필요')
        elif done:tags.append('준비 완료')
        if item['category']!='필수' and item['applicability']=='아직 모름':tags.append('대상 여부 확인 필요')
        with content:
            st.markdown('<div class="prep-doc-title'+(' prep-focused' if focus else '')+'"><strong>'+esc(item['name'])+'</strong>'+''.join(prep_badge(t) for t in tags)+'</div>',unsafe_allow_html=True)
            brief=' · '.join(v for v in [item['requirements'],item['target'] if item['target']!='공통' else ''] if v)
            if brief:st.markdown('<div class="prep-doc-brief">'+esc(brief[:140]+('…' if len(brief)>140 else ''))+'</div>',unsafe_allow_html=True)
        with st.expander('원문 '+(item['source_page'] or '미확인')+'쪽 · 조건·근거 보기',expanded=focus):
            st.markdown('**'+item['name']+'**')
            st.write('제출 단계: '+item['stage'])
            if item['target']:st.write('적용 대상: '+item['target'])
            if item.get('requirements_candidate') and not item.get('requirement_verified'):
                st.write('제출 설명의 세부 기준은 아래 원문에서 확인해주세요.')
            if item['category']!='필수':
                if item['linked_social']:
                    st.write('우대 대상 답변: '+('확인 필요' if item['applicability']=='아직 모름' else item['applicability']))
                    st.write('대상 여부는 내 상황에서, 서류 준비는 여기서 관리해요.')
                else:
                    item['applicability']=st.selectbox('적용 대상 확인 · '+item['name'],['아직 모름','해당','해당 없음'],key=key+'_applies')
            for s in item['sources']:
                st.write(s['name']+' · '+(s['page'] or '미확인')+'쪽')
                st.text(s['quote'] or '연결된 원문 근거를 찾지 못했어요.')
                if s['url']:st.link_button('이 원문 열기 ↗',s['url'])
            if not item['source_found']:st.write('추출된 이름과 원문을 연결하지 못했어요. 필수 여부와 제출 시점을 확인해주세요.')
            if item.get('stage_quote'):st.text(item['stage_quote'])
            # URLs are actionable only when literally present in this item's verified evidence.
            links=list(dict.fromkeys(re.findall(r'https?://[^\s<>\"]+',item['source_quote']))) if item['source_found'] else []
            for j,url in enumerate(links[:3]):
                url=submission_url(url)
                if url:st.link_button('서류 안내 링크 ↗',url)
            if item['needs_recheck']:
                st.write('이전 준비 완료 표시는 보관했어요. 바뀐 요구사항을 확인한 뒤 다시 확인해주세요.')
                if st.button('변경된 요구사항 확인 완료',key='prep_ack_'+item['storage_key']):
                    store[item['storage_key']]={**store.get(item['storage_key'],{}),'signature':item['signature']}
                    st.rerun()
        previous=store.get(item['storage_key'],{})
        store[item['storage_key']]={'done':done,'applicability':item['applicability'],
            'signature':previous.get('signature',item['signature']) if item['needs_recheck'] else item['signature']}
        item['done']=done
        item['readiness']='준비 완료' if done and not (item['needs_recheck'] or item.get('conflict') or item.get('stale')) and item['applicability']!='해당 없음' else '아직 확인하지 않음'


def render_preparation(root,connection,go):
    state=st.session_state;n=state.notice;a=deepcopy(state.get('draft_answers',{}))
    if state.pop('_prep_refresh_requested',False):
        refresh(root,source_bundle(root,state),connection,state.pop('_prep_refresh_targets',None))
    a.setdefault('other_facts','')
    a['profile_facts']=applied_facts(n,state.get('common_profile',{}),state.get('profile_overrides',{}),a,state.get('profile_provenance',{}))
    for fact in a['profile_facts'].values():
        if fact['field']=='social_support' and has_social(n):fact.update(value=social_answer(a),origin='이번 공고 답변')
    scope=state.source_hash[:12]
    state.setdefault('answer_review_stage',a.get('review_stage',STAGES[0]))
    with st.container(key='prep_header'):
        title,stage_column=st.columns([3.2,1.15],vertical_alignment='bottom')
        with title:
            st.header('나의 지원 준비')
            st.markdown('<div class="prep-notice-title">'+esc(n.get('notice_title','공고'))+'</div>',unsafe_allow_html=True)
        with stage_column:
            stage=st.selectbox('현재 지원 단계',STAGES,key='answer_review_stage',on_change=change_stage)
    a['review_stage']=stage
    from situation_questions import build_questionnaire
    questionnaire=build_questionnaire(n,state.get('pages',[]),a,stage)
    keys=[q['key'] for q in questionnaire['current'] if q['kind']=='basic']
    extra=[q['question'] for q in questionnaire['current'] if q['kind']=='extra']
    extra += [c for q in questionnaire['current'] for c in q.get('companions',[]) if a.get('question_answers',{}).get(c['text'])]
    a['condition_answers']=bind_answers(n,keys,extra,a,a.get('question_answers',{}))
    if a.get('profile_revision')!=fingerprint(state.get('common_profile',{})):
        st.warning('내 정보가 바뀌었어요. 내 상황에서 적용 답변을 다시 확인해주세요.')
        state.pop('result',None)
    bundle=source_bundle(root,state)
    if bundle['stale']:st.warning('현재 열린 결과의 최신 원문 확인이 필요해요. 이전 준비 기록을 표시하고 있습니다.')
    if state.get('_prep_refresh_result'):
        r=state['_prep_refresh_result']
        st.write(('일부 자료 확인 필요' if r['failed'] else '원문 확인 완료')+f' · 새 분석 {r["analyzed"]} · 재사용 {r["reused"]}')
    for change in bundle['changes']:
        st.markdown('<div class="prep-change">원문이 변경됐어요 · '+esc(change['name'])+'</div>',unsafe_allow_html=True)
        with st.expander('변경 내용 보기 · '+change['name']):
            st.write('이전 확인: '+change.get('previous_checked_at','')+' / 새 확인: '+change.get('checked_at',''))
            if change['status']=='source_and_config_changed':st.write('원문과 분석 설정이 함께 바뀌어 항목별 자동 비교를 확정할 수 없어요.')
            for detail in change['items']:
                st.write('**'+detail['kind']+'**');st.text('이전: '+detail['before']+'\n현재: '+detail['after'])
                if detail.get('needs_review'):st.write('원문 변경 후 확보한 근거의 차이예요. 추가·삭제 여부는 원문을 대조해주세요.')
            if not change['items']:st.write('원본 파일이 바뀌었어요. 구체적인 변경 사항은 원문을 확인해주세요.')
    metrics=st.container();coverage=st.container();actions_panel=st.container()
    rows=document_rows(bundle,stage,state,a)
    st.markdown('### 제출서류 체크리스트')
    st.markdown('<div id="prep-checklist" class="section-anchor"></div>',unsafe_allow_html=True)
    groups=[b for b in ('현재 단계','시점 확인 필요','이후 단계','이전 단계') if any(r['bucket']==b for r in rows)]
    focus=state.get('_prep_focus','')
    if rows:
        with st.container(key='prep_doc_tabs'):
            tabs=st.tabs([b+' '+str(sum(r['bucket']==b for r in rows)) for b in groups])
        for index,(tab,group) in enumerate(zip(tabs,groups)):
            with tab:
                if group!='현재 단계':st.write('현재 단계의 준비 진행률에 포함하지 않아요.')
                with st.container(border=True,key='prep_document_list_'+str(index)):
                    for row in rows:
                        if row['bucket']==group:draw_document(row,scope)
        with st.popover('준비 상태 안내'):
            st.write('체크는 직접 표시한 준비 상태예요. 서류 내용·유효성이나 실제 접수를 검증한 결과가 아닙니다. 선택하지 않은 항목은 확인 필요로 남아요.')
    else:
        with st.container(border=True,key='prep_empty'):
            st.markdown('**제출서류 목록을 확인하지 못했어요**')
            st.write('서류가 필요 없다는 뜻은 아니에요.')
            if n.get('_schema_limits'):st.write('이전 분석에는 서류별 항목이 포함되지 않았어요.')
            if bundle['url']:st.link_button('원문에서 확인하기 ↗',bundle['url'])
            else:st.download_button('원본 내려받아 확인하기',state.get('pdf',b''),state.get('source_filename','notice.pdf'),key='prep_empty_source')
    a['document_checklist']=rows
    conditions=condition_rows(n,a,state.get('pages',[]));a['independent_conditions']=conditions
    # Other documents keep their own provenance. They are available for separate
    # review; selected-document answers must never be applied to a different rule.
    for doc in bundle['documents'][1:]:
        if doc['notice'].get('eligibility_rule') or doc['notice'].get('_structured_notice',{}).get('지원조건'):
            st.write('추가 자료의 조건도 확인해주세요: '+doc['name'])
    from deadline_calendar import document_deadlines,consolidate,event_status
    dates=consolidate([document_deadlines(d['notice'],d['pages'],{'id':d['sha256'],'source_url':d['url'],'checked_at':d.get('checked_at','')}) for d in bundle['documents']],bundle['stale'])
    events=dates['events'];expired=bool(events) and all(event_status(e)=='마감' for e in events)
    progress=document_progress(rows,bundle)
    actions=preparation_actions(bundle,rows,conditions,a,expired)
    with metrics:
        with st.container(key='prep_metrics'):
            c1,c2,c3=st.columns(3)
            with c1,st.container(border=True,key='metric_deadline'):
                date_value='\n'.join((event['stage']+' · ' if len(events)>1 else '')+event['date'].replace('-','.')+(' · '+event['time'] if event['time'] else '') for event in events) or dates['category']
                metric_heading('date','접수 마감',date_value)
                if expired:st.markdown('<div class="prep-metric-foot">'+prep_badge('마감됨')+'</div>',unsafe_allow_html=True)
                with st.popover('마감 근거'):
                    for event in events:
                        st.write(event_status(event))
                        st.write(event['date']+' · '+(event['time'] or '시간 확인 필요')+' · '+(event.get('timezone') or '시간대 확인 필요'))
                        st.write(event.get('delivery',''))
                    for ev in dates.get('evidence',[]):st.text(ev.get('quote',''))
            with c2,st.container(border=True,key='metric_submission'):
                method=n.get('submission_method') or '확인 필요'
                brief=re.sub(r'https?://\S+','',method).split('\n')[0].split('(')[0].strip(' ·:')
                metric_heading('link','신청 방법',brief[:30]+('…' if len(brief)>30 else ''))
                url=submission_url(method)
                if url and any(url in p for p in state.get('pages',[])):st.link_button('접수 페이지 ↗',url)
                else:
                    with st.popover('신청 방법 확인'):st.write(method)
            with c3,st.container(border=True,key='metric_progress'):
                value=f'{progress["done"]} / {progress["total"]} 준비 완료' if progress['total'] else '필수 목록 확인 필요'
                metric_heading('file','확인된 현재 단계 필수 서류',value)
                if progress['total']:
                    st.progress(progress['done']/progress['total'])
                if progress['partial']:st.markdown('<div class="prep-metric-foot">'+prep_badge('목록·적용 범위 확인 필요')+'</div>',unsafe_allow_html=True)
    with coverage:
        ready=sum(d.get('status')=='ready' for d in bundle['inventory']);pending=len(bundle['inventory'])-ready
        text=f'분석 완료 {ready}건' if ready else '분석 범위 확인 필요'
        if pending:text+=f' · 미완료 {pending}건'
        if bundle['warnings'] or bundle['status']=='legacy':text+=' · 전체 범위 확인 필요'
        with st.container(border=True,key='prep_sources'):
            st.markdown('<div class="prep-coverage">'+prep_icon('file')+'<strong>'+esc(f'자료 {ready}건 분석 완료' if ready else '분석 범위 확인 필요')+'</strong>'+(prep_badge(f'미완료 {pending}건') if pending else '')+(prep_badge('전체 범위 확인 필요') if bundle['warnings'] or bundle['status']=='legacy' else '')+'</div>',unsafe_allow_html=True)
            render_sources(root,bundle,connection,go)
    with actions_panel:
        st.markdown('### 지금 할 일')
        if expired:st.write('지원 접수는 마감됐어요. 현재 활동 단계의 서류를 확인해주세요.' if stage in STAGES[-2:] else '마감된 공고예요. 아래는 조건 확인과 준비 기록을 위한 안내입니다.')
        with st.container(border=True,key='prep_action_list'):
          for i,action in enumerate(actions):
            with st.container(key='prep_action_'+str(i)):
                copy,button=st.columns([4,1.3],vertical_alignment='center')
                copy.markdown('<div class="prep-action-copy"><span class="prep-action-number">'+str(i+1)+'</span><div><strong>'+esc(action['title'])+'</strong><p>'+esc(action['detail'])+'</p></div></div>',unsafe_allow_html=True)
                if button.button(action['label'],key='prep_action_button_'+str(i),type='primary' if i==0 else 'secondary',use_container_width=True):
                    if action['target']=='question':
                        state['_prep_focus_condition']=action.get('condition_id');go(3)
                    else:
                        from ui_focus import queue_focus
                        jump('document:'+action['doc_id'] if action.get('doc_id') else action['target'])
                        doc=next((r for r in rows if r['id']==action.get('doc_id')),None)
                        selector='.st-key-prep_document_'+doc['storage_key'] if doc else '.st-key-prep_sources' if action['target']=='sources' else '#prep-conditions' if action['target']=='conditions' else '#prep-checklist'
                        queue_focus(selector)
                    st.rerun()
    counts=Counter(r['status'] for r in conditions if r['status']!='이후 단계')
    conflicts=[r for r in conditions if r.get('category')=='eligibility' and r['status']=='불일치' and r.get('verified')]
    if conflicts:st.warning('지원 자격 불일치: '+' · '.join(r['label'] for r in conflicts))
    st.markdown('<div id="prep-conditions" class="section-anchor"></div>',unsafe_allow_html=True)
    with st.expander('조건 검토 · 불일치 '+str(counts['불일치'])+' · 확인 필요 '+str(counts['확인 필요']),expanded=focus=='conditions'):
        st.write('확보한 조건별 검토 결과예요. 불일치가 없더라도 전체 지원 가능 확정은 아닙니다.')
        render_conditions(conditions,scope)
    a['other_facts']+='\n제출물 준비 상태(본인 확인):\n'+'\n'.join(r['text']+' / 적용: '+r['applicability']+' / 상태: '+r['readiness']+' / 제출 단계: '+r['stage']+' / 자료: '+r['source_name'] for r in rows)
    state.preparation={'answers':a,'checklist':rows,'condition_rows':conditions,'next_actions':actions,'coverage':{
        'status':bundle['status'],'inventory':bundle['inventory'],'warnings':bundle['warnings'],'checked_at':bundle['checked_at']},'progress':progress}
    export_notice={**n,'application_deadline':' / '.join((e['stage']+' · ' if len(events)>1 else '')+e['date']+(' '+e['time'] if e['time'] else ' · 시간 확인 필요') for e in events) or dates['category'],
        'deadline_note':'\n'.join(ev.get('quote','') for ev in dates.get('evidence',[])) or '근거 확인 필요'}
    exported=preparation_text(export_notice,a,rows,actions)+'\n\n분석 범위\n'+text+'\n원문 확인: '+(bundle['checked_at'] or '기록 없음')
    for row in rows:
        exported+='\n'+row['name']+' / '+row['bucket']+' / '+('다시 확인 필요' if row['needs_recheck'] else row['readiness'])+' / '+row['requirements']+'\n근거: '+row['source_name']+' '+row['source_page']+'쪽 '+row['source_quote']
    return a,rows,actions,exported
