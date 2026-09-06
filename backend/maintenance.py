"""运行时数据治理（2026-09-06 新增）

针对长驻服务（部署到网站后很少重启）的无限增长表做惰性治理，全部静默失败：
- user_progress 保险丝：每 N 次答题登记动态检查一次总行数，超过阈值才压缩
  （只删 (用户,题目,池) 分组内「非首条答对且不在最近窗口内」的重复答对行，
   答错行、每题首条答对行、组内最近记录永不删除——错题集/选题排除/点亮规则均不受影响）
- admin_sessions：管理员登录时批量清理过期 token（validate_admin_token 只清理被用到的；
   diagnostic_results 为按用户 upsert，天然有界，无需治理）

阈值可通过环境变量调整：USER_PROGRESS_MAX_ROWS（默认 100000）、
USER_PROGRESS_CHECK_EVERY（默认 500，<=0 关闭检查）。
"""
import os
import threading

from db import get_connection
from logs import log_system

_UP_MAX_ROWS = int(os.environ.get('USER_PROGRESS_MAX_ROWS', '100000'))
_CHECK_EVERY = int(os.environ.get('USER_PROGRESS_CHECK_EVERY', '500'))
_KEEP_RECENT = 30         # 分组内最近 N 条记录无条件保留（覆盖段内速度/streak 计算）

_counter = 0
_lock = threading.Lock()


def on_answer_inserted():
    """save_answer 每次入库后调用：内存计数达标才真正查一次行数（动态触发，不依赖重启）"""
    global _counter
    if _CHECK_EVERY <= 0:
        return
    with _lock:
        _counter += 1
        if _counter % _CHECK_EVERY:
            return
    _fuse_check()


def _fuse_check():
    """行数超阈值时执行压缩并留痕系统日志"""
    try:
        conn = get_connection()
        n = conn.execute('SELECT COUNT(*) FROM user_progress').fetchone()[0]
        if n <= _UP_MAX_ROWS:
            return
        deleted = compress_user_progress()
        log_system('warn', 'user_progress 保险丝触发：已压缩重复答对记录',
                   detail=f'压缩前行数={n}，删除={deleted}', source='maintenance')
    except Exception as e:
        try:
            log_system('error', 'user_progress 保险丝检查失败',
                       detail=str(e)[:500], source='maintenance')
        except Exception:
            pass


def compress_user_progress(keep_recent=_KEEP_RECENT):
    """压缩每个 (session_id, question_id, pool) 分组内的重复答对行。

    保留：全部答错行、分组内首条答对行（选题排除/点亮计数依赖）、分组内最近 keep_recent 条。
    删除：其余的重复答对行（同题循环复用反复答对产生的中间行）。
    返回删除条数；异常返回 0。
    """
    try:
        conn = get_connection()
        conn.execute('''
            WITH g AS (
                SELECT id, is_correct,
                    ROW_NUMBER() OVER (PARTITION BY session_id, question_id, pool, is_correct
                                       ORDER BY id) AS rn_kind,
                    ROW_NUMBER() OVER (PARTITION BY session_id, question_id, pool
                                       ORDER BY id DESC) AS rn_desc,
                    COUNT(*) OVER (PARTITION BY session_id, question_id, pool) AS cnt
                FROM user_progress
            )
            DELETE FROM user_progress WHERE id IN (
                SELECT id FROM g
                WHERE is_correct = 1 AND rn_kind > 1 AND rn_desc > ? AND cnt > ?
            )''', (keep_recent, keep_recent))
        # DELETE...IN(子查询) 的 cursor.rowcount 不可靠（返回 -1），用 changes() 取真实删除量
        deleted = conn.execute('SELECT changes()').fetchone()[0]
        conn.commit()
        return deleted or 0
    except Exception as e:
        try:
            log_system('error', 'user_progress 压缩失败',
                       detail=str(e)[:500], source='maintenance')
        except Exception:
            pass
        return 0


def cleanup_expired_admin_sessions():
    """批量删除已过期的管理员会话 token，返回删除条数（解析失败的行保守保留）"""
    try:
        conn = get_connection()
        conn.execute(
            "DELETE FROM admin_sessions "
            "WHERE julianday(expires_at) IS NOT NULL AND julianday(expires_at) < julianday('now')")
        deleted = conn.execute('SELECT changes()').fetchone()[0]
        conn.commit()
        return deleted or 0
    except Exception:
        return 0


def startup_maintenance():
    """启动时的一次性治理（长驻服务的日常触发靠 on_answer_inserted / 管理员登录钩子）"""
    n_sess = cleanup_expired_admin_sessions()
    if n_sess:
        log_system('info', '启动数据治理完成',
                   detail=f'清理过期管理员会话={n_sess}',
                   source='maintenance')
