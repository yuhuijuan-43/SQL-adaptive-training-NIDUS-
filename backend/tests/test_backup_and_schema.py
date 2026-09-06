"""自动备份与 schema 版本记录测试（2026-09-03 新增）"""
import os
import sqlite3


def test_backup_creates_and_keeps_file(tmp_path, monkeypatch):
    import backup
    src = tmp_path / 'questions.db'
    conn = sqlite3.connect(str(src))
    conn.execute('CREATE TABLE demo (id INTEGER)')
    conn.commit()
    conn.close()
    import db
    monkeypatch.setattr(db, 'DB_PATH', str(src))
    monkeypatch.setattr(backup, 'BACKUP_DIR', str(tmp_path / 'backups'))
    p = backup.backup_database(tag='unit-test')
    assert p and os.path.exists(p)
    # 目标库可打开且包含表数据
    dst = sqlite3.connect(p)
    assert dst.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='demo'").fetchone()
    dst.close()


def test_schema_version_recorded(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'schema.db'))
    db.init_db()
    conn = db.get_connection()
    row = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
    assert row and row['value'] == db.SCHEMA_VERSION
