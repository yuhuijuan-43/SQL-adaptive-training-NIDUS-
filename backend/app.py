import json, uuid, os, random, secrets, hmac, sys, mimetypes, html, traceback

from functools import wraps
from urllib.parse import urlencode
from flask import Flask, jsonify, redirect, request, send_from_directory, session, g
from flask_cors import CORS
from sql_judge import judge as judge_sql
from db import init_db, get_connection, close_db
from repositories import (get_all_questions, get_exam_questions, get_question_by_id,
    get_exam_question_by_id, get_questions_by_node, get_question_node_id, save_answer, get_progress, get_graph,
    get_mastery, save_diagnostic_result, get_diagnostic_result,
    get_or_create_derived_question, get_derived_question_by_id,
    get_questions_by_node_and_type, get_node_id_for_question,
    get_diagnostic_questions, get_admin_stats, get_admin_users, get_admin_accounts,
    get_progress_summary, reset_user_password, rollback_user_password, delete_user,
    delete_admin, _account_kind)
from auth import (login_user, register_user, login_or_register, check_username_exists,
    _is_authenticated, register_admin, login_admin, check_admin_username_exists,
    get_admin_colleagues, get_admin_profile, admin_bootstrap_pending,
    get_referral_codes, add_referral_code,
    delete_referral_code, create_admin_session, validate_admin_token, is_primary_admin)
from logs import (log_user_event, log_admin_event, log_system,
    get_user_events, get_admin_events, get_system_logs,
    count_user_events, count_admin_events, count_system_logs, username_by_session)
import oauth   # 模块式 import：测试可 monkeypatch oauth.exchange_code 等内部函数
from engine import init_journey, journey_next, get_journey_state, compute_lights
from seeding import seed_questions, seed_exam_questions, seed_knowledge_graph

# 注册字体 MIME：字体预加载（preload font/woff2）与 @font-face 以正确类型返回
mimetypes.add_type('font/woff2', '.woff2')
mimetypes.add_type('font/ttf', '.ttf')

app = Flask(__name__, static_folder=None)
# GitHub OAuth state 用 Flask session cookie 签名；随机密钥重启即失效（进行中的授权重点一次即可自愈），
# 需跨重启稳定可设 FLASK_SECRET_KEY 环境变量
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
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
    log_system('error', '服务器内部错误（500）', detail=(traceback.format_exc() or str(e))[-2000:],
               source=request.path or 'app')
    return jsonify({"error": "服务器内部错误，请稍后重试"}), 500

@app.errorhandler(429)
def too_many_requests(e):
    """限流命中：返回 JSON 而非 flask-limiter 的纯文本，前端可解析并明确提示"""
    log_system('warn', '触发限流', detail=f'path={request.path}', source='rate-limit')
    return jsonify({"error": "操作过于频繁，请稍后再试"}), 429

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


def _user_rate_key():
    """用户接口按人计数：优先 session_id（已登录会话），其次请求体用户名（登录/注册），
    兜底客户端 IP。ngrok/局域网部署下所有请求同源，按 IP 计数会把全班误判为同一人"""
    data = request.get_json(silent=True) or {}
    sid = data.get('session_id') or request.args.get('session_id')
    if sid:
        return 'u:' + str(sid)
    name = (data.get('username') or '').strip()
    if name:
        return 'u:' + name
    return get_remote_address()


def _admin_rate_key():
    """管理接口按管理员计数：优先 Bearer token 解析出的管理员用户名（登录/注册前按请求体用户名），
    兜底客户端 IP。多位管理员共用面板时互不挤占限流额度"""
    admin = _admin_username()
    if admin:
        return 'a:' + admin
    data = request.get_json(silent=True) or {}
    name = (data.get('username') or '').strip()
    if name:
        return 'a:' + name
    return get_remote_address()

# ---- Admin 鉴权：Bearer 会话 token（C2 重构：token 绑定管理员身份，不再校验共享密钥） ----

def _admin_username():
    """从 Authorization: Bearer <token> 解析当前管理员用户名；无效/过期返回 None"""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    return validate_admin_token(auth[len('Bearer '):].strip())

