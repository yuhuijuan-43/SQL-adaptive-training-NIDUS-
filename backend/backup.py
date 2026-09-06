"""SQLite 自动备份（2026-09-03 新增）

- 启动 / 题库重建等有风险动作前自动备份 questions.db
- 使用 sqlite3.Connection.backup()（在线安全备份，不依赖文件复制）
- 按 tag 落盘到 backend/backups/，保留最近 BACKUP_KEEP 份
"""
import os
import glob
import time

BACKUP_DIR = os.path.join(os.path.dirname(__file__), 'backups')
BACKUP_KEEP = int(os.environ.get('DB_BACKUP_KEEP', '20'))


def _db_path():
    """动态读取当前 DB_PATH（测试 monkeypatch db.DB_PATH 后同样生效）"""
    try:
        import db
        return db.DB_PATH
    except Exception:
        return os.path.join(os.path.dirname(__file__), 'questions.db')


def backup_database(tag='manual'):
    """在线备份当前数据库，返回备份文件绝对路径；失败返回 None（不阻断主流程）"""
    try:
        import sqlite3
        db_path = _db_path()
        if not os.path.exists(db_path):
            return None
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = time.strftime('%Y%m%d-%H%M%S')
        safe_tag = ''.join(c for c in tag if c.isalnum() or c in '-_') or 'manual'
        target = os.path.join(BACKUP_DIR, f'questions-{stamp}-{safe_tag}.db')
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        # 清理旧备份：只保留最近 N 份（按文件名时间序）
        files = sorted(glob.glob(os.path.join(BACKUP_DIR, 'questions-*.db')))
        for old in files[:-BACKUP_KEEP]:
            try:
                os.remove(old)
            except OSError:
                pass
        return target
    except Exception as e:
        print(f'[backup] 备份失败（可忽略，不影响启动）：{e}')
        return None
