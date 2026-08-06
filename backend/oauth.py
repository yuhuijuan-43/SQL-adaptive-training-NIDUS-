"""GitHub OAuth 登录：配置读取、授权码流程、GitHub 用户与平台 users 表的绑定/建档。

配置来源（优先级）：环境变量 GITHUB_OAUTH_CLIENT_ID / GITHUB_OAUTH_CLIENT_SECRET > backend/oauth_config.json。
oauth_config.json 已被 .gitignore（含 client_secret 明文，不进版本库）。
"""
import json
import os
import random
import secrets
import sqlite3
import uuid

import requests

from auth import check_username_exists
from db import get_connection

# 模块属性：测试可 monkeypatch 重定向，防开发机本地真实配置泄漏进测试
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'oauth_config.json')

GITHUB_AUTHORIZE_URL = 'https://github.com/login/oauth/authorize'
GITHUB_TOKEN_URL = 'https://github.com/login/oauth/access_token'
GITHUB_USER_URL = 'https://api.github.com/user'


def get_oauth_config():
    """返回 {'github_client_id': str, 'github_client_secret': str}；未配置返回 None。
    环境变量优先（服务器部署），JSON 文件兜底（双击 start_server.bat 场景）。"""
    client_id = os.environ.get('GITHUB_OAUTH_CLIENT_ID', '').strip()
    client_secret = os.environ.get('GITHUB_OAUTH_CLIENT_SECRET', '').strip()
    if not client_id or not client_secret:
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f) or {}
        except (OSError, ValueError):
            cfg = {}
        if not client_id:
            client_id = (cfg.get('github_client_id') or '').strip()
        if not client_secret:
            client_secret = (cfg.get('github_client_secret') or '').strip()
    if not client_id or not client_secret:
        return None
    return {'github_client_id': client_id, 'github_client_secret': client_secret}


def build_authorize_url(client_id, state):
    """构造 GitHub 授权页地址。刻意不传 redirect_uri：由 GitHub 使用注册时填写的回调
    URL，彻底规避 redirect_uri_mismatch 错误。"""
    return (f'{GITHUB_AUTHORIZE_URL}?client_id={client_id}&scope=read:user'
            f'&state={state}')


def exchange_code(code, cfg):
    """用授权码换取 access_token。GitHub 只接受表单编码 body，返回 JSON。
    失败（4xx/网络异常）抛异常，由路由层统一转为 oauth_error 重定向。"""
    resp = requests.post(GITHUB_TOKEN_URL,
                         data={
                             'client_id': cfg['github_client_id'],
                             'client_secret': cfg['github_client_secret'],
                             'code': code,
                         },
                         headers={'Accept': 'application/json'},
                         timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if 'access_token' not in data:
        raise RuntimeError(f"GitHub token exchange failed: {data.get('error_description') or data.get('error') or 'unknown'}")
    return data['access_token']


def fetch_github_user(token):
    """拉取当前授权用户信息（id / login / name / avatar_url）。"""
    resp = requests.get(GITHUB_USER_URL,
                        headers={
                            'Authorization': f'Bearer {token}',
                            'Accept': 'application/vnd.github+json',
                            'User-Agent': 'sql-adaptive-training',
                        },
                        timeout=10)
    resp.raise_for_status()
    return resp.json()


def find_or_create_github_user(gh_id, gh_login):
    """按 GitHub 数字 ID 查/建 users 行，返回 (session_id, username)。
    - 已绑定：复用既有 session_id（全站进度/掌握度数据零迁移）
    - 未绑定：新建行，username 取 GitHub 登录名（冲突加后缀），password 为随机
      bcrypt（该账号不可走密码登录，管理员重置后可转双通道）
    - 并发双回调：唯一索引拦截 + IntegrityError 改查，不建重复行"""
    conn = get_connection()
    gh_id = str(gh_id)
    row = conn.execute('SELECT session_id, username FROM users WHERE github_id=?', (gh_id,)).fetchone()
    if row:
        return row['session_id'], row['username']

    username = _resolve_unique_username(gh_login)
    pw_hash = _random_bcrypt_hash()
    sid = str(uuid.uuid4())
    try:
        conn.execute('INSERT INTO users (username, password, session_id, github_id) VALUES (?,?,?,?)',
                     (username, pw_hash, sid, gh_id))
        conn.commit()
    except sqlite3.IntegrityError:
        # 并发双回调：另一请求已建档，改查不新建
        conn.rollback()
        row = conn.execute('SELECT session_id, username FROM users WHERE github_id=?', (gh_id,)).fetchone()
        if row:
            return row['session_id'], row['username']
        raise
    return sid, username


def _random_bcrypt_hash():
    """生成不可登录的随机 bcrypt 哈希（$2b$ 开头，任何密码都校验失败）。"""
    import bcrypt
    return bcrypt.hashpw(secrets.token_urlsafe(32).encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def _resolve_unique_username(gh_login):
    """分配唯一平台用户名。刻意不复用 auth.valid_username：GitHub 登录名可含 '-'
    （如 octocat-dev），现有正则不匹配；GitHub 名天然 [a-z0-9-] 安全字符集，无需格式校验。
    候选顺序：原名（截断 32）→ _gh → _ghNN 随机 → uuid 后缀（理论不可达）。"""
    base = (gh_login or 'gh_user')[:32]  # GitHub 名最长 39 字符，截断对齐平台 32 字符惯例
    for candidate in (base, base + '_gh'):
        if not check_username_exists(candidate):
            return candidate
    for _ in range(100):
        candidate = base + '_gh' + str(random.randint(10, 99))
        if not check_username_exists(candidate):
            return candidate
    candidate = base + '_gh' + uuid.uuid4().hex[:6]
    if not check_username_exists(candidate):
        return candidate
    raise RuntimeError('无法分配唯一用户名')  # 理论不可达，兜底走 oauth_error
