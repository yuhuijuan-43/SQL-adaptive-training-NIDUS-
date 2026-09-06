"""题库 / 进度 / 掌握度 / 知识图谱查询层"""
import json

from db import get_connection
from auth import _is_authenticated
from logs import log_user_event, username_by_session
from maintenance import on_answer_inserted

# EWMA 掌握度参数：学习率（越大越敏感）与中性先验（无历史时的起点）
EWMA_LR = 0.3
EWMA_PRIOR = 0.5

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

def get_exam_question_by_id(qid):
    """真题详情（exam_questions 表；与 questions 表 id 各自从 1 起，调用方须按池取）"""
    conn = get_connection()
    row = conn.execute('SELECT * FROM exam_questions WHERE id = ?', (qid,)).fetchone()
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
        AND q.id NOT IN (SELECT question_id FROM user_progress WHERE session_id=? AND pool='practice' AND is_correct=1)
        AND q.id NOT IN ({placeholders})
        ORDER BY q.difficulty LIMIT 1'''
        params = [node_id, session_id] + exclude
    else:
        query = f'''{base_query}
        AND q.id NOT IN (SELECT question_id FROM user_progress WHERE session_id=? AND pool='practice' AND is_correct=1)
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
        nodes = [dict(r) for r in conn.execute('SELECT * FROM knowledge_nodes').fetchall()]
        edges = [dict(r) for r in conn.execute('SELECT * FROM knowledge_edges').fetchall()]
        # 按图谱声明顺序排序（枝→叶→根，2026-08-05 改为 DML→SELECT→函数→子查询→表连接→约束→DDL）
        try:
            from seeding import OFFICIAL_TAGS, TOP_NODE_ORDER
        except Exception:
            OFFICIAL_TAGS, TOP_NODE_ORDER = {}, None
        top_rank = {tid: i for i, tid in enumerate(TOP_NODE_ORDER or ())}
        leaf_rank = {tid: j for top, (_, leaves) in OFFICIAL_TAGS.items() for j, (tid, _, _) in enumerate(leaves)}
        def _rank(n):
            if n['id'] == 'root':
                return (0, 0, 0)
            if n['id'] in top_rank:
                return (1, top_rank[n['id']], 0)
            if n['id'] in leaf_rank:
                top_id = next((t for t, (_, leaves) in OFFICIAL_TAGS.items()
                               if n['id'] in [l[0] for l in leaves]), '')
                return (2, top_rank.get(top_id, 999), leaf_rank.get(n['id'], 999))
            return (3, 999, 999)
        nodes.sort(key=_rank)
        _graph_cache = {'nodes': nodes, 'edges': edges}
    return _graph_cache

def invalidate_graph_cache():
    """种子数据更新后使图谱缓存失效"""
    global _graph_cache
    _graph_cache = None


def save_answer(session_id, question_id, user_answer, is_correct, duration=0, pool='practice'):
    # 未登录用户不记录答题记录
    if not _is_authenticated(session_id):
        return None
    conn = get_connection()
    cur = conn.execute('INSERT INTO user_progress (session_id,question_id,user_answer,is_correct,duration,pool) VALUES (?,?,?,?,?,?)',
                 (session_id, question_id, user_answer, 1 if is_correct else 0, duration, pool))
    # update mastery for related nodes (EWMA：指数加权移动平均，近期作答权重更高；
    # 取代原贝叶斯 Beta 分布——Beta 无遗忘机制，早期错误永久拖累掌握度)
    nodes = conn.execute('SELECT node_id FROM question_knowledge WHERE question_id = ?', (question_id,)).fetchall()
    for n in nodes:
        nid = n['node_id']
        existing = conn.execute('SELECT * FROM user_mastery WHERE session_id=? AND node_id=?', (session_id,nid)).fetchone()
        outcome = 1.0 if is_correct else 0.0
        if existing:
            prev = existing['ewma'] if existing['ewma'] is not None else EWMA_PRIOR
            new_ewma = prev + EWMA_LR * (outcome - prev)
            conn.execute('''UPDATE user_mastery SET correct_count=correct_count+?, total_count=total_count+1,
                ewma=?, updated_at=CURRENT_TIMESTAMP WHERE session_id=? AND node_id=?''',
                (1 if is_correct else 0, new_ewma, session_id, nid))
        else:
            new_ewma = EWMA_PRIOR + EWMA_LR * (outcome - EWMA_PRIOR)
            conn.execute('INSERT INTO user_mastery (session_id,node_id,correct_count,total_count,ewma) VALUES (?,?,?,?,?)',
                         (session_id, nid, 1 if is_correct else 0, 1, new_ewma))
    conn.commit()
    # 数据治理保险丝：计数达标后动态检查 user_progress 是否需要压缩（静默失败）
    try:
        on_answer_inserted()
    except Exception:
        pass
    # 用户动态：答题事件（管理后台实时排查用；名称/标题缺失时静默跳过）
    try:
        uname = username_by_session(session_id)
        if uname:
            tbl = 'exam_questions' if pool == 'exam' else 'questions'
            trow = conn.execute(f'SELECT title FROM {tbl} WHERE id=?', (question_id,)).fetchone()
            title = (trow['title'][:80] if trow and trow['title'] else f'题目#{question_id}')
            log_user_event(uname, 'answer', target=title,
                           detail='答对' if is_correct else '答错',
                           extra={'question_id': question_id, 'pool': pool, 'is_correct': bool(is_correct)})
    except Exception:
        pass
    return cur.lastrowid

