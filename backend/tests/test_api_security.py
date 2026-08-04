"""API 安全测试：admin 鉴权、密码策略、匿名访问契约"""
import db
from repositories import get_progress


class TestAdminAuth:
    def test_stats_requires_token(self, client):
        assert client.get('/api/admin/stats').status_code == 401

    def test_users_requires_token(self, client):
        assert client.get('/api/admin/users').status_code == 401

    def test_wrong_token_rejected(self, client):
        r = client.get('/api/admin/stats', headers={'Authorization': 'Bearer wrong-token'})
        assert r.status_code == 401

    def test_correct_token_allowed(self, client):
        r = client.get('/api/admin/stats', headers={'Authorization': 'Bearer test-admin-token'})
        assert r.status_code == 200
        assert 'total_users' in r.get_json()

        r = client.get('/api/admin/users', headers={'Authorization': 'Bearer test-admin-token'})
        assert r.status_code == 200


class TestPasswordPolicy:
    def test_short_password_rejected(self, client):
        r = client.post('/api/register', json={'username': 'u_short', 'password': 'short'})
        assert r.status_code == 400
        assert '8-64' in r.get_json()['error']

    def test_ok_password_accepted(self, client):
        r = client.post('/api/register', json={'username': 'u_ok', 'password': 'password123'})
        assert r.status_code == 200
        assert r.get_json()['session_id']

    def test_long_password_rejected(self, client):
        r = client.post('/api/register', json={'username': 'u_long', 'password': 'x' * 65})
        assert r.status_code == 400


class TestAnonymousContract:
    """当前行为契约：游客可读题/提交判题，但进度不落库"""

    def test_anonymous_can_read_question_list(self, client):
        assert client.get('/api/questions').status_code == 200

    def test_anonymous_gets_full_question(self, client):
        r = client.get('/api/questions/1')
        assert r.status_code == 200
        assert 'correct_answer' in r.get_json()
        assert 'initial_data' in r.get_json()

    def test_anonymous_submit_judges_but_does_not_record(self, client):
        r = client.post('/api/submit', json={
            'question_id': 1, 'answer': 'SELECT * FROM employees', 'session_id': 'anon-xyz'})
        assert r.status_code == 200
        assert r.get_json()['is_correct'] is True
        assert len(get_progress('anon-xyz')) == 0

    def test_anonymous_submit_wrong_gets_judge_error(self, client):
        r = client.post('/api/submit', json={
            'question_id': 1, 'answer': 'SELECT * FROM nosuchtable', 'session_id': 'anon-xyz'})
        d = r.get_json()
        assert d['is_correct'] is False
        assert 'judge_error' in d and '表不存在' in d['judge_error']
