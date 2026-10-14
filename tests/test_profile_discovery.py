import json
from copy import deepcopy
from pathlib import Path
from profiles import applied_facts,atomic_conditions,profile_rows,profile_fact
from browser_draft import snapshot,restore,single_snapshot
from workspaces import checkpoint,activate,seed_basic,explicit_basic,refresh_profile
from catalog import status_label,available_record,cached_public
from core import fingerprint
import datetime as dt

ROOT=Path(__file__).parents[1]
def fact(value,period='',scale=''):
    return dict(state='known',value=value,period=period,scale=scale)
def sample():
    n=json.loads((ROOT/'data/demo_notice.json').read_text(encoding='utf-8'))
    data=(ROOT/'data/hyundai_jump_13.pdf').read_bytes()
    return dict(notice=n,pdf=data,source_hash=fingerprint(data),source_filename='a.pdf',pages=['원문'],last_mode='예시 화면 체험',screen=3)
def condition(**kwargs):
    return dict(field='remaining_terms',category='eligibility',rule='잔여학기 2학기 이상',quote='2026년 3월 기준 잔여학기 2학기 이상',page='1',operator='gte',value='2',period='2026-03',scale='',logic='single',scope='',**kwargs)
def notice(c):return {'profile_conditions_json':json.dumps([c],ensure_ascii=False)}

def test_profile_without_notice_roundtrip_excludes_key():
    p={'school':fact('가상대'),'gpa':fact(3.5,'2026-1학기','4.5')}
    restored=restore(snapshot({'common_profile':p,'api_key':'SECRET'}))
    assert restored['common_profile']==p and 'SECRET' not in json.dumps(restored)

def test_v1_migration_preserves_answers_and_does_not_promote_free_text():
    s=sample();s.update(answer_other_facts='가상대 재학',draft_answers={'other_facts':'가상대 재학'})
    p=single_snapshot(s);r=restore(p)
    assert r['answer_other_facts']=='가상대 재학' and not r.get('common_profile')

def test_a_b_a_checklists_and_answers_do_not_mix():
    s=sample();s['answer_remaining_terms']=1;s['doc_012345abcdef_abcdef_done']=True
    checkpoint(s);a=s['workspaces'][s['source_hash']]
    b=sample();b['pdf']+=b'\n';b['source_hash']=fingerprint(b['pdf']);b['source_filename']='b.pdf'
    activate(s,single_snapshot(b))
    assert 'answer_remaining_terms' not in s and 'doc_012345abcdef_abcdef_done' not in s
    s['answer_remaining_terms']=4;checkpoint(s);activate(s,a)
    assert s['answer_remaining_terms']==1 and s['doc_012345abcdef_abcdef_done']
    assert len(restore(snapshot(s))['workspaces'])==1

def test_explicit_unknown_blocks_profile_and_explicit_value_wins():
    n=notice(condition());c=atomic_conditions(n)[0];p={'remaining_terms':fact(3,'2026-03')}
    assert applied_facts(n,p,{})[c['id']]['value']==3
    assert applied_facts(n,p,{c['id']:{'state':'unknown'}})[c['id']]['value'] is None
    assert applied_facts(n,p,{c['id']:fact(1)})[c['id']]['value']==1

def test_time_mismatch_does_not_convert_current_facts_to_historical():
    p={'remaining_terms':fact(3,'2026-10')}
    assert profile_fact(p,'remaining_terms','2026-03')[0] is None
    assert profile_fact(p,'remaining_terms','')[0] is None

def test_basic_explicit_unknown_never_refilled_after_profile_update():
    n={'eligibility_rule':'2026년 3월 기준 잔여학기 2학기 이상'};s={};p={'remaining_terms':fact(3,'2026-03')}
    seed_basic(s,n,p);assert s['answer_remaining_terms']==3
    s['answer_remaining_terms']=None;explicit_basic(s,'remaining_terms');seed_basic(s,n,p)
    assert s['answer_remaining_terms'] is None

