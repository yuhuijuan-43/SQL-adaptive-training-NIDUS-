import uuid, os, random

from flask import Flask, jsonify, redirect, request, send_from_directory
from flask_cors import CORS
from sql_judge import judge as judge_sql
from db import init_db, get_connection, close_db
from repositories import (get_all_questions, get_exam_questions, get_question_by_id,
    get_questions_by_node, get_question_node_id, save_answer, get_progress, get_graph,
    get_mastery, save_diagnostic_result, get_diagnostic_result,
    get_or_create_derived_question, get_derived_question_by_id,
    get_questions_by_node_and_type, get_node_id_for_question, is_mcq,
    get_diagnostic_questions, get_admin_stats, get_admin_users, get_progress_summary,
    reset_user_password, rollback_user_password)
from auth import (login_user, register_user, login_or_register, check_username_exists,
    _is_authenticated, register_admin, login_admin, check_admin_username_exists,
    get_admin_colleagues, REFERRAL_CODE)
from engine import init_journey, journey_next, get_journey_state, _get_unlocked_nodes
from seeding import seed_questions, seed_exam_questions, seed_knowledge_graph

app = Flask(__name__, static_folder=None)
# 同源部署（Flask 托管前端 + /api），仅放行本机来源；跨域仅影响浏览器，不影响正常访问
CORS(app, resources={r"/api/*": {"origins": [
    "http://localhost:5000", "http://127.0.0.1:5000", "http://localhost:3000", "http://127.0.0.1:3000",
    # file:// 直接打开 admin.html 时浏览器发送 Origin: null，需放行
    "null",
]}})
app.teardown_appcontext(close_db)

# ---- 全局错误处理 ----
@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": "请求参数有误"}), 400

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "请求的资源不存在"}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "请求方法不允许"}), 405

@app.errorhandler(500)
def internal_error(e):
    app.logger.error(f"Internal server error: {e}")
    return jsonify({"error": "服务器内部错误，请稍后重试"}), 500

# ---- 速率限制（安全降级：未安装flask-limiter时无操作） ----
# 只对写接口 / 登录注册 / admin 限流；读题、练习接口不限（避免误伤正常练习用户）
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        storage_uri="memory://",
    )
except ImportError:
    class _NoopLimiter:
        def limit(self, *args, **kwargs):
            def decorator(f): return f
            return decorator
    limiter = _NoopLimiter()

# ---- Admin 鉴权：Bearer token（可通过环境变量覆盖） ----
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', 'change-me-admin-token-2024')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')

def _check_admin_token():
    """校验 Authorization: Bearer <token> 头"""
    return request.headers.get('Authorization', '') == f'Bearer {ADMIN_TOKEN}'

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend')

# ---- 登录门槛：游客不允许读题/答题 ----
# 公开端点白名单：登录注册、用户名检查、知识图谱结构、背景装饰标题、admin（自行校验 token）
_PUBLIC_API_PATHS = {'/api/login', '/api/register', '/api/check-username',
                     '/api/graph', '/api/admin/login', '/api/admin/auth-register',
                     '/api/admin/auth-login', '/api/admin/auth-check-username',
                     '/api/admin/stats', '/api/admin/users', '/api/admin/user-progress',
                     '/api/admin/colleagues', '/api/admin/user-reset',
                     '/api/admin/password-rollback', '/api/admin/key'}

def _request_session_id():
    """从请求体 / 查询参数 / 路径参数中提取 session_id"""
    data = request.get_json(silent=True) or {}
    sid = data.get('session_id')
    if not sid:
        sid = request.args.get('session_id')
    if not sid and request.view_args:
        sid = request.view_args.get('session_id')
    return sid

@app.before_request
def login_required_for_question_apis():
    """除公开端点外，/api/* 均需注册用户的 session_id"""
    if not request.path.startswith('/api/'):
        return None
    if request.path in _PUBLIC_API_PATHS:
        return None
    sid = _request_session_id()
    if not sid or not _is_authenticated(sid):
        return jsonify({"error": "请先登录"}), 401
    return None

