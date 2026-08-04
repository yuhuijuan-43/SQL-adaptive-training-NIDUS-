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

    def test_admin_login_double_verify(self, client):
        """管理后台登录双重验证：管理员账号密码 + 统一管理员密钥"""
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'gate_admin', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        # 全对 → 200
        r = client.post('/api/admin/login', json={
            'username': 'gate_admin', 'password': 'Passw0rd1', 'key': 'test-admin-token'})
        assert r.status_code == 200 and r.get_json()['token'] == 'test-admin-token'
        # 密码错 → 401
        r = client.post('/api/admin/login', json={
            'username': 'gate_admin', 'password': 'wrong', 'key': 'test-admin-token'})
        assert r.status_code == 401
        # 密钥错 → 401
        r = client.post('/api/admin/login', json={
            'username': 'gate_admin', 'password': 'Passw0rd1', 'key': 'wrong'})
        assert r.status_code == 401
        # 缺密钥 → 401
        r = client.post('/api/admin/login', json={
            'username': 'gate_admin', 'password': 'Passw0rd1'})
        assert r.status_code == 401
        # 用户名不存在 → 404（提示先注册）
        r = client.post('/api/admin/login', json={
            'username': 'nobody', 'password': 'Passw0rd1', 'key': 'test-admin-token'})
        assert r.status_code == 404

    def test_admin_gate_page_served(self, client):
        r = client.get('/admin-gate')
        assert r.status_code == 200
        assert '管理员' in r.get_data(as_text=True) or 'admin' in r.get_data(as_text=True).lower()

    def test_user_progress_requires_token(self, client):
        assert client.get('/api/admin/user-progress?session_id=x').status_code == 401

    def test_user_progress_missing_param(self, client):
        r = client.get('/api/admin/user-progress', headers={'Authorization': 'Bearer test-admin-token'})
        assert r.status_code == 400

    def test_user_progress_returns_answers(self, client):
        sid = client.post('/api/register', json={'username': 'u_prog', 'password': 'password123'}).get_json()['session_id']
        client.post('/api/submit', json={
            'question_id': 1, 'answer': 'SELECT * FROM employees', 'session_id': sid})
        r = client.get('/api/admin/user-progress?session_id=' + sid,
                       headers={'Authorization': 'Bearer test-admin-token'})
        assert r.status_code == 200
        d = r.get_json()
        assert len(d['answers']) == 1
        a = d['answers'][0]
        # 摘要不含大字段，但含关键信息
        assert set(a.keys()) >= {'question_id', 'user_answer', 'is_correct', 'title', 'answered_at'}


