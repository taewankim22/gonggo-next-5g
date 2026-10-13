"""Server-only team access and atomic, shared call accounting.

The SQLite ledger contains timestamps and random reservation IDs only.
Cloud rebuilds can replace this local disk; this is not a billing budget.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from pathlib import Path
import secrets
import sqlite3
import time


@dataclass(repr=False)
class TeamConfig:
    api_key: str = field(repr=False)
    password: str = field(repr=False)
    notice_id: str
    notice_version: str
    review_id: str
    review_version: str
    daily_limit: int = 0
    require_password: bool = True

    @property
    def auth_tag(self):
        return hmac.new(self.api_key.encode(), self.password.encode(), hashlib.sha256).hexdigest()


def parse_config(values,password_required=True):
    if values.get('enabled') is not True:
        raise ValueError('팀 공유 설정의 enabled를 true로 설정해주세요.')
    fields=['api_key','password','notice_id','notice_version','review_id','review_version']
    data={k:str(values.get(k,'')).strip() for k in fields}
    require_password=values.get('require_password',password_required)
    if type(require_password) is not bool:
        raise ValueError('require_password는 true 또는 false로 설정해주세요.')
    if not all(data[k] for k in fields if k!='password'):
        raise ValueError('서버 비밀 설정에 API 키와 두 Agent ID·버전이 필요합니다.')
    if require_password and len(data['password']) < 12:
        raise ValueError('암호 접속을 사용할 때는 12자 이상의 팀 암호가 필요합니다.')
    if not all(data[k].startswith('agt_') for k in ('notice_id','review_id')):
        raise ValueError('서버 비밀 설정의 Agent ID를 확인해주세요.')
    if not all(data[k].isdigit() and int(data[k])>0 for k in ('notice_version','review_version')):
        raise ValueError('설정 버전은 양의 정수여야 합니다.')
    limit=values.get('daily_limit',0)
    if type(limit) is not int or limit<0:
        raise ValueError('daily_limit은 0 이상의 정수로 설정해주세요. 0은 횟수 제한 없음입니다.')
    return TeamConfig(**data,daily_limit=limit,require_password=require_password)


def authorized(state, config, now=None):
    if not config.require_password:
        return True
    now=time.time() if now is None else now
    return (hmac.compare_digest(str(state.get('_team_auth','')),config.auth_tag)
            and 0<=now-state.get('_team_login_at',0)<7200)


class Ledger:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS calls (token TEXT PRIMARY KEY, ts REAL NOT NULL, active INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS attempts (ts REAL NOT NULL)')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def allow_login_attempt(self,now=None):
        now=time.time() if now is None else now
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM attempts WHERE ts<=?',(now-600,))
            if db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]>=20:
                return False
            db.execute('INSERT INTO attempts VALUES (?)',(now,))
            return True

    @staticmethod
    def day_start(now):
        return datetime.fromtimestamp(now,timezone(timedelta(hours=9))).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()

    def used(self,now=None):
        now=time.time() if now is None else now
        with self.connect() as db:
            return db.execute('SELECT COUNT(*) FROM calls WHERE ts>=?',(self.day_start(now),)).fetchone()[0]

    def reserve(self,limit,now=None):
        now=time.time() if now is None else now
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if limit>0 and db.execute('SELECT COUNT(*) FROM calls WHERE ts>=?',(self.day_start(now),)).fetchone()[0]>=limit:
                raise ValueError('오늘 팀 전체 AI 호출 한도에 도달했습니다. 한국 시간 자정 이후 다시 사용하세요.')
            if db.execute('SELECT COUNT(*) FROM calls WHERE active=1 AND ts>?',(now-600,)).fetchone()[0]:
                raise ValueError('다른 분석이 진행 중입니다. 완료 후 다시 눌러주세요.')
            last=db.execute('SELECT MAX(ts) FROM calls').fetchone()[0]
            if last is not None and now-last<10:
                raise ValueError('연속 호출을 막기 위해 10초 후 다시 실행해주세요.')
            token=secrets.token_hex(16)
            db.execute('INSERT INTO calls VALUES (?,?,1)',(token,now))
            return token

    def release(self,token):
        with self.connect() as db:
            db.execute('UPDATE calls SET active=0 WHERE token=?',(token,))


def protected_call(config,state,ledger,runner,api_key,agent_id,version,*args,**kwargs):
    if config is None:
        return runner(api_key,agent_id,version,*args,**kwargs)
    if not authorized(state,config):
        raise ValueError('팀 접속이 만료되었습니다. 새로고침 후 팀 암호로 다시 접속해주세요.')
    if (agent_id,str(version)) not in {(config.notice_id,config.notice_version),(config.review_id,config.review_version)}:
        raise ValueError('팀에서 지정한 에이전트만 실행할 수 있습니다.')
    token=ledger.reserve(config.daily_limit)
    try:
        return runner(config.api_key,agent_id,version,*args,**kwargs)
    finally:
        ledger.release(token)


def team_gate(root,required=False,password_required=True):
    import streamlit as st
    try:
        raw=st.secrets.get('team',None)
    except FileNotFoundError:
        raw=None
    except Exception:
        st.error('서버 비밀 설정을 읽을 수 없습니다. 운영자가 Streamlit 설정을 확인해야 합니다.')
        st.stop()
    if raw is None and not required:
        return None,None
    try:
        config=parse_config(raw or {},password_required=password_required)
        # Public release pins tested agent versions; credentials and access policy remain in Secrets.
        import json
        from dataclasses import replace
        release_path=root/'settings.json'
        release=json.loads(release_path.read_text(encoding='utf-8')) if release_path.exists() else {}
        if release.get('pin_agent_versions'):
            config=replace(config,notice_id=release['notice_agent_id'],notice_version=release['notice_config_id'],
                           review_id=release['review_agent_id'],review_version=release['review_config_id'])
        ledger=Ledger(root/'runtime'/'team_usage.sqlite3')
    except (ValueError,sqlite3.Error,OSError) as exc:
        st.title('공고다음 · 팀 체험 준비 중')
        st.info('운영자가 서버의 Upstage 연결 설정을 완료하면 사용할 수 있습니다.')
        # Configuration errors contain fixed messages only, never values.
        if isinstance(exc,ValueError):st.caption(str(exc))
        st.stop()
    if not authorized(st.session_state,config):
        st.title('공고다음 · 5G 팀 체험')
        st.caption('팀 암호로 접속하면 운영자의 Upstage 연결로 분석합니다. API 키를 입력할 필요가 없습니다.')
        with st.form('team_login',clear_on_submit=True):
            password=st.text_input('팀 접속 암호',type='password')
            submit=st.form_submit_button('팀 체험 시작',type='primary')
        if submit:
            if not ledger.allow_login_attempt():
                st.error('접속 시도가 많습니다. 10분 후 다시 시도해주세요.')
            elif hmac.compare_digest(password.encode(),config.password.encode()):
                st.session_state['_team_auth']=config.auth_tag
                st.session_state['_team_login_at']=time.time()
                st.rerun()
            else:
                st.error('팀 암호를 확인해주세요.')
        st.stop()
    if config.require_password and st.button('팀 접속 종료'):
        st.session_state.clear()
        st.rerun()
    return config,ledger
