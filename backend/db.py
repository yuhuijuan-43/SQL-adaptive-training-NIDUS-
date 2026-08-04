"""数据库连接与 schema 管理"""
import sqlite3
import os

from flask import g, has_app_context

DB_PATH = os.path.join(os.path.dirname(__file__), 'questions.db')

def get_connection():
    """获取数据库连接。Flask请求上下文内复用 g 连接；外部创建独立连接。"""
    if has_app_context():
        if 'db' not in g:
            g.db = sqlite3.connect(DB_PATH)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA journal_mode=WAL")
            g.db.execute("PRAGMA busy_timeout=5000")
        return g.db
    # 非Flask上下文（启动脚本等）：独立连接
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def close_db(e=None):
    """关闭请求上下文中的数据库连接（Flask teardown 回调）"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def _cleanup_stale_wal(conn):
    """清理上次异常退出残留的 WAL 文件，合并未写入数据"""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("PRAGMA journal_mode=DELETE")

def init_db():
    conn = get_connection()
    _cleanup_stale_wal(conn)  # 启动时清理上次残留
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
        category TEXT NOT NULL, difficulty TEXT NOT NULL CHECK(difficulty IN ('easy','medium','hard')),
        title TEXT NOT NULL, description TEXT NOT NULL, table_schema TEXT, initial_data TEXT,
        correct_answer TEXT NOT NULL, explanation TEXT, options TEXT, option_explanations TEXT,
        expected_output TEXT, pool TEXT DEFAULT 'practice')''')
    try: c.execute('ALTER TABLE questions ADD COLUMN expected_output TEXT')
    except: pass
    try: c.execute("ALTER TABLE questions ADD COLUMN pool TEXT DEFAULT 'practice'")
    except: pass
    # 真题测试题库（独立表，schema 同 questions）
    c.execute('''CREATE TABLE IF NOT EXISTS exam_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
        category TEXT NOT NULL, difficulty TEXT NOT NULL CHECK(difficulty IN ('easy','medium','hard')),
        title TEXT NOT NULL, description TEXT NOT NULL, table_schema TEXT, initial_data TEXT,
        correct_answer TEXT NOT NULL, explanation TEXT, options TEXT, option_explanations TEXT,
        expected_output TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
        question_id INTEGER NOT NULL, user_answer TEXT,
        is_correct INTEGER NOT NULL DEFAULT 0,
        duration REAL DEFAULT 0,
        answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(question_id) REFERENCES questions(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS knowledge_nodes (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
        category TEXT, level INTEGER DEFAULT 0, icon TEXT DEFAULT 'fa-code')''')
    c.execute('''CREATE TABLE IF NOT EXISTS knowledge_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_node TEXT NOT NULL REFERENCES knowledge_nodes(id),
        to_node TEXT NOT NULL REFERENCES knowledge_nodes(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS question_knowledge (
        question_id INTEGER NOT NULL REFERENCES questions(id),
        node_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
        PRIMARY KEY(question_id, node_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_mastery (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL, node_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
        correct_count INTEGER DEFAULT 0, total_count INTEGER DEFAULT 0,
        alpha REAL DEFAULT 1.0, beta REAL DEFAULT 1.0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS journey_state (
        session_id TEXT PRIMARY KEY,
        current_node TEXT, node_queue TEXT DEFAULT '[]',
        skipped_nodes TEXT DEFAULT '[]',
        fillin_queue TEXT DEFAULT '[]',
        fillin_pending INTEGER DEFAULT 0,
        deep_mode INTEGER DEFAULT 1,
        phase TEXT DEFAULT 'cold',
        recent_modules TEXT DEFAULT '[]',
        wrong_streak INTEGER DEFAULT 0,
        total_answered INTEGER DEFAULT 0,
        total_correct INTEGER DEFAULT 0,
        avg_speed REAL DEFAULT 0,
        speed_count INTEGER DEFAULT 0,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        password TEXT DEFAULT '',
        session_id TEXT NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        referral_code TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    # 平台用户密码历史：重置前入档，供管理员回退（每账号最多保留 3 条；kind 区分用户/管理员）
    c.execute('''CREATE TABLE IF NOT EXISTS user_password_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        password TEXT NOT NULL,
        kind TEXT DEFAULT 'user',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    try: c.execute("ALTER TABLE user_password_history ADD COLUMN kind TEXT DEFAULT 'user'")
    except: pass
    c.execute('CREATE INDEX IF NOT EXISTS idx_uph_user ON user_password_history(username)')
    c.execute('''CREATE TABLE IF NOT EXISTS diagnostic_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        data TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS derived_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prototype_id INTEGER NOT NULL REFERENCES questions(id),
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        table_schema TEXT,
        initial_data TEXT,
        correct_answer TEXT NOT NULL,
        explanation TEXT,
        expected_output TEXT,
        difficulty TEXT NOT NULL,
        category TEXT NOT NULL,
        source TEXT DEFAULT 'derived',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    # ---- 性能索引 ----
    c.execute('CREATE INDEX IF NOT EXISTS idx_up_session ON user_progress(session_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_up_question ON user_progress(question_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_up_correct ON user_progress(session_id, is_correct)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_up_answered ON user_progress(answered_at)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_qk_node ON question_knowledge(node_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_qk_question ON question_knowledge(question_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_um_session ON user_mastery(session_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_um_node ON user_mastery(node_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_ke_from ON knowledge_edges(from_node)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_ke_to ON knowledge_edges(to_node)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_dq_proto ON derived_questions(prototype_id)')
    conn.commit()
