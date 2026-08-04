import sqlite3
import json
import os
import uuid
import hashlib
import secrets

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
    conn.execute("PRAGMA journal_mode=DELETE")  # 启动阶段用 DELETE，请求阶段自动切 WAL

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

def seed_knowledge_graph():
    conn = get_connection()
    needs_init = conn.execute('SELECT COUNT(*) FROM knowledge_nodes').fetchone()[0] == 0
    if needs_init:
        nodes = [
            ('select_basic','SELECT 基础查询','从单表中查询列','SELECT',0,'fa-table'),
            ('alias','别名 AS','为列或表取别名','SELECT',1,'fa-tag'),
            ('distinct','DISTINCT 去重','去除重复行','SELECT',1,'fa-eraser'),
            ('where_basic','WHERE 条件筛选','按条件过滤行','WHERE',1,'fa-filter'),
            ('order_by','ORDER BY 排序','对结果集排序','ORDER BY',1,'fa-sort'),
            ('where_andor','AND / OR 多条件','组合多个条件','WHERE',2,'fa-plus-circle'),
            ('where_like','LIKE 模糊查询','字符串模式匹配','WHERE',2,'fa-search'),
            ('where_null','NULL 值判断','IS NULL / IS NOT NULL','WHERE',2,'fa-question-circle'),
            ('where_in','IN 运算符','匹配值列表','WHERE',2,'fa-list-ul'),
            ('where_between','BETWEEN 范围查询','值区间筛选','WHERE',2,'fa-arrows-alt-h'),
            ('limit_offset','LIMIT / OFFSET 分页','限制返回行数','ORDER BY',2,'fa-cut'),
            ('aggregate_basic','聚合函数基础','COUNT/SUM/MAX/MIN','聚合',2,'fa-calculator'),
            ('group_by','GROUP BY 分组','按列分组聚合','聚合',3,'fa-object-group'),
            ('having','HAVING 过滤分组','过滤分组后结果','聚合',4,'fa-filter'),
            ('avg','AVG 平均值','计算均值','聚合',4,'fa-chart-line'),
            ('count_distinct','COUNT(DISTINCT)','去重计数','聚合',4,'fa-sort-numeric-up'),
            ('case_when','CASE WHEN 条件','条件分支逻辑','聚合',5,'fa-code-branch'),
            ('join_inner','INNER JOIN 内连接','等值连接两表','JOIN',2,'fa-link'),
            ('join_left','LEFT JOIN 左连接','保留左表全部记录','JOIN',3,'fa-arrow-right'),
            ('join_self','自连接','同一表连接自身','JOIN',3,'fa-redo'),
            ('join_multi','多表 JOIN','连续 JOIN 多表','JOIN',4,'fa-project-diagram'),
            ('join_full','FULL OUTER JOIN','全外连接模拟','JOIN',5,'fa-arrows-alt'),
            ('subquery_basic','子查询基础','WHERE 中子查询','子查询',2,'fa-indent'),
            ('subquery_exists','EXISTS 子查询','存在性检查','子查询',4,'fa-check-double'),
            ('subquery_all','ALL / ANY 子查询','多行比较','子查询',4,'fa-greater-than'),
            ('subquery_select','SELECT 中子查询','标量子查询','子查询',5,'fa-code'),
            ('cte','CTE (WITH)','公共表表达式','子查询',6,'fa-layer-group'),
        ]
        for n in nodes:
            conn.execute('INSERT INTO knowledge_nodes (id,name,description,category,level,icon) VALUES (?,?,?,?,?,?)', n)
        edges = [
            ('select_basic','alias'),('select_basic','distinct'),
            ('select_basic','where_basic'),('select_basic','order_by'),('select_basic','aggregate_basic'),
            ('where_basic','where_andor'),('where_basic','where_like'),('where_basic','where_null'),
            ('where_basic','where_in'),('where_basic','where_between'),
            ('order_by','limit_offset'),
            ('aggregate_basic','group_by'),
            ('group_by','having'),('group_by','avg'),('group_by','count_distinct'),('group_by','case_when'),
            ('select_basic','join_inner'),
            ('join_inner','join_left'),('join_inner','join_self'),
            ('join_left','join_multi'),('join_left','join_full'),
            ('select_basic','subquery_basic'),
            ('subquery_basic','subquery_exists'),('subquery_basic','subquery_all'),('subquery_basic','subquery_select'),
            ('subquery_select','cte'),
        ]
        for f,t in edges:
            conn.execute('INSERT INTO knowledge_edges (from_node,to_node) VALUES (?,?)', (f,t))
        qn = [
            (1,'select_basic'),(2,'select_basic'),
            (3,'where_basic'),(4,'where_andor'),(5,'order_by'),(6,'limit_offset'),
            (7,'aggregate_basic'),(7,'group_by'),(8,'avg'),(9,'having'),
            (10,'join_inner'),(11,'join_left'),(12,'subquery_basic'),(13,'subquery_exists'),
            (14,'aggregate_basic'),(15,'where_like'),(16,'distinct'),
            (17,'join_multi'),(18,'subquery_all'),(19,'aggregate_basic'),(20,'where_between'),
            (21,'order_by'),(22,'join_self'),(23,'having'),
            (24,'subquery_select'),(25,'alias'),(26,'where_in'),(27,'cte'),
            (28,'case_when'),(29,'join_full'),(30,'where_null'),(31,'count_distinct'),(32,'limit_offset'),
        ]
        for qid,nid in qn:
            conn.execute('INSERT OR IGNORE INTO question_knowledge (question_id,node_id) VALUES (?,?)', (qid,nid))
    # Auto-map ALL questions by their category field（仅在新题目出现时执行）
    total_q = conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    mapped_q = conn.execute('SELECT COUNT(DISTINCT question_id) FROM question_knowledge').fetchone()[0]
    if mapped_q < total_q:
        all_qs = conn.execute('SELECT id, category FROM questions').fetchall()
        cat_to_node = {
            '基础查询': 'select_basic', '条件筛选': 'where_basic',
            '排序分页': 'order_by', '聚合与分组': 'aggregate_basic',
            '多表连接': 'join_inner', '子查询与CTE': 'subquery_basic',
            '窗口函数': 'window', '日期处理': 'date', '字符串处理': 'string',
            # 新增 viz 分类标签映射
            'dml_select': 'select_basic', 'dml_insert': 'dml', 'dml_update': 'dml', 'dml_delete': 'dml',
            'ddl_create': 'select_basic', 'ddl_alter': 'select_basic', 'ddl_drop': 'select_basic',
            'ddl_truncate': 'select_basic', 'ddl_rename': 'select_basic', 'ddl_comment': 'select_basic',
            'string_func': 'string', 'numeric_func': 'aggregate_basic', 'aggregate_func': 'aggregate_basic',
            'cast_func': 'select_basic', 'window_func': 'window',
            'join_outer': 'join_left', 'join_cross': 'join_inner',
            'constraint_primary_key': 'select_basic', 'constraint_foreign_key': 'select_basic',
            'subquery_scalar': 'subquery_basic', 'subquery_column': 'subquery_basic',
            'subquery_table': 'subquery_basic', 'subquery_in': 'where_in',
            'where_basic': 'where_basic', 'having': 'having', 'group_by': 'group_by',
        }
        for r in all_qs:
            node_id = cat_to_node.get(r['category'], 'select_basic')
            conn.execute('INSERT OR IGNORE INTO question_knowledge (question_id,node_id) VALUES (?,?)', (r['id'], node_id))
    conn.commit()
    print("Knowledge graph seeded.")

# ---- 查询 ----
def get_diagnostic_questions():
    """按知识图谱层级获取摸底测试题：level 0-1→easy, 2-3→medium, 4+→hard"""
    import random as _random
    conn = get_connection()
    level_map = [
        ('easy', [0, 1]),
        ('medium', [2, 3]),
        ('hard', [4, 5, 6]),
    ]
    selected = []
    for difficulty, levels in level_map:
        placeholders = ','.join('?' for _ in levels)
        rows = conn.execute(f'''SELECT q.*, qk.node_id FROM questions q
            JOIN question_knowledge qk ON q.id = qk.question_id
            JOIN knowledge_nodes kn ON qk.node_id = kn.id
            WHERE kn.level IN ({placeholders}) AND q.difficulty = ?''', levels + [difficulty]).fetchall()
        if rows:
            q = dict(_random.choice(rows))
            selected.append(q)
        else:
            fallback = conn.execute(
                'SELECT * FROM questions WHERE difficulty=?', (difficulty,)).fetchall()
            if fallback:
                q = dict(_random.choice(fallback))
                q['node_id'] = get_question_node_id(q['id'])
                selected.append(q)
    return selected

def _expand_node_to_categories(node_id):
    """Given a knowledge node ID, return all leaf category names under it.
    Follows knowledge_edges to find all descendant nodes, then maps to
    the question category field via cat_to_node reverse mapping."""
    conn = get_connection()
    # BFS/DFS to collect all descendant node IDs
    all_nodes = set([node_id])
    queue = [node_id]
    while queue:
        current = queue.pop(0)
        children = conn.execute(
            'SELECT to_node FROM knowledge_edges WHERE from_node=?', (current,)
        ).fetchall()
        for child in children:
            child_id = child['to_node']
            if child_id not in all_nodes:
                all_nodes.add(child_id)
                queue.append(child_id)
    return list(all_nodes)