def get_mastery(session_id):
    """每知识点掌握度。score 统一为 EWMA（0-1，越高越熟练）；
    历史行 ewma 为空时回退 Beta 均值（迁移工具回填后不再出现）"""
    conn = get_connection()
    rows = conn.execute('SELECT * FROM user_mastery WHERE session_id=?', (session_id,)).fetchall()
    out = {}
    for r in rows:
        d = dict(r)
        if d.get('ewma') is not None:
            d['score'] = round(d['ewma'], 4)
        else:
            a, b = d.get('alpha') or 1.0, d.get('beta') or 1.0
            d['score'] = round(a / (a + b), 4)
        out[r['node_id']] = d
    return out

def _account_kind(username):
    """判断账号类型：'user'（平台用户）/ 'admin'（管理员）/ None（不存在）"""
    conn = get_connection()
    if conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
        return 'user'
    if conn.execute('SELECT id FROM admin_users WHERE username=?', (username,)).fetchone():
        return 'admin'
    return None

def reset_user_password(username, new_password):
    """重置密码（自动识别平台用户/管理员）：旧密码入历史（kind 区分，每账号最多 3 条），新密码 bcrypt。
    管理员密码被重置后其全部会话立即失效（C2 重构，需重新登录）"""
    import bcrypt
    kind = _account_kind(username)
    if kind is None:
        return None, 'not_found'
    conn = get_connection()
    table = 'users' if kind == 'user' else 'admin_users'
    old_hash = dict(conn.execute(f'SELECT password FROM {table} WHERE username=?', (username,)).fetchone())['password']
    if old_hash:
        conn.execute('INSERT INTO user_password_history (username, password, kind) VALUES (?,?,?)',
                     (username, old_hash, kind))
        conn.execute('''DELETE FROM user_password_history WHERE username=? AND kind=? AND id NOT IN (
            SELECT id FROM user_password_history WHERE username=? AND kind=? ORDER BY id DESC LIMIT 3)''',
            (username, kind, username, kind))
    pw_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    conn.execute(f'UPDATE {table} SET password=? WHERE username=?', (pw_hash, username))
    if kind == 'admin':
        conn.execute('DELETE FROM admin_sessions WHERE username=?', (username,))
    conn.commit()
    return True, None

def rollback_user_password(username):
    """回退到最近一次历史密码（消费一条历史；最多可回退 3 次；按账号类型恢复各自历史）。
    管理员密码被回退后其全部会话立即失效（C2 重构，与 reset_user_password 行为一致，需重新登录）"""
    kind = _account_kind(username)
    if kind is None:
        return None, 'not_found'
    conn = get_connection()
    h = conn.execute(
        'SELECT id, password FROM user_password_history WHERE username=? AND kind=? ORDER BY id DESC LIMIT 1',
        (username, kind)).fetchone()
    if not h:
        return None, 'no_history'
    table = 'users' if kind == 'user' else 'admin_users'
    conn.execute(f'UPDATE {table} SET password=? WHERE username=?', (dict(h)['password'], username))
    conn.execute('DELETE FROM user_password_history WHERE id=?', (dict(h)['id'],))
    if kind == 'admin':
        conn.execute('DELETE FROM admin_sessions WHERE username=?', (username,))
    conn.commit()
    return True, None

