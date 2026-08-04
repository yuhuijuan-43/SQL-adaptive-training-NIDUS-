"""题库 / 进度 / 掌握度 / 知识图谱查询层"""
import json

from db import get_connection
from auth import _is_authenticated

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

# 知识图谱结构只随 seed 变化，进程内缓存避免每次 journey 请求重复查库
_graph_cache = None

def get_graph():
    """返回知识图谱（进程内缓存，种子数据变更时由 invalidate_graph_cache 失效）"""
    global _graph_cache
    if _graph_cache is None:
        conn = get_connection()
        nodes = [dict(r) for r in conn.execute('SELECT * FROM knowledge_nodes ORDER BY level,id').fetchall()]
        edges = [dict(r) for r in conn.execute('SELECT * FROM knowledge_edges').fetchall()]
        _graph_cache = {'nodes': nodes, 'edges': edges}
    return _graph_cache

def invalidate_graph_cache():
    """种子数据更新后使图谱缓存失效"""
    global _graph_cache
    _graph_cache = None


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

def get_progress_summary(session_id, limit=200):
    """单用户答题记录摘要（管理后台用）：仅题目标题+答案+对错+用时，不传题目正文等大字段。
    LEFT JOIN：真题库答题记录可能无对应 questions 行（数据模型历史原因），回退显示题目 id。"""
    conn = get_connection()
    rows = conn.execute('''SELECT up.question_id, up.user_answer, up.is_correct, up.duration,
        up.answered_at, q.title, q.difficulty
        FROM user_progress up LEFT JOIN questions q ON up.question_id = q.id
        WHERE up.session_id=? ORDER BY up.answered_at DESC, up.id DESC LIMIT ?''',
        (session_id, limit)).fetchall()
    return [dict(r) for r in rows]
