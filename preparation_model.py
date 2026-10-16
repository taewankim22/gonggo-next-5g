"""Preparation facts and actions. No network, AI, or private data publication."""
from copy import deepcopy
import re
from core import fingerprint, normalize, evidence
from planning import document_items, STAGES
from source_context import CURRENT, FUTURE, AFTER, UNKNOWN


def compare_sources(old_record, old, record, new):
    """Source bytes, not extraction/config changes, establish a source revision."""
    if old_record.get('sha256') == record.get('sha256'):
        return {'status':'unchanged','items':[]}
    result={'status':'source_changed','items':[], 'previous_checked_at':old_record.get('checked_at',''),
            'checked_at':record.get('checked_at',''), 'old_hash':old_record.get('sha256'), 'new_hash':record.get('sha256')}
    if old_record.get('config') != record.get('config'):
        result['status']='source_and_config_changed'
        return result
    from deadline_calendar import document_deadlines,consolidate
    def dates(a,r):
        return consolidate([document_deadlines(a['notice'],a['pages'],r)])['events']
    before,after=dates(old,old_record),dates(new,record)
    if len(before)==len(after)==1 and before[0]['stage']==after[0]['stage']:
        a,b=before[0],after[0]
        if (a['date'],a['time'])!=(b['date'],b['time']):
            result['items'].append({'kind':'접수 마감','before':a['date']+' '+a['time'],'after':b['date']+' '+b['time'],
                                    'evidence_before':a,'evidence_after':b})
    # Describe a grounded excerpt changing, not an inferred requirement being repealed.
    for table,label in [('제출서류','제출서류·양식 근거'),('지원조건','지원 조건 근거')]:
        def quotes(a):
            return sorted({r['근거원문'] for r in a['notice'].get('_structured_notice',{}).get(table,[])
                           if evidence(r.get('근거원문'),r.get('근거페이지'),a['pages'])})
        a,b=quotes(old),quotes(new)
        if a!=b:
            result['items'].append({'kind':label,'before':'\n'.join(a) or '확보하지 못함',
                                    'after':'\n'.join(b) or '확보하지 못함', 'needs_review':True})
    return result