def get_admin_stats():
    conn = get_connection()
    total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    total_answers = conn.execute('SELECT COUNT(*) FROM user_progress').fetchone()[0]
    total_correct = conn.execute('SELECT COUNT(*) FROM user_progress WHERE is_correct=1').fetchone()[0]
    total_journeys = conn.execute('SELECT COUNT(*) FROM journey_state').fetchone()[0]
    accuracy = round(total_correct / total_answers * 100, 1) if total_answers > 0 else 0
    # per-difficulty stats（真题记录 id 与练习重叠，仅统计练习池避免错位）
    diffs = conn.execute('''SELECT q.difficulty, COUNT(*) as cnt FROM user_progress up
        JOIN questions q ON up.question_id = q.id WHERE up.pool='practice' GROUP BY q.difficulty''').fetchall()
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
        (SELECT MAX(answered_at) FROM user_progress WHERE session_id=u.session_id) as last_active,
        (SELECT COUNT(*) FROM user_password_history h WHERE h.username=u.username AND h.kind='user') as rollback_count
        FROM users u ORDER BY u.created_at DESC''').fetchall()
    users = []
    for r in rows:
        u = dict(r)
        u['accuracy'] = round(u['correct'] / u['answered'] * 100, 1) if u['answered'] > 0 else 0
        users.append(u)
    return users

def get_admin_accounts():
    """管理员面板账号列表：平台用户 + 管理员（role 区分，供密码管理；不含管理后台）"""
    conn = get_connection()
    rows = conn.execute('''SELECT u.username, u.session_id, u.created_at,
        (SELECT COUNT(*) FROM user_progress WHERE session_id=u.session_id) as answered,
        (SELECT COUNT(*) FROM user_progress WHERE session_id=u.session_id AND is_correct=1) as correct,
        (SELECT MAX(answered_at) FROM user_progress WHERE session_id=u.session_id) as last_active,
        (SELECT COUNT(*) FROM user_password_history h WHERE h.username=u.username AND h.kind='user') as rollback_count,
        'user' as role
        FROM users u ORDER BY u.created_at DESC''').fetchall()
    admins = conn.execute('''SELECT a.username, '' as session_id, a.created_at,
        0 as answered, 0 as correct, a.last_login_at as last_active,
        (SELECT COUNT(*) FROM user_password_history h WHERE h.username=a.username AND h.kind='admin') as rollback_count,
        a.is_primary, 'admin' as role
        FROM admin_users a ORDER BY a.created_at DESC''').fetchall()
    users = []
    for r in list(rows) + list(admins):
        u = dict(r)
        u['accuracy'] = round(u['correct'] / u['answered'] * 100, 1) if u['answered'] > 0 else 0
        users.append(u)
    return users

def delete_user(username):
    """删除平台用户及其全部关联数据（答题记录/掌握度/旅程/诊断结果/密码历史），单事务同步生效。
    仅支持平台用户；管理员账号返回 is_admin 错误（用户名全局唯一，需先查管理员表拦截）"""
    conn = get_connection()
    if conn.execute('SELECT id FROM admin_users WHERE username=?', (username,)).fetchone():
        return None, 'is_admin'
    row = conn.execute('SELECT id, session_id FROM users WHERE username=?', (username,)).fetchone()
    if not row:
        return None, 'not_found'
    sid = row['session_id']
    conn.execute('DELETE FROM user_progress WHERE session_id=?', (sid,))
    conn.execute('DELETE FROM user_mastery WHERE session_id=?', (sid,))
    conn.execute('DELETE FROM journey_state WHERE session_id=?', (sid,))
    conn.execute('DELETE FROM user_lights WHERE session_id=?', (sid,))
    conn.execute('DELETE FROM diagnostic_results WHERE session_id=?', (sid,))
    conn.execute("DELETE FROM user_password_history WHERE username=? AND kind='user'", (username,))
    conn.execute('DELETE FROM users WHERE id=?', (row['id'],))
    conn.commit()
    return True, None

def delete_admin(username, operator):
    """删除管理员账号（仅主管理员可删除其他管理员）。
    防护：操作者须为主管理员；不能删除自己；主管理员账号不可删除（唯一主管理员保护）。
    同步删除该管理员的密码修改历史与会话（kind='admin'），删除后其无法再登录管理后台。"""
    from auth import get_admin_profile
    profile = get_admin_profile(operator)
    if not profile or not profile.get('is_primary'):
        return None, 'not_primary'
    if username == operator:
        return None, 'self'
    conn = get_connection()
    row = conn.execute('SELECT id, is_primary FROM admin_users WHERE username=?', (username,)).fetchone()
    if not row:
        return None, 'not_found'
    if row['is_primary']:
        return None, 'is_primary'
    conn.execute('DELETE FROM admin_users WHERE id=?', (row['id'],))
    conn.execute("DELETE FROM user_password_history WHERE username=? AND kind='admin'", (username,))
    conn.execute('DELETE FROM admin_sessions WHERE username=?', (username,))
    conn.commit()
    return True, None

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

def get_progress(session_id, pool='practice'):
    """用户答题进度（按池过滤：practice 联 questions 表；exam 联 exam_questions 表，id 互不串扰）"""
    conn = get_connection()
    tbl = 'questions' if pool == 'practice' else 'exam_questions'
    rows = conn.execute(f'''SELECT q.*, up.question_id, up.user_answer, up.is_correct, up.answered_at
        FROM user_progress up JOIN {tbl} q ON up.question_id = q.id
        WHERE up.session_id=? AND up.pool=? ORDER BY up.answered_at''', (session_id, pool)).fetchall()
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