def get_all_questions(category=None, difficulty=None, pool='practice', node=None):
    conn = get_connection()
    if node:
        # Filter by knowledge node (and all descendants)
        # Dual match: via question_knowledge table AND via category field directly
        node_ids = _expand_node_to_categories(node)
        placeholders = ','.join('?' for _ in node_ids)
        cat_placeholders = ','.join('?' for _ in node_ids)
        query = f'''SELECT DISTINCT q.* FROM questions q
            LEFT JOIN question_knowledge qk ON q.id = qk.question_id
            WHERE q.pool=? AND (qk.node_id IN ({placeholders}) OR q.category IN ({cat_placeholders}))'''
        params = [pool] + node_ids + node_ids
    else:
        query = 'SELECT * FROM questions WHERE pool=?'
        params = [pool]
    if category:
        query += ' AND q.category = ?' if node else ' AND category = ?'
        params.append(category)
    if difficulty:
        query += ' AND q.difficulty = ?' if node else ' AND difficulty = ?'
        params.append(difficulty)
    query += ' ORDER BY q.id' if node else ' ORDER BY id'
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]

def get_exam_questions(category=None, difficulty=None, node=None):
    """Query the exam_questions table (independent pool for exam/interview questions)."""
    conn = get_connection()
    if node:
        node_ids = _expand_node_to_categories(node)
        placeholders = ','.join('?' for _ in node_ids)
        query = f'''SELECT DISTINCT eq.* FROM exam_questions eq
            LEFT JOIN question_knowledge qk ON eq.id = qk.question_id
            WHERE qk.node_id IN ({placeholders}) OR eq.category IN ({placeholders})'''
        params = node_ids + node_ids
    else:
        query = 'SELECT * FROM exam_questions WHERE 1=1'
        params = []
    if category:
        query += ' AND eq.category = ?' if node else ' AND category = ?'
        params.append(category)
    if difficulty:
        query += ' AND eq.difficulty = ?' if node else ' AND difficulty = ?'
        params.append(difficulty)
    query += ' ORDER BY eq.id' if node else ' ORDER BY id'
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]

def get_question_node_id(question_id):
    conn = get_connection()
    row = conn.execute('SELECT node_id FROM question_knowledge WHERE question_id=? LIMIT 1', (question_id,)).fetchone()
    return row['node_id'] if row else None

def get_question_by_id(qid):
    conn = get_connection()
    row = conn.execute('SELECT * FROM questions WHERE id = ?', (qid,)).fetchone()
    return dict(row) if row else None

def is_mcq(question):
    """Check if a question is multiple-choice (has options)."""
    opts = question.get('options', '')
    return bool(opts and (isinstance(opts, str) and opts.strip() or len(opts) > 0))

def get_or_create_derived_question(prototype_id):
    """Generate a fill-in derived question from a multiple-choice prototype.
    Returns the derived question dict, or None if prototype doesn't exist or is already fill-in."""
    proto = get_question_by_id(prototype_id)
    if not proto or not is_mcq(proto):
        return None
    conn = get_connection()
    existing = conn.execute('SELECT * FROM derived_questions WHERE prototype_id=? LIMIT 1', (prototype_id,)).fetchone()
    if existing:
            return dict(existing)
    import copy
    dq = {
        'prototype_id': proto['id'],
        'title': proto['title'] + '（举一反三）',
        'description': proto['description'] + '\n\n（提示：请手动编写 SQL 语句，无需选择选项）',
        'table_schema': proto.get('table_schema', ''),
        'initial_data': proto.get('initial_data', ''),
        'correct_answer': proto['correct_answer'],
        'explanation': proto.get('explanation', ''),
        'expected_output': proto.get('expected_output', ''),
        'difficulty': proto['difficulty'],
        'category': proto['category'],
    }
    conn.execute('''INSERT INTO derived_questions
        (prototype_id,title,description,table_schema,initial_data,correct_answer,explanation,expected_output,difficulty,category)
        VALUES (?,?,?,?,?,?,?,?,?,?)''',
        (dq['prototype_id'], dq['title'], dq['description'], dq['table_schema'],
         dq['initial_data'], dq['correct_answer'], dq['explanation'],
         dq['expected_output'], dq['difficulty'], dq['category']))
    dq['id'] = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.commit()
    return dq

def get_derived_question_by_id(dqid):
    conn = get_connection()
    row = conn.execute('SELECT * FROM derived_questions WHERE id=?', (dqid,)).fetchone()
    return dict(row) if row else None

def get_questions_by_node_and_type(node_id, session_id, is_mcq_type, exclude_ids=None):
    """Find questions linked to a knowledge node, filtering by type (MCQ or fill-in)
    that the user hasn't answered yet (or answered incorrectly)."""
    conn = get_connection()
    exclude = [int(x) for x in (exclude_ids or []) if x is not None]
    base_query = '''SELECT q.* FROM questions q
        JOIN question_knowledge qk ON q.id = qk.question_id
        WHERE qk.node_id = ?
        AND (q.options IS NOT NULL AND q.options != '')''' if is_mcq_type else '''SELECT q.* FROM questions q
        JOIN question_knowledge qk ON q.id = qk.question_id
        WHERE qk.node_id = ?
        AND (q.options IS NULL OR q.options = '')'''
    if exclude:
        placeholders = ','.join('?' for _ in exclude)
        query = f'''{base_query}
        AND q.id NOT IN (SELECT question_id FROM user_progress WHERE session_id=? AND is_correct=1)
        AND q.id NOT IN ({placeholders})
        ORDER BY q.difficulty LIMIT 1'''
        params = [node_id, session_id] + exclude
    else:
        query = f'''{base_query}
        AND q.id NOT IN (SELECT question_id FROM user_progress WHERE session_id=? AND is_correct=1)
        ORDER BY q.difficulty LIMIT 1'''
        params = [node_id, session_id]
    row = conn.execute(query, params).fetchone()
    return dict(row) if row else None

def get_node_id_for_question(question_id):
    conn = get_connection()
    row = conn.execute('SELECT node_id FROM question_knowledge WHERE question_id=? LIMIT 1', (question_id,)).fetchone()
    return row['node_id'] if row else None

def get_questions_by_node(node_id):
    conn = get_connection()
    rows = conn.execute('''SELECT q.* FROM questions q
        JOIN question_knowledge qk ON q.id = qk.question_id
        WHERE qk.node_id = ? ORDER BY q.difficulty''', (node_id,)).fetchall()
    return [dict(r) for r in rows]

# ---- 知识图谱 ----
def get_graph():
    conn = get_connection()
    nodes = [dict(r) for r in conn.execute('SELECT * FROM knowledge_nodes ORDER BY level,id').fetchall()]
    edges = [dict(r) for r in conn.execute('SELECT * FROM knowledge_edges').fetchall()]
    return {'nodes': nodes, 'edges': edges}

# ---- 用户画像 ----
def _is_authenticated(session_id):
    """检查 session_id 是否属于已注册用户"""
    conn = get_connection()
    row = conn.execute('SELECT id FROM users WHERE session_id=?', (session_id,)).fetchone()
    return row is not None

def save_answer(session_id, question_id, user_answer, is_correct, duration=0):
    # 未登录用户不记录答题记录
    if not _is_authenticated(session_id):
        return
    conn = get_connection()
    conn.execute('INSERT INTO user_progress (session_id,question_id,user_answer,is_correct,duration) VALUES (?,?,?,?,?)',
                 (session_id, question_id, user_answer, 1 if is_correct else 0, duration))
    # update mastery for related nodes (BKT: Beta distribution)
    nodes = conn.execute('SELECT node_id FROM question_knowledge WHERE question_id = ?', (question_id,)).fetchall()
    for n in nodes:
        nid = n['node_id']
        existing = conn.execute('SELECT * FROM user_mastery WHERE session_id=? AND node_id=?', (session_id,nid)).fetchone()
        if existing:
            conn.execute('''UPDATE user_mastery SET correct_count=correct_count+?, total_count=total_count+1,
                alpha=alpha+?, beta=beta+?, updated_at=CURRENT_TIMESTAMP WHERE session_id=? AND node_id=?''',
                (1 if is_correct else 0, 1 if is_correct else 0, 0 if is_correct else 1, session_id, nid))
        else:
            a = 1 + (1 if is_correct else 0)
            b = 1 + (0 if is_correct else 1)
            conn.execute('INSERT INTO user_mastery (session_id,node_id,correct_count,total_count,alpha,beta) VALUES (?,?,?,?,?,?)',
                         (session_id, nid, 1 if is_correct else 0, 1, a, b))
    conn.commit()

def get_mastery(session_id):
    conn = get_connection()
    rows = conn.execute('SELECT * FROM user_mastery WHERE session_id=?', (session_id,)).fetchall()
    return {r['node_id']: dict(r) for r in rows}

# ---- Journey 自适应引擎 ----
def get_journey_state(session_id):
    conn = get_connection()
    row = conn.execute('SELECT * FROM journey_state WHERE session_id=?', (session_id,)).fetchone()
    return dict(row) if row else None

