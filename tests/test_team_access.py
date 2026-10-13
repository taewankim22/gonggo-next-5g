from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time
import pytest
from team_access import TeamConfig, Ledger, authorized, parse_config, protected_call


def config():
    return TeamConfig('unit-test-key','unit-test-password','agt_notice','4','agt_review','2',2)


def test_missing_or_invalid_secrets_fail_closed():
    for values in ({},{'enabled':False},{'enabled':True,'api_key':'test'}):
        with pytest.raises(ValueError):parse_config(values)
    values={'enabled':True,'api_key':'test','password':'test-password-123',
            'notice_id':'agt_n','notice_version':'4','review_id':'agt_r','review_version':'2'}
    assert parse_config(values).daily_limit==0
    for limit in (-1,True,'20'):
        with pytest.raises(ValueError):parse_config(dict(values,daily_limit=limit))


def test_authorization_expires_and_secret_rotation_revokes():
    cfg=config(); state={'_team_auth':cfg.auth_tag,'_team_login_at':1000}
    assert authorized(state,cfg,1001)
    assert not authorized(state,cfg,8200)
    cfg.password='rotated-password'
    assert not authorized(state,cfg,1001)
    assert cfg.api_key not in repr(cfg)


def test_atomic_concurrent_reservation_across_connections(tmp_path):
    path=tmp_path/'usage.sqlite'; Ledger(path)
    def reserve(_):
        try:return Ledger(path).reserve(20,100000)
        except ValueError:return None
    with ThreadPoolExecutor(max_workers=6) as pool:
        tokens=list(pool.map(reserve,range(6)))
    assert sum(t is not None for t in tokens)==1
    assert Ledger(path).used(100000)==1


def test_failures_count_and_limit_persists_in_new_ledger(tmp_path):
    ledger=Ledger(tmp_path/'usage.sqlite')
    token=ledger.reserve(2,100000);ledger.release(token)
    with pytest.raises(ValueError,match='10초'):ledger.reserve(2,100001)
    token=ledger.reserve(2,100010);ledger.release(token)
    with pytest.raises(ValueError,match='한도'):Ledger(ledger.path).reserve(2,100020)
    assert Ledger(ledger.path).used(100020)==2
    assert Ledger(ledger.path).used(200000)==0


def test_unlimited_calls_exceed_old_cap_but_keep_concurrency_and_cooldown(tmp_path):
    ledger=Ledger(tmp_path/'unlimited.sqlite')
    for i in range(25):
        token=ledger.reserve(0,100000+i*10)
        ledger.release(token)
    assert ledger.used(100240)==25
    with pytest.raises(ValueError,match='10초'):ledger.reserve(0,100241)
    token=ledger.reserve(0,100250)
    with pytest.raises(ValueError,match='진행 중'):ledger.reserve(0,100260)
    ledger.release(token)


def test_auth_and_agent_checks_happen_before_call_or_quota(tmp_path):
    cfg=config(); ledger=Ledger(tmp_path/'usage.sqlite');calls=[]
    runner=lambda *a,**k:calls.append(a)
    with pytest.raises(ValueError,match='만료'):protected_call(cfg,{},ledger,runner,'','agt_notice','4',b'pdf')
    state={'_team_auth':cfg.auth_tag,'_team_login_at':time.time()}
    with pytest.raises(ValueError,match='지정'):protected_call(cfg,state,ledger,runner,'','agt_other','4',b'pdf')
    assert not calls and ledger.used()==0
    def failing(key,*a,**k):
        assert key==cfg.api_key
        raise ValueError('provider failure')
    with pytest.raises(ValueError,match='provider'):protected_call(cfg,state,ledger,failing,'ignored','agt_notice','4',b'pdf')
    assert ledger.used()==1
    with ledger.connect() as db:assert db.execute('SELECT SUM(active) FROM calls').fetchone()[0]==0


