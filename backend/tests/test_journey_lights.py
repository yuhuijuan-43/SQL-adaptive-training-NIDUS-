"""2026-08 图谱点亮版引擎测试：双循环出题 + 叶/枝/根三级点亮

conftest 题库（活跃叶 3 个，按枝序 top_dml → top_select → top_join）：
- dml_select:   q5(基础选择) q6(填空)                    → plan [5,5,5,6,6]
- select_basic: q3(基础选择) q1(进阶选择) q2(填空)        → plan [3,1,3,2,2]
- join_inner:   q4(填空)                                 → plan [4,4,4,4,4]（池不足循环复用）
"""
import sqlite3
import uuid

import db as db_mod
from engine import LEAF_ORDER


def _conn():
    """独立 sqlite3 连接（动态读 db.DB_PATH：fixture 已 monkeypatch 到临时库）"""
    c = sqlite3.connect(db_mod.DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _register(client):
    name = f'ru{uuid.uuid4().hex[:8]}'
    r = client.post('/api/register', json={'username': name, 'password': 'password123'})
    assert r.status_code == 200
    return r.get_json()['session_id']


def _start(client, sid):
    return client.post('/api/journey/start', json={'session_id': sid}).get_json()


def _answer(client, sid, qid, answer, duration=8):
    return client.post('/api/journey/next', json={
        'session_id': sid, 'question_id': qid, 'answer': answer, 'duration': duration}).get_json()


def _status(client, sid):
    return client.post('/api/journey/status', json={'session_id': sid}).get_json()


def _backdate_last(sid):
    """把该 session 最近一条答题记录时间回拨 5 分钟（相邻间隔 >2min，阻断规则1）"""
    conn = _conn()
    conn.execute("UPDATE user_progress SET answered_at = datetime(answered_at, '-5 minutes') "
                 "WHERE id = (SELECT MAX(id) FROM user_progress WHERE session_id=?)", (sid,))
    conn.commit()


def _add_question(conn, qid, node='dml_select'):
    """向临时库追加一道指定叶节点的题（规则3 语义修正后只算不同题目，凑 distinct 计数用）"""
    conn.execute("INSERT OR IGNORE INTO questions (id, source, category, difficulty, title, description, correct_answer, pool) "
                 "VALUES (?, 'test', ?, 'easy', ?, 'desc', 'ans', 'practice')", (qid, node, f't{qid}'))
    conn.execute("INSERT OR IGNORE INTO question_knowledge (question_id, node_id) VALUES (?, ?)", (qid, node))


# 答案常量
ANS_Q5 = 'B. SELECT * FROM employees'            # dml_select 基础选择
ANS_Q6 = "SELECT name FROM employees WHERE dept = '技术部'"   # dml_select 填空
ANS_Q3 = 'B. SELECT'                             # select_basic 基础选择
WRONG = 'bad'


class TestRoundSequence:
    """双循环出题：枝→叶固定顺序、每叶 5 题（3 选择 + 2 填空选择先行）、池不足循环复用"""

    def test_first_question_is_dml_select_mcq(self, client):
        """首题：第一个活跃枝 top_dml 的第一个活跃叶 dml_select 的基础选择题（空枝跳过）"""
        sid = _register(client)
        d = _start(client, sid)
        assert d['current_node'] == 'dml_select'
        assert d['question']['id'] == 5
        assert d['round']['pos'] == 1
        assert d['round']['leaf_total'] == 5
        assert d['round']['leaf_count'] == 3
        assert d['phase'] == 'active'
        assert d['round_complete'] is False

    def test_leaf_sequence_mcq_then_fillin(self, client):
        """每叶 [选择×3, 填空×2]：前三道选择题，第 4 题为填空"""
        sid = _register(client)
        d = _start(client, sid)
        for i in range(3):
            q = d['question']
            assert q['id'] == 5
            assert bool(q.get('options'))            # 选择题
            d = _answer(client, sid, q['id'], WRONG, 8)
        assert d['current_node'] == 'dml_select'
        assert d['question']['id'] == 6              # 填空
        assert not bool(d['question'].get('options'))
        assert d['round']['pos'] == 4

    def test_pool_reuse_when_insufficient(self, client):
        """join_inner 题池仅 1 道填空 → 5 题循环复用同一题"""
        sid = _register(client)
        d = _start(client, sid)
        # 答错刷完 dml_select 5 题（避免点亮）→ select_basic 5 题 → 进入 join_inner
        for _ in range(5):
            d = _answer(client, sid, d['question']['id'], WRONG, 8)
        assert d['current_node'] == 'select_basic'
        for _ in range(5):
            d = _answer(client, sid, d['question']['id'], WRONG, 8)
        assert d['current_node'] == 'join_inner'
        assert d['question']['id'] == 4
        for i in range(4):
            d = _answer(client, sid, d['question']['id'], WRONG, 8)
            assert d['question']['id'] == 4           # 循环复用
            assert d['round']['pos'] == i + 2

    def test_lit_leaf_skipped_in_new_round(self, client, test_db):
        """规则3 已点亮的叶节点不进新一轮（直接跳过）"""
        sid = _register(client)
        conn = _conn()
        for qid in range(201, 211):                   # 10 道不同 dml_select 题（distinct 计数）
            _add_question(conn, qid)
            conn.execute("INSERT INTO user_progress (session_id,question_id,user_answer,is_correct) VALUES (?,?,?,1)",
                         (sid, qid, ANS_Q5))
        conn.commit()
        d = _start(client, sid)
        assert d['current_node'] == 'select_basic'    # dml_select 已点亮 → 跳过
        assert d['round']['leaf_count'] == 2


class TestRule1:
    """规则1：连续答对 3 道（相邻间隔 ≤2min）→ 点亮并跳过剩余题目"""

    def test_three_correct_in_row_lights_and_skips(self, client, test_db):
        sid = _register(client)
        d = _start(client, sid)
        for i in range(3):
            q = d['question']
            assert q['id'] == 5
            d = _answer(client, sid, q['id'], ANS_Q5, 5)
        # 第 3 连对 → 点亮 dml_select 并跳过剩余 2 题 → 直接到 select_basic 第 1 题
        assert d['lit_now'] == 'dml_select'
        assert d['current_node'] == 'select_basic'
        assert d['question']['id'] == 3
        assert d['round']['pos'] == 1
        conn = _conn()
        row = conn.execute("SELECT lit FROM user_lights WHERE session_id=? AND node_id='dml_select'",
                           (sid,)).fetchone()
        assert row and row['lit'] == 1
        # 点亮状态同步到响应：叶 lit、枝 x/y、根 x/7
        lights = d['lights']
        assert lights['dml_select']['lit'] is True
        assert lights['top_dml'] == {'lit': False, 'x': 1, 'y': 4}
        assert lights['root'] == {'lit': False, 'x': 0, 'y': 7}

    def test_interval_over_2min_blocks_rule1(self, client, test_db):
        """相邻间隔 >2min → 连对 3 也不点亮"""
        sid = _register(client)
        d = _start(client, sid)
        for i in range(3):
            q = d['question']
            d = _answer(client, sid, q['id'], ANS_Q5, 5)
            if i < 2:
                _backdate_last(sid)
        assert d['lit_now'] is None
        assert d['current_node'] == 'dml_select'      # 未点亮，仍在 dml_select
        assert d['question']['id'] == 6               # 第 4 题（填空）继续出题
        assert d['lights']['dml_select']['lit'] is False

    def test_streak_broken_by_wrong_answer(self, client):
        """连对被答错打断 → 不触发规则1；5 题出完（有错）规则2 也不触发"""
        sid = _register(client)
        d = _start(client, sid)
        for ok in [True, True, False, True]:
            q = d['question']
            d = _answer(client, sid, q['id'], ANS_Q5 if ok else 'A. DELETE FROM employees', 5)
            assert d['lit_now'] is None
        assert d['current_node'] == 'dml_select'
        # 第 5 题答对：尾部 3 条 = [错,对,对] 非全对 → 规则1 仍不触发
        q = d['question']
        d = _answer(client, sid, q['id'], ANS_Q5, 5)
        assert d['lit_now'] is None
        assert d['current_node'] == 'select_basic'    # 5 题出完（有错）→ 规则2 不亮，推进


class TestRule2:
    """规则2：本轮该叶全部题均答对（不计间隔）→ 点亮"""

    def test_all_correct_lights_rule2(self, client, test_db):
        """全程回拨间隔（阻断规则1）→ 5 题全对走规则2 点亮"""
        sid = _register(client)
        d = _start(client, sid)
        for i in range(5):
            q = d['question']
            ans = ANS_Q5 if q['id'] == 5 else ANS_Q6
            d = _answer(client, sid, q['id'], ans, 5)
            _backdate_last(sid)
        assert d['lit_now'] is None                   # 规则1 被间隔阻断
        assert d['current_node'] == 'select_basic'    # 段末推进
        conn = _conn()
        row = conn.execute("SELECT lit FROM user_lights WHERE session_id=? AND node_id='dml_select'",
                           (sid,)).fetchone()
        assert row and row['lit'] == 1                # 规则2 点亮
        assert d['lights']['dml_select']['lit'] is True

    def test_wrong_answer_prevents_rule2(self, client, test_db):
        """任 1 题答错 → 5 题出完也不点亮"""
        sid = _register(client)
        d = _start(client, sid)
        for i in range(5):
            q = d['question']
            ans = (ANS_Q5 if q['id'] == 5 else ANS_Q6) if i != 3 else WRONG
            d = _answer(client, sid, q['id'], ans, 5)
            _backdate_last(sid)
        assert d['current_node'] == 'select_basic'
        conn = _conn()
        row = conn.execute("SELECT lit FROM user_lights WHERE session_id=? AND node_id='dml_select'",
                           (sid,)).fetchone()
        assert row is None or row['lit'] == 0


class TestRule3:
    """规则3：累计答对 10 道该叶类型题（跨池）→ 点亮；correct 计数与 x/10 进度"""

    def test_correct_count_derived(self, client, test_db):
        """未开始 journey 也有 lights；答对 3 道不同题 → correct=3 未点亮"""
        sid = _register(client)
        conn = _conn()
        for qid in (5, 205, 206):                     # 3 道不同 dml_select 题（distinct 计数）
            _add_question(conn, qid)
            conn.execute("INSERT INTO user_progress (session_id,question_id,user_answer,is_correct) VALUES (?,?,?,1)",
                         (sid, qid, ANS_Q5))
        conn.commit()
        d = _status(client, sid)
        assert d['state'] is None
        assert len(d['lights']) == 37                 # root + 7 枝 + 29 叶 全量
        assert d['lights']['dml_select'] == {'lit': False, 'correct': 3}
        assert all(v['lit'] is False for v in d['lights'].values())

    def test_rule3_lights_at_10_cross_pool(self, client, test_db):
        """直插 9 道不同题 + /api/submit（自主练习路径）第 10 道 → 累计 10 点亮"""
        sid = _register(client)
        conn = _conn()
        for qid in range(201, 210):                   # 9 道不同 dml_select 题
            _add_question(conn, qid)
            conn.execute("INSERT INTO user_progress (session_id,question_id,user_answer,is_correct) VALUES (?,?,?,1)",
                         (sid, qid, ANS_Q5))
        conn.commit()
        r = client.post('/api/submit', json={'session_id': sid, 'question_id': 5, 'answer': ANS_Q5})
        assert r.status_code == 200
        assert r.get_json()['is_correct'] is True
        d = _status(client, sid)
        assert d['lights']['dml_select'] == {'lit': True, 'correct': 10}
        assert d['lights']['top_dml'] == {'lit': False, 'x': 1, 'y': 4}


class TestBranchRoot:
    """枝节点 x/y 推导（全亮后点亮）与根节点 x/7"""

    def test_branch_derivation_and_partial(self, client, test_db):
        sid = _register(client)
        conn = _conn()
        for leaf in ['ddl_create', 'ddl_alter', 'ddl_drop', 'ddl_truncate', 'ddl_rename', 'ddl_comment']:
            conn.execute("INSERT INTO user_lights (session_id,node_id,lit) VALUES (?,?,1)", (sid, leaf))
        conn.commit()
        d = _status(client, sid)
        assert d['lights']['top_ddl'] == {'lit': True, 'x': 6, 'y': 6}   # 全亮 → 枝点亮
        assert d['lights']['root'] == {'lit': False, 'x': 1, 'y': 7}
        # 部分点亮：撤掉 1 叶 → 枝未亮但 x/y 显示
        conn.execute("DELETE FROM user_lights WHERE session_id=? AND node_id='ddl_alter'", (sid,))
        conn.commit()
        d = _status(client, sid)
        assert d['lights']['top_ddl'] == {'lit': False, 'x': 5, 'y': 6}

    def test_root_lights_when_all_branches(self, client, test_db):
        """29 叶全亮 → 7 枝全亮 → 根点亮"""
        sid = _register(client)
        conn = _conn()
        for leaves in LEAF_ORDER.values():
            for leaf in leaves:
                conn.execute("INSERT INTO user_lights (session_id,node_id,lit) VALUES (?,?,1)", (sid, leaf))
        conn.commit()
        d = _status(client, sid)
        assert d['lights']['root'] == {'lit': True, 'x': 7, 'y': 7}


class TestRoundComplete:
    """一轮完成：round_complete 标记 + 点亮保留 + 重新开始新一轮"""

    def test_round_complete_and_restart(self, client, test_db):
        sid = _register(client)
        d = _start(client, sid)
        answered = 0
        while not d.get('round_complete'):
            q = d['question']
            assert q is not None
            d = _answer(client, sid, q['id'], WRONG, 8)
            answered += 1
            assert answered <= 20
        assert d['round_complete'] is True
        assert d['round']['answered_total'] == 15      # 3 叶 × 5 题
        assert d['round']['leaf_count'] == 3
        assert d['total_answered'] == 15               # journey_state 计数器累计
        assert d['question'] is None
        assert d['phase'] == 'complete'
        # 全程答错 → 无任何点亮，状态保留
        d2 = _status(client, sid)
        assert all(v['lit'] is False for v in d2['lights'].values())
        # 再开始 → 新一轮（15 题重新开始，点亮保留）
        d3 = _start(client, sid)
        assert d3['round_complete'] is False
        assert d3['current_node'] == 'dml_select'
        assert d3['round']['answered_total'] == 0
        assert d3['round']['leaf_count'] == 3

    def test_round_complete_with_lights_preserved(self, client, test_db):
        """一轮中点亮的叶，新一轮跳过（点亮保留 + 刷新后仍亮）"""
        sid = _register(client)
        d = _start(client, sid)
        # 连对 3 点亮 dml_select → 剩余 join_inner/select_basic 答错刷完
        for i in range(3):
            q = d['question']
            d = _answer(client, sid, q['id'], ANS_Q5, 5)
        while not d.get('round_complete'):
            q = d['question']
            d = _answer(client, sid, q['id'], WRONG, 8)
        assert d['round_complete'] is True
        assert 'dml_select' in d['round']['lit_round']
        # 新一轮：dml_select 已点亮跳过，只剩 2 叶（select_basic 在前）
        d2 = _start(client, sid)
        assert d2['round']['leaf_count'] == 2
        assert d2['current_node'] == 'select_basic'
        assert d2['lights']['dml_select']['lit'] is True