def init_journey(session_id, diagnostic_data=None):
    conn = get_connection()
    existing = conn.execute('SELECT * FROM journey_state WHERE session_id=?', (session_id,)).fetchone()
    if existing:
            return dict(existing)
    # Determine starting level based on diagnostic results
    start_level = 0
    phase = 'cold'
    if diagnostic_data:
        acc = diagnostic_data.get('accuracy', 0)
        skipped = diagnostic_data.get('skipped', 0)
        total = diagnostic_data.get('total', 3)
        if skipped >= 2 or total == 0:
            start_level = 0; phase = 'cold'
        elif acc >= 80:
            start_level = 2; phase = 'exploration'  # high performer
        elif acc >= 50:
            start_level = 1; phase = 'exploration'
        else:
            start_level = 0; phase = 'cold'
        # Pre-seed alpha/beta for nodes the user answered correctly/incorrectly in diagnostic
        details = diagnostic_data.get('details', [])
        for d in details:
            if d.get('skipped'): continue
            nid = d.get('node_id')
            if not nid: continue
            existing_m = conn.execute('SELECT * FROM user_mastery WHERE session_id=? AND node_id=?', (session_id, nid)).fetchone()
            if not existing_m:
                a = 2 if d.get('is_correct') else 1
                b = 1 if d.get('is_correct') else 2
                conn.execute('INSERT INTO user_mastery (session_id,node_id,correct_count,total_count,alpha,beta) VALUES (?,?,?,?,?,?)',
                             (session_id, nid, 1 if d.get('is_correct') else 0, 1, a, b))
    all_nodes = [dict(r) for r in conn.execute('SELECT id, level FROM knowledge_nodes ORDER BY level, id').fetchall()]
    first_nodes = [n['id'] for n in all_nodes if n['level'] == start_level]
    if not first_nodes:
        first_nodes = ['select_basic']
    queue_json = json.dumps(first_nodes)
    conn.execute('''INSERT INTO journey_state (session_id,current_node,node_queue,skipped_nodes,fillin_queue,fillin_pending,deep_mode,phase,recent_modules)
        VALUES (?,?,?,?,?,?,?,?,?)''',
                 (session_id, None, queue_json, json.dumps([]), json.dumps([]), 0, 1, phase, json.dumps([])))
    conn.commit()
    return get_journey_state(session_id)

def _get_unlocked_nodes(session_id):
    """Return node_ids the user has unlocked based on mastery of prerequisites."""
    conn = get_connection()
    graph = [dict(r) for r in conn.execute('SELECT * FROM knowledge_edges').fetchall()]
    mastery = {r['node_id']: dict(r) for r in conn.execute('SELECT * FROM user_mastery WHERE session_id=?', (session_id,)).fetchall()}
    all_nodes = [dict(r)['id'] for r in conn.execute('SELECT id FROM knowledge_nodes ORDER BY level').fetchall()]

    def is_mastered(nid):
        return _mastery_prob(mastery.get(nid)) >= 0.7

    def node_has_unlocked_prereqs(nid):
        prereqs = [e['from_node'] for e in graph if e['to_node'] == nid]
        if not prereqs: return True
        return all(is_mastered(p) for p in prereqs)

    unlocked = [nid for nid in all_nodes if node_has_unlocked_prereqs(nid)]
    return unlocked

def _recommend_weak_prereq(session_id, node_id):
    """Find the weakest prerequisite of node_id that isn't mastered."""
    conn = get_connection()
    prereqs = [dict(r)['from_node'] for r in conn.execute('SELECT from_node FROM knowledge_edges WHERE to_node=?', (node_id,)).fetchall()]
    mastery = {r['node_id']: dict(r) for r in conn.execute('SELECT * FROM user_mastery WHERE session_id=?', (session_id,)).fetchall()}
    weakest = None; weakest_prob = 1.0
    for pid in prereqs:
        prob = _mastery_prob(mastery.get(pid))
        if prob < weakest_prob:
            weakest_prob = prob
            weakest = pid
    return weakest if weakest_prob < 0.7 else None

def _mastery_prob(m):
    """BKT: Beta distribution mean."""
    if not m: return 0.5
    a = m.get('alpha', 1)
    b = m.get('beta', 1)
    return a / (a + b)

def _mastery_uncertainty(m):
    """BKT: Beta distribution variance (exploration score)."""
    if not m: return 0.5
    a = m.get('alpha', 1)
    b = m.get('beta', 1)
    s = a + b
    return (a * b) / (s * s * (s + 1))

def _is_mastered(node_id, mastery):
    """Mastered if mastery probability >= 0.7."""
    m = mastery.get(node_id)
    return _mastery_prob(m) >= 0.7

def _thompson_score(node_id, mastery, total_answered, phase='exploration'):
    """Compute Thompson sampling score for a knowledge node."""
    m = mastery.get(node_id)
    prob = _mastery_prob(m)
    unc = _mastery_uncertainty(m)
    # Exploitation: want nodes with low mastery (high learning potential)
    exploit = 1 - prob
    # Exploration: want nodes with high uncertainty
    explore = unc
    # Dynamic exploration rate λ
    lam = max(0.1, 0.5 * (2.718 ** (-total_answered / 15)))
    if phase == 'cold':
        lam = 0.6  # more exploration in cold start
    elif phase == 'mastery':
        lam = 0.1  # less exploration in mastery phase
    return lam * explore + (1 - lam) * exploit

# ---- Journey 子函数 ----

def _record_answer_stats(session_id, state, was_correct, duration):
    """记录答题统计：速度、总答题数、连错计数"""
    conn = get_connection()
    if duration is not None:
        sp = state.get('speed_count', 0)
        sa = state.get('avg_speed', 0)
        new_count = sp + 1
        new_avg = (sa * sp + duration) / new_count if sp > 0 else duration
        conn.execute('UPDATE journey_state SET avg_speed=?, speed_count=? WHERE session_id=?', (new_avg, new_count, session_id))
    conn.execute('UPDATE journey_state SET total_answered=total_answered+1 WHERE session_id=?', (session_id,))
    if was_correct is True:
        conn.execute('UPDATE journey_state SET wrong_streak=0 WHERE session_id=?', (session_id,))
    elif was_correct is False:
        conn.execute('UPDATE journey_state SET wrong_streak=wrong_streak+1 WHERE session_id=?', (session_id,))
    conn.commit()

def _determine_phase(session_id, phase, total_answered, was_correct, state):
    """阶段切换决策：cold→exploration→mastery"""
    conn = get_connection()
    if phase == 'cold' and total_answered >= 5:
        phase = 'exploration'
        conn.execute('UPDATE journey_state SET phase=? WHERE session_id=?', (phase, session_id))
        conn.commit()
    elif phase == 'exploration' and total_answered > 30:
        recent = [dict(r) for r in conn.execute(
            'SELECT is_correct FROM user_progress WHERE session_id=? ORDER BY answered_at DESC LIMIT 10', (session_id,)).fetchall()]
        if len(recent) >= 10:
            vals = [r['is_correct'] for r in recent]
            mean = sum(vals) / len(vals)
            variance = sum((v - mean) ** 2 for v in vals) / len(vals)
            if variance < 0.15:
                phase = 'mastery'
                conn.execute('UPDATE journey_state SET phase=? WHERE session_id=?', (phase, session_id))
                conn.commit()
    if phase == 'mastery' and was_correct is False and state.get('wrong_streak', 0) >= 3:
        phase = 'exploration'
        conn.execute('UPDATE journey_state SET phase=? WHERE session_id=?', (phase, session_id))
        conn.commit()
    return phase

def _check_fillin_mode(state, just_answered_qid, deep_mode):
    """检查是否应进入填空模式（MCQ答完后触发）"""
    if not deep_mode or not just_answered_qid:
        return False, '', '', None
    jaq = get_question_by_id(just_answered_qid)
    if jaq and jaq.get('options') and jaq['options'].strip():
        current_node = state.get('current_node')
        if current_node:
            return True, '请手动输入 SQL 语句来确认你是否真正掌握了该知识点。', 'fillin', current_node
    return False, '', '', None

def _select_candidate_node(session_id, unlocked, mastery, total_answered, phase, state,
                           is_fast, was_correct, recent_modules_raw, skipped_raw):
    """Thompson采样选择下一个知识点节点"""
    recent_modules = list(recent_modules_raw)
    skipped = list(skipped_raw)
    action = ''

    # Update recent modules (for safety constraint)
    if state.get('current_node'):
        graph_nodes = get_graph()['nodes']
        current_node_obj = next((n for n in graph_nodes if n['id'] == state['current_node']), None)
        if current_node_obj:
            recent_modules.append(current_node_obj.get('category', ''))
            if len(recent_modules) > 5:
                recent_modules = recent_modules[-5:]

    # Safety: check if 5 consecutive same-module
    same_module_count = 0
    last_mod = None
    if len(recent_modules) >= 5:
        last_mod = recent_modules[-1]
        same_module_count = sum(1 for m in recent_modules if m == last_mod)

    # Collect candidates: unlocked, not mastered
    candidates = [nid for nid in unlocked if not _is_mastered(nid, mastery)]
    if same_module_count >= 5 and candidates:
        all_nodes = get_graph()['nodes']
        node_map = {n['id']: n for n in all_nodes}
        candidates = [nid for nid in candidates if node_map.get(nid, {}).get('category', '') != last_mod]
    if not candidates:
        candidates = unlocked

    # Difficulty damping
    recent_progress = get_progress(session_id)[-10:]
    recent_correct = sum(1 for p in recent_progress if p['is_correct'])
    difficulty_damping = (len(recent_progress) >= 5 and recent_correct / max(len(recent_progress), 1) > 0.8)
    if difficulty_damping and phase != 'cold':
        all_nodes = get_graph()['nodes']
        node_map = {n['id']: n for n in all_nodes}
        weighted = []
        for nid in candidates:
            score = _thompson_score(nid, mastery, total_answered, phase)
            level = node_map.get(nid, {}).get('level', 0)
            score *= (1 + level * 0.2)
            weighted.append((score, nid))
    else:
        weighted = [(_thompson_score(nid, mastery, total_answered, phase), nid) for nid in candidates]

    weighted.sort(key=lambda x: -x[0])
    recommend_node = weighted[0][1] if weighted else 'select_basic'
    action = 'advance' if phase != 'cold' else 'cold'

    # Fast+correct: push same-level peers to skipped
    if is_fast and was_correct is True and phase != 'cold':
        all_nodes = get_graph()['nodes']
        node_map = {n['id']: n for n in all_nodes}
        rec_level = node_map.get(recommend_node, {}).get('level', 0)
        same_level = [nid for nid in candidates if node_map.get(nid, {}).get('level', 0) == rec_level and nid != recommend_node]
        for s in same_level:
            if s not in skipped:
                skipped.append(s)

    # Review interspersion (every 5 questions)
    if total_answered > 0 and total_answered % 5 == 0 and skipped:
        review_node = random.choice(skipped)
        skipped.remove(review_node)
        if not _is_mastered(review_node, mastery):
            recommend_node = review_node
            action = 'review'
            recent_modules = []

    # Persist
    conn = get_connection()
    conn.execute('UPDATE journey_state SET skipped_nodes=?, recent_modules=? WHERE session_id=?',
                 (json.dumps(skipped), json.dumps(recent_modules), session_id))
    conn.commit()
    return recommend_node, action

