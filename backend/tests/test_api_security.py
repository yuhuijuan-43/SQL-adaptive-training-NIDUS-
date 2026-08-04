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


class TestLoginGate:
    """产品决策：游客不允许读题/答题，全部 401；仅公开端点放行"""

    def test_anonymous_cannot_list_questions(self, client):
        assert client.get('/api/questions').status_code == 401

    def test_anonymous_cannot_get_question_detail(self, client):
        assert client.get('/api/questions/1').status_code == 401

    def test_anonymous_cannot_submit(self, client):
        r = client.post('/api/submit', json={
            'question_id': 1, 'answer': 'SELECT * FROM employees', 'session_id': 'anon-xyz'})
        assert r.status_code == 401

    def test_anonymous_cannot_read_progress(self, client):
        assert client.get('/api/progress/anon-xyz').status_code == 401

    def test_anonymous_cannot_start_journey(self, client):
        assert client.post('/api/journey/start', json={'session_id': 'anon-xyz'}).status_code == 401

    def test_public_graph_open(self, client):
        assert client.get('/api/graph').status_code == 200

    def test_public_ambient_titles_only(self, client):
        r = client.get('/api/ambient')
        assert r.status_code == 200
        items = r.get_json()
        assert items
        for i in items:
            assert set(i.keys()) == {'title', 'difficulty'}   # 不含任何可做题内容

    def test_public_check_username_open(self, client):
        assert client.get('/api/check-username?name=abc').status_code == 200

    def test_logged_in_can_read(self, client):
        sid = client.post('/api/register', json={'username': 'u_gate', 'password': 'password123'}).get_json()['session_id']
        # GET 走查询参数（前端 apiGet 自动注入），POST 走请求体
        assert client.get('/api/questions?session_id=' + sid).status_code == 200
        r = client.post('/api/submit', json={
            'question_id': 1, 'answer': 'SELECT * FROM employees', 'session_id': sid})
        assert r.status_code == 200
        assert r.get_json()['is_correct'] is True
        assert len(get_progress(sid)) == 1