@app.route('/')
def index():
    # 门户入口页（玻璃拟态），「进入平台」按钮跳转 /index.html 练习前端
    return send_from_directory(FRONTEND_DIR, 'index_glass.html')

@app.route('/index.html')
def index_html():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/index_glass.html')
def index_glass_page():
    return send_from_directory(FRONTEND_DIR, 'index_glass.html')

@app.route('/about.html')
def about_page():
    return send_from_directory(FRONTEND_DIR, 'about.html')

@app.route('/about')
def about_page_alias():
    return redirect('/about.html', 301)

@app.route('/nidus_logo.png')
def nidus_logo():
    return send_from_directory(FRONTEND_DIR, 'nidus_logo.png')

@app.route('/login')
def login_page():
    # 玻璃拟态登录/注册页（原 login.html 已废弃）
    return send_from_directory(FRONTEND_DIR, 'login_glass.html')

@app.route('/login_glass.html')
def login_glass_page():
    return send_from_directory(FRONTEND_DIR, 'login_glass.html')

@app.route('/index_ngrok.html')
def index_ngrok():
    return redirect('/index.html', 301)

@app.route('/login_ngrok.html')
def login_ngrok():
    return redirect('/login', 301)

@app.route('/echarts.min.js')
def echarts_js():
    return send_from_directory(FRONTEND_DIR, 'echarts.min.js')


@app.route('/knowledge-map')
def knowledge_map_page():
    return send_from_directory(FRONTEND_DIR, 'knowledge_map.html')

@app.route('/diagnostic-page')
def diagnostic_page():
    return send_from_directory(FRONTEND_DIR, 'diagnostic.html')

@app.route('/basic-select')
def basic_select_page():
    return send_from_directory(FRONTEND_DIR, 'basic_select.html')

@app.route('/advanced-select')
def advanced_select_page():
    return send_from_directory(FRONTEND_DIR, 'advanced_select.html')

@app.route('/format-sample')
def format_sample_page():
    return send_from_directory(FRONTEND_DIR, 'format_sample.html')

# ---- 摸底小测 ----
@app.route('/api/diagnostic')
def get_diagnostic():
    """按知识图谱层级选取摸底题：level 0-1→easy, 2-3→medium, 4+→hard"""
    selected = get_diagnostic_questions()
    if not selected:
        return jsonify({"error": "题库为空"}), 404
    for q in selected:
        shuffle_options(q)
    return jsonify({"diagnostic": selected, "total": len(selected)})

@app.route('/api/diagnostic/complete', methods=['POST'])
def diagnostic_complete():
    data = request.get_json()
    session_id = data.get('session_id')
    results = data.get('results', [])
    if not session_id:
        return jsonify({"error": "缺少 session_id"}), 400
    total = len(results)
    answered = [r for r in results if not r.get('skipped')]
    correct = sum(1 for r in answered if r.get('is_correct'))
    skipped = sum(1 for r in results if r.get('skipped'))
    accuracy = round(correct / total * 100, 1) if total > 0 else 0
    # Store results
    diagnostic_data = {
        'total': total, 'correct': correct, 'skipped': skipped,
        'accuracy': accuracy, 'details': results
    }
    save_diagnostic_result(session_id, diagnostic_data)
    return jsonify(diagnostic_data)

@app.route('/api/diagnostic/result')
def diagnostic_result():
    session_id = request.args.get('session_id')
    if not session_id:
        return jsonify({"error": "缺少 session_id"}), 400
    result = get_diagnostic_result(session_id)
    if not result:
        return jsonify({"completed": False, "total": 0, "correct": 0, "skipped": 0, "accuracy": 0, "details": []})
    result['completed'] = True
    return jsonify(result)