def _select_question_for_node(recommend_node, fillin_mode, session_id, just_answered_qid):
    """为指定知识点节点选择一道合适的题目，返回 (question, fillin_mode, action, hint)"""
    action = ''
    hint = ''
    node_qs = get_questions_by_node(recommend_node)
    if fillin_mode:
        node_qs = [q for q in node_qs if not q.get('options') or not q['options'].strip()]
    else:
        mcq = [q for q in node_qs if q.get('options') and q['options'].strip()]
        if mcq:
            node_qs = mcq

    progress = get_progress(session_id)
    answered_ids = set(p['question_id'] for p in progress)
    correct_ids = set(p['question_id'] for p in progress if p['is_correct'])

    unanswered = [q for q in node_qs if q['id'] not in answered_ids]
    if not unanswered:
        unanswered = [q for q in node_qs if q['id'] not in correct_ids]
    if not unanswered:
        unanswered = node_qs

    # 填空模式下该节点无题 → 回退到普通选择
    if not unanswered:
        if fillin_mode:
            node_qs = get_questions_by_node(recommend_node)
            mcq = [q for q in node_qs if q.get('options') and q['options'].strip()]
            if mcq:
                node_qs = mcq
            unanswered = [q for q in node_qs if q['id'] not in answered_ids]
            if not unanswered:
                unanswered = [q for q in node_qs if q['id'] not in correct_ids]
            if not unanswered:
                unanswered = node_qs
            if not unanswered:
                fallback = [q for q in get_all_questions() if q.get('options') and q['options'].strip()]
                unanswered = fallback if fallback else get_all_questions()
            fillin_mode = False
            action = ''
            hint = ''
        else:
            fallback = [q for q in get_all_questions() if q.get('options') and q['options'].strip()]
            unanswered = fallback if fallback else get_all_questions()
    if not unanswered:
        unanswered = get_all_questions()

    # 填空模式：不重复刚刚做过的MCQ
    if fillin_mode and unanswered and just_answered_qid:
        alt = [q for q in unanswered if q['id'] != just_answered_qid]
        if alt:
            unanswered = alt
        else:
            fillin_mode = False
            action = ''
            hint = ''
            node_qs = get_questions_by_node(recommend_node)
            mcq = [q for q in node_qs if q.get('options') and q['options'].strip()]
            if mcq:
                node_qs = mcq
            unanswered = [q for q in node_qs if q['id'] not in answered_ids]
            if not unanswered:
                unanswered = [q for q in node_qs if q['id'] not in correct_ids]
            if not unanswered:
                unanswered = node_qs
            if not unanswered:
                fallback = [q for q in get_all_questions() if q.get('options') and q['options'].strip()]
                unanswered = fallback if fallback else get_all_questions()

    return random.choice(unanswered) if unanswered else None, fillin_mode, action, hint

def journey_next(session_id, just_answered_qid=None, was_correct=None, duration=None):
    """自适应选题引擎：基于BKT+Thompson采样选择下一道题"""
    state = get_journey_state(session_id)
    if not state:
        state = init_journey(session_id)

    # 1. 记录答题统计
    if was_correct is not None:
        _record_answer_stats(session_id, state, was_correct, duration)

    # 2. 重新加载状态
    state = get_journey_state(session_id)
    total_answered = state.get('total_answered', 0)
    phase = state.get('phase', 'cold')
    deep_mode = state.get('deep_mode', 1)
    wrong_streak = state.get('wrong_streak', 0)

    # 3. 阶段切换
    phase = _determine_phase(session_id, phase, total_answered, was_correct, state)

    # 4. 检查填空模式触发
    is_fast = duration is not None and duration < 10
    fillin_mode, hint, fillin_action, recommend_node = _check_fillin_mode(
        state, just_answered_qid, deep_mode)

    # 5. 非填空模式：Thompson采样选节点
    if not fillin_mode:
        unlocked = _get_unlocked_nodes(session_id)
        mastery = get_mastery(session_id)
        recent_modules = json.loads(state.get('recent_modules', '[]'))
        skipped = json.loads(state.get('skipped_nodes', '[]'))
        recommend_node, action = _select_candidate_node(
            session_id, unlocked, mastery, total_answered, phase, state,
            is_fast, was_correct, recent_modules, skipped)
    else:
        action = fillin_action
        unlocked = _get_unlocked_nodes(session_id)
        mastery = get_mastery(session_id)

    # 6. 持久化当前节点
    conn = get_connection()
    conn.execute('UPDATE journey_state SET current_node=? WHERE session_id=?', (recommend_node, session_id))
    conn.commit()

    # 7. 选题
    question, fillin_mode, returned_action, returned_hint = _select_question_for_node(
        recommend_node, fillin_mode, session_id, just_answered_qid)
    if returned_action:
        action = returned_action
    if returned_hint:
        hint = returned_hint

    # 8. 组装响应
    progress = get_progress(session_id)
    graph_data = get_graph()
    mastery_data = get_mastery(session_id)

    return {
        'action': action,
        'current_node': recommend_node,
        'question': question,
        'graph': graph_data,
        'mastery': mastery_data,
        'unlocked_nodes': _get_unlocked_nodes(session_id),
        'wrong_streak': wrong_streak,
        'total_answered': total_answered,
        'total_correct': sum(1 for p in progress if p['is_correct']) + (1 if was_correct else 0),
        'fillin_mode': fillin_mode,
        'deep_mode': deep_mode,
        'hint': hint,
        'phase': phase
    }

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
    if not password or len(password.strip()) < 8 or len(password.strip()) > 16:
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

def get_admin_stats():
    conn = get_connection()
    total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    total_answers = conn.execute('SELECT COUNT(*) FROM user_progress').fetchone()[0]
    total_correct = conn.execute('SELECT COUNT(*) FROM user_progress WHERE is_correct=1').fetchone()[0]
    total_journeys = conn.execute('SELECT COUNT(*) FROM journey_state').fetchone()[0]
    accuracy = round(total_correct / total_answers * 100, 1) if total_answers > 0 else 0
    # per-difficulty stats
    diffs = conn.execute('''SELECT q.difficulty, COUNT(*) as cnt FROM user_progress up
        JOIN questions q ON up.question_id = q.id GROUP BY q.difficulty''').fetchall()
    diff_data = {r['difficulty']: r['cnt'] for r in diffs}
    return {
        'total_users': total_users,
        'total_answers': total_answers,
        'total_correct': total_correct,
        'total_journeys': total_journeys,
        'accuracy': accuracy,
        'by_difficulty': diff_data
    }

def get_admin_users():
    conn = get_connection()
    rows = conn.execute('''SELECT u.username, u.session_id, u.created_at,
        (SELECT COUNT(*) FROM user_progress WHERE session_id=u.session_id) as answered,
        (SELECT COUNT(*) FROM user_progress WHERE session_id=u.session_id AND is_correct=1) as correct,
        (SELECT MAX(answered_at) FROM user_progress WHERE session_id=u.session_id) as last_active
        FROM users u ORDER BY u.created_at DESC''').fetchall()
    users = []
    for r in rows:
        u = dict(r)
        u['accuracy'] = round(u['correct'] / u['answered'] * 100, 1) if u['answered'] > 0 else 0
        users.append(u)
    return users

def save_diagnostic_result(session_id, data):
    conn = get_connection()
    existing = conn.execute('SELECT id FROM diagnostic_results WHERE session_id=?', (session_id,)).fetchone()
    if existing:
        conn.execute('UPDATE diagnostic_results SET data=? WHERE session_id=?', (json.dumps(data), session_id))
    else:
        conn.execute('INSERT INTO diagnostic_results (session_id, data) VALUES (?,?)', (session_id, json.dumps(data)))
    conn.commit()

def get_diagnostic_result(session_id):
    conn = get_connection()
    row = conn.execute('SELECT data FROM diagnostic_results WHERE session_id=?', (session_id,)).fetchone()
    return json.loads(row['data']) if row else None

