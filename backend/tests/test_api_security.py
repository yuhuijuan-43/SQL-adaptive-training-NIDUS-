"""API 安全测试：admin 鉴权、密码策略、匿名访问契约

C2 重构后语义：Bearer 一律使用 per-admin 会话 token（admin_session fixture），
不再使用旧共享密钥；操作者身份由 token 解析，请求体里的 operator / ?me= 不再生效。
一人一钥（C3）：登录门第二重验证为各管理员个人密钥；主管理员可查看/停用/重置同事密钥。
"""
import db
from conftest import _register_admin, _make_primary, _get_admin_key
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

    def test_admin_login_double_verify(self, client):
        """管理后台登录双重验证：管理员账号密码 + 个人密钥（一人一钥）；登录返回 per-admin 会话 token"""
        _register_admin(client, 'gate_admin')
        key = _get_admin_key('gate_admin')
        # 全对 → 200，token 为随机会话 token（不是密钥本身），且可用于访问
        r = client.post('/api/admin/login', json={
            'username': 'gate_admin', 'password': 'Passw0rd1', 'key': key})
        assert r.status_code == 200
        assert r.get_json()['token'] != key
        assert client.get('/api/admin/stats', headers=_h(r.get_json()['token'])).status_code == 200
        # 密码错 → 401
        r = client.post('/api/admin/login', json={
            'username': 'gate_admin', 'password': 'wrong', 'key': key})
        assert r.status_code == 401
        # 密钥错（他人密钥/任意错误值）→ 401
        r = client.post('/api/admin/login', json={
            'username': 'gate_admin', 'password': 'Passw0rd1', 'key': 'wrong'})
        assert r.status_code == 401
        # 缺密钥 → 401
        r = client.post('/api/admin/login', json={
            'username': 'gate_admin', 'password': 'Passw0rd1'})
        assert r.status_code == 401
        # 用户名不存在 → 404（提示先注册）
        r = client.post('/api/admin/login', json={
            'username': 'nobody', 'password': 'Passw0rd1', 'key': key})
        assert r.status_code == 404

    def test_admin_gate_page_served(self, client):
        r = client.get('/admin-gate')
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

    def test_admin_key_requires_token(self, client):
        assert client.get('/api/admin/key').status_code == 401

    def test_admin_key_returns_own_key(self, client, admin_session):
        """一人一钥：/api/admin/key 返回的是该管理员自己的个人密钥（= DB personal_key）"""
        r = client.get('/api/admin/key', headers=_h(admin_session))
        assert r.status_code == 200
        assert r.get_json()['key'] == _get_admin_key('primary_admin')
        assert r.get_json()['key_disabled'] is False

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
        # 一人一钥：主管理员视角同事列表附带个人密钥与停用标记（监控）
        assert names['p_a']['personal_key'] and names['p_a']['key_disabled'] == 0
        assert names['p_b']['personal_key'] and names['p_b']['key_disabled'] == 0

    def test_colleagues_keys_only_visible_to_primary(self, client, admin_session):
        """一人一钥：子管理员（非主管理员）的同事列表不附带他人密钥"""
        sub_token = _register_admin(client, 'key_peek')
        client.post('/api/admin/auth-register', json={
            'username': 'key_peer', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        r = client.get('/api/admin/colleagues', headers=_h(sub_token)).get_json()
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


class TestAdminKeyUpdate:
    """一人一钥：更换个人密钥为自助操作（每位管理员可更换自己的密钥，无需主管理员）；
    更换后本人全部会话注销（含当前），需重新登录"""

    def test_key_update_requires_token(self, client):
        r = client.post('/api/admin/key-update', json={
            'new_key': 'newkey-1234'})
        assert r.status_code == 401

    def test_key_update_self_service(self, client):
        """任意管理员（含子管理员）可更换本人密钥"""
        sub_token = _register_admin(client, 'ku_sub')
        r = client.post('/api/admin/key-update', json={
            'new_key': 'newkey-1234'}, headers=_h(sub_token))
        assert r.status_code == 200 and r.get_json()['key'] == 'newkey-1234'
        assert _get_admin_key('ku_sub') == 'newkey-1234'

    def test_key_update_validation(self, client, admin_session):
        H = _h(admin_session)
        # 过短 / 与当前相同 → 400
        assert client.post('/api/admin/key-update', json={
            'new_key': 'short'}, headers=H).status_code == 400
        assert client.post('/api/admin/key-update', json={
            'new_key': _get_admin_key('primary_admin')}, headers=H).status_code == 400

    def test_key_update_revokes_own_sessions(self, client, admin_session):
        """更换密钥后本人全部会话失效（含操作者自身）；新密钥可重新登录"""
        H = _h(admin_session)
        old_key = _get_admin_key('primary_admin')
        r = client.post('/api/admin/key-update', json={
            'new_key': 'brand-new-key-0001'}, headers=H)
        assert r.status_code == 200 and r.get_json()['key'] == 'brand-new-key-0001'
        # 旧会话失效、旧密钥登录被拒
        assert client.get('/api/admin/key', headers=H).status_code == 401
        assert client.post('/api/admin/login', json={
            'username': 'primary_admin', 'password': 'Passw0rd1', 'key': old_key}).status_code == 401
        # 新密钥重新登录 → 新随机会话可访问，且 /api/admin/key 返回新密钥
        r = client.post('/api/admin/login', json={
            'username': 'primary_admin', 'password': 'Passw0rd1', 'key': 'brand-new-key-0001'})
        assert r.status_code == 200
        new_token = r.get_json()['token']
        assert new_token and new_token != 'brand-new-key-0001'
        assert client.get('/api/admin/key', headers=_h(new_token)).get_json()['key'] == 'brand-new-key-0001'
        # 新注册的管理员仍拿到随机会话 token，可访问管理接口
        r = client.post('/api/admin/auth-register', json={
            'username': 'ku_sub2', 'password': 'Passw0rd1', 'referral_code': 'NIDUS_Agent'})
        assert r.status_code == 200 and r.get_json()['token']
        assert client.get('/api/admin/stats', headers=_h(r.get_json()['token'])).status_code == 200

    def test_key_update_blocked_when_disabled(self, client, admin_session):
        """密钥被停用时该管理员会话已注销：旧 token 调用任何接口（含 key-update）一律 401"""
        H = _h(admin_session)
        sub_token = _register_admin(client, 'ku_locked')
        client.post('/api/admin/key-toggle', json={
            'username': 'ku_locked', 'disabled': True}, headers=H)
        assert client.post('/api/admin/key-update', json={
            'new_key': 'newkey-1234'}, headers=_h(sub_token)).status_code == 401


class TestAdminKeyControl:
    """主管理员风险管控：停用/启用/重置同事的个人密钥（一人一钥）"""

    def test_toggle_and_reset_require_token(self, client):
        assert client.post('/api/admin/key-toggle', json={
            'username': 'x', 'disabled': True}).status_code == 401
        assert client.post('/api/admin/key-reset', json={
            'username': 'x'}).status_code == 401

    def test_toggle_and_reset_require_primary(self, client):
        sub_token = _register_admin(client, 'kc_sub')
        assert client.post('/api/admin/key-toggle', json={
            'username': 'any', 'disabled': True}, headers=_h(sub_token)).status_code == 403
        assert client.post('/api/admin/key-reset', json={
            'username': 'any'}, headers=_h(sub_token)).status_code == 403

    def test_cannot_operate_on_self(self, client, admin_session):
        """主管理员不能停用/重置自己的密钥（自身密钥走自助更换）"""
        H = _h(admin_session)
        assert client.post('/api/admin/key-toggle', json={
            'username': 'primary_admin', 'disabled': True}, headers=H).status_code == 400
        assert client.post('/api/admin/key-reset', json={
            'username': 'primary_admin'}, headers=H).status_code == 400

    def test_disable_kills_sessions_and_blocks_login(self, client, admin_session):
        """停用 = 立即注销该管理员全部会话（强制下线）+ gate 与账号登录均被拒绝（防绕过）"""
        H = _h(admin_session)
        sub_token = _register_admin(client, 'kc_sub')
        # 停用前：子管理员可正常访问
        assert client.get('/api/admin/stats', headers=_h(sub_token)).status_code == 200
        r = client.post('/api/admin/key-toggle', json={
            'username': 'kc_sub', 'disabled': True}, headers=H)
        assert r.status_code == 200 and r.get_json()['key_disabled'] is True
        # 旧会话立即失效（强制下线）
        assert client.get('/api/admin/stats', headers=_h(sub_token)).status_code == 401
        # gate 登录（个人密钥）被拒 403
        r = client.post('/api/admin/login', json={
            'username': 'kc_sub', 'password': 'Passw0rd1', 'key': _get_admin_key('kc_sub')})
        assert r.status_code == 403
        # 账号登录（免密钥入口）同样被拒 403
        r = client.post('/api/admin/auth-login', json={
            'username': 'kc_sub', 'password': 'Passw0rd1'})
        assert r.status_code == 403

    def test_enable_restores_login(self, client, admin_session):
        H = _h(admin_session)
        _register_admin(client, 'kc_sub')
        client.post('/api/admin/key-toggle', json={
            'username': 'kc_sub', 'disabled': True}, headers=H)
        r = client.post('/api/admin/key-toggle', json={
            'username': 'kc_sub', 'disabled': False}, headers=H)
        assert r.status_code == 200 and r.get_json()['key_disabled'] is False
        r = client.post('/api/admin/login', json={
            'username': 'kc_sub', 'password': 'Passw0rd1', 'key': _get_admin_key('kc_sub')})
        assert r.status_code == 200

    def test_toggle_unknown_admin(self, client, admin_session):
        H = _h(admin_session)
        assert client.post('/api/admin/key-toggle', json={
            'username': 'ghost', 'disabled': True}, headers=H).status_code == 404
        assert client.post('/api/admin/key-reset', json={
            'username': 'ghost'}, headers=H).status_code == 404

    def test_reset_generates_new_key_and_revokes_sessions(self, client, admin_session):
        """重置 = 生成新密钥（旧密钥立即失效）+ 注销全部会话 + 自动解除停用"""
        H = _h(admin_session)
        sub_token = _register_admin(client, 'kc_sub')
        old_key = _get_admin_key('kc_sub')
        # 先停用再重置：重置后应自动恢复可用
        client.post('/api/admin/key-toggle', json={
            'username': 'kc_sub', 'disabled': True}, headers=H)
        r = client.post('/api/admin/key-reset', json={'username': 'kc_sub'}, headers=H)
        assert r.status_code == 200
        new_key = r.get_json()['key']
        assert new_key and new_key != old_key
        assert _get_admin_key('kc_sub') == new_key
        # 旧会话失效、旧密钥失效
        assert client.get('/api/admin/stats', headers=_h(sub_token)).status_code == 401
        assert client.post('/api/admin/login', json={
            'username': 'kc_sub', 'password': 'Passw0rd1', 'key': old_key}).status_code == 401
        # 新密钥可登录（已自动解除停用）
        r = client.post('/api/admin/login', json={
            'username': 'kc_sub', 'password': 'Passw0rd1', 'key': new_key})
        assert r.status_code == 200


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