def test_confirmed_conflict_survives_unanswered_profile_fields():
    c=condition();n=notice(c);p={'remaining_terms':fact(1,'2026-03')}
    r=profile_rows(n,{'profile_facts':applied_facts(n,p,{})},[c['quote']])
    assert r[0]['status']=='불일치'
    c['quote']='문서에 없는 기준';n=notice(c)
    assert profile_rows(n,{'profile_facts':applied_facts(n,p,{})},['실제 원문'])[0]['status']=='확인 필요'

def test_ambiguous_gpa_scale_or_or_condition_cannot_reject():
    c=condition();c.update(field='gpa',operator='gte',value='3.5',quote='4.5점 만점 3.5점 이상 또는 백분위 85점 이상',scale='4.5',period='2026-1학기',logic='complex')
    n=notice(c);p={'gpa':fact(3.0,'2026-1학기','4.3')}
    assert profile_rows(n,{'profile_facts':applied_facts(n,p,{})},[c['quote']])[0]['status']=='확인 필요'
    c.update(logic='single',quote='4.5점 만점 3.5점 이상');n=notice(c)
    assert profile_rows(n,{'profile_facts':applied_facts(n,p,{})},[c['quote']])[0]['status']=='확인 필요'

def test_profile_edit_invalidates_derived_results_not_explicit_answers():
    s=sample();s.update(result=['old'],answer_remaining_terms=1,common_profile={'school':fact('다른대')})
    refresh_profile(s)
    assert 'result' not in s and s['answer_remaining_terms']==1 and s['screen']==3

def test_sessions_not_shared_and_no_profile_in_public_catalog():
    a=sample();a['common_profile']={'school':fact('개인학교')};b=restore(snapshot(sample()))
    assert not b['common_profile']
    assert '개인학교' not in (ROOT/'data/catalog/index.json').read_text(encoding='utf-8') if (ROOT/'data/catalog/index.json').exists() else True

def test_closed_and_missing_source_are_distinct():
    assert status_label({'deadline':'2026-01-26'},dt.date(2026,10,13))=='과거 검증 사례'
    assert status_label({'deadline':''})=='접수 상태 확인 필요'
    assert available_record(ROOT,{'status':'failed'}) is None

def test_collector_canonical_dedup_and_no_jobs():
    from collect_notices import normalized
    assert normalized('https://example.org/x?mode=view&articleNo=1&article.offset=20#top')==normalized('https://example.org/x?articleNo=1&mode=view')
    code=(ROOT/'collect_notices.py').read_text(encoding='utf-8')
    assert 'create_job(' not in code and 'Store(' not in code

def test_public_cache_requires_exact_file_and_configuration():
    from catalog import load_catalog
    records=load_catalog(ROOT)
    if not records:return
    row=next(r for r in records if r['id']=='notice1')
    assert cached_public(ROOT,row['sha256'],'agt_bmPkaZ9TyocTVn7Nw4BEbh','7')
    assert cached_public(ROOT,row['sha256'],'agt_bmPkaZ9TyocTVn7Nw4BEbh','4') is None
    assert cached_public(ROOT,'changed-content','agt_bmPkaZ9TyocTVn7Nw4BEbh','7') is None

def test_profile_first_numeric_fact_reaches_real_question_and_review(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from catalog import load_catalog
    monkeypatch.setattr('browser_draft.bootstrap',lambda:None)
    monkeypatch.setattr('browser_draft.save_browser',lambda:None)
    monkeypatch.setattr('team_access.team_gate',lambda *args,**kwargs:(None,None))
    state=available_record(ROOT,next(r for r in load_catalog(ROOT) if r['id']=='notice1'));assert state
    at=AppTest.from_file(str(ROOT/'app.py')).run()
    for key,value in state.items():at.session_state[key]=value
    at.session_state.common_profile={'remaining_terms':fact(1.0,'2026-03')}
    at.session_state.screen=3;at.session_state.route='review';at.run()
    assert not at.exception and at.number_input(key='answer_remaining_terms').value==1
    at.button(key='nav_4').click().run()
    assert not at.exception and any(r['status']=='불일치' for r in at.session_state['preparation']['condition_rows'])