def get_progress(session_id):
    conn = get_connection()
    rows = conn.execute('''SELECT q.*, up.question_id, up.user_answer, up.is_correct, up.answered_at
        FROM user_progress up JOIN questions q ON up.question_id = q.id
        WHERE up.session_id=? ORDER BY up.answered_at''', (session_id,)).fetchall()
    return [dict(r) for r in rows]

import random

def get_seed_questions():
    return [
        {"source": "curated", "category": "基础查询", "difficulty": "easy", "title": "查询所有员工",
         "description": "从 employees 表中查询所有列的所有记录。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT * FROM employees;",
         "explanation": "SELECT * FROM 表名 可以查询表中的所有列。",
         "options": "SELECT * FROM employees;|SELECT ALL FROM employees;|SELECT * FROM emp;|SHOW employees;",
         "option_explanations": "✓ SELECT * 可查询表中所有列。|✗ SELECT ALL 不是标准 SQL 语法。|✗ 表名错误，应为 employees。|✗ SHOW 是查看数据库的命令，非查询语句。"},
        {"source": "curated", "category": "基础查询", "difficulty": "easy", "title": "查询特定列",
         "description": "从 employees 表中查询所有员工的姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary FROM employees;",
         "explanation": "SELECT 列名1, 列名2 FROM 表名 可以查询指定列。",
         "options": "SELECT name, salary FROM employees;|SELECT * FROM employees;|SELECT name AND salary FROM employees;|SELECT name+salary FROM employees;",
         "option_explanations": "✓ 逗号分隔列名，查询 name 和 salary。|✗ * 查询所有列，未限定为特定列。|✗ AND 不能连接列名，应使用逗号。|✗ + 用于数值运算，不能连接列名。"},
        {"source": "curated", "category": "条件筛选", "difficulty": "easy", "title": "WHERE 条件筛选",
         "description": "从 employees 表中查询薪资大于 13000 的员工姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary FROM employees WHERE salary > 13000;",
         "explanation": "WHERE 子句用于筛选满足条件的记录。",
         "options": "SELECT name, salary FROM employees WHERE salary > 13000;|SELECT name, salary FROM employees HAVING salary > 13000;|SELECT name, salary FROM employees IF salary > 13000;|SELECT name, salary FROM employees WHERE salary > 13000;",
         "option_explanations": "✓ WHERE 按 salary>13000 过滤行。|✗ HAVING 用于分组后过滤，无 GROUP BY 时无效。|✗ IF 不是 SQL 条件关键字。|✗ 与第一选项相同，均为正确写法。"},
        {"source": "curated", "category": "条件筛选", "difficulty": "easy", "title": "AND 多条件查询",
         "description": "从 employees 表中查询技术部且薪资大于 14000 的员工姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary FROM employees WHERE department = '技术部' AND salary > 14000;",
         "explanation": "AND 用于同时满足多个条件。",
         "options": "SELECT name, salary FROM employees WHERE department = '技术部' AND salary > 14000;|SELECT name, salary FROM employees WHERE department = '技术部' OR salary > 14000;|SELECT name, salary FROM employees WHERE department = '技术部' && salary > 14000;|SELECT name, salary FROM employees WHERE department = '技术部', salary > 14000;",
         "option_explanations": "✓ AND 要求两个条件同时满足。|✗ OR 只需一个条件，可能查出其他部门。|✗ && 不是 SQL 标准逻辑运算符。|✗ 逗号不能连接 WHERE 条件。"},
        {"source": "curated", "category": "排序分页", "difficulty": "easy", "title": "ORDER BY 排序",
         "description": "从 employees 表中按薪资降序查询所有员工的姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary FROM employees ORDER BY salary DESC;",
         "explanation": "ORDER BY 列名 DESC 表示按该列降序排列，ASC 为升序（默认）。",
         "options": "SELECT name, salary FROM employees ORDER BY salary DESC;|SELECT name, salary FROM employees SORT BY salary DESC;|SELECT name, salary FROM employees ORDER BY salary;|SELECT name, salary FROM employees ORDER DESC salary;",
         "option_explanations": "✓ DESC 指定按薪资降序排列。|✗ SORT BY 不是标准 SQL 语法。|✗ 缺 DESC，默认升序排列。|✗ DESC 位置错误，应放在列名后。"},
        {"source": "curated", "category": "排序分页", "difficulty": "easy", "title": "LIMIT 限制结果数量",
         "description": "从 employees 表中查询薪资最高的前 3 名员工的姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary FROM employees ORDER BY salary DESC LIMIT 3;",
         "explanation": "LIMIT n 限制返回前 n 条记录，常与 ORDER BY 配合使用。",
         "options": "SELECT name, salary FROM employees ORDER BY salary DESC LIMIT 3;|SELECT TOP 3 name, salary FROM employees ORDER BY salary DESC;|SELECT name, salary FROM employees WHERE ROWNUM <= 3 ORDER BY salary DESC;|SELECT name, salary FROM employees ORDER BY salary DESC LIMIT 3;",
         "option_explanations": "✓ LIMIT 3 取薪资最高的前 3 条记录。|✗ TOP 3 是 SQL Server/MySQL 方言。|✗ ROWNUM 在 WHERE 之后执行，先筛选后排序。|✗ 与第一选项相同，均为正确写法。"},
        {"source": "curated", "category": "聚合与分组", "difficulty": "medium", "title": "COUNT 统计数量",
         "description": "统计 employees 表中每个部门的员工人数。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT department, COUNT(*) FROM employees GROUP BY department;",
         "explanation": "COUNT(*) 统计每组行数，GROUP BY 按部门分组。",
         "options": "SELECT department, COUNT(*) FROM employees GROUP BY department;|SELECT department, COUNT(*) FROM employees;|SELECT department, COUNT(department) FROM employees;|SELECT department, SUM(*) FROM employees GROUP BY department;",
         "option_explanations": "✓ COUNT(*) 统计每组行数，GROUP BY 分组。|✗ 无 GROUP BY，COUNT 会聚合整个表返回一条记录。|✗ COUNT(department) 不统计 NULL 值行。|✗ SUM(*) 无效，SUM 需要数值列。"},
        {"source": "curated", "category": "聚合与分组", "difficulty": "medium", "title": "AVG 求平均值",
         "description": "查询 employees 表中每个部门的平均薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT department, AVG(salary) FROM employees GROUP BY department;",
         "explanation": "AVG() 函数计算平均值，GROUP BY 按部门分组。",
         "options": "SELECT department, AVG(salary) FROM employees GROUP BY department;|SELECT department, AVG(salary) FROM employees;|SELECT department, AVG(salary) FROM employees GROUP BY department;|SELECT department, AVG(salary) AS avg_salary FROM employees GROUP BY department;",
         "option_explanations": "✓ AVG(salary) 计算平均薪资，GROUP BY 分组。|✗ 无 GROUP BY，AVG 返回整体平均值。|✗ 与第一选项相同，均为正确写法。|✗ AS avg_salary 仅添加别名，功能相同。"},
        {"source": "curated", "category": "聚合与分组", "difficulty": "medium", "title": "HAVING 过滤分组",
         "description": "查询 employees 中平均薪资大于 13000 的部门及其平均薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT department, AVG(salary) FROM employees GROUP BY department HAVING AVG(salary) > 13000;",
         "explanation": "HAVING 用于过滤分组后的结果，WHERE 不能用于聚合函数。",
         "options": "SELECT department, AVG(salary) FROM employees GROUP BY department HAVING AVG(salary) > 13000;|SELECT department, AVG(salary) FROM employees WHERE AVG(salary) > 13000 GROUP BY department;|SELECT department, AVG(salary) FROM employees GROUP BY department WHERE AVG(salary) > 13000;|SELECT department, AVG(salary) FROM employees HAVING AVG(salary) > 13000;",
         "option_explanations": "✓ HAVING 过滤平均薪资>13000 的分组。|✗ WHERE 中不能直接使用聚合函数 AVG。|✗ WHERE 不能放在 GROUP BY 之后。|✗ 缺少 GROUP BY，无法按部门分组。"},
        {"source": "curated", "category": "多表连接", "difficulty": "medium", "title": "INNER JOIN 内连接",
         "description": "查询每位员工的姓名及其所属部门名称。\n\n表结构：\nemployees(id, name, dept_id)\ndepartments(id, dept_name)",
         "table_schema": "employees(id INT, name VARCHAR(100), dept_id INT);\ndepartments(id INT, dept_name VARCHAR(50))",
         "initial_data": "INSERT INTO employees VALUES (1,'张三',1),(2,'李四',2),(3,'王五',1);\nINSERT INTO departments VALUES (1,'技术部'),(2,'市场部');",
         "correct_answer": "SELECT e.name, d.dept_name FROM employees e JOIN departments d ON e.dept_id = d.id;",
         "explanation": "INNER JOIN 返回两个表中匹配的行，ON 指定连接条件。",
         "options": "SELECT e.name, d.dept_name FROM employees e JOIN departments d ON e.dept_id = d.id;|SELECT e.name, d.dept_name FROM employees e, departments d WHERE e.dept_id = d.id;|SELECT name, dept_name FROM employees, departments;|SELECT e.name, d.dept_name FROM employees e INNER departments d ON e.dept_id = d.id;",
         "option_explanations": "✓ JOIN ON 正确连接员工与部门表。|✗ 隐式连接，WHERE 做关联条件亦可。|✗ 无连接条件，产生笛卡尔积（交叉连接）。|✗ INNER 后缺少 JOIN 关键字。"},
        {"source": "curated", "category": "多表连接", "difficulty": "medium", "title": "LEFT JOIN 左连接",
         "description": "查询所有员工及其部门名称，包括未分配部门的员工。\n\n表结构：\nemployees(id, name, dept_id)\ndepartments(id, dept_name)",
         "table_schema": "employees(id INT, name VARCHAR(100), dept_id INT);\ndepartments(id INT, dept_name VARCHAR(50))",
         "initial_data": "INSERT INTO employees VALUES (1,'张三',1),(2,'李四',2),(3,'王五',NULL);\nINSERT INTO departments VALUES (1,'技术部'),(2,'市场部');",
         "correct_answer": "SELECT e.name, d.dept_name FROM employees e LEFT JOIN departments d ON e.dept_id = d.id;",
         "explanation": "LEFT JOIN 返回左表所有记录，右表无匹配时显示 NULL。",
         "options": "SELECT e.name, d.dept_name FROM employees e LEFT JOIN departments d ON e.dept_id = d.id;|SELECT e.name, d.dept_name FROM employees e JOIN departments d ON e.dept_id = d.id;|SELECT e.name, d.dept_name FROM employees e RIGHT JOIN departments d ON e.dept_id = d.id;|SELECT e.name, d.dept_name FROM employees e LEFT OUTER departments d ON e.dept_id = d.id;",
         "option_explanations": "✓ LEFT JOIN 保留左表所有员工，包括无部门的王五。|✗ INNER JOIN 只返回匹配的行，王五将被排除。|✗ RIGHT JOIN 保留右表全部，语义相反。|✗ LEFT OUTER 后缺少 JOIN 关键字。"},
        {"source": "curated", "category": "子查询与CTE", "difficulty": "hard", "title": "子查询 IN",
         "description": "查询薪资高于所有员工平均薪资的员工姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary FROM employees WHERE salary > (SELECT AVG(salary) FROM employees);",
         "explanation": "子查询 (SELECT AVG(salary) FROM employees) 先计算平均薪资，外层查询筛选高于该值的员工。",
         "options": "SELECT name, salary FROM employees WHERE salary > (SELECT AVG(salary) FROM employees);|SELECT name, salary FROM employees WHERE salary > AVG(salary);|SELECT name, salary FROM employees HAVING salary > AVG(salary);|SELECT name, salary FROM employees WHERE salary > (SELECT salary FROM employees);",
         "option_explanations": "✓ 子查询计算平均薪资，外层 > 比较。|✗ AVG(salary) 不能直接在 WHERE 中使用。|✗ HAVING 用于分组后，此处无 GROUP BY。|✗ 子查询返回多行 salary，> 无法与多行比较。"},
        {"source": "curated", "category": "子查询与CTE", "difficulty": "hard", "title": "子查询 EXISTS",
         "description": "查询有员工的部门名称。\n\n表结构：\ndepartments(id, dept_name)\nemployees(id, name, dept_id)",
         "table_schema": "departments(id INT, dept_name VARCHAR(50));\nemployees(id INT, name VARCHAR(100), dept_id INT)",
         "initial_data": "INSERT INTO departments VALUES (1,'技术部'),(2,'市场部'),(3,'财务部');\nINSERT INTO employees VALUES (1,'张三',1),(2,'李四',2);",
         "correct_answer": "SELECT dept_name FROM departments d WHERE EXISTS (SELECT 1 FROM employees e WHERE e.dept_id = d.id);",
         "explanation": "EXISTS 检查子查询是否有返回结果，有则满足条件。",
         "options": "SELECT dept_name FROM departments d WHERE EXISTS (SELECT 1 FROM employees e WHERE e.dept_id = d.id);|SELECT dept_name FROM departments WHERE id IN (SELECT dept_id FROM employees);|SELECT dept_name FROM departments d WHERE d.id IN (SELECT e.dept_id FROM employees e);|SELECT dept_name FROM departments, employees;",
         "option_explanations": "✓ EXISTS 检查每个部门是否有员工存在。|✗ IN 也能实现相同功能，但 EXISTS 更高效。|✗ IN 也能实现，写法不同但功能相同。|✗ 无连接条件，产生笛卡尔积。"},
        {"source": "curated", "category": "聚合与分组", "difficulty": "medium", "title": "MAX/MIN 最大值最小值",
         "description": "查询 employees 表中每个部门的最高薪资和最低薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT department, MAX(salary), MIN(salary) FROM employees GROUP BY department;",
         "explanation": "MAX() 和 MIN() 分别返回最大值和最小值，常与 GROUP BY 配合。",
         "options": "SELECT department, MAX(salary), MIN(salary) FROM employees GROUP BY department;|SELECT department, MAX(salary), MIN(salary) FROM employees;|SELECT department, MAX(salary), MIN(salary) FROM employees GROUP BY department;|SELECT department, MAX(salary), MIN(salary) FROM employees GROUP BY department;",
         "option_explanations": "✓ MAX/MIN 结合 GROUP BY 按部门统计。|✗ 无 GROUP BY 返回整体最大最小。|✗ 与第一选项相同。|✗ 与第一选项相同。"},
        {"source": "curated", "category": "条件筛选", "difficulty": "easy", "title": "LIKE 模糊查询",
         "description": "从 employees 表中查询姓名中包含'张'的员工信息。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'张伟','技术部',16000,30),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT * FROM employees WHERE name LIKE '%张%';",
         "explanation": "LIKE '%张%' 匹配包含'张'字的字符串，% 表示任意字符序列。",
         "options": "SELECT * FROM employees WHERE name LIKE '%张%';|SELECT * FROM employees WHERE name = '张';|SELECT * FROM employees WHERE name LIKE '张';|SELECT * FROM employees WHERE name IN ('张');",
         "option_explanations": "✓ LIKE '%张%' 匹配含'张'的所有名字。|✗ = 要求完全等于'张'，不匹配张三/张伟。|✗ LIKE '张' 无通配符，等于精确匹配。|✗ IN ('张') 只匹配完全等于'张'的记录。"},
        {"source": "curated", "category": "基础查询", "difficulty": "easy", "title": "DISTINCT 去重",
         "description": "查询 employees 表中所有不重复的部门名称。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT DISTINCT department FROM employees;",
         "explanation": "DISTINCT 关键字用于去除重复行。",
         "options": "SELECT DISTINCT department FROM employees;|SELECT UNIQUE department FROM employees;|SELECT department FROM employees DISTINCT;|SELECT department FROM employees GROUP BY department;",
         "option_explanations": "✓ DISTINCT 去除重复部门名。|✗ UNIQUE 不是 SQL 标准关键字。|✗ DISTINCT 位置错误，应放在 SELECT 后。|✗ GROUP BY 也能去重，但语义不同，用于聚合。"},
        {"source": "curated", "category": "多表连接", "difficulty": "hard", "title": "多表 JOIN",
         "description": "查询每位员工的姓名、部门名称以及其项目名称。\n\n表结构：\nemployees(id, name, dept_id)\ndepartments(id, dept_name)\nprojects(id, project_name, emp_id)",
         "table_schema": "employees(id INT, name VARCHAR(100), dept_id INT);\ndepartments(id INT, dept_name VARCHAR(50));\nprojects(id INT, project_name VARCHAR(50), emp_id INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三',1),(2,'李四',2),(3,'王五',1);\nINSERT INTO departments VALUES (1,'技术部'),(2,'市场部');\nINSERT INTO projects VALUES (1,'项目A',1),(2,'项目B',1),(3,'项目C',2);",
         "correct_answer": "SELECT e.name, d.dept_name, p.project_name FROM employees e JOIN departments d ON e.dept_id = d.id LEFT JOIN projects p ON e.id = p.emp_id;",
         "explanation": "多表 JOIN 可以连续连接多个表，LEFT JOIN 确保没有项目的员工也能显示。",
         "options": "SELECT e.name, d.dept_name, p.project_name FROM employees e JOIN departments d ON e.dept_id = d.id LEFT JOIN projects p ON e.id = p.emp_id;|SELECT e.name, d.dept_name, p.project_name FROM employees e, departments d, projects p;|SELECT e.name, d.dept_name, p.project_name FROM employees e JOIN departments d, projects p;|SELECT e.name, d.dept_name, p.project_name FROM employees e JOIN departments d ON e.dept_id = d.id JOIN projects p ON e.id = p.emp_id;",
         "option_explanations": "✓ 多表 JOIN + LEFT JOIN 保留无项目的员工。|✗ 无连接条件，产生三表笛卡尔积。|✗ 第二个 JOIN 缺少 ON 连接条件。|✗ INNER JOIN 会排除无项目的员工王五。"},
        {"source": "curated", "category": "子查询与CTE", "difficulty": "hard", "title": "子查询多行结果",
         "description": "查询技术部中薪资高于市场部所有员工薪资的员工姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',7000,29);",
         "correct_answer": "SELECT name, salary FROM employees WHERE department = '技术部' AND salary > ALL (SELECT salary FROM employees WHERE department = '市场部');",
         "explanation": "> ALL 表示大于子查询返回的所有值，即大于市场部最高薪资。",
         "options": "SELECT name, salary FROM employees WHERE department = '技术部' AND salary > ALL (SELECT salary FROM employees WHERE department = '市场部');|SELECT name, salary FROM employees WHERE department = '技术部' AND salary > (SELECT MAX(salary) FROM employees WHERE department = '市场部');|SELECT name, salary FROM employees WHERE department = '技术部' AND salary > ANY (SELECT salary FROM employees WHERE department = '市场部');|SELECT name, salary FROM employees WHERE department = '技术部' AND salary > (SELECT salary FROM employees WHERE department = '市场部');",
         "option_explanations": "✓ > ALL 大于市场部所有员工薪资。|✗ > MAX 等效，但写法不同。|✗ > ANY 大于任意一个即可，逻辑不符。|✗ 子查询返回多行，> 无法与多行比较。"},
        {"source": "curated", "category": "聚合与分组", "difficulty": "medium", "title": "SUM 求和",
         "description": "查询 employees 表中每个部门的薪资总和。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT department, SUM(salary) FROM employees GROUP BY department;",
         "explanation": "SUM() 函数计算数值列的总和。",
         "options": "SELECT department, SUM(salary) FROM employees GROUP BY department;|SELECT department, SUM(salary) FROM employees;|SELECT department, TOTAL(salary) FROM employees GROUP BY department;|SELECT department, SUM(salary) FROM employees GROUP BY department;",
         "option_explanations": "✓ SUM(salary) 按部门求和。|✗ 无 GROUP BY，SUM 返回所有部门总和。|✗ TOTAL() 不是 SQL 标准函数。|✗ 与第一选项相同。"},
        {"source": "curated", "category": "条件筛选", "difficulty": "medium", "title": "BETWEEN 范围查询",
         "description": "从 employees 表中查询薪资在 12000 到 16000 之间的员工姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary FROM employees WHERE salary BETWEEN 12000 AND 16000;",
         "explanation": "BETWEEN x AND y 选取介于 x 和 y 之间的值（包含边界）。",
         "options": "SELECT name, salary FROM employees WHERE salary BETWEEN 12000 AND 16000;|SELECT name, salary FROM employees WHERE salary >= 12000 AND salary <= 16000;|SELECT name, salary FROM employees WHERE salary IN (12000, 16000);|SELECT name, salary FROM employees WHERE salary >= 12000 AND <= 16000;",
         "option_explanations": "✓ BETWEEN 12000 AND 16000 包含边界值。|✗ >= 和 <= 功能等效但写法更长。|✗ IN 只匹配 12000 或 16000，不是区间。|✗ AND 后缺少 salary 列名，语法错误。"},
        {"source": "curated", "category": "排序分页", "difficulty": "easy", "title": "多列排序",
         "description": "从 employees 表中先按部门升序，再按薪资降序查询所有员工信息。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT * FROM employees ORDER BY department ASC, salary DESC;",
         "explanation": "ORDER BY 支持多列排序，先按第一列排，再按第二列排。",
         "options": "SELECT * FROM employees ORDER BY department ASC, salary DESC;|SELECT * FROM employees ORDER BY department, salary;|SELECT * FROM employees ORDER BY department, salary DESC;|SELECT * FROM employees ORDER BY department ASC, salary DESC;",
         "option_explanations": "✓ 先按部门升序，再按薪资降序。|✗ 两列均默认 ASC 升序，薪资未降序。|✗ 部门缺少 ASC，默认为升序。|✗ 与第一选项相同。"},
        {"source": "curated", "category": "多表连接", "difficulty": "medium", "title": "自连接",
         "description": "查询所有员工及其直接上级的姓名。\n\n表结构：employees(id, name, manager_id)",
         "table_schema": "employees(id INT, name VARCHAR(100), manager_id INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'王总',NULL),(2,'张三',1),(3,'李四',1),(4,'王五',2);",
         "correct_answer": "SELECT e1.name AS employee, e2.name AS manager FROM employees e1 LEFT JOIN employees e2 ON e1.manager_id = e2.id;",
         "explanation": "自连接将同一张表视为两个不同的表进行连接。",
         "options": "SELECT e1.name AS employee, e2.name AS manager FROM employees e1 LEFT JOIN employees e2 ON e1.manager_id = e2.id;|SELECT e1.name, e2.name FROM employees e1, employees e2 WHERE e1.manager_id = e2.id;|SELECT e1.name, e2.name FROM employees e1 JOIN employees e2;|SELECT e1.name AS employee, e2.name AS manager FROM employees e1 INNER JOIN employees e2 ON e1.manager_id = e2.id;",
         "option_explanations": "✓ LEFT JOIN 自连接，王总无上级仍显示。|✗ INNER JOIN 只返回有上级的员工，王总被排除。|✗ 无连接条件，产生笛卡尔积。|✗ INNER JOIN 排除无上级的王总。"},
        {"source": "curated", "category": "聚合与分组", "difficulty": "hard", "title": "HAVING 与聚合函数组合",
         "description": "查询至少有 2 名员工的部门及其员工人数。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT department, COUNT(*) FROM employees GROUP BY department HAVING COUNT(*) >= 2;",
         "explanation": "HAVING 用于筛选分组后的结果，COUNT(*) >= 2 表示至少有2名员工。",
         "options": "SELECT department, COUNT(*) FROM employees GROUP BY department HAVING COUNT(*) >= 2;|SELECT department, COUNT(*) FROM employees WHERE COUNT(*) >= 2 GROUP BY department;|SELECT department, COUNT(*) FROM employees GROUP BY department WHERE COUNT(*) >= 2;|SELECT department, COUNT(*) FROM employees GROUP BY department HAVING COUNT(*) >= 2;",
         "option_explanations": "✓ HAVING 筛选人数>=2 的部门（技术部2人）。|✗ WHERE 不能直接使用聚合函数。|✗ WHERE 不能放在 GROUP BY 之后。|✗ 与第一选项相同。"},
        {"source": "curated", "category": "子查询与CTE", "difficulty": "hard", "title": "SELECT 中子查询",
         "description": "查询每位员工及其薪资在部门内的排名（按薪资降序）。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary, (SELECT COUNT(*) + 1 FROM employees e2 WHERE e2.department = e1.department AND e2.salary > e1.salary) AS rank FROM employees e1 ORDER BY department, rank;",
         "explanation": "SELECT 子句中可以使用子查询计算每行相关的标量值。",
         "options": "SELECT name, salary, (SELECT COUNT(*) + 1 FROM employees e2 WHERE e2.department = e1.department AND e2.salary > e1.salary) AS rank FROM employees e1 ORDER BY department, rank;|SELECT name, salary, RANK() OVER (PARTITION BY department ORDER BY salary DESC) FROM employees;|SELECT name, salary, ROW_NUMBER() OVER (PARTITION BY department ORDER BY salary DESC) FROM employees;|SELECT name, salary, (SELECT COUNT(*) FROM employees e2 WHERE e2.department = e1.department) FROM employees e1;",
         "option_explanations": "✓ 子查询计算同部门薪资高于自己的员工数+1作为排名。|✗ RANK() 是窗口函数，非所有数据库支持。|✗ ROW_NUMBER() 也是窗口函数。|✗ 子查询只计算部门总人数，非排名。"},
        {"source": "curated", "category": "基础查询", "difficulty": "easy", "title": "别名 AS",
         "description": "查询 employees 表中所有员工的姓名和薪资，将薪资列重命名为 '月薪'。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary AS 月薪 FROM employees;",
         "explanation": "AS 关键字为列或表取别名，使输出更易读。",
         "options": "SELECT name, salary AS 月薪 FROM employees;|SELECT name, salary 月薪 FROM employees;|SELECT name, salary AS '月薪' FROM employees;|SELECT name, salary AS 月薪 FROM employees;",
         "option_explanations": "✓ AS 将 salary 重命名为'月薪'。|✗ 省略 AS 也可取别名（隐式写法）。|✗ 引号括起的别名语法正确。|✗ 与第一选项相同。"},
        {"source": "curated", "category": "条件筛选", "difficulty": "medium", "title": "IN 运算符",
         "description": "从 employees 表中查询部门为 '技术部' 或 '财务部' 的员工姓名和部门。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, department FROM employees WHERE department IN ('技术部', '财务部');",
         "explanation": "IN 运算符用于判断列值是否匹配列表中的任意一个值。",
         "options": "SELECT name, department FROM employees WHERE department IN ('技术部', '财务部');|SELECT name, department FROM employees WHERE department = '技术部' OR department = '财务部';|SELECT name, department FROM employees WHERE department = '技术部' AND '财务部';|SELECT name, department FROM employees WHERE department IN ('技术部', '财务部');",
         "option_explanations": "✓ IN 匹配部门列表中的任意一个值。|✗ OR 功能等效，写法较冗长。|✗ AND '财务部' 缺少完整条件，语法错误。|✗ 与第一选项相同。"},
        {"source": "curated", "category": "子查询与CTE", "difficulty": "hard", "title": "WITH (CTE) 公共表表达式",
         "description": "使用 CTE 查询每个部门薪资最高的员工姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "WITH dept_max AS (SELECT department, MAX(salary) AS max_salary FROM employees GROUP BY department) SELECT e.name, e.department, e.salary FROM employees e JOIN dept_max d ON e.department = d.department AND e.salary = d.max_salary;",
         "explanation": "WITH 子句定义临时视图（CTE），使复杂查询更清晰。",
         "options": "WITH dept_max AS (SELECT department, MAX(salary) AS max_salary FROM employees GROUP BY department) SELECT e.name, e.department, e.salary FROM employees e JOIN dept_max d ON e.department = d.department AND e.salary = d.max_salary;|SELECT name, department, MAX(salary) FROM employees GROUP BY department;|SELECT name, department, salary FROM employees WHERE salary IN (SELECT MAX(salary) FROM employees GROUP BY department);|WITH dept_max AS (SELECT department, MAX(salary) FROM employees GROUP BY department) SELECT * FROM employees, dept_max;",
         "option_explanations": "✓ CTE 先取部门最高薪，再关联查出员工名。|✗ GROUP BY 部门无法直接查出员工姓名。|✗ IN 子查询无法保证部门与薪资对应。|✗ 无连接条件，CTE 与 employees 笛卡尔积。"},
        {"source": "curated", "category": "聚合与分组", "difficulty": "hard", "title": "CASE WHEN 条件统计",
         "description": "统计 employees 表中各薪资区间的员工人数。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT CASE WHEN salary < 12000 THEN '低薪' WHEN salary BETWEEN 12000 AND 15000 THEN '中薪' ELSE '高薪' END AS level, COUNT(*) FROM employees GROUP BY level;",
         "explanation": "CASE WHEN 实现条件分支逻辑，可在 GROUP BY 中使用。",
         "options": "SELECT CASE WHEN salary < 12000 THEN '低薪' WHEN salary BETWEEN 12000 AND 15000 THEN '中薪' ELSE '高薪' END AS level, COUNT(*) FROM employees GROUP BY level;|SELECT CASE WHEN salary < 12000 THEN '低薪' WHEN salary < 15000 THEN '中薪' ELSE '高薪' END, COUNT(*) FROM employees GROUP BY 1;|SELECT IF(salary < 12000, '低薪', IF(salary < 15000, '中薪', '高薪')) AS level, COUNT(*) FROM employees GROUP BY level;|SELECT CASE WHEN salary < 12000 THEN '低薪' WHEN salary BETWEEN 12000 AND 15000 THEN '中薪' WHEN salary > 15000 THEN '高薪' END AS level, COUNT(*) FROM employees GROUP BY level;",
         "option_explanations": "✓ CASE WHEN 按薪资区间分组统计人数。|✗ GROUP BY 1 按表达式位置分组，可运行但可读性差。|✗ IF 函数是 MySQL 方言，非标准 SQL。|✗ 第三条件 WHEN salary>15000 正确但写法冗长。"},
        {"source": "curated", "category": "多表连接", "difficulty": "hard", "title": "FULL OUTER JOIN 模拟",
         "description": "查询所有员工和所有部门，包括未分配部门的员工和没有员工的部门。\n\n表结构：employees(id, name, dept_id); departments(id, dept_name)",
         "table_schema": "employees(id INT, name VARCHAR(100), dept_id INT);\ndepartments(id INT, dept_name VARCHAR(50))",
         "initial_data": "INSERT INTO employees VALUES (1,'张三',1),(2,'李四',NULL),(3,'王五',2);\nINSERT INTO departments VALUES (1,'技术部'),(2,'市场部'),(3,'财务部');",
         "correct_answer": "SELECT e.name, d.dept_name FROM employees e LEFT JOIN departments d ON e.dept_id = d.id UNION SELECT e.name, d.dept_name FROM employees e RIGHT JOIN departments d ON e.dept_id = d.id;",
         "explanation": "SQLite 不支持 FULL OUTER JOIN，可以用 LEFT JOIN UNION RIGHT JOIN 模拟。",
         "options": "SELECT e.name, d.dept_name FROM employees e LEFT JOIN departments d ON e.dept_id = d.id UNION SELECT e.name, d.dept_name FROM employees e RIGHT JOIN departments d ON e.dept_id = d.id;|SELECT e.name, d.dept_name FROM employees e FULL JOIN departments d ON e.dept_id = d.id;|SELECT e.name, d.dept_name FROM employees e, departments d;|SELECT e.name, d.dept_name FROM employees e LEFT JOIN departments d ON e.dept_id = d.id;",
         "option_explanations": "✓ LEFT UNION RIGHT 模拟 FULL JOIN，包含所有员工和部门。|✗ FULL JOIN 在 SQLite 中不支持。|✗ 无连接条件，产生笛卡尔积。|✗ LEFT JOIN 只保留左表记录，缺少财务部。"},
        {"source": "curated", "category": "条件筛选", "difficulty": "easy", "title": "NULL 值判断",
         "description": "从 employees 表中查询没有分配部门（dept_id 为 NULL）的员工姓名。",
         "table_schema": "employees(id INT, name VARCHAR(100), dept_id INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三',1),(2,'李四',NULL),(3,'王五',2);",
         "correct_answer": "SELECT name FROM employees WHERE dept_id IS NULL;",
         "explanation": "NULL 值不能用 = 判断，必须使用 IS NULL 或 IS NOT NULL。",
         "options": "SELECT name FROM employees WHERE dept_id IS NULL;|SELECT name FROM employees WHERE dept_id = NULL;|SELECT name FROM employees WHERE dept_id IS NULL;|SELECT name FROM employees WHERE dept_id == NULL;",
         "option_explanations": "✓ IS NULL 正确判断空值。|✗ = NULL 在 SQL 中永远为假，无法判断空值。|✗ 与第一选项相同。|✗ == NULL 无法判断空值，SQL 使用 = 而非 ==。"},
        {"source": "curated", "category": "聚合与分组", "difficulty": "medium", "title": "COUNT(DISTINCT) 去重计数",
         "description": "查询 employees 表中不同部门的数量。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35);",
         "correct_answer": "SELECT COUNT(DISTINCT department) FROM employees;",
         "explanation": "COUNT(DISTINCT 列名) 统计某列不重复值的个数。",
         "options": "SELECT COUNT(DISTINCT department) FROM employees;|SELECT COUNT(DISTINCT department) FROM employees;|SELECT DISTINCT COUNT(department) FROM employees;|SELECT COUNT(DISTINCT department) FROM employees;",
         "option_explanations": "✓ COUNT(DISTINCT department) 统计不重复部门数（2个）。|✗ 与第一选项相同。|✗ DISTINCT COUNT 先计数再去重，语义不同。|✗ 与第一选项相同。"},
        {"source": "curated", "category": "基础查询", "difficulty": "easy", "title": "LIMIT OFFSET 分页",
         "description": "从 employees 表中跳过前 2 条，查询接下来的 2 条记录。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT * FROM employees LIMIT 2 OFFSET 2;",
         "explanation": "LIMIT n OFFSET m 跳过 m 条后取 n 条，用于分页查询。",
         "options": "SELECT * FROM employees LIMIT 2 OFFSET 2;|SELECT * FROM employees LIMIT 2, 2;|SELECT * FROM employees OFFSET 2 LIMIT 2;|SELECT * FROM employees SKIP 2 TAKE 2;",
         "option_explanations": "✓ LIMIT 2 OFFSET 2 跳过2条取2条。|✗ LIMIT 2,2 是 MySQL 方言写法。|✗ OFFSET 在前 SQLite 不支持。|✗ SKIP TAKE 是 SQL Server 方言。"},
    ]

