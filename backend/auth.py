"""用户认证：bcrypt 密码存储、登录/注册"""
import hashlib
import os
import uuid

from db import get_connection

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

# ---- 平台级设置：统一管理员密钥 + 内推码（主管理员可管理，DB 存储） ----
DEFAULT_REFERRAL_CODE = 'NIDUS_Agent'   # 默认内推码（首次使用时种入，可增删）

def get_admin_key():
    """当前统一管理员密钥：DB 优先（主管理员可更换），未设置时回退 env / 默认值（运行时读取 env，支持测试注入）"""
    conn = get_connection()
    row = conn.execute("SELECT value FROM admin_settings WHERE key='admin_key'").fetchone()
    if row:
        return row['value']
    return os.environ.get('ADMIN_TOKEN', 'change-me-admin-token-2024')

def set_admin_key(new_key):
    """主管理员更换统一管理员密钥（同步影响全部管理员登录与 Bearer 鉴权）"""
    conn = get_connection()
    conn.execute('''INSERT INTO admin_settings (key, value, updated_at) VALUES ('admin_key', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP''', (new_key,))
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
    conn.execute('INSERT INTO admin_users (username, password, referral_code) VALUES (?,?,?)',
                 (username, pw_hash, referral_code.strip()))
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
    """返回管理员个人资料（含是否主管理员 is_primary）；不存在返回 None"""
    conn = get_connection()
    row = conn.execute('SELECT username, is_primary FROM admin_users WHERE username=?', (username,)).fetchone()
    return dict(row) if row else None

def get_admin_colleagues(exclude_username=None):
    """我的同事：其他管理员的用户名、最后上线时间、是否主管理员与可回退次数"""
    conn = get_connection()
    base = '''SELECT a.username, a.last_login_at, a.is_primary,
        (SELECT COUNT(*) FROM user_password_history h WHERE h.username=a.username AND h.kind='admin') as rollback_count
        FROM admin_users a'''
    if exclude_username:
        rows = conn.execute(base + ' WHERE a.username != ? ORDER BY a.last_login_at DESC', (exclude_username,)).fetchall()
    else:
        rows = conn.execute(base + ' ORDER BY a.last_login_at DESC').fetchall()
    return [dict(r) for r in rows]
