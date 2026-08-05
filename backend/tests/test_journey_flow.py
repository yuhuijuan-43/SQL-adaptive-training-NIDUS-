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
        assert r['current_node'] == 'dml_select'
        assert r['question'] is not None
        # 图谱点亮版：首个活跃叶 dml_select，选择先行（q5 基础选择）
        assert r['question']['id'] == 5 and r['question'].get('q_level') == 'basic'
        assert r['phase'] == 'active'

    def test_anonymous_journey_rejected(self, client):
        # 登录门槛：游客不能开始 Journey
        r = client.post('/api/journey/start', json={'session_id': 'anon-journey'})
        assert r.status_code == 401

    def test_status_before_start_returns_map_data(self, client):
        """图谱入口视图：未开始 journey 时 status 返回 200（state=null），前端据此显示初始 0 点亮"""
        sid = _register(client)
        r = client.post('/api/journey/status', json={'session_id': sid})
        assert r.status_code == 200
        d = r.get_json()
        assert d['state'] is None
        assert len(d['lights']) == 37             # root + 7 大类 + 29 标签全量
        assert all(v['lit'] is False for v in d['lights'].values())   # 未开始：初始 0 点亮
        assert len(d['graph']['nodes']) == 37     # 图谱结构仍可获取（root + 7 大类 + 29 标签）
        assert d['total_answered'] == 0

    def test_answer_correct_advances(self, client):
        sid = _register(client)
        start = client.post('/api/journey/start', json={'session_id': sid}).get_json()
        qid = start['question']['id']
        r = client.post('/api/journey/next', json={
            'session_id': sid, 'question_id': qid,
            'answer': 'B. SELECT * FROM employees', 'duration': 8}).get_json()
        assert r['last_answer_correct'] is True
        assert r['total_answered'] == 1
        assert r['total_correct'] == 1          # 不重复计数

    def test_answer_wrong_recommends_remedy(self, client):
        sid = _register(client)
        start = client.post('/api/journey/start', json={'session_id': sid}).get_json()
        qid = start['question']['id']
        r = client.post('/api/journey/next', json={
            'session_id': sid, 'question_id': qid,
            'answer': 'A. DELETE FROM employees', 'duration': 8}).get_json()
        assert r['last_answer_correct'] is False
        assert r['total_correct'] == 0

    def test_status_consistent(self, client):
        sid = _register(client)
        start = client.post('/api/journey/start', json={'session_id': sid}).get_json()
        qid = start['question']['id']
        client.post('/api/journey/next', json={
            'session_id': sid, 'question_id': qid, 'answer': 'B. SELECT * FROM employees'})
        st = client.post('/api/journey/status', json={'session_id': sid}).get_json()
        assert st['total_answered'] == 1 and st['total_correct'] == 1
        assert 'select_basic' in st['lights']   # lights 为全量 37 节点

    def test_submit_route_judges_real_sql(self, client):
        sid = _register(client)
        # 填空题（q2 无 options）走真实执行判题
        r = client.post('/api/submit', json={
            'question_id': 2, 'answer': 'SELECT name FROM employees', 'session_id': sid})
        assert r.get_json()['is_correct'] is True
        assert len(db.get_connection().execute(
            'SELECT * FROM user_progress WHERE session_id=?', (sid,)).fetchall()) == 1
        # 选择题（q3 有 options）走文本比对判题
        r = client.post('/api/submit', json={
            'question_id': 3, 'answer': 'B. SELECT', 'session_id': sid})
        assert r.get_json()['is_correct'] is True

    def test_mcq_html_entity_normalization(self, client):
        """选择题判题：浏览器 textContent（真字符）与 DB 选项（HTML 实体）双向归一后比对
        conftest 模拟：DB 存 '&gt;' 实体选项，浏览器提交 '>' 真字符也应判对"""
        conn = db.get_connection()
        # 插入一道含 HTML 实体的选择题
        conn.execute(
            "INSERT INTO questions (source,category,difficulty,title,description,correct_answer,options) "
            "VALUES (?,?,?,?,?,?,?)",
            ('static_advanced', 'select_basic', 'easy', '实体题', '比较运算',
             'B. SELECT * FROM employee WHERE salary &gt; 5000 OR salary IS NULL',
             'A. SELECT * FROM employee WHERE salary &gt; 5000|B. SELECT * FROM employee WHERE salary &gt; 5000 OR salary IS NULL'))
        conn.commit()
        qid = conn.execute("SELECT id FROM questions WHERE title='实体题'").fetchone()[0]
        sid = client.post('/api/register', json={
            'username': 'u_ent', 'password': 'password123'}).get_json()['session_id']
        # 浏览器视角：真字符 '>'（HTML 实体已被浏览器解析）
        r = client.post('/api/submit', json={
            'session_id': sid, 'question_id': qid,
            'answer': 'B. SELECT * FROM employee WHERE salary > 5000 OR salary IS NULL'})
        assert r.get_json()['is_correct'] is True
        # DB 视角：实体字符串同样判对
        r = client.post('/api/submit', json={
            'session_id': sid, 'question_id': qid,
            'answer': 'B. SELECT * FROM employee WHERE salary &gt; 5000 OR salary IS NULL'})
        assert r.get_json()['is_correct'] is True
        # 错误选项仍判错
        r = client.post('/api/submit', json={
            'session_id': sid, 'question_id': qid,
            'answer': 'A. SELECT * FROM employee WHERE salary > 5000'})
        assert r.get_json()['is_correct'] is False


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
        """conftest 题按官方标签/星级：select_basic（★）→ easy；join_inner（★★）→ medium"""
        rows = db.get_connection().execute('SELECT category, difficulty FROM questions').fetchall()
        by_cat = {}
        for r in rows:
            by_cat.setdefault(r['category'], set()).add(r['difficulty'])
        assert by_cat['select_basic'] == {'easy'}
        assert by_cat['join_inner'] == {'medium'}

    def test_filter_by_official_tag(self, client):
        sid = client.post('/api/register', json={
            'username': 'u_tag', 'password': 'password123'}).get_json()['session_id']
        # 有题标签：select_basic 返回 6 题（自身 3 + 学习边展开的 join_inner 1 + dml_select 2）
        r = client.get('/api/questions?node=select_basic&session_id=' + sid).get_json()
        assert r['total'] == 6
        # 无题标签（如外键）：不报错，返回空
        r = client.get('/api/questions?node=constraint_foreign_key&session_id=' + sid).get_json()
        assert r['total'] == 0
        # 大类展开：top_dml → 覆盖全部 4 个 DML 标签（dml_select 有 2 题）
        r = client.get('/api/questions?node=top_dml&session_id=' + sid).get_json()
        assert r['total'] == 2