def seed_questions():
    conn = get_connection()
    count = conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    if count > 0:
        return
    # 优先从 questions.json 加载（纯JSON，直接 json.load）；回退到 questions.py（旧格式，正则解析）
    qpath_json = os.path.join(os.path.dirname(__file__), '..', 'questions.json')
    qpath_py = os.path.join(os.path.dirname(__file__), '..', 'questions.py')
    questions = []
    if os.path.exists(qpath_json):
        with open(qpath_json, 'r', encoding='utf-8') as f:
            questions = json.load(f)
        print(f"Loaded {len(questions)} questions from questions.json")
    elif os.path.exists(qpath_py):
        import re
        with open(qpath_py, 'r', encoding='utf-8') as _f:
            _content = _f.read()
        _m = re.search(r'(\[.*\])', _content, re.DOTALL)
        if _m:
            questions = json.loads(_m.group(1))
        print(f"Loaded {len(questions)} questions from questions.py (legacy, consider migrating to .json)")
    if not questions:
        questions = get_seed_questions()
    for q in questions:
            conn.execute('''INSERT INTO questions (source,category,difficulty,title,description,table_schema,initial_data,correct_answer,explanation,options,option_explanations,expected_output,pool)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (q['source'],q['category'],q['difficulty'],q['title'],q['description'],
             q.get('table_schema'),q.get('initial_data'),q['correct_answer'],q.get('explanation'),q.get('options'), q.get('option_explanations'), q.get('expected_output'), 'practice'))
    conn.commit()
    print(f"Seeded {len(questions)} practice questions.")


def seed_exam_questions():
    """Load exam questions from exam_questions.json into exam_questions table."""
    conn = get_connection()
    count = conn.execute('SELECT COUNT(*) FROM exam_questions').fetchone()[0]
    if count > 0:
        return
    qpath = os.path.join(os.path.dirname(__file__), '..', 'exam_questions.json')
    if not os.path.exists(qpath):
        print("exam_questions.json not found, skipping exam seed.")
        return
    with open(qpath, 'r', encoding='utf-8') as f:
        questions = json.load(f)
    for q in questions:
        conn.execute('''INSERT INTO exam_questions (source,category,difficulty,title,description,table_schema,initial_data,correct_answer,explanation,options,option_explanations,expected_output)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
        (q['source'],q['category'],q['difficulty'],q['title'],q['description'],
         q.get('table_schema'),q.get('initial_data'),q.get('correct_answer',''),q.get('explanation'),q.get('options'), q.get('option_explanations'), q.get('expected_output')))
    conn.commit()
    print(f"Seeded {len(questions)} exam questions.")
