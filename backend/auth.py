"""用户认证：bcrypt 密码存储、登录/注册"""
import datetime
import hashlib
import re
import secrets
import uuid

from db import get_connection

# 用户名白名单：2-32 位字母/数字/下划线/中文（注册时校验，防 HTML/引号注入管理页面）
_USERNAME_RE = re.compile(r'^[\w一-龥]{2,32}$')

def valid_username(username):
    """用户名是否合法（白名单字符集）"""
    return bool(_USERNAME_RE.match(username or ''))

def _is_authenticated(session_id):
    """检查 session_id 是否属于已注册用户"""
    conn = get_connection()
    row = conn.execute('SELECT id FROM users WHERE session_id=?', (session_id,)).fetchone()
    return row is not None

def _upgrade_to_bcrypt(conn, username, password):
    """将用户密码升级为bcrypt格式"""
    import bcrypt
    new_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    conn.execute('UPDATE users SET password=? WHERE username=?', (new_hash, username))
    conn.commit()

def _verify_bcrypt(stored, password):
    """验证bcrypt密码"""
    import bcrypt
    try:
        return bcrypt.checkpw(password.encode('utf-8'), stored.encode('utf-8'))
    except Exception:
        return False

def login_user(username, password):
    """登录：支持bcrypt（新格式）和sha256:盐（旧格式，自动升级）"""
    conn = get_connection()
    row = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    if not row:
        return None, 'not_found'
    stored = dict(row)['password'] or ''
    session_id = dict(row)['session_id']

    # bcrypt格式（$2b$或$2a$开头）
    if stored.startswith('$2b$') or stored.startswith('$2a$'):
        if _verify_bcrypt(stored, password):
            return session_id, None
    # 旧sha256格式（salt:sha256hash）
    elif ':' in stored:
        salt, stored_hash = stored.split(':', 1)
        if hashlib.sha256((salt + password).encode('utf-8')).hexdigest() == stored_hash:
            _upgrade_to_bcrypt(conn, username, password)
            return session_id, None
    # 明文（极旧用户，自动升级后移除该分支）
    elif stored == password:
        _upgrade_to_bcrypt(conn, username, password)
        return session_id, None

    return None, 'wrong_password'

def register_user(username, password):
    """注册：使用bcrypt存储密码"""
    import bcrypt
    if not valid_username(username):
        return None, 'invalid_username'
    if not password or len(password.strip()) < 8 or len(password.strip()) > 64:
        return None, 'weak_password'
    conn = get_connection()
    existing = conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
    if existing:
        return None, 'exists'
    if conn.execute('SELECT id FROM admin_users WHERE username=?', (username,)).fetchone():
        return None, 'exists'   # 全局唯一：平台用户名不得与管理员重复
    pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    session_id = str(uuid.uuid4())
    conn.execute('INSERT INTO users (username, password, session_id) VALUES (?,?,?)',
                 (username, pw_hash, session_id))
    conn.commit()
    return session_id, None

def check_username_exists(username):
    """检查用户名是否已存在（含管理员同名）"""
    conn = get_connection()
    if conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
        return True
    if conn.execute('SELECT id FROM admin_users WHERE username=?', (username,)).fetchone():
        return True
    return False

def login_or_register(username, password=''):
    """Legacy: kept for backward compatibility (admin page login).
    Tries login first; if user doesn't exist, registers as new."""
    sid, reason = login_user(username, password)
    if sid:
        return sid, False
    if reason == 'not_found':
        sid, _ = register_user(username, password)
        if sid:
            return sid, True
    return None, False

# ---- 平台级设置：内推码（主管理员可管理，DB 存储） ----
DEFAULT_REFERRAL_CODE = 'NIDUS_Agent'   # 默认内推码（首次使用时种入，可增删）

# ---- 一人一钥：每位管理员专属个人密钥（登录门第二重验证；主管理员可监控/停用/重置） ----

def generate_personal_key():
    """生成新个人密钥（token_urlsafe(16) → 22 字符，满足 8-64 字符校验）"""
    return secrets.token_urlsafe(16)

def get_personal_key(username):
    """返回管理员的个人密钥；NULL（存量管理员）时惰性生成并落库"""
    conn = get_connection()
    row = conn.execute('SELECT personal_key FROM admin_users WHERE username=?', (username,)).fetchone()
    if not row:
        return None
    key = row['personal_key']
    if not key:
        key = generate_personal_key()
        conn.execute('UPDATE admin_users SET personal_key=? WHERE username=?', (key, username))
        conn.commit()
    return key