# ---- 刷题 ----
def shuffle_options(question):
    """Shuffle options together with their explanations."""
    # If already a list (previously shuffled), just re-shuffle in-place
    if isinstance(question['options'], list):
        combined = list(zip(question['options'], question.get('option_explanations', [])))
        random.shuffle(combined)
        question['options'] = [c[0] for c in combined]
        question['option_explanations'] = [c[1] for c in combined] if question.get('option_explanations') else []
        return
    opts_raw = question['options'] if isinstance(question['options'], str) else ''
    exps_raw = question.get('option_explanations', '') or ''
    # Protect || before splitting by | (|| is SQL concat, not delimiter)
    opts = [o.replace('\x00', '||') for o in opts_raw.replace('||', '\x00').split('|') if o.strip()] if opts_raw else []
    exps = [e.replace('\x00', '||') for e in exps_raw.replace('||', '\x00').split('|') if e.strip()] if exps_raw else []
    combined = list(zip(opts, exps)) if exps and len(exps) == len(opts) else [(o, '') for o in opts]
    random.shuffle(combined)
    question['options'] = [c[0] for c in combined]
    question['option_explanations'] = [c[1] for c in combined] if exps else []

@app.route('/api/questions')
def list_questions():
    category = request.args.get('category')
    difficulty = request.args.get('difficulty')
    node = request.args.get('node')
    pool = request.args.get('pool', 'practice')  # 'practice' or 'exam'
    if pool == 'exam':
        questions = get_exam_questions(category, difficulty, node=node)
    else:
        questions = get_all_questions(category, difficulty, node=node)
    # 列表视图只返回轻量字段（详情、schema、data 等在 /api/questions/<id> 才给）
    summary = [{'id': q['id'], 'title': q['title'], 'category': q['category'],
                'difficulty': q['difficulty'], 'source': q.get('source',''),
                'pool': q.get('pool','practice'),
                'description': (q.get('description','') or '')[:120],
                'options': q.get('options','')} for q in questions]
    return jsonify({"questions": summary, "total": len(summary), "pool": pool})

@app.route('/api/questions/<int:qid>')
def get_question(qid):
    q = get_question_by_id(qid)
    if not q:
        return jsonify({"error": "题目不存在"}), 404
    shuffle_options(q)
    return jsonify(q)

# ---- 提交答案 ----
@app.route('/api/submit', methods=['POST'])
@limiter.limit("30 per minute")
def submit_answer():
    data = request.get_json()
    session_id = data.get('session_id', str(uuid.uuid4()))
    question_id = data.get('question_id')
    user_answer = data.get('answer', '').strip()
    save_qid = question_id
    # Try regular question first, then derived question
    q = get_question_by_id(question_id)
    is_derived = False
    if not q:
        dq = get_derived_question_by_id(question_id)
        if dq:
            q = dq
            is_derived = True
            save_qid = dq['prototype_id']
            del q['prototype_id']
        else:
            return jsonify({"error": "题目不存在"}), 404
    correct = q['correct_answer'].strip()
    # 真实执行判题：内存 SQLite 构建题目环境，比较用户 SQL 与标准答案的结果集
    is_correct, _rows, judge_error = judge_sql(
        user_answer, correct, q.get('table_schema'), q.get('initial_data'))
    save_answer(session_id, save_qid, user_answer, is_correct)
    resp = {
        "is_correct": is_correct,
        "correct_answer": correct,
        "explanation": q['explanation'],
        "session_id": session_id
    }
    if judge_error:
        resp['judge_error'] = judge_error
    return jsonify(resp)

# ---- 衍生题（举一反三）----
@app.route('/api/practice/derive', methods=['POST'])
def derive_question():
    """Create or retrieve a fill-in derived question from a MCQ prototype."""
    data = request.get_json()
    prototype_id = data.get('question_id')
    if not prototype_id:
        return jsonify({"error": "缺少 question_id"}), 400
    dq = get_or_create_derived_question(prototype_id)
    if not dq:
        return jsonify({"error": "原型题不存在或不是选择题"}), 400
    return jsonify({"derived_question": dq})

