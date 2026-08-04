"""用户认证：bcrypt 密码存储、登录/注册"""
import hashlib
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
    pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    session_id = str(uuid.uuid4())
    conn.execute('INSERT INTO users (username, password, session_id) VALUES (?,?,?)',
                 (username, pw_hash, session_id))
    conn.commit()
    return session_id, None

def check_username_exists(username):
    """检查用户名是否已存在"""
    conn = get_connection()
    row = conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
    return row is not None

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