def set_personal_key(username, new_key):
    """更换个人密钥（自助；更换后由调用方注销该管理员全部会话）"""
    conn = get_connection()
    conn.execute('UPDATE admin_users SET personal_key=? WHERE username=?', (new_key, username))
    conn.commit()

def reset_personal_key(username):
    """一键重置个人密钥（主管理员用）：生成新密钥并落库，返回新密钥"""
    key = generate_personal_key()
    set_personal_key(username, key)
    return key

def is_key_disabled(username):
    """该管理员个人密钥是否已被主管理员停用"""
    conn = get_connection()
    row = conn.execute('SELECT key_disabled FROM admin_users WHERE username=?', (username,)).fetchone()
    return bool(row and row['key_disabled'])

def set_key_disabled(username, disabled):
    """停用/启用个人密钥（停用时调用方负责注销该管理员全部会话）"""
    conn = get_connection()
    conn.execute('UPDATE admin_users SET key_disabled=? WHERE username=?', (1 if disabled else 0, username))
    conn.commit()

def get_referral_codes():
    """全部内推码（首次使用时惰性种入默认码，保证至少一个可用）"""
    conn = get_connection()
    rows = conn.execute('SELECT code, note, created_at FROM referral_codes ORDER BY id').fetchall()
    codes = [dict(r) for r in rows]
    if not codes:
        conn.execute('INSERT OR IGNORE INTO referral_codes (code, note) VALUES (?,?)', (DEFAULT_REFERRAL_CODE, '默认内推码'))
        conn.commit()
        return [{'code': DEFAULT_REFERRAL_CODE, 'note': '默认内推码', 'created_at': None}]
    return codes

def add_referral_code(code, note=''):
    """新增内推码；返回 (ok, reason)：exists / invalid"""
    code = (code or '').strip()
    if not code or len(code) > 32:
        return None, 'invalid'
    conn = get_connection()
    if conn.execute('SELECT id FROM referral_codes WHERE code=?', (code,)).fetchone():
        return None, 'exists'
    conn.execute('INSERT INTO referral_codes (code, note) VALUES (?,?)', (code, note.strip()))
    conn.commit()
    return True, None

def delete_referral_code(code):
    """删除内推码；最后一个不允许删除（保证注册入口存在）"""
    conn = get_connection()
    row = conn.execute('SELECT id FROM referral_codes WHERE code=?', (code,)).fetchone()
    if not row:
        return None, 'not_found'
    if conn.execute('SELECT COUNT(*) FROM referral_codes').fetchone()[0] <= 1:
        return None, 'last_one'
    conn.execute('DELETE FROM referral_codes WHERE id=?', (row['id'],))
    conn.commit()
    return True, None

def register_admin(username, password, referral_code):
    """管理员注册：内推码校验（与 DB 实时同步）+ 用户名全局唯一（含平台用户）+ bcrypt；密码规则与平台一致（8-64 字符）"""
    import bcrypt
    if not valid_username(username):
        return None, 'invalid_username'
    if not password or len(password.strip()) < 8 or len(password.strip()) > 64:
        return None, 'weak_password'
    valid_codes = [c['code'] for c in get_referral_codes()]
    if (referral_code or '').strip() not in valid_codes:
        return None, 'bad_referral'
    conn = get_connection()
    existing = conn.execute('SELECT id FROM admin_users WHERE username=?', (username,)).fetchone()
    if existing:
        return None, 'exists'
    if conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
        return None, 'exists'
    pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    personal_key = generate_personal_key()   # 一人一钥：注册即签发专属密钥
    conn.execute('INSERT INTO admin_users (username, password, referral_code, personal_key) VALUES (?,?,?,?)',
                 (username, pw_hash, referral_code.strip(), personal_key))
    conn.commit()
    return True, None

def login_admin(username, password):
    """管理员登录：bcrypt 校验 + 更新最后上线时间"""
    import bcrypt
    conn = get_connection()
    row = conn.execute('SELECT * FROM admin_users WHERE username=?', (username,)).fetchone()
    if not row:
        return None, 'not_found'
    stored = dict(row)['password']
    try:
        if not bcrypt.checkpw(password.encode('utf-8'), stored.encode('utf-8')):
            return None, 'wrong_password'
    except Exception:
        return None, 'wrong_password'
    conn.execute('UPDATE admin_users SET last_login_at=CURRENT_TIMESTAMP WHERE username=?', (username,))
    conn.commit()
    return True, None