@app.route('/api/practice/recommend', methods=['POST'])
def practice_recommend():
    """After answering a derived question, recommend the next question.
    - If derived was correct → recommend a fill-in from same node
    - If derived was wrong → recommend a MCQ from same node
    """
    data = request.get_json()
    session_id = data.get('session_id')
    derived_qid = data.get('derived_question_id')
    was_correct = data.get('was_correct')
    if not session_id or not derived_qid or was_correct is None:
        return jsonify({"error": "缺少参数"}), 400
    dq = get_derived_question_by_id(derived_qid)
    if not dq:
        return jsonify({"error": "衍生题不存在"}), 400
    node_id = get_node_id_for_question(dq['prototype_id'])
    if not node_id:
        return jsonify({"error": "未找到知识点映射"}), 400
    recommend_fillin = bool(was_correct)
    rec = get_questions_by_node_and_type(node_id, session_id, is_mcq_type=not recommend_fillin, exclude_ids=[dq['prototype_id'], derived_qid])
    return jsonify({
        "recommended": rec is not None,
        "question": rec,
        "node_id": node_id,
        "reason": "已掌握该知识点，推荐同知识点填空题继续巩固" if recommend_fillin else "该知识点仍需练习，推荐同知识点选择题先巩固"
    })

# ---- 知识图谱 ----
@app.route('/api/graph')
def get_knowledge_graph():
    return jsonify(get_graph())

# ---- Journey 自适应模式 ----
@app.route('/api/journey/start', methods=['POST'])
def journey_start():
    data = request.get_json()
    session_id = data.get('session_id', str(uuid.uuid4()))
    diag = get_diagnostic_result(session_id)
    init_journey(session_id, diagnostic_data=diag)
    result = journey_next(session_id)
    if result.get('question'):
        shuffle_options(result['question'])
    return jsonify(result)

@app.route('/api/journey/next', methods=['POST'])
def journey_next_route():
    data = request.get_json()
    session_id = data.get('session_id')
    question_id = data.get('question_id')
    if question_id is not None:
        question_id = int(question_id)
    user_answer = data.get('answer', '').strip()
    duration = data.get('duration')
    if duration is not None:
        duration = float(duration)
    if not session_id:
        return jsonify({"error": "缺少 session_id"}), 400
    # grade answer
    is_correct = None
    if question_id and user_answer:
        q = get_question_by_id(question_id)
        if q:
            is_correct, _rows, _err = judge_sql(
                user_answer, q['correct_answer'], q.get('table_schema'), q.get('initial_data'))
            save_answer(session_id, question_id, user_answer, is_correct, duration or 0)
    result = journey_next(session_id, just_answered_qid=question_id, was_correct=is_correct, duration=duration)
    if result.get('question'):
        shuffle_options(result['question'])
    result['last_answer_correct'] = is_correct
    return jsonify(result)

@app.route('/api/journey/status', methods=['POST'])
def journey_status():
    data = request.get_json()
    session_id = data.get('session_id')
    if not session_id:
        return jsonify({"error": "缺少 session_id"}), 400
    state = get_journey_state(session_id)
    if not state:
        return jsonify({"error": "尚未开始 Journey"}), 404
    graph = get_graph()
    mastery = get_mastery(session_id)
    unlocked = _get_unlocked_nodes(session_id)
    progress = get_progress(session_id)
    total = len(progress)
    correct = sum(1 for p in progress if p['is_correct'])
    return jsonify({
        "state": state,
        "graph": graph,
        "mastery": mastery,
        "unlocked_nodes": unlocked,
        "total_answered": total,
        "total_correct": correct,
        "accuracy": round(correct / total * 100, 1) if total > 0 else 0
    })

@app.route('/api/journey/toggle_deep', methods=['POST'])
def toggle_deep():
    data = request.get_json()
    session_id = data.get('session_id')
    enabled = data.get('enabled', True)
    if not session_id:
        return jsonify({"error": "缺少 session_id"}), 400
    conn = get_connection()
    conn.execute('UPDATE journey_state SET deep_mode=? WHERE session_id=?', (1 if enabled else 0, session_id))
    conn.commit()
    return jsonify({"deep_mode": enabled, "session_id": session_id})

@app.route('/api/login', methods=['POST'])
@limiter.limit("8 per minute")
def login():
    """Login only — does NOT auto-register."""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username:
        return jsonify({"error": "请输入用户名"}), 400
    if not password:
        return jsonify({"error": "请输入密码"}), 400
    session_id, reason = login_user(username, password)
    if not session_id:
        if reason == 'not_found':
            return jsonify({"error": "用户不存在，请先注册"}), 404
        return jsonify({"error": "密码错误"}), 401
    return jsonify({"session_id": session_id, "username": username})

