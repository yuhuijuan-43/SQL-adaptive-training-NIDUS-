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

    def test_anonymous_journey_creates_state(self, client):
        # 当前契约：游客也能建 journey 会话（进度不落库但会话存在）
        r = client.post('/api/journey/start', json={'session_id': 'anon-journey'})
        assert r.status_code == 200
        assert db.get_connection().execute(
            "SELECT COUNT(*) FROM journey_state WHERE session_id='anon-journey'").fetchone()[0] == 1

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