def test_login_throttle_is_shared_and_expires(tmp_path):
    path=tmp_path/'usage.sqlite'
    assert all(Ledger(path).allow_login_attempt(1000) for _ in range(20))
    assert not Ledger(path).allow_login_attempt(1001)
    assert Ledger(path).allow_login_attempt(1601)


def test_public_access_needs_explicit_setting_and_keeps_quota(tmp_path):
    values={'enabled':True,'api_key':'unit-test-key','notice_id':'agt_notice',
            'notice_version':'4','review_id':'agt_review','review_version':'2','daily_limit':1}
    with pytest.raises(ValueError):parse_config(values)
    cfg=parse_config(values,password_required=False)
    assert authorized({},cfg)
    ledger=Ledger(tmp_path/'public.sqlite')
    calls=[]
    def runner(key,*args,**kwargs):
        assert key=='unit-test-key'
        calls.append(args)
        return {'result':'ok'}
    assert protected_call(cfg,{},ledger,runner,'','agt_notice','4',b'pdf')=={'result':'ok'}
    with pytest.raises(ValueError,match='한도'):
        protected_call(cfg,{},ledger,runner,'','agt_review','2',b'pdf')
    assert len(calls)==1
    with pytest.raises(ValueError):parse_config(dict(values,require_password=True),password_required=False)
    with pytest.raises(ValueError):parse_config(dict(values,require_password='false'))


def test_public_ui_opens_without_password_but_never_exposes_key(monkeypatch,tmp_path):
    from streamlit.testing.v1 import AppTest
    import team_access
    monkeypatch.setattr('browser_draft.bootstrap',lambda:None)
    monkeypatch.setattr('browser_draft.save_browser',lambda:None)
    original=team_access.Ledger
    monkeypatch.setattr(team_access,'Ledger',lambda path:original(tmp_path/'public-ui.sqlite'))
    at=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'))
    at.secrets['team']={'enabled':True,'require_password':False,'api_key':'unit-test-key',
                        'notice_id':'agt_notice','notice_version':'4','review_id':'agt_review','review_version':'2'}
    at.run()
    assert not at.exception and len(at.radio)==1
    assert not any(x.label in ('팀 접속 암호','Upstage API 키','공고 분석 Agent ID') for x in at.text_input)
    assert any('암호 없이' in x.value for x in at.caption)
    assert not any(b.label=='팀 접속 종료' for b in at.button)


def test_team_ui_hides_keys_and_prevents_unauthenticated_controls(monkeypatch,tmp_path):
    from streamlit.testing.v1 import AppTest
    import team_access
    monkeypatch.setattr('browser_draft.bootstrap',lambda:None)
    monkeypatch.setattr('browser_draft.save_browser',lambda:None)
    original=team_access.Ledger
    monkeypatch.setattr(team_access,'Ledger',lambda path:original(tmp_path/'app.sqlite'))
    at=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'))
    at.secrets['team']={'enabled':True,'require_password':True,'api_key':'unit-test-key','password':'unit-test-password',
                        'notice_id':'agt_notice','notice_version':'4','review_id':'agt_review','review_version':'2'}
    at.run()
    assert not at.exception and len(at.radio)==0
    assert [x.label for x in at.text_input]==['팀 접속 암호']
    at.text_input[0].set_value('wrong')
    next(b for b in at.button if b.label=='팀 체험 시작').click().run()
    assert at.error and len(at.radio)==0
    at.text_input[0].set_value('unit-test-password')
    next(b for b in at.button if b.label=='팀 체험 시작').click().run()
    assert not at.exception and len(at.radio)==1
    assert not any(x.label in ('Upstage API 키','공고 분석 Agent ID','팀 접속 암호') for x in at.text_input)
    next(b for b in at.button if b.label=='팀 접속 종료').click().run()
    assert not at.exception and len(at.radio)==0
    assert [x.label for x in at.text_input]==['팀 접속 암호']