def source_bundle(root,state):
    """Only same bulletin URL + current hash/config join. Never join on title."""
    from catalog import load_catalog,available_record
    from live_catalog import LiveCatalog
    source=state.get('catalog_source',{})
    url=source.get('source_url') or source.get('url','')
    current={'notice':state['notice'],'pages':state.get('pages',[]),'sha256':state['source_hash'],
             'name':state.get('source_filename','공고 원문'),'url':source.get('document_url') or url,
             'config':state.get('notice_config',{}),'selected':True,'checked_at':source.get('checked_at',''),
             'analyzed_at':source.get('analyzed_at',''), 'source_changes':source.get('source_changes') or {}}
    bundle={'url':url,'documents':[current],'inventory':[],'warnings':[],'status':'uploaded' if not url else 'legacy',
            'checked_at':source.get('checked_at',''),'fetch_failed':False,'stale':False,'changes':[]}
    if not url:
        bundle['inventory']=[{'name':current['name'],'status':'ready','url':'','selected':True}]
        return bundle
    records=[r for r in load_catalog(root) if r.get('source_url')==url]
    selected=next((r for r in records if r.get('sha256')==current['sha256'] and
                   (r.get('id')==source.get('id') or r.get('document_url')==current['url'])),None)
    if selected:
        current.update(name=selected.get('document_name') or current['name'],url=selected.get('document_url',url),
                       analyzed_at=selected.get('analyzed_at',''),source_changes=selected.get('source_changes') or {})
    scan=LiveCatalog(root).scans().get(url)
    if scan:
        bundle.update(status='complete' if scan.get('complete') else 'partial',checked_at=scan.get('checked_at',''),
                      warnings=scan.get('warnings',[]),fetch_failed=bool(scan.get('fetch_failed')))
        bundle['inventory']=deepcopy(scan.get('documents',[]))
        urls={d['url'] for d in bundle['inventory']}
        for a in scan.get('attachments',[]):
            if a['url'] not in urls:
                unsupported=bool(re.search(r'\.(zip|xlsx|docx)(?:$|\?)',a.get('name',''),re.I))
                bundle['inventory'].append({**a,'status':'unsupported' if unsupported else 'download_failed'})
        selected_scan=next((d for d in scan.get('documents',[]) if d['url']==current['url']),None)
        bundle['stale']=bool(scan.get('fetch_failed') or not selected_scan or
                             selected_scan.get('sha256')!=current['sha256'] or selected_scan.get('status')!='ready')
        current['stale']=bundle['stale']
    else:
        bundle['inventory']=[dict(name=r.get('document_name',r.get('filename','공고 원문')),url=r.get('document_url',url),status='ready') for r in records]
        bundle['warnings']=['전체 첨부의 처리 기록이 없습니다. 현재 열어 둔 자료의 결과를 표시합니다.']
    for r in records:
        if r.get('sha256')==current['sha256']:continue
        if not scan or scan.get('fetch_failed'):continue
        if not any(d.get('status')=='ready' and d.get('url')==r.get('document_url') and
                   d.get('sha256')==r.get('sha256') and r.get('config')==scan.get('config') for d in scan['documents']):continue
        loaded=available_record(root,r)
        if loaded:
            bundle['documents'].append({'notice':loaded['notice'],'pages':loaded['pages'],'sha256':r['sha256'],
                'name':r.get('document_name',r['filename']),'url':r.get('document_url',url),'config':r.get('config',{}),
                'selected':False,'record_id':r['id'],'record':r,'checked_at':r.get('checked_at',''),
                'analyzed_at':r.get('analyzed_at',''),'source_changes':r.get('source_changes') or {}})
    for doc in bundle['documents']:
        if doc.get('source_changes',{}).get('status') in ('source_changed','source_and_config_changed'):
            bundle['changes'].append({'name':doc['name'],**doc['source_changes']})
    return bundle


def bucket(item,stage):
    if item['stage']==UNKNOWN:return '시점 확인 필요'
    rank={CURRENT:0,FUTURE:1,AFTER:2}
    now=2 if stage==STAGES[-1] else 1 if stage==STAGES[-2] else 0
    target=rank.get(item['stage'],0)
    if target>now:return '이후 단계'
    if target<now or (stage in ('서류 제출 후','면접 준비 중') and target==0):return '이전 단계'
    return '현재 단계'


def document_rows(bundle,stage,state,answers):
    from conditions import has_social,social_document,social_answer
    rows=[];exact={}; identities={}
    for source in bundle['documents']:
        for item in document_items(source['notice'],source['pages']):
            item=dict(item)
            item.setdefault('target','')
            item.setdefault('requirements','')
            item.setdefault('category_verified',item.get('source_found',False))
            item['source_name']=source['name'];item['source_url']=source['url'];item['source_hash']=source['sha256']
            item['source_selected']=source['selected'];item['stale']=source.get('stale',False)
            item['prefix']='doc_'+source['sha256'][:12]+'_'+item['id']
            # Scope by bulletin/document identity, recipient and phase. No fuzzy name matching.
            item['storage_key']=fingerprint([bundle['url'] or source['sha256'],normalize(item['name']),item['target'],item['stage']])[:24]
            item['signature']=fingerprint([item['category'],item['target'],item['stage'],item.get('requirements_candidate',item['requirements']),normalize(item['source_quote'])])
            signature=(item['storage_key'],item['signature'])
            if signature in exact:
                exact[signature]['sources'].append({'name':source['name'],'page':item['source_page'],'quote':item['source_quote'],'url':source['url']})
                continue
            # Conflicting current documents stay separate; do not resolve based on upload order.
            if item['storage_key'] in identities:
                previous=identities[item['storage_key']];previous['conflict']=True;item['conflict']=True
                item['storage_key']+='_'+fingerprint(source['url'])[:8]
            identities[item['storage_key']]=item
            item['sources']=[{'name':source['name'],'page':item['source_page'],'quote':item['source_quote'],'url':source['url']}]
            saved=state.get('prep_document_states',{}).get(item['storage_key'],{})
            done=saved.get('done',state.get(item['prefix']+'_done',state.get(item['prefix']+'_ready') in ('준비 완료','제출 완료')))
            linked=has_social(source['notice']) and social_document(item) and item['category']!='필수'
            applies=(social_answer(answers) or '아직 모름') if linked and source['selected'] else saved.get('applicability',state.get(item['prefix']+'_applies','아직 모름')) if item['category']!='필수' else '해당'
            item.update(done=bool(done),applicability=applies,linked_social=linked,
                        needs_recheck=bool(saved.get('signature') and saved['signature']!=item['signature']),
                        bucket=bucket(item,stage),later=bucket(item,stage)=='이후 단계')
            item['readiness']='준비 완료' if done and not item['needs_recheck'] and applies!='해당 없음' else '아직 확인하지 않음'
            rows.append(item);exact[signature]=item
    for item in rows:
        if item.get('conflict'):item['readiness']='아직 확인하지 않음'
    return rows