class TestAdminAccount:
    """管理员账号体系：内推码注册 + 登录 + 同事 + 密码重置"""

    def test_register_bad_referral(self, client):
        r = client.post('/api/admin/auth-register', json={
            'username': 'boss', 'password': 'Passw0rd1', 'referral_code': 'WRONG'})
        assert r.status_code == 403

    def test_register_ok_returns_token(self, client):
        r = client.post('/api/admin/auth-register', json={
            'username': 'boss', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        assert r.status_code == 200
        assert r.get_json()['token'] == 'test-admin-token'

    def test_register_duplicate_username(self, client):
        for _ in range(2):
            r = client.post('/api/admin/auth-register', json={
                'username': 'boss2', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        assert r.status_code == 409

    def test_register_weak_password(self, client):
        r = client.post('/api/admin/auth-register', json={
            'username': 'boss3', 'password': 'short', 'referral_code': 'NIDUS_Agent'})
        assert r.status_code == 400

    def test_check_admin_username(self, client):
        assert client.get('/api/admin/auth-check-username?name=boss').get_json()['exists'] is False
        client.post('/api/admin/auth-register', json={
            'username': 'boss4', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        assert client.get('/api/admin/auth-check-username?name=boss4').get_json()['exists'] is True

    def test_login_wrong_password(self, client):
        client.post('/api/admin/auth-register', json={
            'username': 'boss5', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        assert client.post('/api/admin/auth-login', json={
            'username': 'boss5', 'password': 'wrong'}).status_code == 401

    def test_login_not_found(self, client):
        assert client.post('/api/admin/auth-login', json={
            'username': 'ghost', 'password': 'whatever'}).status_code == 404

    def test_login_ok(self, client):
        client.post('/api/admin/auth-register', json={
            'username': 'boss6', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        r = client.post('/api/admin/auth-login', json={
            'username': 'boss6', 'password': 'Passw0rd1'})
        assert r.status_code == 200
        assert r.get_json()['username'] == 'boss6'

    def test_colleagues_requires_token(self, client):
        assert client.get('/api/admin/colleagues').status_code == 401

    def test_colleagues_excludes_self(self, client):
        client.post('/api/admin/auth-register', json={
            'username': 'alice', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        client.post('/api/admin/auth-register', json={
            'username': 'bob', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        r = client.get('/api/admin/colleagues?me=alice',
                       headers={'Authorization': 'Bearer test-admin-token'})
        assert r.status_code == 200
        names = [c['username'] for c in r.get_json()['colleagues']]
        assert names == ['bob'] and 'alice' not in names

    def test_user_reset_requires_token(self, client):
        assert client.post('/api/admin/user-reset', json={
            'username': 'x', 'new_password': 'NewPass123'}).status_code == 401

    def test_user_reset_changes_password(self, client):
        sid = client.post('/api/register', json={
            'username': 'stu_reset', 'password': 'Password1'}).get_json()['session_id']
        assert sid
        r = client.post('/api/admin/user-reset', json={
            'username': 'stu_reset', 'new_password': 'NewPass123'},
            headers={'Authorization': 'Bearer test-admin-token'})
        assert r.status_code == 200
        assert client.post('/api/login', json={
            'username': 'stu_reset', 'password': 'NewPass123'}).status_code == 200
        assert client.post('/api/login', json={
            'username': 'stu_reset', 'password': 'Password1'}).status_code == 401

    def test_user_reset_unknown_user(self, client):
        r = client.post('/api/admin/user-reset', json={
            'username': 'nobody', 'new_password': 'NewPass123'},
            headers={'Authorization': 'Bearer test-admin-token'})
        assert r.status_code == 404

    def test_password_rollback_restores_old_password(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/register', json={'username': 'stu_rb', 'password': 'PassOld1'})
        # 重置 → 历史 +1，回退按钮应出现
        client.post('/api/admin/user-reset', json={
            'username': 'stu_rb', 'new_password': 'PassNew1'}, headers=H)
        users = client.get('/api/admin/users', headers=H).get_json()
        u = next(x for x in users if x['username'] == 'stu_rb')
        assert u['rollback_count'] == 1
        # 回退 → 旧密码恢复
        r = client.post('/api/admin/password-rollback', json={'username': 'stu_rb'}, headers=H)
        assert r.status_code == 200
        assert client.post('/api/login', json={
            'username': 'stu_rb', 'password': 'PassOld1'}).status_code == 200
        assert client.post('/api/login', json={
            'username': 'stu_rb', 'password': 'PassNew1'}).status_code == 401
        users = client.get('/api/admin/users', headers=H).get_json()
        u = next(x for x in users if x['username'] == 'stu_rb')
        assert u['rollback_count'] == 0

    def test_password_rollback_max_three(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/register', json={'username': 'stu_rb3', 'password': 'PassA123'})
        for pwd in ('PassB123', 'PassC123', 'PassD123', 'PassE123'):   # 4 次重置
            assert client.post('/api/admin/user-reset', json={
                'username': 'stu_rb3', 'new_password': pwd}, headers=H).status_code == 200
        users = client.get('/api/admin/users', headers=H).get_json()
        u = next(x for x in users if x['username'] == 'stu_rb3')
        assert u['rollback_count'] == 3          # 历史只保留最近 3 条
        # 回退 3 次成功（PassD123 → PassC123 → PassB123），第 4 次 409
        for expect in ('PassD123', 'PassC123', 'PassB123'):
            assert client.post('/api/admin/password-rollback', json={
                'username': 'stu_rb3'}, headers=H).status_code == 200
            assert client.post('/api/login', json={
                'username': 'stu_rb3', 'password': expect}).status_code == 200
        r = client.post('/api/admin/password-rollback', json={'username': 'stu_rb3'}, headers=H)
        assert r.status_code == 409

    def test_admin_key_requires_token(self, client):
        assert client.get('/api/admin/key').status_code == 401

    def test_admin_key_returns_current_key(self, client):
        r = client.get('/api/admin/key', headers={'Authorization': 'Bearer test-admin-token'})
        assert r.status_code == 200
        assert r.get_json()['key'] == 'test-admin-token'   # 复制值 = 实际配置值

    def test_password_rollback_requires_token(self, client):
        r = client.post('/api/admin/password-rollback', json={'username': 'x'})
        assert r.status_code == 401

    def test_password_rollback_no_history(self, client):
        r = client.post('/api/admin/password-rollback', json={
            'username': 'nobody'},
            headers={'Authorization': 'Bearer test-admin-token'})
        assert r.status_code == 409

    def test_users_list_excludes_admins(self, client):
        """管理后台 /api/admin/users 仅平台用户，不含管理员信息"""
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/register', json={'username': 'learner1', 'password': 'Password1'})
        client.post('/api/admin/auth-register', json={
            'username': 'admin_sync', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        users = client.get('/api/admin/users', headers=H).get_json()
        names = [u['username'] for u in users]
        assert 'learner1' in names and 'admin_sync' not in names
        assert all('role' not in u for u in users)

    def test_admin_accounts_syncs_admins(self, client):
        """管理员面板 /api/admin/accounts 含平台用户+管理员（role 区分）"""
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/register', json={'username': 'learner2', 'password': 'Password1'})
        client.post('/api/admin/auth-register', json={
            'username': 'admin_sync2', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        accounts = client.get('/api/admin/accounts', headers=H).get_json()
        by_name = {u['username']: u for u in accounts}
        assert by_name['learner2']['role'] == 'user'
        assert by_name['admin_sync2']['role'] == 'admin'
        assert 'last_active' in by_name['admin_sync2']

    def test_reset_admin_password_and_rollback(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'admin_rb', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        # 重置管理员密码
        r = client.post('/api/admin/user-reset', json={
            'username': 'admin_rb', 'new_password': 'Passw0rd2'}, headers=H)
        assert r.status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'admin_rb', 'password': 'Passw0rd2'}).status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'admin_rb', 'password': 'Passw0rd1'}).status_code == 401
        # 回退 → 恢复原密码
        r = client.post('/api/admin/password-rollback', json={
            'username': 'admin_rb'}, headers=H)
        assert r.status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'admin_rb', 'password': 'Passw0rd1'}).status_code == 200

    def test_global_username_uniqueness(self, client):
        """平台用户与管理员全局用户名唯一（双向禁止同名）"""
        H = {'Authorization': 'Bearer test-admin-token'}
        # 平台注册后，管理员不能再用同名
        client.post('/api/register', json={'username': 'taken_u', 'password': 'Password1'})
        r = client.post('/api/admin/auth-register', json={
            'username': 'taken_u', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        assert r.status_code == 409
        # 管理员注册后，平台不能再注册同名
        client.post('/api/admin/auth-register', json={
            'username': 'taken_a', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        r = client.post('/api/register', json={'username': 'taken_a', 'password': 'Password1'})
        assert r.status_code == 409
        assert client.get('/api/admin/auth-check-username?name=taken_u').get_json()['exists'] is True

    def test_history_kind_separated(self, client):
        """平台用户与管理员各自维护历史，回退互不干扰"""
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/register', json={'username': 'u_k', 'password': 'UserOld1'})
        client.post('/api/admin/auth-register', json={
            'username': 'a_k', 'password': 'AdminOld1', 'referral_code': 'NIDUS_Agent'})
        client.post('/api/admin/user-reset', json={
            'username': 'u_k', 'new_password': 'UserNew1'}, headers=H)
        client.post('/api/admin/user-reset', json={
            'username': 'a_k', 'new_password': 'AdminNew1'}, headers=H)
        users = client.get('/api/admin/accounts', headers=H).get_json()
        by_name = {u['username']: u for u in users}
        assert by_name['u_k']['rollback_count'] == 1
        assert by_name['a_k']['rollback_count'] == 1
        # 回退平台用户 → 恢复 UserOld1；管理员不受影响仍用 AdminNew1
        client.post('/api/admin/password-rollback', json={
            'username': 'u_k'}, headers=H)
        assert client.post('/api/login', json={
            'username': 'u_k', 'password': 'UserOld1'}).status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'a_k', 'password': 'AdminNew1'}).status_code == 200

    def test_admin_auth_pages_served(self, client):
        assert client.get('/admin-auth').status_code == 200
        assert client.get('/admin-panel').status_code == 200


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