def _require_admin():
    """校验管理会话，返回当前管理员用户名；未授权返回 None"""
    return _admin_username()

def require_admin(f):
    """管理接口鉴权装饰器：未授权统一返回 401；授权后管理员用户名写入 g.admin_username，
    替代各 handler 内重复的 if not _require_admin() 样板（2026-08-12）"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        admin = _require_admin()
        if not admin:
            return jsonify({"error": "未授权，请提供管理员 Token"}), 401
        g.admin_username = admin
        return f(*args, **kwargs)
    return wrapper

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend')

@app.route('/lib/<path:filename>')
def lib_assets(filename):
    """本地化前端依赖（Font Awesome / CodeMirror，2026-08-05 CDN 离线化）"""
    return send_from_directory(os.path.join(FRONTEND_DIR, 'lib'), filename)

# ---- 登录门槛：游客不允许读题/答题 ----
# 公开端点白名单：登录注册、用户名检查、知识图谱结构、背景装饰标题、admin（自行校验 token）
_PUBLIC_API_PATHS = {'/api/login', '/api/register', '/api/check-username', '/api/logout',
                     '/api/oauth/github', '/api/oauth/github/callback', '/api/oauth/github/check',
                     '/api/graph', '/api/admin/login', '/api/admin/auth-register',
                     '/api/admin/auth-login', '/api/admin/auth-check-username',
                     '/api/admin/registration-status',
                     '/api/admin/stats', '/api/admin/users', '/api/admin/accounts',
                     '/api/admin/user-progress', '/api/admin/colleagues',
                     '/api/admin/user-reset', '/api/admin/password-rollback',
                     '/api/admin/user-delete', '/api/admin/admin-delete',
                     '/api/admin/referral-codes', '/api/admin/user-activity',
                     '/api/admin/system-logs', '/api/admin/admin-activity',
                     '/api/admin/referral-add', '/api/admin/referral-delete'}

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
    """摸底小测提交：服务端重算每题对错，客户端自报的 is_correct 不再被信任。
    选择题按选项文本比对；填空题用 judge_sql 实判（答案由前端随提交携带）。"""
    data = request.get_json()
    session_id = data.get('session_id')
    results = data.get('results', [])
    if not session_id:
        return jsonify({"error": "缺少 session_id"}), 400
    recomputed = []
    for r in results:
        item = dict(r) if isinstance(r, dict) else {}
        qid = item.get('question_id')
        if not item.get('skipped') and isinstance(qid, int):
            q = get_question_by_id(qid)
            answer = (item.get('answer') or '').strip()
            if q and answer:
                if q.get('options') and str(q.get('options', '')).strip():
                    # 选择题：选项文本比对（双向 HTML 实体归一，与 /api/submit 一致）
                    item['is_correct'] = (html.unescape(answer).lower()
                                          == html.unescape(q['correct_answer'].strip()).lower())
                else:
                    item['is_correct'], _rows, _err = judge_sql(
                        answer, q['correct_answer'], q.get('table_schema'), q.get('initial_data'))
            else:
                item['is_correct'] = False
        recomputed.append(item)
    total = len(recomputed)
    answered = [r for r in recomputed if not r.get('skipped')]
    correct = sum(1 for r in answered if r.get('is_correct'))
    skipped = sum(1 for r in recomputed if r.get('skipped'))
    # 正确率只基于已作答的题（跳过的题不进分母，2026-08-12 修复）
    accuracy = round(correct / len(answered) * 100, 1) if answered else 0
    # Store results
    diagnostic_data = {
        'total': total, 'correct': correct, 'skipped': skipped,
        'accuracy': accuracy, 'details': recomputed
    }
    save_diagnostic_result(session_id, diagnostic_data)
    uname = username_by_session(session_id)
    if uname:
        log_user_event(uname, 'diagnostic', detail=f'正确 {correct} / 已作答 {len(answered)}')
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
    pool = request.args.get('pool', 'practice')  # exam → 真题库（两表 id 各自从 1 起）
    q = get_exam_question_by_id(qid) if pool == 'exam' else get_question_by_id(qid)
    if not q:
        return jsonify({"error": "题目不存在"}), 404
    return jsonify(q)

# ---- 提交答案 ----
@app.route('/api/submit', methods=['POST'])
@limiter.limit("30 per minute", key_func=_user_rate_key)
def submit_answer():
    data = request.get_json()
    session_id = data.get('session_id', str(uuid.uuid4()))
    question_id = data.get('question_id')
    user_answer = data.get('answer', '').strip()
    # 池：practice 查 questions 表，exam 查 exam_questions 表（两表 id 各自从 1 起，必须按池取）
    pool = data.get('pool', 'practice')
    save_qid = question_id
    # Try regular question first, then derived question
    q = get_exam_question_by_id(question_id) if pool == 'exam' else get_question_by_id(question_id)
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
    if q.get('options') and str(q.get('options', '')).strip():
        # 选择题：选项文本比对（概念题非 SQL，不执行 judge_sql）
        # 双向 HTML 实体归一：DB 选项存 &gt; 等实体，浏览器 textContent 已是 >，需统一后再比
        is_correct = html.unescape(user_answer.strip()).lower() == html.unescape(correct).lower()
        judge_error = None
    else:
        # 真实执行判题：内存 SQLite 构建题目环境，比较用户 SQL 与标准答案的结果集
        is_correct, _rows, judge_error = judge_sql(
            user_answer, correct, q.get('table_schema'), q.get('initial_data'))
    save_answer(session_id, save_qid, user_answer, is_correct, pool=pool)
    resp = {
        "is_correct": is_correct,
        "correct_answer": correct,
        "explanation": q['explanation'],
        "session_id": session_id
    }
    if judge_error:
        resp['judge_error'] = judge_error
        log_system('warn', 'SQL 判题异常', detail=f'question_id={question_id} pool={pool} 错误：{judge_error[:500]}',
                   source='sql-judge')
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
    uname = username_by_session(session_id)
    if uname:
        log_user_event(uname, 'journey_start')
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
    row_id = None
    if question_id and user_answer:
        q = get_question_by_id(question_id)
        if q:
            if q.get('options') and str(q.get('options', '')).strip():
                # 选择题：选项文本比对（双向 HTML 实体归一，浏览器 textContent 与 DB 实体统一后比较）
                is_correct = html.unescape(user_answer.strip()).lower() == html.unescape(q['correct_answer'].strip()).lower()
            else:
                is_correct, _rows, _err = judge_sql(
                    user_answer, q['correct_answer'], q.get('table_schema'), q.get('initial_data'),
                    q.get('required_points'))
            row_id = save_answer(session_id, question_id, user_answer, is_correct, duration or 0)
    result = journey_next(session_id, just_answered_qid=question_id, was_correct=is_correct,
                          duration=duration, just_answered_id=row_id)
    result['last_answer_correct'] = is_correct
    return jsonify(result)


@app.route('/api/journey/skip', methods=['POST'])
@limiter.limit("30 per minute", key_func=_user_rate_key)
def journey_skip_route():
    """跳过当前题：不写入答题记录（不计入正确/错误/不点亮），但本轮 plan 位置前进一格。
    跳过题在下一轮若仍答错仍可能再次出现；本轮不再回访。"""
    data = request.get_json()
    session_id = data.get('session_id')
    question_id = data.get('question_id')
    if question_id is not None:
        try:
            question_id = int(question_id)
        except (TypeError, ValueError):
            question_id = None
    if not session_id:
        return jsonify({"error": "缺少 session_id"}), 400
    # 仅校验当前题存在；不调用 save_answer，也不计入 stats/answers
    if question_id and not get_question_by_id(question_id):
        return jsonify({"error": "题目不存在"}), 404
    # was_correct=None → 不更新 total_correct/total_answered；just_answered_id=None → 不入 rs['answers']
    result = journey_next(session_id, just_answered_qid=question_id, was_correct=None,
                          duration=None, just_answered_id=None)
    result['last_answer_correct'] = None
    result['skipped'] = True
    return jsonify(result)

@app.route('/api/journey/status', methods=['POST'])
def journey_status():
    """旅程状态 + 图谱解锁数据。未开始时也返回 200（state=null），供图谱入口视图展示「初始 0 点亮」"""
    data = request.get_json()
    session_id = data.get('session_id')
    if not session_id:
        return jsonify({"error": "缺少 session_id"}), 400
    state = get_journey_state(session_id)
    graph = get_graph()
    mastery = get_mastery(session_id)
    # 点亮状态始终计算（未开始 journey 也显示规则3 跨池点亮）
    lights = compute_lights(session_id)
    round_state = json.loads(state['round_state']) if state and state.get('round_state') else None
    progress = get_progress(session_id) if state else []
    total = len(progress)
    correct = sum(1 for p in progress if p['is_correct'])
    return jsonify({
        "state": state,
        "graph": graph,
        "mastery": mastery,
        "lights": lights,
        "round": round_state,
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
@limiter.limit("8 per minute", key_func=_user_rate_key)
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
@limiter.limit("5 per minute", key_func=_user_rate_key)
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
        if reason == 'invalid_username':
            return jsonify({"error": "用户名需为2-32位字母/数字/下划线/中文"}), 400
        return jsonify({"error": "注册失败，请重试"}), 500
    return jsonify({"session_id": session_id, "username": username})

@app.route('/api/logout', methods=['POST'])
def logout():
    """登出：服务端把会话标记为过期（last_active 置为远古时间），此后该 session_id 一律 401。
    前端随后清除本地会话；幂等，未登录/已过期调用同样返回 ok"""
    sid = _request_session_id()
    if sid:
        conn = get_connection()
        conn.execute("UPDATE users SET last_active='2000-01-01 00:00:00' WHERE session_id=?", (sid,))
        conn.commit()
        uname = username_by_session(sid)
        if uname:
            log_user_event(uname, 'logout')
    return jsonify({"ok": True})

@app.route('/api/check-username')
def check_username():
    """检查用户名是否已被占用"""
    name = request.args.get('name', '').strip()
    if not name or len(name) < 2:
        return jsonify({"exists": False})
    exists = check_username_exists(name)
    return jsonify({"exists": exists})

# ---- GitHub OAuth 登录（2026-08-06）：授权码模式，state 存 Flask session 防 CSRF ----
@app.route('/api/oauth/github')
@limiter.limit("60 per minute")
def oauth_github():
    """发起 GitHub 授权：校验已配置 → 生成 state 存 session → 302 跳 GitHub"""
    cfg = oauth.get_oauth_config()
    if not cfg:
        return redirect('/login_glass.html?oauth_error=1')
    session['oauth_state'] = secrets.token_urlsafe(32)   # 每次重开流程都写新值，旧授权自动作废
    return redirect(oauth.build_authorize_url(cfg['github_client_id'], session['oauth_state']))

@app.route('/api/oauth/github/callback')
@limiter.limit("30 per minute")
def oauth_github_callback():
    """GitHub 授权回跳：校验 state（单次使用）→ 换 token → 拉用户 → 建档/复用 → 回登录页携带 session_id"""
    def fail():
        session.pop('oauth_state', None)   # 单次使用：失败/拒绝也销毁，防重放
        return redirect('/login_glass.html?oauth_error=1')

    if request.args.get('error'):          # 用户在 GitHub 授权页点了拒绝（access_denied）
        return fail()
    got = request.args.get('state')
    expected = session.get('oauth_state')
    if not got or not expected or not hmac.compare_digest(got, expected):
        return fail()                      # 缺 state / 无签发记录 / 不匹配（防 CSRF 与伪造回调）
    code = request.args.get('code')
    cfg = oauth.get_oauth_config()
    if not code or not cfg:
        return fail()
    try:
        token = oauth.exchange_code(code, cfg)
        gh = oauth.fetch_github_user(token)
        sid, uname = oauth.find_or_create_github_user(gh['id'], gh['login'])
        log_user_event(uname, 'login', detail='GitHub 登录')
    except Exception:
        return fail()                      # 网络异常 / GitHub 4xx / code 无效：统一转 oauth_error，绝不 500
    session.pop('oauth_state', None)       # 单次使用：成功即销
    return redirect('/login_glass.html?oauth=1&' + urlencode({'sid': sid, 'uname': uname}))

@app.route('/api/oauth/github/check')
def oauth_github_check():
    """GitHub 登录是否已配置（前端按钮据此决定跳转或提示未配置）"""
    return jsonify({"enabled": bool(oauth.get_oauth_config())})

@app.route('/api/progress/<session_id>')
def get_user_progress(session_id):
    pool = request.args.get('pool', 'practice')  # 练习/真题池进度各自独立（id 各自从 1 起）
    progress = get_progress(session_id, pool=pool)
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

@app.route('/admin.html')
def admin_page_alias():
    """旧链接兜底：/admin.html 别名"""
    return send_from_directory(FRONTEND_DIR, 'admin.html')

@app.route('/admin-gate')
def admin_gate_page():
    """旧入口兜底：/admin-gate 已与「加入我们」融合为单一 /admin-auth（移除密钥）"""
    return redirect('/admin-auth', 302)

@app.route('/admin-auth')
def admin_auth_page():
    """管理后台统一入口：管理员登录 + 内推码注册（并入原「加入我们」功能，移除个人密钥）"""
    return send_from_directory(FRONTEND_DIR, 'admin_auth.html')

@app.route('/admin-panel')
def admin_panel_page():
    """管理后台主面板：实时用户动态/系统日志/管理员动态 + 我的同事与团队管理"""
    return send_from_directory(FRONTEND_DIR, 'admin_panel.html')

@app.route('/api/admin/login', methods=['POST'])
@limiter.limit("5 per minute", key_func=_admin_rate_key)
def admin_login():
    """管理后台登录：管理员账号密码（登录自动更新最后上线时间）；成功签发 per-admin 会话 token"""
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({"error": "请输入用户名和密码"}), 400
    ok, reason = login_admin(username, password)
    if not ok:
        if reason == 'not_found':
            return jsonify({"error": "管理员不存在，请先凭内推码注册"}), 404
        return jsonify({"error": "账号或密码不正确"}), 401
    return jsonify({"ok": True, "token": create_admin_session(username), "username": username})

@app.route('/api/admin/stats')
@limiter.limit("120 per minute", key_func=_admin_rate_key)
@require_admin
def admin_stats():
    return jsonify(get_admin_stats())

@app.route('/api/admin/users')
@limiter.limit("120 per minute", key_func=_admin_rate_key)
@require_admin
def admin_users():
    """管理后台用户列表：仅平台用户（不含管理员信息）"""
    return jsonify(get_admin_users())

@app.route('/api/admin/accounts')
@limiter.limit("120 per minute", key_func=_admin_rate_key)
@require_admin
def admin_accounts():
    """管理员面板账号列表：平台用户 + 管理员（role 区分，供密码管理）"""
    return jsonify(get_admin_accounts())

@app.route('/api/admin/user-progress')
@limiter.limit("120 per minute", key_func=_admin_rate_key)
@require_admin
def admin_user_progress():
    """管理员查看指定用户的答题记录摘要（?session_id=xxx）"""
    session_id = request.args.get('session_id', '').strip()
    if not session_id:
        return jsonify({"error": "缺少 session_id"}), 400
    return jsonify({"session_id": session_id, "answers": get_progress_summary(session_id)})

# ---- 管理员账号体系（内推码注册 + 登录） ----
@app.route('/api/admin/auth-register', methods=['POST'])
@limiter.limit("5 per minute", key_func=_admin_rate_key)
def admin_auth_register():
    """管理员注册：内推码 + 用户名唯一 + 密码规则与平台一致"""
    if os.environ.get('ADMIN_REGISTRATION_OPEN', '1') == '0' and not admin_bootstrap_pending():
        return jsonify({"error": "管理员注册已关闭，请联系主管理员开通"}), 403
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    referral = (data.get('referral_code') or '').strip()
    if not username:
        return jsonify({"error": "请输入用户名"}), 400
    if not password or len(password) < 8 or len(password) > 64:
        return jsonify({"error": "密码需为8-64个字符"}), 400
    valid_codes = [c['code'] for c in get_referral_codes()]
    if referral not in valid_codes:
        return jsonify({"error": "内推码不正确"}), 403
    ok, reason = register_admin(username, password, referral)
    if not ok:
        if reason == 'exists':
            return jsonify({"error": "用户名已存在"}), 409
        if reason == 'invalid_username':
            return jsonify({"error": "用户名需为2-32位字母/数字/下划线/中文"}), 400
        return jsonify({"error": "注册失败，请重试"}), 500
    log_admin_event(username, 'register', detail=f'内推码：{referral}')
    return jsonify({"ok": True, "token": create_admin_session(username), "username": username})

@app.route('/api/admin/auth-login', methods=['POST'])
@limiter.limit("8 per minute", key_func=_admin_rate_key)
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
    return jsonify({"ok": True, "token": create_admin_session(username), "username": username})

@app.route('/api/admin/auth-check-username')
@limiter.limit("20 per minute", key_func=_admin_rate_key)
def admin_auth_check_username():
    """管理员用户名占用预检（注册时防重复）"""
    name = request.args.get('name', '').strip()
    return jsonify({"exists": check_admin_username_exists(name) if name else False})

@app.route('/api/admin/registration-status')
def admin_registration_status():
    """管理后台注册开关状态：环境变量 ADMIN_REGISTRATION_OPEN=0 关闭；
    尚无任何管理员（引导期）时始终开放，保证首个管理员可注册"""
    open_flag = os.environ.get('ADMIN_REGISTRATION_OPEN', '1') != '0'
    bootstrap = admin_bootstrap_pending()
    return jsonify({"open": bool(open_flag or bootstrap), "bootstrap": bootstrap})

@app.route('/api/admin/colleagues')
@limiter.limit("120 per minute", key_func=_admin_rate_key)
@require_admin
def admin_colleagues():
    """我的同事：其他管理员的用户名、最后上线时间与是否主管理员
    当前管理员身份由 Bearer 会话 token 解析（C2 重构：不再信任 ?me= 自报）"""
    admin = g.get('admin_username')
    return jsonify({
        "me": get_admin_profile(admin),
        "colleagues": get_admin_colleagues(exclude_username=admin)
    })

@app.route('/api/admin/user-reset', methods=['POST'])
@limiter.limit("60 per minute", key_func=_admin_rate_key)
@require_admin
def admin_user_reset():
    """管理员重置密码（Bearer 会话 token 鉴权）。平台用户：任意管理员可重置；管理员账号：仅主管理员可重置
    （防互相改密；操作者身份由 token 解析，C2 重构后不再信任自报 operator）"""
    admin = g.get('admin_username')
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    new_password = data.get('new_password') or ''
    if not username or not new_password:
        return jsonify({"error": "缺少参数"}), 400
    if len(new_password) < 8 or len(new_password) > 64:
        return jsonify({"error": "密码需为8-64个字符"}), 400
    if _account_kind(username) == 'admin' and not is_primary_admin(admin):
        return jsonify({"error": "仅主管理员可修改管理员密码"}), 403
    ok, reason = reset_user_password(username, new_password)
    if not ok:
        return jsonify({"error": "用户不存在"}), 404
    log_admin_event(admin, 'reset_admin' if _account_kind(username) == 'admin' else 'reset_user', target=username)
    return jsonify({"ok": True})

@app.route('/api/admin/user-activity')
@limiter.limit("300 per minute", key_func=_admin_rate_key)  # 自动刷新约每 6s（10/min），点击翻页为突发；300/min 给翻页与自动轮询留足余量
@require_admin
def admin_user_activity():
    """用户动态（实时，分页）：注册/登录/登出/答题/摸底/开启练习；所有管理员可见；
    ?page=&page_size=（默认 5 条/页）；?actor=用户名 时只看该用户的动态"""
    try:
        page = max(int(request.args.get('page', 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = min(max(int(request.args.get('page_size', 5)), 1), 200)
    except (TypeError, ValueError):
        page_size = 5
    actor = (request.args.get('actor') or '').strip()[:64]
    actor = actor or None
    total = count_user_events(actor) or 0
    pages = max(1, (total + page_size - 1) // page_size)
    return jsonify({
        "events": get_user_events(page_size, actor, (page - 1) * page_size),
        "total": total, "page": min(page, pages), "page_size": page_size, "pages": pages
    })

@app.route('/api/admin/system-logs')
@limiter.limit("300 per minute", key_func=_admin_rate_key)  # 同上：自动刷新 + 翻页突发
@require_admin
def admin_system_logs():
    """系统日志（实时，分页）：异常/判题错误/失败登录/限流等；所有管理员可见"""
    try:
        page = max(int(request.args.get('page', 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = min(max(int(request.args.get('page_size', 5)), 1), 200)
    except (TypeError, ValueError):
        page_size = 5
    level = request.args.get('level', '') or None
    if level not in ('info', 'warn', 'error'):
        level = None
    total = count_system_logs(level) or 0
    pages = max(1, (total + page_size - 1) // page_size)
    return jsonify({
        "logs": get_system_logs(page_size, level, (page - 1) * page_size),
        "total": total, "page": min(page, pages), "page_size": page_size, "pages": pages
    })

@app.route('/api/admin/admin-activity')
@limiter.limit("300 per minute", key_func=_admin_rate_key)  # 同上：自动刷新 + 翻页突发
@require_admin
def admin_admin_activity():
    """管理员动态（实时，分页）：登录/注册/改密/删除/内推码等；仅主管理员可见（定位与追责）；
    ?actor=管理员用户名 时只看该管理员的动态"""
    admin = g.get('admin_username')
    if not is_primary_admin(admin):
        return jsonify({"error": "仅主管理员可查看管理员动态"}), 403
    try:
        page = max(int(request.args.get('page', 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = min(max(int(request.args.get('page_size', 5)), 1), 200)
    except (TypeError, ValueError):
        page_size = 5
    actor = (request.args.get('actor') or '').strip()[:64]
    actor = actor or None
    total = count_admin_events(actor) or 0
    pages = max(1, (total + page_size - 1) // page_size)
    return jsonify({
        "events": get_admin_events(page_size, actor, (page - 1) * page_size),
        "total": total, "page": min(page, pages), "page_size": page_size, "pages": pages
    })

@app.route('/api/admin/referral-codes')
@limiter.limit("120 per minute", key_func=_admin_rate_key)
@require_admin
def admin_referral_codes():
    """主管理员查看全部内推码（操作者身份由 token 解析；与注册校验实时同步）"""
    admin = g.get('admin_username')
    if not is_primary_admin(admin):
        return jsonify({"error": "仅主管理员可查看内推码"}), 403
    return jsonify({"codes": get_referral_codes()})

@app.route('/api/admin/referral-add', methods=['POST'])
@limiter.limit("60 per minute", key_func=_admin_rate_key)
@require_admin
def admin_referral_add():
    """主管理员新增内推码（注册校验即时生效）"""
    admin = g.get('admin_username')
    if not is_primary_admin(admin):
        return jsonify({"error": "仅主管理员可新增内推码"}), 403
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    note = (data.get('note') or '').strip()
    ok, reason = add_referral_code(code, note)
    if not ok:
        if reason == 'exists':
            return jsonify({"error": "该内推码已存在"}), 409
        return jsonify({"error": "内推码需为1-32个字符"}), 400
    log_admin_event(admin, 'add_referral', target=code, detail=note)
    return jsonify({"ok": True, "codes": get_referral_codes()})

@app.route('/api/admin/referral-delete', methods=['POST'])
@limiter.limit("60 per minute", key_func=_admin_rate_key)
@require_admin
def admin_referral_delete():
    """主管理员删除内推码（最后一个不允许删除，保证注册入口存在）"""
    admin = g.get('admin_username')
    if not is_primary_admin(admin):
        return jsonify({"error": "仅主管理员可删除内推码"}), 403
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    if not code:
        return jsonify({"error": "缺少参数"}), 400
    ok, reason = delete_referral_code(code)
    if not ok:
        if reason == 'last_one':
            return jsonify({"error": "至少保留一个内推码"}), 409
        return jsonify({"error": "内推码不存在"}), 404
    log_admin_event(admin, 'delete_referral', target=code)
    return jsonify({"ok": True, "codes": get_referral_codes()})

@app.route('/api/admin/password-rollback', methods=['POST'])
@limiter.limit("60 per minute", key_func=_admin_rate_key)
@require_admin
def admin_password_rollback():
    """回退密码到上一个版本（历史保留 3 条 → 最多回退 3 次；Bearer 会话 token 鉴权）。
    管理员账号回退同样仅限主管理员（与 user-reset 一致）"""
    admin = g.get('admin_username')
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    if not username:
        return jsonify({"error": "缺少参数"}), 400
    if _account_kind(username) == 'admin' and not is_primary_admin(admin):
        return jsonify({"error": "仅主管理员可回退管理员密码"}), 403
    ok, reason = rollback_user_password(username)
    if not ok:
        return jsonify({"error": "该账号没有可回退的历史密码（最多可回退 3 次）"}), 409
    log_admin_event(admin, 'rollback_admin' if _account_kind(username) == 'admin' else 'rollback_user', target=username)
    return jsonify({"ok": True})

@app.route('/api/admin/user-delete', methods=['POST'])
@limiter.limit("60 per minute", key_func=_admin_rate_key)
@require_admin
def admin_user_delete():
    """删除平台用户（Bearer 会话 token 鉴权 + confirm 显式确认）。
    同步删除该用户的答题记录/掌握度/旅程/诊断结果/密码历史；管理员账号不允许删除"""
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    if not username:
        return jsonify({"error": "缺少参数"}), 400
    if not data.get('confirm'):
        return jsonify({"error": "删除操作需显式确认（confirm=true）"}), 400
    ok, reason = delete_user(username)
    if not ok:
        if reason == 'is_admin':
            return jsonify({"error": "管理员账号不允许删除"}), 400
        return jsonify({"error": "用户不存在"}), 404
    log_admin_event(g.get('admin_username'), 'delete_user', target=username)
    return jsonify({"ok": True})

@app.route('/api/admin/admin-delete', methods=['POST'])
@limiter.limit("60 per minute", key_func=_admin_rate_key)
@require_admin
def admin_admin_delete():
    """删除管理员账号（Bearer 会话 token 鉴权 + confirm 显式确认 + 仅主管理员可删其他管理员）。
    操作者身份由 token 解析（C2 重构）；同步删除该管理员的密码修改历史与会话；删除后其无法再登录"""
    admin = g.get('admin_username')
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    if not username:
        return jsonify({"error": "缺少参数"}), 400
    if not data.get('confirm'):
        return jsonify({"error": "删除操作需显式确认（confirm=true）"}), 400
    ok, reason = delete_admin(username, admin)
    if not ok:
        if reason == 'not_primary':
            return jsonify({"error": "仅主管理员可删除管理员账号"}), 403
        if reason == 'self':
            return jsonify({"error": "不能删除自己的账号"}), 400
        if reason == 'is_primary':
            return jsonify({"error": "主管理员账号不可删除"}), 400
        return jsonify({"error": "管理员不存在"}), 404
    log_admin_event(admin, 'delete_admin', target=username)
    return jsonify({"ok": True})

if __name__ == '__main__':
    init_db()
    from maintenance import startup_maintenance
    startup_maintenance()   # 启动治理：清理过期管理员会话等（静默失败）
    from backup import backup_database
    backup_database(tag='startup')
    seed_questions()
    seed_exam_questions()   # 与 run.py 一致：python app.py 直跑时真题库同样播种
    seed_knowledge_graph()
    # 本地调试用 Werkzeug 开发服务器（FLASK_DEBUG=1，含热重载；调试器在暴露网络环境可致 RCE，仅限本机）
    if os.environ.get('FLASK_DEBUG') == '1':
        app.run(debug=True, port=5000)
        sys.exit(0)
    # 正式运行用 waitress 生产级服务：多线程 + 高连接上限，课堂多人同时涌入也不瘫痪
    # （Windows 下 gunicorn 不可用，waitress 是正解；多进程跑 SQLite 反而增加写锁争用，故单进程多线程）
    try:
        from waitress import serve
    except ImportError:
        sys.exit('waitress 未安装：请先执行 pip install -r requirements.txt 后重试')
    serve(app, host='0.0.0.0', port=5000, threads=16, connection_limit=512)
