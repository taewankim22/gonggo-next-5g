"""Per-notice private state. No process-wide cache or account data."""
from copy import deepcopy
from core import fingerprint

EXTRA={'profile_overrides','profile_seeded','profile_provenance','notice_config','catalog_source','profile_revision'}
RUNTIME={'pdf','raw_notice','result','raw_review','review_hash','review_pdf','notice_trace','review_trace','profile','preparation'}

def checkpoint(state):
    from browser_draft import single_snapshot
    record=single_snapshot(state)
    if record:
        records=deepcopy(state.get('workspaces',{}))
        records[state['source_hash']]=record
        state['workspaces']=records

def clear_active(state):
    from browser_draft import allowed
    for key in list(state):
        if allowed(key) or key in RUNTIME:state.pop(key,None)
    state.pop('pending_file',None)
    state['_upload_generation']=state.get('_upload_generation',0)+1

def activate(state,record):
    from browser_draft import restore_single
    checkpoint(state)
    restored=restore_single(record)
    clear_active(state);state.update(restored)
    state.update(route='review',screen=restored.get('screen',2))

def refresh_profile(state):
    """Discard derived output, keep all explicit notice overrides and checkboxes."""
    for key in ('result','review_hash','preparation','raw_review'):state.pop(key,None)
    state['profile_revision']=fingerprint(state.get('common_profile',{}))
    state['profile_changed']=True
    if state.get('notice'):state['screen']=3

def seed_basic(state,notice,profile):
    from profiles import profile_fact, atomic_conditions
    provenance=dict(state.get('profile_provenance',{}));seeded=dict(state.get('profile_seeded',{}))
    for key in ('enrollment_status','remaining_terms'):
        widget='answer_'+key
        prior=seeded.get(key)
        if provenance.get(key)=='이번 공고 답변':continue
        if widget in state and (key not in seeded or state[widget]!=prior):
            provenance[key]='이번 공고 답변';continue
        conditions=[c for c in atomic_conditions(notice) if c['field']==key]
        period=conditions[0]['period'] if conditions else ''
        # Legacy extraction has a visible reference month for Hyundai, etc.
        if not period:
            import re
            m=re.search(r'(20\d{2})년\s*(\d{1,2})월\s*기준',notice.get('eligibility_rule',''))
            if m:period=f'{m[1]}-{int(m[2]):02d}'
        value,origin=profile_fact(profile,key,period)
        if value is not None:
            state[widget]=value;seeded[key]=value;provenance[key]=origin
        elif prior is not None:
            state[widget]=None if key=='remaining_terms' else '모르겠어요'
            seeded[key]=state[widget];provenance[key]=origin
        else:
            seeded[key]=None if key=='remaining_terms' else '모르겠어요';provenance[key]=origin
    state['profile_seeded']=seeded;state['profile_provenance']=provenance

def explicit_basic(state,key):
    provenance=dict(state.get('profile_provenance',{}));provenance[key]='이번 공고 답변'
    seeded=dict(state.get('profile_seeded',{}));seeded.pop(key,None)
    state['profile_provenance']=provenance;state['profile_seeded']=seeded