def check_admin_username_exists(username):
    """检查管理员用户名是否已占用（注册预检，含平台用户同名）"""
    conn = get_connection()
    if conn.execute('SELECT id FROM admin_users WHERE username=?', (username,)).fetchone():
        return True
    if conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
        return True
    return False

def get_admin_profile(username):
    """返回管理员个人资料（含是否主管理员 is_primary、密钥是否停用）；不存在返回 None"""
    conn = get_connection()
    row = conn.execute('SELECT username, is_primary, key_disabled FROM admin_users WHERE username=?', (username,)).fetchone()
    return dict(row) if row else None

# ---- 管理员会话（per-admin token，2026-08-05 C2 鉴权重构） ----
# 此前所有 /api/admin/* 仅校验统一密钥（Bearer == 密钥），且主管理员权限依赖请求体自报的 operator 字段，
# 任意持有密钥者（每个管理员都有密钥）可伪装主管理员。现改为登录/注册时签发随机会话 token：
# - Bearer token 与管理员身份一一绑定，服务端从 token 解析真实操作者，废弃 operator 自声明
# - auth-login / auth-register 不再返回统一密钥
# - 更换统一密钥时清空全部会话，强制重新登录
SESSION_TTL_DAYS = 30

def create_admin_session(username):
    """为管理员签发会话 token（30 天有效），返回 token 字符串"""
    token = secrets.token_urlsafe(32)
    expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=SESSION_TTL_DAYS)
    conn = get_connection()
    conn.execute('INSERT INTO admin_sessions (token, username, expires_at) VALUES (?,?,?)',
                 (token, username, expires.isoformat()))
    conn.commit()
    return token

def validate_admin_token(token):
    """校验管理员会话 token，返回绑定的用户名；无效/过期返回 None（过期行顺带清理）"""
    if not token:
        return None
    conn = get_connection()
    row = conn.execute('SELECT username, expires_at FROM admin_sessions WHERE token=?', (token,)).fetchone()
    if not row:
        return None
    try:
        expires = datetime.datetime.fromisoformat(row['expires_at'])
        if expires < datetime.datetime.now(datetime.timezone.utc):
            conn.execute('DELETE FROM admin_sessions WHERE token=?', (token,))
            conn.commit()
            return None
    except ValueError:
        return None
    return row['username']

def revoke_admin_sessions(username=None):
    """注销会话：username=None 时清空全部（更换统一密钥时强制全员重新登录）"""
    conn = get_connection()
    if username:
        conn.execute('DELETE FROM admin_sessions WHERE username=?', (username,))
    else:
        conn.execute('DELETE FROM admin_sessions')
    conn.commit()

def is_primary_admin(username):
    """该管理员是否为主管理员"""
    profile = get_admin_profile(username)
    return bool(profile and profile.get('is_primary'))

def get_admin_colleagues(exclude_username=None, include_keys=False):
    """我的同事：其他管理员的用户名、最后上线时间、是否主管理员与可回退次数；
    include_keys（主管理员视角）时附带个人密钥 personal_key 与停用标记 key_disabled。
    存量管理员（一人一钥上线前创建）的 personal_key 可能为 NULL，此处惰性生成并落库，
    否则主管理员查看同事密钥时按钮会静默失效（前端对 null 密钥不响应）"""
    conn = get_connection()
    base = '''SELECT a.username, a.last_login_at, a.is_primary,
        (SELECT COUNT(*) FROM user_password_history h WHERE h.username=a.username AND h.kind='admin') as rollback_count'''
    if include_keys:
        base += ', a.personal_key, a.key_disabled'
    base += ' FROM admin_users a'
    if exclude_username:
        rows = conn.execute(base + ' WHERE a.username != ? ORDER BY a.last_login_at DESC', (exclude_username,)).fetchall()
    else:
        rows = conn.execute(base + ' ORDER BY a.last_login_at DESC').fetchall()
    result = [dict(r) for r in rows]
    if include_keys:
        for c in result:
            if not c.get('personal_key'):
                c['personal_key'] = get_personal_key(c['username'])   # 惰性生成（与 get_personal_key 逻辑一致）
    return result
