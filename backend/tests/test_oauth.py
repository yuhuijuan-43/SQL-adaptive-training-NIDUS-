"""GitHub OAuth 登录测试：monkeypatch 隔离 GitHub 外部调用与本地真实配置。

- 所有用例先重定向 oauth.CONFIG_PATH 到 tmp_path（防开发机本地 oauth_config.json 真实凭证泄漏进测试）
- exchange_code / fetch_github_user 用 monkeypatch 拦截，不发起真实网络请求
- session cookie 由 Flask test client 自动保持，_start_flow 拿到的 state 在回调时直接可用
"""
from urllib.parse import parse_qs, urlparse

import pytest

import db
import oauth

CLIENT_ID = 'test-client-id'
CLIENT_SECRET = 'test-client-secret'


@pytest.fixture()
def oauth_off(tmp_path, monkeypatch):
    """未配置环境：无 env + 配置路径指向不存在的文件"""
    monkeypatch.delenv('GITHUB_OAUTH_CLIENT_ID', raising=False)
    monkeypatch.delenv('GITHUB_OAUTH_CLIENT_SECRET', raising=False)
    monkeypatch.setattr(oauth, 'CONFIG_PATH', str(tmp_path / 'none.json'))


@pytest.fixture()
def oauth_on(tmp_path, monkeypatch):
    """已配置环境：env 注入测试凭证 + 配置路径重定向"""
    monkeypatch.setenv('GITHUB_OAUTH_CLIENT_ID', CLIENT_ID)
    monkeypatch.setenv('GITHUB_OAUTH_CLIENT_SECRET', CLIENT_SECRET)
    monkeypatch.setattr(oauth, 'CONFIG_PATH', str(tmp_path / 'none.json'))
    return oauth.get_oauth_config()


def _start_flow(client):
    """发起授权流程（不 follow 重定向），返回 GitHub 回调所需的 state"""
    r = client.get('/api/oauth/github')
    assert r.status_code == 302
    return parse_qs(urlparse(r.headers['Location']).query)['state'][0]


def _complete_flow(client, monkeypatch, state, gh_user=None, exchange=None):
    """模拟 GitHub 回跳：拦截外部调用后访问回调端点，返回响应"""
    if gh_user is None:
        gh_user = {'id': 123456, 'login': 'octocat'}
    monkeypatch.setattr(oauth, 'exchange_code', lambda code, cfg: exchange if exchange else 'fake-token')
    monkeypatch.setattr(oauth, 'fetch_github_user', lambda token: gh_user)
    return client.get(f'/api/oauth/github/callback?code=fake-code&state={state}')


# ---- check：未配置 / 已配置 ----

def test_check_disabled_when_not_configured(client, oauth_off):
    r = client.get('/api/oauth/github/check')
    assert r.status_code == 200
    assert r.get_json() == {'enabled': False}


def test_check_enabled_when_configured(client, oauth_on):
    r = client.get('/api/oauth/github/check')
    assert r.status_code == 200
    assert r.get_json() == {'enabled': True}


# ---- 发起授权 ----

def test_redirect_builds_authorize_url(client, oauth_on):
    r = client.get('/api/oauth/github')
    assert r.status_code == 302
    loc = r.headers['Location']
    assert 'github.com/login/oauth/authorize' in loc
    assert f'client_id={CLIENT_ID}' in loc
    assert 'scope=read:user' in loc
    assert 'state=' in loc
    assert 'redirect_uri' not in loc   # 刻意不传：由 GitHub 使用注册回调，规避 mismatch


def test_redirect_when_not_configured_goes_error(client, oauth_off):
    r = client.get('/api/oauth/github')
    assert r.status_code == 302
    assert 'oauth_error=1' in r.headers['Location']


# ---- 回调：建档 / 复用 / 冲突 / 拒绝 ----

def test_callback_new_user_created(client, oauth_on, monkeypatch):
    state = _start_flow(client)
    r = _complete_flow(client, monkeypatch, state)
    assert r.status_code == 302
    q = parse_qs(urlparse(r.headers['Location']).query)
    assert q['oauth'] == ['1']
    sid, uname = q['sid'][0], q['uname'][0]
    assert uname == 'octocat'

    # DB 断言：users 行存在且 github_id 绑定
    row = db.get_connection().execute(
        'SELECT username, github_id, session_id FROM users WHERE github_id=?', ('123456',)).fetchone()
    assert row is not None and row['username'] == 'octocat' and row['session_id'] == sid

    # 登录态真实可用：带 session_id 可读题
    r2 = client.get(f'/api/questions?session_id={sid}')
    assert r2.status_code == 200


def test_callback_existing_user_reuses_session(client, oauth_on, monkeypatch):
    state = _start_flow(client)
    first = parse_qs(urlparse(_complete_flow(client, monkeypatch, state).headers['Location']).query)
    state = _start_flow(client)   # 第二次登录（同 test client，session cookie 延续）
    second = parse_qs(urlparse(_complete_flow(client, monkeypatch, state).headers['Location']).query)
    assert first['sid'] == second['sid']          # session_id 复用，进度连续
    assert first['uname'] == second['uname']


def test_callback_username_conflict_suffix(client, oauth_on, monkeypatch):
    client.post('/api/register', json={'username': 'octocat', 'password': 'password123'})
    state = _start_flow(client)
    q = parse_qs(urlparse(_complete_flow(client, monkeypatch, state).headers['Location']).query)
    assert q['uname'] == ['octocat_gh']           # 冲突自动加 _gh 后缀
    # 两个账号并存且互不覆盖
    conn = db.get_connection()
    assert conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 2


def test_callback_state_mismatch_rejected(client, oauth_on, monkeypatch):
    _start_flow(client)
    r = _complete_flow(client, monkeypatch, 'wrong-state')   # 伪造/过期 state
    assert r.status_code == 302
    assert 'oauth_error=1' in r.headers['Location']
    assert db.get_connection().execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0


def test_callback_user_denied(client, oauth_on):
    r = client.get('/api/oauth/github/callback?error=access_denied')
    assert r.status_code == 302
    assert 'oauth_error=1' in r.headers['Location']


def test_callback_network_failure(client, oauth_on, monkeypatch):
    state = _start_flow(client)

    def _boom(code, cfg):
        raise RuntimeError('github unreachable')
    monkeypatch.setattr(oauth, 'exchange_code', _boom)
    monkeypatch.setattr(oauth, 'fetch_github_user', lambda token: {'id': 1, 'login': 'x'})
    r = client.get(f'/api/oauth/github/callback?code=fake-code&state={state}')
    assert r.status_code == 302                       # 网络异常 → oauth_error 重定向，绝不 500
    assert 'oauth_error=1' in r.headers['Location']
    assert db.get_connection().execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0


def test_callback_missing_code(client, oauth_on):
    state = _start_flow(client)
    r = client.get(f'/api/oauth/github/callback?state={state}')   # 缺 code（GitHub 异常回跳）
    assert r.status_code == 302
    assert 'oauth_error=1' in r.headers['Location']


# ---- 白名单回归：OAuth 端点必须免登录可访问 ----

def test_oauth_endpoints_whitelisted(client, oauth_on):
    r = client.get('/api/oauth/github/check')
    assert r.status_code == 200                      # 匿名访问不被 401 拦截