def document_progress(rows,bundle):
    current=[r for r in rows if r['bucket']=='현재 단계' and r['category']=='필수' and r['applicability']=='해당'
             and r['source_found'] and r['category_verified'] and not r.get('conflict') and not r.get('stale')]
    done=sum(r['readiness']=='준비 완료' and not r['needs_recheck'] for r in current)
    uncertain=bool(bundle['status']!='complete' or bundle['warnings'] or bundle['stale'] or any(
        r['stage']==UNKNOWN or not r['source_found'] or r['category']=='대상·필수 여부 확인' or r.get('conflict') or r['applicability']=='아직 모름' for r in rows))
    return {'done':done,'total':len(current),'partial':uncertain,'unknown':not bool(current)}


def preparation_actions(bundle,rows,conditions,answers,expired=False):
    actions=[]
    def add(title,detail,target,label,**kw):actions.append(dict(title=title,detail=detail,target=target,label=label,**kw))
    conflicts=[r for r in conditions if r.get('category')=='eligibility' and r.get('status')=='불일치' and r.get('verified')]
    if conflicts:add('지원 자격이 다른 조건을 확인해주세요',conflicts[0]['reason'],'conditions','조건 확인')
    retry=next((d for d in bundle['inventory'] if d.get('status') in ('failed','pending','download_failed')),None)
    if retry:add('누락된 자료를 확인해주세요',retry['name']+' · 일부 조건과 서류가 빠져 있을 수 있어요.','sources','분석 범위 보기')
    changed=next((r for r in rows if r['needs_recheck']),None)
    if changed:add('서류 요구사항이 바뀌었어요',changed['name']+' · 기존 준비 기록을 보존했어요.','document','변경 확인',doc_id=changed['id'])
    unclear=next((r for r in rows if r.get('conflict')),None)
    if unclear:add('자료마다 서류 안내가 달라요',unclear['name'],'document','근거 비교',doc_id=unclear['id'])
    # An expired or already-submitted application must not receive an urgent application-prep CTA.
    stage=answers.get('review_stage',STAGES[0])
    preparing=not expired and stage not in ('서류 제출 후','면접 준비 중')
    pending=[r for r in rows if r['bucket']=='현재 단계' and r['category']=='필수' and r['applicability']=='해당'
             and r['readiness']!='준비 완료' and r['source_found'] and not r.get('conflict') and not r.get('stale')]
    if preparing and pending:add(pending[0]['name']+' 준비 상태를 확인해주세요','확인된 현재 단계 필수 서류예요.','document','서류 확인',doc_id=pending[0]['id'])
    for r in conditions:
        if r.get('status')=='확인 필요' and r.get('category')!='documents':
            title=(r['label']+' 확인이 필요해요') if len(r['label'])<35 else '지원 조건 답변을 확인해주세요'
            add(title,r.get('reason',''),'question','답변 확인',condition_id=r['id']);break
    if not rows:add('제출서류 목록을 확인해주세요','분석에서 목록을 확보하지 못했어요. 서류가 필요 없다는 뜻은 아니에요.','sources','원문 확인')
    if not actions:
        if expired:add('마감된 공고의 준비 기록입니다','원문과 이전 준비 내용을 확인할 수 있어요.','sources','원문 보기')
        elif stage in ('서류 제출 후','면접 준비 중'):add('접수 기록과 이후 일정을 확인해주세요','접수 여부는 제출한 사이트에서 직접 확인해주세요.','sources','원문 보기')
        else:add('표시한 준비 내용을 확인해주세요','확인한 서류의 준비 상태이며 전체 지원 자격이나 접수 완료를 뜻하지 않아요.','checklist','준비 목록 보기')
    return actions[:3]