@app.route('/api/register', methods=['POST'])
@limiter.limit("5 per minute")
def register():
    """Register new user — username must be unique, password >= 6 chars."""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username:
        return jsonify({"error": "请输入用户名"}), 400
    if not password or len(password) < 8 or len(password) > 64:
        return jsonify({"error": "密码需为8-64个字符"}), 400
    session_id, reason = register_user(username, password)
    if not session_id:
        if reason == 'exists':
            return jsonify({"error": "用户名已存在，请直接登录"}), 409
        return jsonify({"error": "注册失败，请重试"}), 500
    return jsonify({"session_id": session_id, "username": username})

@app.route('/api/check-username')
def check_username():
    """检查用户名是否已被占用"""
    name = request.args.get('name', '').strip()
    if not name or len(name) < 2:
        return jsonify({"exists": False})
    exists = check_username_exists(name)
    return jsonify({"exists": exists})

@app.route('/api/progress/<session_id>')
def get_user_progress(session_id):
    progress = get_progress(session_id)
    total = len(progress)
    correct = sum(1 for p in progress if p['is_correct'])
    return jsonify({
        "session_id": session_id,
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
        "progress": progress
})
    
@app.route('/admin')
def admin_page():
    return send_from_directory(FRONTEND_DIR, 'admin.html')

@app.route('/admin-gate')
def admin_gate_page():
    """管理员登录门（用户名 + 统一密钥）"""
    return send_from_directory(FRONTEND_DIR, 'admin_gate.html')

@app.route('/admin-auth')
def admin_auth_page():
    """管理员账号登录/注册（内推码）"""
    return send_from_directory(FRONTEND_DIR, 'admin_auth.html')

@app.route('/admin-panel')
def admin_panel_page():
    """管理员自身页面（我的同事 + 平台用户密码管理）"""
    return send_from_directory(FRONTEND_DIR, 'admin_panel.html')

@app.route('/api/admin/login', methods=['POST'])
@limiter.limit("5 per minute")
def admin_login():
    """校验管理员用户名 + 统一密钥；通过后返回密钥供前端带进 admin.html"""
    import hmac
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    key = (data.get('key') or '').strip()
    # 常量时间比较，防时序攻击；统一返回模糊错误，不泄露哪一项不对
    if username == ADMIN_USERNAME and key and hmac.compare_digest(key, ADMIN_TOKEN):
        return jsonify({"ok": True, "token": ADMIN_TOKEN})
    return jsonify({"error": "用户名或密钥不正确"}), 401

@app.route('/api/admin/stats')
@limiter.limit("20 per minute")
def admin_stats():
    if not _check_admin_token():
        return jsonify({"error": "未授权，请提供管理员 Token"}), 401
    return jsonify(get_admin_stats())

@app.route('/api/admin/users')
@limiter.limit("20 per minute")
def admin_users():
    if not _check_admin_token():
        return jsonify({"error": "未授权，请提供管理员 Token"}), 401
    return jsonify(get_admin_users())

@app.route('/api/admin/user-progress')
@limiter.limit("30 per minute")
def admin_user_progress():
    """管理员查看指定用户的答题记录摘要（?session_id=xxx）"""
    if not _check_admin_token():
        return jsonify({"error": "未授权，请提供管理员 Token"}), 401
    session_id = request.args.get('session_id', '').strip()
    if not session_id:
        return jsonify({"error": "缺少 session_id"}), 400
    return jsonify({"session_id": session_id, "answers": get_progress_summary(session_id)})

# ---- 管理员账号体系（内推码注册 + 登录） ----
@app.route('/api/admin/auth-register', methods=['POST'])
@limiter.limit("5 per minute")
def admin_auth_register():
    """管理员注册：内推码 + 用户名唯一 + 密码规则与平台一致"""
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    referral = (data.get('referral_code') or '').strip()
    if not username:
        return jsonify({"error": "请输入用户名"}), 400
    if not password or len(password) < 8 or len(password) > 64:
        return jsonify({"error": "密码需为8-64个字符"}), 400
    if referral != REFERRAL_CODE:
        return jsonify({"error": "内推码不正确"}), 403
    ok, reason = register_admin(username, password, referral)
    if not ok:
        if reason == 'exists':
            return jsonify({"error": "用户名已存在"}), 409
        return jsonify({"error": "注册失败，请重试"}), 500
    return jsonify({"ok": True, "token": ADMIN_TOKEN, "username": username})

