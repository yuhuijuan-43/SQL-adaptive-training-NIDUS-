"""API 安全测试：admin 鉴权、密码策略、匿名访问契约

当前语义（2026-09-03 融合「管理后台 + 加入我们」）：
- Bearer 一律使用 per-admin 会话 token（admin_session fixture），操作者身份由 token 解析；
- 管理后台统一入口：管理员账号密码登录 / 内推码注册，个人密钥体系已移除；
- 所有管理员可实时查询用户动态与系统日志；管理员动态仅主管理员可见。
"""
import db
from conftest import _register_admin, _make_primary
from repositories import get_progress


def _h(token):
    return {'Authorization': 'Bearer ' + token}


class TestAdminAuth:
    def test_stats_requires_token(self, client):
        assert client.get('/api/admin/stats').status_code == 401

    def test_users_requires_token(self, client):
        assert client.get('/api/admin/users').status_code == 401

    def test_wrong_token_rejected(self, client):
        r = client.get('/api/admin/stats', headers={'Authorization': 'Bearer wrong-token'})
        assert r.status_code == 401

    def test_correct_token_allowed(self, client, admin_session):
        r = client.get('/api/admin/stats', headers=_h(admin_session))
        assert r.status_code == 200
        assert 'total_users' in r.get_json()

        r = client.get('/api/admin/users', headers=_h(admin_session))
        assert r.status_code == 200

    def test_admin_login_password_only(self, client):
        """融合后管理后台登录：仅账号密码（个人密钥已移除）；登录返回 per-admin 会话 token"""
        _register_admin(client, 'gate_admin')
        # 账号密码正确 → 200，token 为随机会话 token，且可用于访问
        r = client.post('/api/admin/login', json={
            'username': 'gate_admin', 'password': 'Passw0rd1'})
        assert r.status_code == 200
        assert client.get('/api/admin/stats', headers=_h(r.get_json()['token'])).status_code == 200
        # 缺密码 → 400
        r = client.post('/api/admin/login', json={'username': 'gate_admin'})
        assert r.status_code == 400
        # 密码错 → 401
        r = client.post('/api/admin/login', json={
            'username': 'gate_admin', 'password': 'wrong'})
        assert r.status_code == 401
        # 用户名不存在 → 404（提示先注册）
        r = client.post('/api/admin/login', json={
            'username': 'nobody', 'password': 'Passw0rd1'})
        assert r.status_code == 404

    def test_admin_gate_redirects_to_unified_auth(self, client):
        """旧 /admin-gate 已融合为 /admin-auth 单一入口（302 跳转）"""
        r = client.get('/admin-gate')
        assert r.status_code == 302
        assert '/admin-auth' in r.headers['Location']
        r = client.get('/admin-auth')
        assert r.status_code == 200
        assert '管理员' in r.get_data(as_text=True) or 'admin' in r.get_data(as_text=True).lower()

    def test_user_progress_requires_token(self, client):
        assert client.get('/api/admin/user-progress?session_id=x').status_code == 401

    def test_user_progress_missing_param(self, client, admin_session):
        r = client.get('/api/admin/user-progress', headers=_h(admin_session))
        assert r.status_code == 400

    def test_user_progress_returns_answers(self, client, admin_session):
        sid = client.post('/api/register', json={'username': 'u_prog', 'password': 'password123'}).get_json()['session_id']
        client.post('/api/submit', json={
            'question_id': 1, 'answer': 'SELECT * FROM employees', 'session_id': sid})
        r = client.get('/api/admin/user-progress?session_id=' + sid, headers=_h(admin_session))
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
        # C2 重构：注册返回 per-admin 会话 token（随机的、可访问管理接口），绝不返回共享密钥
        token = r.get_json()['token']
        assert token and token != 'test-admin-token'
        assert client.get('/api/admin/stats', headers=_h(token)).status_code == 200

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
        alice_token = _register_admin(client, 'alice')
        _register_admin(client, 'bob')
        # C2 重构：当前身份由 Bearer token 解析，?me= 自报不再生效
        r = client.get('/api/admin/colleagues?me=bob', headers=_h(alice_token))
        assert r.status_code == 200
        d = r.get_json()
        assert d['me']['username'] == 'alice'          # 服务端按 token 识别身份
        names = [c['username'] for c in d['colleagues']]
        assert names == ['bob'] and 'alice' not in names

    def test_user_reset_requires_token(self, client):
        assert client.post('/api/admin/user-reset', json={
            'username': 'x', 'new_password': 'NewPass123'}).status_code == 401

    def test_user_reset_changes_password(self, client, admin_session):
        sid = client.post('/api/register', json={
            'username': 'stu_reset', 'password': 'Password1'}).get_json()['session_id']
        assert sid
        r = client.post('/api/admin/user-reset', json={
            'username': 'stu_reset', 'new_password': 'NewPass123'}, headers=_h(admin_session))
        assert r.status_code == 200
        assert client.post('/api/login', json={
            'username': 'stu_reset', 'password': 'NewPass123'}).status_code == 200
        assert client.post('/api/login', json={
            'username': 'stu_reset', 'password': 'Password1'}).status_code == 401

    def test_user_reset_unknown_user(self, client, admin_session):
        r = client.post('/api/admin/user-reset', json={
            'username': 'nobody', 'new_password': 'NewPass123'}, headers=_h(admin_session))
        assert r.status_code == 404

    def test_password_rollback_restores_old_password(self, client, admin_session):
        H = _h(admin_session)
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

    def test_password_rollback_max_three(self, client, admin_session):
        H = _h(admin_session)
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

    def test_password_rollback_requires_token(self, client):
        r = client.post('/api/admin/password-rollback', json={'username': 'x'})
        assert r.status_code == 401

    def test_password_rollback_no_history(self, client, admin_session):
        r = client.post('/api/admin/password-rollback', json={
            'username': 'nobody'}, headers=_h(admin_session))
        assert r.status_code == 409

    def test_users_list_excludes_admins(self, client, admin_session):
        """管理后台 /api/admin/users 仅平台用户，不含管理员信息"""
        H = _h(admin_session)
        client.post('/api/register', json={'username': 'learner1', 'password': 'Password1'})
        client.post('/api/admin/auth-register', json={
            'username': 'admin_sync', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        users = client.get('/api/admin/users', headers=H).get_json()
        names = [u['username'] for u in users]
        assert 'learner1' in names and 'admin_sync' not in names
        assert all('role' not in u for u in users)

    def test_admin_accounts_syncs_admins(self, client, admin_session):
        """管理员面板 /api/admin/accounts 含平台用户+管理员（role 区分）"""
        H = _h(admin_session)
        client.post('/api/register', json={'username': 'learner2', 'password': 'Password1'})
        client.post('/api/admin/auth-register', json={
            'username': 'admin_sync2', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        accounts = client.get('/api/admin/accounts', headers=H).get_json()
        by_name = {u['username']: u for u in accounts}
        assert by_name['learner2']['role'] == 'user'
        assert by_name['admin_sync2']['role'] == 'admin'
        assert 'last_active' in by_name['admin_sync2']

    def test_reset_admin_password_and_rollback(self, client, admin_session):
        """管理员密码重置/回退仅主管理员（C2：操作者身份由 Bearer token 解析，operator 自报无效）"""
        H = _h(admin_session)
        client.post('/api/admin/auth-register', json={
            'username': 'admin_rb', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        r = client.post('/api/admin/user-reset', json={
            'username': 'admin_rb', 'new_password': 'Passw0rd2'}, headers=H)
        assert r.status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'admin_rb', 'password': 'Passw0rd2'}).status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'admin_rb', 'password': 'Passw0rd1'}).status_code == 401
        # 回退（主管理员）→ 恢复原密码
        r = client.post('/api/admin/password-rollback', json={
            'username': 'admin_rb'}, headers=H)
        assert r.status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'admin_rb', 'password': 'Passw0rd1'}).status_code == 200

    def test_global_username_uniqueness(self, client):
        """平台用户与管理员全局用户名唯一（双向禁止同名）"""
        H = _h(_register_admin(client, 'uniqueness_admin'))
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

    def test_history_kind_separated(self, client, admin_session):
        """平台用户与管理员各自维护历史，回退互不干扰"""
        H = _h(admin_session)
        client.post('/api/register', json={'username': 'u_k', 'password': 'UserOld1'})
        client.post('/api/admin/auth-register', json={
            'username': 'a_k', 'password': 'AdminOld1', 'referral_code': 'NIDUS_Agent'})
        client.post('/api/admin/user-reset', json={
            'username': 'u_k', 'new_password': 'UserNew1'}, headers=H)
        # 管理员密码重置同样需要主管理员（admin_session 即主管理员）
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


