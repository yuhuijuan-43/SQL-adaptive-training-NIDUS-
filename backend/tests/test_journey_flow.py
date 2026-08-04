"""Journey 自适应流程测试：注册 → 开始 → 答题 → 下一题 → 状态"""
import uuid

import db


def _register(client):
    # 每次测试用唯一用户名，避免并发/串行重复注册冲突
    name = f'u{uuid.uuid4().hex[:8]}'
    r = client.post('/api/register', json={'username': name, 'password': 'password123'})
    assert r.status_code == 200
    return r.get_json()['session_id']


class TestJourneyFlow:
    def test_start_returns_question(self, client):
        sid = _register(client)
        r = client.post('/api/journey/start', json={'session_id': sid}).get_json()
        assert r['current_node'] == 'select_basic'
        assert r['question'] is not None
        assert r['phase'] == 'cold'

    def test_anonymous_journey_rejected(self, client):
        # 登录门槛：游客不能开始 Journey
        r = client.post('/api/journey/start', json={'session_id': 'anon-journey'})
        assert r.status_code == 401

    def test_answer_correct_advances(self, client):
        sid = _register(client)
        start = client.post('/api/journey/start', json={'session_id': sid}).get_json()
        qid = start['question']['id']
        r = client.post('/api/journey/next', json={
            'session_id': sid, 'question_id': qid,
            'answer': 'SELECT * FROM employees', 'duration': 8}).get_json()
        assert r['last_answer_correct'] is True
        assert r['total_answered'] == 1
        assert r['total_correct'] == 1          # 不重复计数

    def test_answer_wrong_recommends_remedy(self, client):
        sid = _register(client)
        start = client.post('/api/journey/start', json={'session_id': sid}).get_json()
        qid = start['question']['id']
        r = client.post('/api/journey/next', json={
            'session_id': sid, 'question_id': qid,
            'answer': 'SELECT name FROM employees', 'duration': 8}).get_json()
        assert r['last_answer_correct'] is False
        assert r['total_correct'] == 0

    def test_status_consistent(self, client):
        sid = _register(client)
        client.post('/api/journey/start', json={'session_id': sid})
        start = client.post('/api/journey/start', json={'session_id': sid}).get_json()
        qid = start['question']['id']
        client.post('/api/journey/next', json={
            'session_id': sid, 'question_id': qid, 'answer': 'SELECT * FROM employees'})
        st = client.post('/api/journey/status', json={'session_id': sid}).get_json()
        assert st['total_answered'] == 1 and st['total_correct'] == 1
        assert st['unlocked_nodes'] and 'select_basic' in st['unlocked_nodes']

    def test_submit_route_judges_real_sql(self, client):
        sid = _register(client)
        # 真正的列重排（4 列齐全）：真实执行下判对
        r = client.post('/api/submit', json={
            'question_id': 1, 'answer': 'SELECT salary, name, dept, id FROM employees', 'session_id': sid})
        assert r.get_json()['is_correct'] is True
        assert len(db.get_connection().execute(
            'SELECT * FROM user_progress WHERE session_id=?', (sid,)).fetchall()) == 1


class TestOfficialTaxonomy:
    """官方知识图谱结构（2026-08）：7 大分类 × 29 标签；难度按星级（1★ 简单 / 2★ 中等 / 3★ 困难）"""

    def test_graph_has_official_structure(self, client):
        conn = db.get_connection()
        nodes = [dict(r) for r in conn.execute('SELECT id, level FROM knowledge_nodes').fetchall()]
        assert len(nodes) == 37                       # root + 7 大类 + 29 标签
        assert 'root' in [n['id'] for n in nodes]
        tops = [n for n in nodes if n['level'] == 1]
        leaves = [n for n in nodes if n['level'] >= 2]
        assert len(tops) == 7 and len(leaves) == 29
        edges = [dict(r) for r in conn.execute('SELECT from_node, to_node FROM knowledge_edges').fetchall()]
        # 官方层级边：root → 大类 → 标签
        for t in tops:
            assert any(e['from_node'] == 'root' and e['to_node'] == t['id'] for e in edges)
        top_ids = {t['id'] for t in tops}
        for leaf in leaves:
            assert any(e['to_node'] == leaf['id'] and e['from_node'] in top_ids for e in edges)
        # 星级 → level：1★=2 / 2★=3 / 3★=4
        levels = {n['id']: n['level'] for n in leaves}
        assert levels['select_basic'] == 2            # ★
        assert levels['join_inner'] == 3              # ★★
        assert levels['window_func'] == 4             # ★★★

    def test_difficulty_matches_stars(self, client):
        """conftest 两题 category=基础查询 → 官方 select_basic（★）→ 难度 easy"""
        rows = db.get_connection().execute('SELECT category, difficulty FROM questions').fetchall()
        assert all(r['category'] == 'select_basic' for r in rows)
        assert all(r['difficulty'] == 'easy' for r in rows)

    def test_filter_by_official_tag(self, client):
        sid = client.post('/api/register', json={
            'username': 'u_tag', 'password': 'password123'}).get_json()['session_id']
        # 有题标签：select_basic 返回 2 题（conftest 种子）
        r = client.get('/api/questions?node=select_basic&session_id=' + sid).get_json()
        assert r['total'] == 2
        # 无题标签（如外键）：不报错，返回空
        r = client.get('/api/questions?node=constraint_foreign_key&session_id=' + sid).get_json()
        assert r['total'] == 0
        # 大类展开：top_dml → 覆盖全部 4 个 DML 标签
        r = client.get('/api/questions?node=top_dml&session_id=' + sid).get_json()
        assert r['total'] == 0