@app.route('/api/admin/auth-login', methods=['POST'])
@limiter.limit("8 per minute")
def admin_auth_login():
    """管理员账号登录"""
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username:
        return jsonify({"error": "请输入用户名"}), 400
    ok, reason = login_admin(username, password)
    if not ok:
        if reason == 'not_found':
            return jsonify({"error": "管理员不存在"}), 404
        return jsonify({"error": "密码错误"}), 401
    return jsonify({"ok": True, "token": ADMIN_TOKEN, "username": username})

@app.route('/api/admin/auth-check-username')
@limiter.limit("20 per minute")
def admin_auth_check_username():
    """管理员用户名占用预检（注册时防重复）"""
    name = request.args.get('name', '').strip()
    return jsonify({"exists": check_admin_username_exists(name) if name else False})

@app.route('/api/admin/colleagues')
@limiter.limit("30 per minute")
def admin_colleagues():
    """我的同事：其他管理员的用户名与最后上线时间（?me=排除自己）"""
    if not _check_admin_token():
        return jsonify({"error": "未授权，请提供管理员 Token"}), 401
    me = request.args.get('me', '').strip()
    return jsonify({"colleagues": get_admin_colleagues(exclude_username=me or None)})

def _check_double_verify(data):
    """双重验证：操作需携带统一管理员密钥（verify_key），常量时间比较"""
    import hmac
    verify_key = (data.get('verify_key') or '').strip()
    if not verify_key or not hmac.compare_digest(verify_key, ADMIN_TOKEN):
        return False
    return True

@app.route('/api/admin/user-reset', methods=['POST'])
@limiter.limit("10 per minute")
def admin_user_reset():
    """管理员重置密码（平台用户/管理员通用，需双重验证 verify_key）"""
    if not _check_admin_token():
        return jsonify({"error": "未授权，请提供管理员 Token"}), 401
    data = request.get_json(silent=True) or {}
    if not _check_double_verify(data):
        return jsonify({"error": "双重验证失败：请输入统一管理员密钥"}), 403
    username = (data.get('username') or '').strip()
    new_password = data.get('new_password') or ''
    if not username or not new_password:
        return jsonify({"error": "缺少参数"}), 400
    if len(new_password) < 8 or len(new_password) > 64:
        return jsonify({"error": "密码需为8-64个字符"}), 400
    ok, reason = reset_user_password(username, new_password)
    if not ok:
        return jsonify({"error": "用户不存在"}), 404
    return jsonify({"ok": True})

@app.route('/api/admin/key')
@limiter.limit("30 per minute")
def admin_key():
    """返回当前统一管理员密钥（面板展示/复制用；与 env 配置实时一致）"""
    if not _check_admin_token():
        return jsonify({"error": "未授权，请提供管理员 Token"}), 401
    return jsonify({"key": ADMIN_TOKEN})

@app.route('/api/admin/password-rollback', methods=['POST'])
@limiter.limit("10 per minute")
def admin_password_rollback():
    """回退密码到上一个版本（历史保留 3 条 → 最多回退 3 次；需双重验证 verify_key）"""
    if not _check_admin_token():
        return jsonify({"error": "未授权，请提供管理员 Token"}), 401
    data = request.get_json(silent=True) or {}
    if not _check_double_verify(data):
        return jsonify({"error": "双重验证失败：请输入统一管理员密钥"}), 403
    username = (data.get('username') or '').strip()
    if not username:
        return jsonify({"error": "缺少参数"}), 400
    ok, reason = rollback_user_password(username)
    if not ok:
        return jsonify({"error": "该账号没有可回退的历史密码（最多可回退 3 次）"}), 409
    return jsonify({"ok": True})

if __name__ == '__main__':
    init_db()
    seed_questions()
    seed_knowledge_graph()
    app.run(debug=True, port=5000)