class TestUsernameValidation:
    """注册用户名白名单（防管理页面存储型 XSS：用户名含 HTML/引号将被拒绝）"""

    def test_register_rejects_html_username(self, client):
        r = client.post('/api/register', json={
            'username': '<img src=x onerror=alert(1)>', 'password': 'Password1'})
        assert r.status_code == 400

    def test_register_rejects_quote_username(self, client):
        r = client.post('/api/register', json={
            'username': "x');alert(1);//", 'password': 'Password1'})
        assert r.status_code == 400

    def test_register_rejects_space_username(self, client):
        r = client.post('/api/register', json={
            'username': 'has space', 'password': 'Password1'})
        assert r.status_code == 400

    def test_register_accepts_normal_usernames(self, client):
        for name in ('user_123', '张三', 'User'):
            r = client.post('/api/register', json={'username': name, 'password': 'Password1'})
            assert r.status_code == 200, name

    def test_admin_register_rejects_html_username(self, client):
        r = client.post('/api/admin/auth-register', json={
            'username': '<img src=x onerror=alert(1)>', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        assert r.status_code == 400


class TestDiagnosticServerSide:
    """摸底提交服务端重算（L2）：客户端自报 is_correct 不被信任，按答案重算"""

    def _register(self, client, name='diag_u'):
        return client.post('/api/register', json={
            'username': name, 'password': 'Password1'}).get_json()['session_id']

    def test_mcq_and_fillin_recomputed(self, client):
        sid = self._register(client)
        # q1 选择题（标准答案 SELECT * FROM employees）、q2 填空题（SELECT name FROM employees）
        r = client.post('/api/diagnostic/complete', json={
            'session_id': sid,
            'results': [
                # 客户端谎报正确，但答案不匹配 → 服务端判错
                {'question_id': 1, 'answer': 'SELECT * FROM employees;', 'is_correct': True, 'skipped': False},
                # 客户端谎报错误，但答案正确 → 服务端判对
                {'question_id': 2, 'answer': 'SELECT name FROM employees', 'is_correct': False, 'skipped': False},
            ]})
        assert r.status_code == 200
        d = r.get_json()
        assert d['total'] == 2 and d['correct'] == 1 and d['skipped'] == 0
        assert d['accuracy'] == 50.0
        assert d['details'][0]['is_correct'] is False    # 谎报正确被纠正
        assert d['details'][1]['is_correct'] is True     # 谎报错误被纠正

    def test_fillin_wrong_sql_judged_false(self, client):
        sid = self._register(client, 'diag_u2')
        r = client.post('/api/diagnostic/complete', json={
            'session_id': sid,
            'results': [
                {'question_id': 2, 'answer': 'SELECT wrong FROM employees', 'is_correct': True, 'skipped': False},
            ]})
        d = r.get_json()
        assert d['correct'] == 0 and d['details'][0]['is_correct'] is False

    def test_skipped_not_counted_correct(self, client):
        sid = self._register(client, 'diag_u3')
        r = client.post('/api/diagnostic/complete', json={
            'session_id': sid,
            'results': [
                {'question_id': 1, 'answer': '', 'is_correct': True, 'skipped': True},
            ]})
        d = r.get_json()
        assert d['total'] == 1 and d['correct'] == 0 and d['skipped'] == 1


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


class TestSessionLifecycle:
    """会话生命周期（2026-08-12 新增）：登出立即失效、90 天不活跃过期、重新登录恢复"""

    def _register(self, client, name='u_sess'):
        return client.post('/api/register', json={
            'username': name, 'password': 'password123'}).get_json()['session_id']

    def test_logout_invalidates_session(self, client):
        sid = self._register(client, 'u_logout')
        assert client.get('/api/questions?session_id=' + sid).status_code == 200
        r = client.post('/api/logout', json={'session_id': sid})
        assert r.status_code == 200
        # 登出后同一 session_id 立即 401（服务端已标记过期）
        assert client.get('/api/questions?session_id=' + sid).status_code == 401

    def test_logout_idempotent_and_anonymous(self, client):
        # 未登录 / 未知 session_id / 缺参数：一律幂等 ok
        assert client.post('/api/logout', json={}).status_code == 200
        assert client.post('/api/logout', json={'session_id': 'ghost-sid'}).status_code == 200

    def test_login_restores_logged_out_session(self, client):
        """登出 → 重新登录 → 同一 session_id 恢复可用（last_active 刷新）"""
        sid = self._register(client, 'u_relogin')
        client.post('/api/logout', json={'session_id': sid})
        assert client.get('/api/questions?session_id=' + sid).status_code == 401
        r = client.post('/api/login', json={'username': 'u_relogin', 'password': 'password123'})
        assert r.status_code == 200 and r.get_json()['session_id'] == sid
        assert client.get('/api/questions?session_id=' + sid).status_code == 200

    def test_stale_session_expires(self, client):
        """last_active 距今超 90 天 → 会话过期 401"""
        sid = self._register(client, 'u_stale')
        conn = db.get_connection()
        conn.execute("UPDATE users SET last_active='2020-01-01 00:00:00' WHERE session_id=?", (sid,))
        conn.commit()
        assert client.get('/api/questions?session_id=' + sid).status_code == 401
        # 重新登录（刷新 last_active）后恢复
        r = client.post('/api/login', json={'username': 'u_stale', 'password': 'password123'})
        assert r.status_code == 200
        assert client.get('/api/questions?session_id=' + r.get_json()['session_id']).status_code == 200


class TestAdminUserDelete:
    """管理员删除用户：Bearer 鉴权 + confirm 显式确认 + 同步删除全部关联数据"""

    def test_delete_requires_token(self, client):
        r = client.post('/api/admin/user-delete', json={'username': 'x', 'confirm': True})
        assert r.status_code == 401

    def test_delete_requires_confirm(self, client, admin_session):
        H = _h(admin_session)
        client.post('/api/register', json={'username': 'del_u', 'password': 'Password1'})
        r = client.post('/api/admin/user-delete', json={'username': 'del_u'}, headers=H)
        assert r.status_code == 400

    def test_delete_removes_user_and_all_data(self, client, admin_session):
        H = _h(admin_session)
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

    def test_delete_admin_rejected(self, client, admin_session):
        H = _h(admin_session)
        client.post('/api/admin/auth-register', json={
            'username': 'del_admin', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        r = client.post('/api/admin/user-delete', json={
            'username': 'del_admin', 'confirm': True}, headers=H)
        assert r.status_code == 400
        # 管理员账号未被删除
        conn = db.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM admin_users WHERE username='del_admin'").fetchone()[0] == 1

    def test_delete_updates_admin_stats(self, client, admin_session):
        H = _h(admin_session)
        client.post('/api/register', json={'username': 'del_stat', 'password': 'Password1'})
        before = client.get('/api/admin/stats', headers=H).get_json()['total_users']
        client.post('/api/admin/user-delete', json={
            'username': 'del_stat', 'confirm': True}, headers=H)
        after = client.get('/api/admin/stats', headers=H).get_json()['total_users']
        assert after == before - 1
        names = [u['username'] for u in client.get('/api/admin/users', headers=H).get_json()]
        assert 'del_stat' not in names


class TestPrimaryAdmin:
    """主管理员体系：仅主管理员可改管理员密码/回退（C2：操作者身份由 Bearer token 解析）"""

    def test_colleagues_includes_me_and_primary(self, client, admin_session):
        """C2：me 由 Bearer token 解析；同事列表带 is_primary 标记"""
        H = _h(admin_session)
        client.post('/api/admin/auth-register', json={
            'username': 'p_a', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        client.post('/api/admin/auth-register', json={
            'username': 'p_b', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        _make_primary('p_a')
        r = client.get('/api/admin/colleagues', headers=H).get_json()
        assert r['me']['username'] == 'primary_admin' and r['me']['is_primary'] == 1
        names = {c['username']: c for c in r['colleagues']}
        assert 'primary_admin' not in names
        assert names['p_a']['is_primary'] == 1 and names['p_b']['is_primary'] == 0
        # 密钥体系已移除：任何视角的同事列表都不含 personal_key / key_disabled
        assert all('personal_key' not in c and 'key_disabled' not in c for c in r['colleagues'])

    def test_reset_admin_requires_primary_operator(self, client, admin_session):
        """仅主管理员可重置管理员密码；平台用户任意管理员可重置（operator 自报不再生效）"""
        H = _h(admin_session)
        _register_admin(client, 'boss_a')
        boss_b_token = _register_admin(client, 'boss_b')
        _make_primary('boss_a')
        # 非主管理员（boss_b）token 重置管理员密码 → 403
        r = client.post('/api/admin/user-reset', json={
            'username': 'boss_a', 'new_password': 'Passw0rd2'}, headers=_h(boss_b_token))
        assert r.status_code == 403
        # 主管理员（admin_session）重置 boss_a → 200，新密码生效
        r = client.post('/api/admin/user-reset', json={
            'username': 'boss_a', 'new_password': 'Passw0rd2'}, headers=H)
        assert r.status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'boss_a', 'password': 'Passw0rd2'}).status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'boss_a', 'password': 'Passw0rd1'}).status_code == 401
        # 平台用户重置不受主管理员限制（任意管理员即可）
        client.post('/api/register', json={'username': 'plain_u', 'password': 'Password1'})
        r = client.post('/api/admin/user-reset', json={
            'username': 'plain_u', 'new_password': 'PassNew1'}, headers=_h(boss_b_token))
        assert r.status_code == 200

    def test_rollback_admin_requires_primary_operator(self, client, admin_session):
        H = _h(admin_session)
        _register_admin(client, 'rb_a')
        _register_admin(client, 'rb_b')
        _make_primary('rb_a')
        # 先由主管理员重置 rb_b 产生一条历史
        assert client.post('/api/admin/user-reset', json={
            'username': 'rb_b', 'new_password': 'Passw0rd2'}, headers=H).status_code == 200
        # C2：管理员密码被重置后其会话已注销，rb_b 需用新密码重新登录拿新 token
        rb_b_token = client.post('/api/admin/auth-login', json={
            'username': 'rb_b', 'password': 'Passw0rd2'}).get_json()['token']
        # 非主管理员（rb_b 自己）回退管理员密码 → 403
        r = client.post('/api/admin/password-rollback', json={
            'username': 'rb_b'}, headers=_h(rb_b_token))
        assert r.status_code == 403
        # 主管理员回退 → 200，恢复旧密码
        r = client.post('/api/admin/password-rollback', json={
            'username': 'rb_b'}, headers=H)
        assert r.status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'rb_b', 'password': 'Passw0rd1'}).status_code == 200

    def test_colleagues_includes_rollback_count(self, client, admin_session):
        """同事列表带 rollback_count：重置过一次管理员密码后应为 1"""
        H = _h(admin_session)
        _register_admin(client, 'pa_rb')
        _register_admin(client, 'peer_rb')
        d = client.get('/api/admin/colleagues', headers=H).get_json()
        peer = next(c for c in d['colleagues'] if c['username'] == 'peer_rb')
        assert peer['rollback_count'] == 0
        client.post('/api/admin/user-reset', json={
            'username': 'peer_rb', 'new_password': 'Passw0rd2'}, headers=H)
        d = client.get('/api/admin/colleagues', headers=H).get_json()
        peer = next(c for c in d['colleagues'] if c['username'] == 'peer_rb')
        assert peer['rollback_count'] == 1


class TestAdminDelete:
    """主管理员删除管理员账号：仅主管理员可删，不能删自己/主管理员，同步清除密码历史"""

    def test_admin_delete_requires_token(self, client):
        r = client.post('/api/admin/admin-delete', json={
            'username': 'x', 'operator': 'y', 'confirm': True})
        assert r.status_code == 401

    def test_admin_delete_requires_confirm(self, client, admin_session):
        H = _h(admin_session)
        client.post('/api/admin/auth-register', json={
            'username': 'ad_c', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        r = client.post('/api/admin/admin-delete', json={'username': 'ad_c'}, headers=H)
        assert r.status_code == 400

    def test_admin_delete_requires_primary_operator(self, client, admin_session):
        """非主管理员操作 403；主管理员删除后该管理员无法再登录"""
        H = _h(admin_session)
        _register_admin(client, 'ad_pa')
        ad_nb_token = _register_admin(client, 'ad_nb')
        _make_primary('ad_pa')
        r = client.post('/api/admin/admin-delete', json={
            'username': 'ad_pa', 'confirm': True}, headers=_h(ad_nb_token))
        assert r.status_code == 403
        r = client.post('/api/admin/admin-delete', json={
            'username': 'ad_nb', 'confirm': True}, headers=H)
        assert r.status_code == 200
        assert client.post('/api/admin/auth-login', json={
            'username': 'ad_nb', 'password': 'Passw0rd1'}).status_code == 404

    def test_admin_delete_self_and_primary_rejected(self, client, admin_session):
        """主管理员不能删除自己；其他主管理员账号也不可删"""
        H = _h(admin_session)
        _register_admin(client, 'ad_pa2')
        _make_primary('ad_pa2')
        # 删除其他主管理员账号 → 400（主管理员账号不可删除）
        r = client.post('/api/admin/admin-delete', json={
            'username': 'ad_pa2', 'confirm': True}, headers=H)
        assert r.status_code == 400
        conn = db.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM admin_users WHERE username='ad_pa2'").fetchone()[0] == 1
        # 删除自己 → 400
        r = client.post('/api/admin/admin-delete', json={
            'username': 'primary_admin', 'confirm': True}, headers=H)
        assert r.status_code == 400

    def test_admin_delete_removes_history_and_colleagues(self, client, admin_session):
        """删除管理员：账号 + 密码历史同步清除，同事列表不再出现"""
        H = _h(admin_session)
        _register_admin(client, 'ad_pa3')
        _register_admin(client, 'ad_victim')
        client.post('/api/admin/user-reset', json={
            'username': 'ad_victim', 'new_password': 'Passw0rd2'}, headers=H)
        conn = db.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM user_password_history WHERE username='ad_victim' AND kind='admin'").fetchone()[0] == 1
        r = client.post('/api/admin/admin-delete', json={
            'username': 'ad_victim', 'confirm': True}, headers=H)
        assert r.status_code == 200
        conn = db.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM admin_users WHERE username='ad_victim'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM user_password_history WHERE username='ad_victim' AND kind='admin'").fetchone()[0] == 0
        d = client.get('/api/admin/colleagues', headers=H).get_json()
        assert 'ad_victim' not in [c['username'] for c in d['colleagues']]

    def test_admin_delete_not_found(self, client, admin_session):
        H = _h(admin_session)
        r = client.post('/api/admin/admin-delete', json={
            'username': 'ad_ghost', 'confirm': True}, headers=H)
        assert r.status_code == 404


class TestReferralCodes:
    """主管理员内推码管理：查看/新增/删除，与注册校验实时同步"""

    def test_referral_codes_requires_token(self, client):
        assert client.get('/api/admin/referral-codes').status_code == 401

    def test_referral_codes_requires_primary(self, client):
        sub_token = _register_admin(client, 'rc_sub')
        assert client.get('/api/admin/referral-codes', headers=_h(sub_token)).status_code == 403
        r = client.post('/api/admin/referral-add', json={
            'code': 'XX-CODE'}, headers=_h(sub_token))
        assert r.status_code == 403

    def test_referral_seeded_with_default(self, client, admin_session):
        """默认码 NIDUS_Agent 惰性种入，主管理员可查看"""
        codes = client.get('/api/admin/referral-codes', headers=_h(admin_session)).get_json()['codes']
        assert [c['code'] for c in codes] == ['NIDUS_Agent']

    def test_referral_add_and_register_sync(self, client, admin_session):
        H = _h(admin_session)
        # 新增 → 用新码注册成功
        r = client.post('/api/admin/referral-add', json={
            'code': 'TEAM-2026', 'note': '团队二期'}, headers=H)
        assert r.status_code == 200
        assert 'TEAM-2026' in [c['code'] for c in r.get_json()['codes']]
        r = client.post('/api/admin/auth-register', json={
            'username': 'rc_member', 'password': 'Passw0rd1', 'referral_code': 'TEAM-2026'})
        assert r.status_code == 200
        # 重复新增 → 409
        assert client.post('/api/admin/referral-add', json={
            'code': 'TEAM-2026'}, headers=H).status_code == 409
        # 删除 → 该码注册被拒（与系统识别同步）
        r = client.post('/api/admin/referral-delete', json={
            'code': 'TEAM-2026'}, headers=H)
        assert r.status_code == 200
        r = client.post('/api/admin/auth-register', json={
            'username': 'rc_member2', 'password': 'Passw0rd1', 'referral_code': 'TEAM-2026'})
        assert r.status_code == 403
        # 默认码不受影响
        assert client.post('/api/admin/auth-register', json={
            'username': 'rc_member3', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'}).status_code == 200

    def test_referral_delete_last_one_rejected(self, client, admin_session):
        H = _h(admin_session)
        # 只有一个默认码 → 删除被拒（保留注册入口）
        r = client.post('/api/admin/referral-delete', json={
            'code': 'NIDUS_Agent'}, headers=H)
        assert r.status_code == 409
        # 不存在 → 404
        assert client.post('/api/admin/referral-delete', json={
            'code': 'GHOST'}, headers=H).status_code == 404


class TestAdminMonitoring:
    """融合后的管理后台监控：用户动态/系统日志全管理员可见，管理员动态仅主管理员（定位与追责）"""

    def test_monitoring_endpoints_require_token(self, client):
        assert client.get('/api/admin/user-activity').status_code == 401
        assert client.get('/api/admin/system-logs').status_code == 401
        assert client.get('/api/admin/admin-activity').status_code == 401

    def test_user_activity_records_register_and_answer(self, client, admin_session):
        H = _h(admin_session)
        sid = client.post('/api/register', json={
            'username': 'mon_u', 'password': 'Password1'}).get_json()['session_id']
        client.post('/api/submit', json={
            'question_id': 1, 'answer': 'SELECT * FROM employees', 'session_id': sid})
        d = client.get('/api/admin/user-activity', headers=H).get_json()
        events = d['events']
        actions = [e['action'] for e in events]
        assert 'register' in actions and 'answer' in actions
        answer = next(e for e in events if e['action'] == 'answer')
        assert answer['actor'] == 'mon_u'
        # 按用户名筛选/锁定：只看该用户的动态
        d = client.get('/api/admin/user-activity?actor=mon_u', headers=H).get_json()
        only = d['events']
        assert only and all(e['actor'] == 'mon_u' for e in only)
        assert d['total'] >= len(only)
        d2 = client.get('/api/admin/user-activity?actor=ghost_no_one', headers=H).get_json()
        assert d2['events'] == [] and d2['total'] == 0

    def test_system_logs_and_user_activity_visible_to_sub_admin(self, client):
        sub_token = _register_admin(client, 'mon_sub')
        # 触发一次失败的管理员登录 → 系统日志应记录 warn
        assert client.post('/api/admin/auth-login', json={
            'username': 'mon_sub', 'password': 'WrongPass1'}).status_code == 401
        logs = client.get('/api/admin/system-logs', headers=_h(sub_token)).get_json()['logs']
        assert any(l['level'] == 'warn' and '登录失败' in l['message'] for l in logs)
        # 用户动态：普通管理员同样可见
        r = client.get('/api/admin/user-activity', headers=_h(sub_token))
        assert r.status_code == 200 and 'events' in r.get_json()
        # 管理员动态：普通管理员 403（仅主管理员）
        assert client.get('/api/admin/admin-activity', headers=_h(sub_token)).status_code == 403

    def test_admin_activity_primary_only_and_tracks_actions(self, client, admin_session):
        H = _h(admin_session)
        sub_token = _register_admin(client, 'mon_peer')
        # 主管理员操作一次平台用户重置密码 → 应进入管理员动态
        client.post('/api/register', json={'username': 'mon_stu', 'password': 'Password1'})
        assert client.post('/api/admin/user-reset', json={
            'username': 'mon_stu', 'new_password': 'PassNew123'}, headers=H).status_code == 200
        # 子管理员不能查看管理员动态
        assert client.get('/api/admin/admin-activity', headers=_h(sub_token)).status_code == 403
        # 主管理员可见全部管理员动态（含本人操作与注册记录）
        d = client.get('/api/admin/admin-activity', headers=H).get_json()
        events = d['events']
        assert events
        actors = {e['actor'] for e in events}
        assert 'primary_admin' in actors and 'mon_peer' in actors
        assert any(e['action'] == 'reset_user' and e['target'] == 'mon_stu' for e in events)
        # 按管理员用户名筛选/锁定：只看该管理员的动态
        d = client.get('/api/admin/admin-activity?actor=mon_peer', headers=H).get_json()
        only = d['events']
        assert only and all(e['actor'] == 'mon_peer' for e in only)
        assert d['total'] >= len(only)

    def test_user_activity_pagination_five_per_page(self, client, admin_session):
        """每页 5 条：产生 6 条用户动态后，第 1 页 5 条、第 2 页 1 条，总数正确"""
        H = _h(admin_session)
        sid = client.post('/api/register', json={
            'username': 'page_user', 'password': 'Password1'}).get_json()['session_id']
        client.post('/api/login', json={'username': 'page_user', 'password': 'Password1'})
        client.post('/api/logout', json={'session_id': sid})
        client.post('/api/login', json={'username': 'page_user', 'password': 'Password1'})
        client.post('/api/submit', json={
            'question_id': 1, 'answer': 'SELECT * FROM employees', 'session_id': sid})
        client.post('/api/submit', json={
            'question_id': 2, 'answer': 'SELECT name FROM employees', 'session_id': sid})
        d1 = client.get('/api/admin/user-activity?page=1&page_size=5', headers=H).get_json()
        d2 = client.get('/api/admin/user-activity?page=2&page_size=5', headers=H).get_json()
        assert d1['total'] >= 6 and d1['pages'] >= 2
        assert len(d1['events']) == 5 and len(d2['events']) >= 1
        # 两页 id 不重复（同一条记录不会同时出现在两页）
        ids1 = {e['id'] for e in d1['events']}
        ids2 = {e['id'] for e in d2['events']}
        assert not (ids1 & ids2)


class TestAdminRegistrationSecurity:
    """注册入口安全收敛（2026-09-03）：默认码仅引导期种入；可整体关闭管理员注册"""

    def test_default_code_not_reseeded_once_admins_exist(self, client, admin_session):
        # 已有管理员后清空内推码：默认码不得自动“复活”
        conn = db.get_connection()
        conn.execute('DELETE FROM referral_codes')
        conn.commit()
        from auth import get_referral_codes
        assert get_referral_codes() == []
        r = client.post('/api/admin/auth-register', json={
            'username': 'no_default_code', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        assert r.status_code == 403

    def test_registration_can_be_closed_by_env(self, client, admin_session, monkeypatch):
        monkeypatch.setenv('ADMIN_REGISTRATION_OPEN', '0')
        r = client.post('/api/admin/auth-register', json={
            'username': 'blocked_reg', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        assert r.status_code == 403
        assert '注册已关闭' in r.get_json()['error']
        # 已有管理员仍可正常登录
        assert client.post('/api/admin/auth-login', json={
            'username': 'primary_admin', 'password': 'Passw0rd1'}).status_code == 200

    def test_registration_status_endpoint(self, client, admin_session):
        d = client.get('/api/admin/registration-status').get_json()
        assert d['bootstrap'] is False
        assert d['open'] is True
