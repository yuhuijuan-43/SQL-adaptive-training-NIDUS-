"""活动动态与系统日志（2026-09-03 新增）

供融合后的「管理后台」实时查询：
- activity_log.kind='user'   → 用户动态（注册/登录/答题/摸底…），所有管理员可见
- activity_log.kind='admin'  → 管理员动态（登录/注册/改密/删除/内推码…），仅主管理员可见
- system_logs                → 系统运行日志（异常/判题错误/失败登录/限流…），所有管理员可见

日志写入必须“静默失败”：日志基础设施异常绝不阻断主业务（try/except 兜底）。
"""
import json

from db import get_connection

_ACTIVITY_KEEP = 12000          # 动态只保留最近约 1.2 万条（实时排查足够）
_SYSTEM_KEEP = 5000             # 系统日志保留最近 5 千条


def _trim(conn, table, keep):
    """惰性清理：每次写入后把最老的溢出记录删除，避免表无限增长"""
    try:
        row = conn.execute(f'SELECT MAX(id) AS m FROM {table}').fetchone()
        if row and row['m']:
            conn.execute(f'DELETE FROM {table} WHERE id <= ?', (row['m'] - keep,))
    except Exception:
        pass


def _log_event(kind, actor, action, target='', detail='', extra=''):
    """写一条活动动态（kind='user' | 'admin'）"""
    try:
        if isinstance(extra, dict):
            extra = json.dumps(extra, ensure_ascii=False)
        conn = get_connection()
        conn.execute(
            'INSERT INTO activity_log (kind, actor, action, target, detail, extra) VALUES (?,?,?,?,?,?)',
            (kind, (actor or '?')[:64], action[:64], (target or '')[:200],
             (detail or '')[:1000], (extra or '')[:500]))
        _trim(conn, 'activity_log', _ACTIVITY_KEEP)
        conn.commit()
    except Exception:
        pass


def log_user_event(actor, action, target='', detail='', extra=''):
    """用户动态（平台学员）：注册/登录/登出/答题/摸底等"""
    _log_event('user', actor, action, target, detail, extra)


def log_admin_event(actor, action, target='', detail='', extra=''):
    """管理员动态（仅主管理员可查，用于定位与追责）"""
    _log_event('admin', actor, action, target, detail, extra)


def log_system(level='info', message='', detail='', source='app'):
    """系统日志：level ∈ info / warn / error"""
    try:
        level = level if level in ('info', 'warn', 'error') else 'info'
        conn = get_connection()
        conn.execute(
            'INSERT INTO system_logs (level, source, message, detail) VALUES (?,?,?,?)',
            (level, (source or 'app')[:80], (message or '')[:500], (detail or '')[:2000]))
        _trim(conn, 'system_logs', _SYSTEM_KEEP)
        conn.commit()
    except Exception:
        pass


def get_user_events(limit=100, actor=None, offset=0):
    """用户动态（倒序，支持分页）：注册/登录/登出/答题/摸底等；actor 传用户名时只看该用户"""
    try:
        conn = get_connection()
        if actor:
            rows = conn.execute(
                'SELECT id, actor, action, target, detail, extra, created_at'
                ' FROM activity_log WHERE kind=\'user\' AND actor=? ORDER BY id DESC LIMIT ? OFFSET ?',
                (actor[:64], min(limit, 2000), max(offset, 0))).fetchall()
        else:
            rows = conn.execute(
                'SELECT id, actor, action, target, detail, extra, created_at'
                ' FROM activity_log WHERE kind=\'user\' ORDER BY id DESC LIMIT ? OFFSET ?',
                (min(limit, 2000), max(offset, 0))).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_admin_events(limit=100, actor=None, offset=0):
    """管理员动态（倒序，支持分页，仅主管理员视角）；actor 传管理员用户名时只看该管理员"""
    try:
        conn = get_connection()
        if actor:
            rows = conn.execute(
                'SELECT id, actor, action, target, detail, extra, created_at'
                ' FROM activity_log WHERE kind=\'admin\' AND actor=? ORDER BY id DESC LIMIT ? OFFSET ?',
                (actor[:64], min(limit, 2000), max(offset, 0))).fetchall()
        else:
            rows = conn.execute(
                'SELECT id, actor, action, target, detail, extra, created_at'
                ' FROM activity_log WHERE kind=\'admin\' ORDER BY id DESC LIMIT ? OFFSET ?',
                (min(limit, 2000), max(offset, 0))).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def count_user_events(actor):
    """动态总数：actor 传用户名时统计该用户，否则统计全部用户动态"""
    try:
        conn = get_connection()
        if actor:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM activity_log WHERE kind='user' AND actor=?",
                (actor[:64],)).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM activity_log WHERE kind='user'").fetchone()
        return row['n'] if row else 0
    except Exception:
        return None


def count_admin_events(actor):
    """动态总数：actor 传管理员用户名时统计该管理员，否则统计全部管理员动态"""
    try:
        conn = get_connection()
        if actor:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM activity_log WHERE kind='admin' AND actor=?",
                (actor[:64],)).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM activity_log WHERE kind='admin'").fetchone()
        return row['n'] if row else 0
    except Exception:
        return None


def get_system_logs(limit=100, level=None, offset=0):
    """系统日志（倒序，支持分页；可选按 level 过滤）"""
    try:
        conn = get_connection()
        if level:
            rows = conn.execute(
                'SELECT id, level, source, message, detail, created_at'
                ' FROM system_logs WHERE level=? ORDER BY id DESC LIMIT ? OFFSET ?',
                (level, min(limit, 300), max(offset, 0))).fetchall()
        else:
            rows = conn.execute(
                'SELECT id, level, source, message, detail, created_at'
                ' FROM system_logs ORDER BY id DESC LIMIT ? OFFSET ?',
                (min(limit, 300), max(offset, 0))).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def count_system_logs(level=None):
    """系统日志总数（可选按 level 过滤）"""
    try:
        conn = get_connection()
        if level:
            row = conn.execute(
                'SELECT COUNT(*) AS n FROM system_logs WHERE level=?', (level,)).fetchone()
        else:
            row = conn.execute('SELECT COUNT(*) AS n FROM system_logs').fetchone()
        return row['n'] if row else 0
    except Exception:
        return None


def username_by_session(session_id):
    """按 session_id 反查平台用户名（无则返回 None）"""
    if not session_id:
        return None
    try:
        conn = get_connection()
        row = conn.execute('SELECT username FROM users WHERE session_id=?', (session_id,)).fetchone()
        return row['username'] if row else None
    except Exception:
        return None
