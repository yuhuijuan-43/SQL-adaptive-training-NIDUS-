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
        # 管理员密码重置需主管理员 operator（先置为主管理员）
        conn = db.get_connection()
        conn.execute("UPDATE admin_users SET is_primary=1 WHERE username='admin_rb'")
        conn.commit()
        r = client.post('/api/admin/user-reset', json={
            'username': 'admin_rb', 'new_password': 'Passw0rd2', 'operator': 'admin_rb'}, headers=H)
        assert r.status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'admin_rb', 'password': 'Passw0rd2'}).status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'admin_rb', 'password': 'Passw0rd1'}).status_code == 401
        # 回退（管理员同样需主管理员 operator）→ 恢复原密码
        r = client.post('/api/admin/password-rollback', json={
            'username': 'admin_rb', 'operator': 'admin_rb'}, headers=H)
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
        # 管理员密码重置需主管理员 operator
        conn = db.get_connection()
        conn.execute("UPDATE admin_users SET is_primary=1 WHERE username='a_k'")
        conn.commit()
        client.post('/api/admin/user-reset', json={
            'username': 'a_k', 'new_password': 'AdminNew1', 'operator': 'a_k'}, headers=H)
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


class TestAdminUserDelete:
    """管理员删除用户：Bearer 鉴权 + confirm 显式确认 + 同步删除全部关联数据"""

    def test_delete_requires_token(self, client):
        r = client.post('/api/admin/user-delete', json={'username': 'x', 'confirm': True})
        assert r.status_code == 401

    def test_delete_requires_confirm(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/register', json={'username': 'del_u', 'password': 'Password1'})
        r = client.post('/api/admin/user-delete', json={'username': 'del_u'}, headers=H)
        assert r.status_code == 400

    def test_delete_removes_user_and_all_data(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        sid = client.post('/api/register', json={
            'username': 'del_u2', 'password': 'Password1'}).get_json()['session_id']
        # 制造关联数据：答题记录 + 旅程状态 + 掌握度 + 密码历史
        client.post('/api/submit', json={
            'question_id': 1, 'answer': 'SELECT * FROM employees', 'session_id': sid})
        client.post('/api/journey/start', json={'session_id': sid})
        client.post('/api/admin/user-reset', json={
            'username': 'del_u2', 'new_password': 'PassNew123'}, headers=H)
        conn = db.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM user_password_history WHERE username='del_u2'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM user_progress WHERE session_id=?", (sid,)).fetchone()[0] == 1
        # 执行删除 → 200，全部关联数据同步消失
        r = client.post('/api/admin/user-delete', json={
            'username': 'del_u2', 'confirm': True}, headers=H)
        assert r.status_code == 200
        conn = db.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM users WHERE username='del_u2'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM user_progress WHERE session_id=?", (sid,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM user_mastery WHERE session_id=?", (sid,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM journey_state WHERE session_id=?", (sid,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM diagnostic_results WHERE session_id=?", (sid,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM user_password_history WHERE username='del_u2'").fetchone()[0] == 0
        # 删除后无法登录，再次删除 → 404
        assert client.post('/api/login', json={
            'username': 'del_u2', 'password': 'Password1'}).status_code == 404
        r = client.post('/api/admin/user-delete', json={
            'username': 'del_u2', 'confirm': True}, headers=H)
        assert r.status_code == 404

    def test_delete_admin_rejected(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'del_admin', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        r = client.post('/api/admin/user-delete', json={
            'username': 'del_admin', 'confirm': True}, headers=H)
        assert r.status_code == 400
        # 管理员账号未被删除
        conn = db.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM admin_users WHERE username='del_admin'").fetchone()[0] == 1

    def test_delete_updates_admin_stats(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/register', json={'username': 'del_stat', 'password': 'Password1'})
        before = client.get('/api/admin/stats', headers=H).get_json()['total_users']
        client.post('/api/admin/user-delete', json={
            'username': 'del_stat', 'confirm': True}, headers=H)
        after = client.get('/api/admin/stats', headers=H).get_json()['total_users']
        assert after == before - 1
        names = [u['username'] for u in client.get('/api/admin/users', headers=H).get_json()]
        assert 'del_stat' not in names


class TestPrimaryAdmin:
    """主管理员体系：Yuhuijuan 唯一主管理员，仅主管理员可改管理员密码"""

    def test_colleagues_includes_me_and_primary(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'p_a', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        client.post('/api/admin/auth-register', json={
            'username': 'p_b', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        conn = db.get_connection()
        conn.execute("UPDATE admin_users SET is_primary=1 WHERE username='p_a'")
        conn.commit()
        r = client.get('/api/admin/colleagues?me=p_a', headers=H).get_json()
        assert r['me'] == {'username': 'p_a', 'is_primary': 1}
        names = {c['username']: c for c in r['colleagues']}
        assert 'p_a' not in names and names['p_b']['is_primary'] == 0

    def test_reset_admin_requires_primary_operator(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'boss_a', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        client.post('/api/admin/auth-register', json={
            'username': 'boss_b', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        conn = db.get_connection()
        conn.execute("UPDATE admin_users SET is_primary=1 WHERE username='boss_a'")
        conn.commit()
        # 未声明 operator / 非主管理员操作 → 403
        r = client.post('/api/admin/user-reset', json={
            'username': 'boss_b', 'new_password': 'Passw0rd2'}, headers=H)
        assert r.status_code == 403
        r = client.post('/api/admin/user-reset', json={
            'username': 'boss_b', 'new_password': 'Passw0rd2', 'operator': 'boss_b'}, headers=H)
        assert r.status_code == 403
        # 主管理员（boss_a）重置 boss_b → 200，新密码生效
        r = client.post('/api/admin/user-reset', json={
            'username': 'boss_b', 'new_password': 'Passw0rd2', 'operator': 'boss_a'}, headers=H)
        assert r.status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'boss_b', 'password': 'Passw0rd2'}).status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'boss_b', 'password': 'Passw0rd1'}).status_code == 401
        # 平台用户重置不受主管理员限制（无 operator 也可）
        client.post('/api/register', json={'username': 'plain_u', 'password': 'Password1'})
        r = client.post('/api/admin/user-reset', json={
            'username': 'plain_u', 'new_password': 'PassNew1'}, headers=H)
        assert r.status_code == 200

    def test_rollback_admin_requires_primary_operator(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'rb_a', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        client.post('/api/admin/auth-register', json={
            'username': 'rb_b', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        conn = db.get_connection()
        conn.execute("UPDATE admin_users SET is_primary=1 WHERE username='rb_a'")
        conn.commit()
        client.post('/api/admin/user-reset', json={
            'username': 'rb_b', 'new_password': 'Passw0rd2', 'operator': 'rb_a'}, headers=H)
        # 非主管理员回退管理员密码 → 403
        r = client.post('/api/admin/password-rollback', json={'username': 'rb_b'}, headers=H)
        assert r.status_code == 403
        # 主管理员回退 → 200，恢复旧密码
        r = client.post('/api/admin/password-rollback', json={
            'username': 'rb_b', 'operator': 'rb_a'}, headers=H)
        assert r.status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'rb_b', 'password': 'Passw0rd1'}).status_code == 200

    def test_colleagues_includes_rollback_count(self, client):
        """同事列表带 rollback_count：重置过一次管理员密码后应为 1"""
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'pa_rb', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        client.post('/api/admin/auth-register', json={
            'username': 'peer_rb', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        conn = db.get_connection()
        conn.execute("UPDATE admin_users SET is_primary=1 WHERE username='pa_rb'")
        conn.commit()
        d = client.get('/api/admin/colleagues?me=pa_rb', headers=H).get_json()
        peer = next(c for c in d['colleagues'] if c['username'] == 'peer_rb')
        assert peer['rollback_count'] == 0
        client.post('/api/admin/user-reset', json={
            'username': 'peer_rb', 'new_password': 'Passw0rd2', 'operator': 'pa_rb'}, headers=H)
        d = client.get('/api/admin/colleagues?me=pa_rb', headers=H).get_json()
        peer = next(c for c in d['colleagues'] if c['username'] == 'peer_rb')
        assert peer['rollback_count'] == 1


class TestAdminDelete:
    """主管理员删除管理员账号：仅主管理员可删，不能删自己/主管理员，同步清除密码历史"""

    def test_admin_delete_requires_token(self, client):
        r = client.post('/api/admin/admin-delete', json={
            'username': 'x', 'operator': 'y', 'confirm': True})
        assert r.status_code == 401

    def test_admin_delete_requires_confirm(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'ad_c', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        r = client.post('/api/admin/admin-delete', json={
            'username': 'ad_c', 'operator': 'boss'}, headers=H)
        assert r.status_code == 400

    def test_admin_delete_requires_primary_operator(self, client):
        """非主管理员操作 403；主管理员删除后该管理员无法再登录"""
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'ad_pa', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        client.post('/api/admin/auth-register', json={
            'username': 'ad_nb', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        conn = db.get_connection()
        conn.execute("UPDATE admin_users SET is_primary=1 WHERE username='ad_pa'")
        conn.commit()
        r = client.post('/api/admin/admin-delete', json={
            'username': 'ad_nb', 'operator': 'ad_nb', 'confirm': True}, headers=H)
        assert r.status_code == 403
        r = client.post('/api/admin/admin-delete', json={
            'username': 'ad_nb', 'operator': 'ad_pa', 'confirm': True}, headers=H)
        assert r.status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'ad_nb', 'password': 'Passw0rd1'}).status_code == 404

    def test_admin_delete_self_and_primary_rejected(self, client):
        """主管理员不能删除自己（即主管理员账号）→ 400"""
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'ad_pa2', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        conn = db.get_connection()
        conn.execute("UPDATE admin_users SET is_primary=1 WHERE username='ad_pa2'")
        conn.commit()
        r = client.post('/api/admin/admin-delete', json={
            'username': 'ad_pa2', 'operator': 'ad_pa2', 'confirm': True}, headers=H)
        assert r.status_code == 400
        conn = db.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM admin_users WHERE username='ad_pa2'").fetchone()[0] == 1

    def test_admin_delete_removes_history_and_colleagues(self, client):
        """删除管理员：账号 + 密码历史同步清除，同事列表不再出现"""
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'ad_pa3', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        client.post('/api/admin/auth-register', json={
            'username': 'ad_victim', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        conn = db.get_connection()
        conn.execute("UPDATE admin_users SET is_primary=1 WHERE username='ad_pa3'")
        conn.commit()
        client.post('/api/admin/user-reset', json={
            'username': 'ad_victim', 'new_password': 'Passw0rd2', 'operator': 'ad_pa3'}, headers=H)
        conn = db.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM user_password_history WHERE username='ad_victim' AND kind='admin'").fetchone()[0] == 1
        r = client.post('/api/admin/admin-delete', json={
            'username': 'ad_victim', 'operator': 'ad_pa3', 'confirm': True}, headers=H)
        assert r.status_code == 200
        conn = db.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM admin_users WHERE username='ad_victim'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM user_password_history WHERE username='ad_victim' AND kind='admin'").fetchone()[0] == 0
        d = client.get('/api/admin/colleagues?me=ad_pa3', headers=H).get_json()
        assert 'ad_victim' not in [c['username'] for c in d['colleagues']]

    def test_admin_delete_not_found(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'ad_pa4', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        conn = db.get_connection()
        conn.execute("UPDATE admin_users SET is_primary=1 WHERE username='ad_pa4'")
        conn.commit()
        r = client.post('/api/admin/admin-delete', json={
            'username': 'ad_ghost', 'operator': 'ad_pa4', 'confirm': True}, headers=H)
        assert r.status_code == 404


class TestAdminKeyUpdate:
    """主管理员更换统一管理员密钥：新密钥立即对全部管理员（子管理员）生效"""

    def _make_primary(self, username):
        conn = db.get_connection()
        conn.execute("UPDATE admin_users SET is_primary=1 WHERE username=?", (username,))
        conn.commit()

    def test_key_update_requires_token(self, client):
        r = client.post('/api/admin/key-update', json={
            'operator': 'x', 'new_key': 'newkey-1234'})
        assert r.status_code == 401

    def test_key_update_requires_primary(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'ku_sub', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        r = client.post('/api/admin/key-update', json={
            'operator': 'ku_sub', 'new_key': 'newkey-1234'}, headers=H)
        assert r.status_code == 403

    def test_key_update_validation(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'ku_pa', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        self._make_primary('ku_pa')
        # 过短 / 与当前相同 → 400
        assert client.post('/api/admin/key-update', json={
            'operator': 'ku_pa', 'new_key': 'short'}, headers=H).status_code == 400
        assert client.post('/api/admin/key-update', json={
            'operator': 'ku_pa', 'new_key': 'test-admin-token'}, headers=H).status_code == 400

    def test_key_update_takes_effect_for_all_admins(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'ku_pa2', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        self._make_primary('ku_pa2')
        r = client.post('/api/admin/key-update', json={
            'operator': 'ku_pa2', 'new_key': 'brand-new-key-0001'}, headers=H)
        assert r.status_code == 200 and r.get_json()['key'] == 'brand-new-key-0001'
        # 新密钥对所有 Bearer 请求生效（子管理员视角）
        H2 = {'Authorization': 'Bearer brand-new-key-0001'}
        assert client.get('/api/admin/key', headers=H2).status_code == 200
        assert client.get('/api/admin/key', headers=H).status_code == 401   # 旧密钥失效
        # 管理后台登录门：第二重验证同步为新密钥
        r = client.post('/api/admin/login', json={
            'username': 'ku_pa2', 'password': 'Passw0rd1', 'key': 'brand-new-key-0001'})
        assert r.status_code == 200 and r.get_json()['token'] == 'brand-new-key-0001'
        # 新密钥注册管理员返回新 token
        r = client.post('/api/admin/auth-register', json={
            'username': 'ku_sub2', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        assert r.status_code == 200 and r.get_json()['token'] == 'brand-new-key-0001'


class TestReferralCodes:
    """主管理员内推码管理：查看/新增/删除，与注册校验实时同步"""

    def _make_primary(self, username):
        conn = db.get_connection()
        conn.execute("UPDATE admin_users SET is_primary=1 WHERE username=?", (username,))
        conn.commit()

    def test_referral_codes_requires_token(self, client):
        assert client.get('/api/admin/referral-codes?me=x').status_code == 401

    def test_referral_codes_requires_primary(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'rc_sub', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        assert client.get('/api/admin/referral-codes?me=rc_sub', headers=H).status_code == 403
        r = client.post('/api/admin/referral-add', json={
            'operator': 'rc_sub', 'code': 'XX-CODE'}, headers=H)
        assert r.status_code == 403

    def test_referral_seeded_with_default(self, client):
        """默认码 NIDUS_Agent 惰性种入，主管理员可查看"""
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'rc_pa', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        self._make_primary('rc_pa')
        codes = client.get('/api/admin/referral-codes?me=rc_pa', headers=H).get_json()['codes']
        assert [c['code'] for c in codes] == ['NIDUS_Agent']

    def test_referral_add_and_register_sync(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'rc_pa2', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        self._make_primary('rc_pa2')
        # 新增 → 用新码注册成功
        r = client.post('/api/admin/referral-add', json={
            'operator': 'rc_pa2', 'code': 'TEAM-2026', 'note': '团队二期'}, headers=H)
        assert r.status_code == 200
        assert 'TEAM-2026' in [c['code'] for c in r.get_json()['codes']]
        r = client.post('/api/admin/auth-register', json={
            'username': 'rc_member', 'password': 'Passw0rd1', 'referral_code': 'TEAM-2026'})
        assert r.status_code == 200
        # 重复新增 → 409
        assert client.post('/api/admin/referral-add', json={
            'operator': 'rc_pa2', 'code': 'TEAM-2026'}, headers=H).status_code == 409
        # 删除 → 该码注册被拒（与系统识别同步）
        r = client.post('/api/admin/referral-delete', json={
            'operator': 'rc_pa2', 'code': 'TEAM-2026'}, headers=H)
        assert r.status_code == 200
        r = client.post('/api/admin/auth-register', json={
            'username': 'rc_member2', 'password': 'Passw0rd1', 'referral_code': 'TEAM-2026'})
        assert r.status_code == 403
        # 默认码不受影响
        assert client.post('/api/admin/auth-register', json={
            'username': 'rc_member3', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'}).status_code == 200

    def test_referral_delete_last_one_rejected(self, client):
        H = {'Authorization': 'Bearer test-admin-token'}
        client.post('/api/admin/auth-register', json={
            'username': 'rc_pa3', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        self._make_primary('rc_pa3')
        # 只有一个默认码 → 删除被拒（保留注册入口）
        r = client.post('/api/admin/referral-delete', json={
            'operator': 'rc_pa3', 'code': 'NIDUS_Agent'}, headers=H)
        assert r.status_code == 409
        # 不存在 → 404
        assert client.post('/api/admin/referral-delete', json={
            'operator': 'rc_pa3', 'code': 'GHOST'}, headers=H).status_code == 404