def selected_review_answers(answers,notice,pages,original_other_facts=''):
    """A document-scoped AI review receives only evidence from that document."""
    from independent_review import condition_rows
    result=deepcopy(answers)
    result['document_checklist']=[r for r in answers.get('document_checklist',[]) if r.get('source_selected',True)]
    result['independent_conditions']=condition_rows(notice,result,pages)
    result['other_facts']=original_other_facts+'\n제출물 준비 상태(본인 확인):\n'+'\n'.join(
        r['text']+' / 적용: '+r['applicability']+' / 상태: '+r['readiness'] for r in result['document_checklist'])
    return result


def adopt_public_update(state,new):
    """Archive old source; preserve explicit inputs only for unchanged condition semantics."""
    from workspaces import checkpoint,clear_active
    from situation_questions import build_questionnaire
    from profiles import atomic_conditions
    old=dict(state);checkpoint(state)
    same=old.get('source_hash')==new['source_hash']
    keep={k:deepcopy(v) for k,v in old.items() if k in ('prep_document_states','prep_source_history')}
    if same:
        keep.update({k:deepcopy(v) for k,v in old.items() if k.startswith(('answer_','question_','doc_','fact_')) or
                     k in ('draft_answers','profile_overrides','profile_seeded','profile_provenance','situation_responses','schedule_state')})
    else:
        a=old.get('draft_answers',{});stage=a.get('review_stage',STAGES[0])
        before=build_questionnaire(old['notice'],old.get('pages',[]),a,stage)
        after=build_questionnaire(new['notice'],new['pages'],a,stage)
        unchanged={q['id'] for q in before['current']+before['later'] for r in after['current']+after['later'] if
                   q['id']==r['id'] and q.get('rule')==r.get('rule') and q.get('stage')==r.get('stage') and q.get('period')==r.get('period')}
        old_scope=old['source_hash'][:12];new_scope=new['source_hash'][:12]
        for q in before['current']+before['later']:
            if q['id'] not in unchanged:continue
            key=q.get('key')
            if key and 'answer_'+key in old:keep['answer_'+key]=old['answer_'+key]
        # Per-condition overrides are keyed by exact rule identity, never by field name alone.
        oldc={c['id']:c for c in atomic_conditions(old['notice'])};newc={c['id']:c for c in atomic_conditions(new['notice'])}
        valid={key for key in oldc.keys() & newc.keys() if oldc[key]==newc[key]}
        for k in ('profile_overrides','profile_provenance','profile_seeded'):
            keep[k]={key:deepcopy(v) for key,v in old.get(k,{}).items() if key in valid}
        keep['answer_review_stage']=stage
        keep['situation_responses']={key:deepcopy(v) for key,v in old.get('situation_responses',{}).items() if key in unchanged}
        for key,value in old.items():
            if key.startswith('question_'+old_scope+'_') and any(qid in key for qid in unchanged):keep[key.replace(old_scope,new_scope,1)]=value
        keep['prep_source_history']={'previous_hash':old['source_hash'],'message':'원문이 갱신됐어요. 이전 준비 기록은 보관했고, 기준이 달라진 답변은 다시 확인해주세요.'}
    clear_active(state);state.update(new);state.update(keep)
    state.update(route='review',screen=4 if same and 'draft_answers' in keep else 3)
