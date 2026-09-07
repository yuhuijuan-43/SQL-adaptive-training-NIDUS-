"""Journey 自适应引擎（2026-08 图谱点亮版）：双循环出题 + 叶/枝/根三级点亮

核心规则（产品需求）：
- 出题：枝节点不放回（固定图谱顺序）→ 叶节点不放回 → 每叶按“选择先行、填空随后”顺序推出该叶全部不重复题目
- 题池不足时只出已有不重复题（不再循环复用，避免同一题重复出现）；某类题池为空则该叶仅推另一类
- 跨轮去重：新一轮构建时剔除本会话已答对（掌握）的题，杜绝“答对过仍跨轮重复出现”
- 点亮规则（叶节点，任一满足即点亮）：
  1. 本轮该叶出的题中连续答对 3 道（相邻两题提交间隔 ≤2min）→ 点亮并跳过剩余题目
  2. 本轮该叶全部题均答对（不计间隔）→ 点亮
  3. 累计答对 10 道该叶类型题（跨自适应/自主/真题）→ 点亮；每答对 2 道点亮 20%，节点内显示 x/10
- 枝节点：x/y（点亮叶数/叶总数），全部叶点亮后枝点亮；根节点：x/7（点亮枝数/枝总数），全亮后点亮
- 一轮 = 所有未点亮且有题叶节点刷完（题数 = 各叶去重题数之和）；完成后保留点亮状态，重新开始新一轮
"""
import json
import re

from db import get_connection
from repositories import get_question_by_id, get_mastery, get_graph
from seeding import OFFICIAL_TAGS

# 出题与点亮常量
LEAF_Q = 5            # 每叶节点题数（作为无计划时的兜底显示值）
STREAK = 3            # 规则1 连续答对数
GAP_MAX = 120         # 规则1 相邻两题提交间隔上限（秒，≤2min）
CORRECT_LIT = 10      # 规则3 累计答对数

# 枝/叶固定顺序（图谱声明序，不放回）
TOP_ORDER = list(OFFICIAL_TAGS.keys())
LEAF_ORDER = {top: [t[0] for t in leaves] for top, (_, leaves) in OFFICIAL_TAGS.items()}


# ==================== 状态读写 ====================

def get_journey_state(session_id):
    conn = get_connection()
    row = conn.execute('SELECT * FROM journey_state WHERE session_id=?', (session_id,)).fetchone()
    return dict(row) if row else None


def _load_round_state(state):
    """本轮状态 JSON：{status, entries, idx, pos, answers, answered_total, lit_round}"""
    try:
        return json.loads(state.get('round_state') or 'null')
    except Exception:
        return None


def _save_round_state(session_id, rs):
    conn = get_connection()
    conn.execute('UPDATE journey_state SET round_state=? WHERE session_id=?',
                 (json.dumps(rs), session_id))
    conn.commit()


def init_journey(session_id, diagnostic_data=None):
    """初始化旅程（本轮状态留空，首次 journey_next 自动建轮）"""
    conn = get_connection()
    existing = conn.execute('SELECT * FROM journey_state WHERE session_id=?', (session_id,)).fetchone()
    if existing:
        return dict(existing)
    conn.execute('''INSERT INTO journey_state (session_id,current_node,deep_mode,phase,recent_modules,total_answered,total_correct)
        VALUES (?,?,?,?,?,?,?)''',
        (session_id, None, 1, 'active', '[]', 0, 0))
    conn.commit()
    return get_journey_state(session_id)


def _is_mcq(q):
    return bool(q.get('options') and str(q.get('options', '')).strip())


# ==================== 出题（双循环 + 循环复用） ====================

# 自适应进阶题源（2026-09-07 拆分为选择题/填空题白名单）
# 选择题白名单：
#   - ai_gen（2026-09-07 审核通过：310 道选择题，全部 ≥2 选项且正确答案均在选项中，
#     options 为 A./B./C./D. 前缀的管道分隔串，与现有 seeded 格式一致，前端/后端解析兼容；
#     2026-09-08 扩题新增 45 道选择题，合计 355 道）
#   - 三资学堂（2026-09-07 审核通过：16 道选择题，全部 4 选项、答案均在选项中、标题/描述/解析齐全；
#     无 table_schema 属正常，选择题走文本比对判题不依赖建表）
ADAPTIVE_MCQ_SOURCES = ('static_basic', 'static_advanced', 'nowcoder_preview', 'ai_gen', '三资学堂')
# 填空题：质量确认后纳入（2026-09-07）
#   - ai_gen：57 道填空，题面/答案/schema/解析齐全（约 22 道缺 initial_data，多为 INSERT 类不受影响，已评估可接受）
#             2026-09-08 扩题新增 34 道填空（表连接/约束/DDL/子查询），合计 91 道；
#             新增题均经 tools/import_questions.py 实判自校验 + 反向验证（破坏答案必须判错）
#   - 蓝客 各预览源：填空题 100% 完整（title/答案/schema/init/解析 均有）
ADAPTIVE_FILLIN_SOURCES = ('ai_gen',)
ADAPTIVE_FILLIN_LIKE = ('蓝客%',)


def _node_pools(leaf):
    """该叶节点的选择题/填空题 id 列表（基础选择先行，其次按 id）
    选择题仅取 ADAPTIVE_MCQ_SOURCES；填空题取 ADAPTIVE_FILLIN_SOURCES + 蓝客 前缀源，
    两类互不串源（ai_gen 的选择题不会进填空池，反之亦然）。"""
    conn = get_connection()
    mcq_rows = conn.execute('''SELECT q.id, q.q_level, q.options FROM questions q
        JOIN question_knowledge qk ON q.id = qk.question_id
        WHERE qk.node_id=? AND q.source IN (%s)''' % ','.join('?' * len(ADAPTIVE_MCQ_SOURCES)),
        (leaf,) + ADAPTIVE_MCQ_SOURCES).fetchall()
    like_clauses = ' OR '.join('q.source LIKE ?' for _ in ADAPTIVE_FILLIN_LIKE)
    fillin_rows = conn.execute('''SELECT q.id, q.q_level, q.options FROM questions q
        JOIN question_knowledge qk ON q.id = qk.question_id
        WHERE qk.node_id=? AND (q.source IN (%s) OR %s)''' % (
            ','.join('?' * len(ADAPTIVE_FILLIN_SOURCES)), like_clauses),
        (leaf,) + ADAPTIVE_FILLIN_SOURCES + ADAPTIVE_FILLIN_LIKE).fetchall()
    mcq, fillin = [], []
    for r in mcq_rows:
        if _is_mcq(dict(r)):
            mcq.append(dict(r))
    for r in fillin_rows:
        if not _is_mcq(dict(r)):
            fillin.append(dict(r))
    mcq.sort(key=lambda x: (x.get('q_level') != 'basic', x['id']))
    return [q['id'] for q in mcq], [q['id'] for q in fillin]


def _leaf_plan(mcq_ids, fillin_ids):
    """按“选择先行、填空随后”输出该叶全部不重复题目，题池不足时不再循环复用（避免同一题重复出现）。
    顺序：选择题（基础优先）→ 填空题；每个题目至多出现一次，故计划长度 = 该叶去重题数。"""
    plan, seen = [], set()
    for q in list(mcq_ids) + list(fillin_ids):
        if q not in seen:
            seen.add(q)
            plan.append(q)
    return plan


# ==================== 点亮判定 ====================

def _correct_counts(session_id):
    """规则3 派生：累计答对的每叶节点不同题数（幂等；真题记录 id 与练习重叠，仅统计练习池）。
    DISTINCT：同题可循环复用，重复答对同一题不叠加点亮进度（2026-09-06 语义修正）"""
    conn = get_connection()
    rows = conn.execute('''SELECT qk.node_id AS node_id, COUNT(DISTINCT up.question_id) AS c
        FROM user_progress up JOIN question_knowledge qk ON up.question_id = qk.question_id
        WHERE up.session_id=? AND up.pool='practice' AND up.is_correct=1 GROUP BY qk.node_id''', (session_id,)).fetchall()
    return {r['node_id']: r['c'] for r in rows}


def _lit_leaves(session_id, counts=None):
    """已点亮叶节点：user_lights 落库（规则1/2）∪ 规则3 派生（累计 ≥10）"""
    conn = get_connection()
    stored = {r['node_id'] for r in conn.execute(
        'SELECT node_id FROM user_lights WHERE session_id=? AND lit=1', (session_id,)).fetchall()}
    counts = counts if counts is not None else _correct_counts(session_id)
    return stored | {nid for nid, c in counts.items() if c >= CORRECT_LIT}


def _mastered_ids(session_id):
    """本会话已答对（掌握）的练习题目 id 集合（pool='practice'）。
    用于构建新一轮时剔除已掌握题，消除‘答对过仍跨轮重复出现’的问题（自适应重复出题的根因）。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT up.question_id FROM user_progress up "
        "WHERE up.session_id=? AND up.pool='practice' AND up.is_correct=1", (session_id,)).fetchall()
    return {r['question_id'] for r in rows}


def _set_lit(session_id, node_id):
    """规则1/2 点亮落库（幂等 upsert）"""
    conn = get_connection()
    conn.execute('''INSERT INTO user_lights (session_id, node_id, lit) VALUES (?,?,1)
        ON CONFLICT(session_id, node_id) DO UPDATE SET lit=1, updated_at=CURRENT_TIMESTAMP''',
        (session_id, node_id))
    conn.commit()


def _gap_seconds(ts1, ts2):
    """相邻两题提交间隔（秒）；时间戳解析失败视为 0（同秒语义）"""
    from datetime import datetime
    def _parse(ts):
        try:
            return datetime.strptime(str(ts)[:19], '%Y-%m-%d %H:%M:%S')
        except Exception:
            return None
    a, b = _parse(ts1), _parse(ts2)
    if a is None or b is None:
        return 0
    return abs((b - a).total_seconds())


def _refresh_answer_ts(answers):
    """判定前从 DB 刷新段内答题时间戳（间隔以 user_progress 记录为准，而非作答瞬间快照）"""
    if not answers:
        return
    conn = get_connection()
    for a in answers:
        row = conn.execute('SELECT answered_at FROM user_progress WHERE id=?', (a.get('pid'),)).fetchone()
        if row:
            a['ts'] = row['answered_at']


def _rule1_hit(answers):
    """规则1：段内尾部连续 3 道答对且相邻两题提交间隔 ≤2min"""
    if len(answers) < STREAK:
        return False
    tail = answers[-STREAK:]
    if not all(a['ok'] for a in tail):
        return False
    for i in range(1, len(tail)):
        if _gap_seconds(tail[i - 1]['ts'], tail[i]['ts']) > GAP_MAX:
            return False
    return True


def compute_lights(session_id, counts=None):
    """全量点亮状态：叶 {lit, correct}；枝 {lit, x, y}；根 {lit, x, y}（journey 与 status 共用）。
    counts 可选：调用方已算过 _correct_counts 时传入复用，避免同一请求内重复聚合（2026-08-12）"""
    conn = get_connection()
    stored = {r['node_id'] for r in conn.execute(
        'SELECT node_id FROM user_lights WHERE session_id=? AND lit=1', (session_id,)).fetchall()}
    if counts is None:
        counts = _correct_counts(session_id)
    out = {}
    for top in TOP_ORDER:
        for leaf in LEAF_ORDER[top]:
            c = counts.get(leaf, 0)
            out[leaf] = {'lit': leaf in stored or c >= CORRECT_LIT, 'correct': c}
    for top in TOP_ORDER:
        leaves = LEAF_ORDER[top]
        x = sum(1 for lf in leaves if out[lf]['lit'])
        out[top] = {'lit': len(leaves) > 0 and x == len(leaves), 'x': x, 'y': len(leaves)}
    lit_tops = sum(1 for t in TOP_ORDER if out[t]['lit'])
    out['root'] = {'lit': lit_tops == len(TOP_ORDER), 'x': lit_tops, 'y': len(TOP_ORDER)}
    return out


# ==================== 一轮构建 ====================

def _build_round(session_id):
    """新一轮：枝→叶固定顺序，跳过已点亮/无题叶节点；每叶输出该叶去重题（已掌握题不再跨轮重复）。
    已掌握 = 本会话练习池中答对的题（_mastered_ids）；答错的题仍保留以复习。"""
    lit = _lit_leaves(session_id)
    mastered = _mastered_ids(session_id)
    entries = []
    for top in TOP_ORDER:
        for leaf in LEAF_ORDER[top]:
            if leaf in lit:
                continue
            mcq, fill = _node_pools(leaf)
            if not mcq and not fill:
                continue
            plan = [q for q in _leaf_plan(mcq, fill) if q not in mastered]
            if not plan:
                continue
            entries.append({'branch': top, 'leaf': leaf, 'plan': plan})
    return {'status': 'active', 'entries': entries, 'idx': 0, 'pos': 0,
            'answers': [], 'answered_total': 0, 'lit_round': []}


def _progress_row(row_id):
    """按 user_progress 主键取答题记录（作答登记用）"""
    conn = get_connection()
    row = conn.execute('SELECT question_id, is_correct, answered_at FROM user_progress WHERE id=?',
                       (row_id,)).fetchone()
    return dict(row) if row else None


# ==================== 主流程 ====================

def journey_next(session_id, just_answered_qid=None, was_correct=None, duration=None,
                 just_answered_id=None):
    """自适应选题引擎（2026-08 图谱点亮版）"""
    state = get_journey_state(session_id)
    if not state:
        init_journey(session_id)
        state = get_journey_state(session_id)

    # 1. 记录答题统计（保留计数器）
    if was_correct is not None:
        _record_answer_stats(session_id, state, was_correct, duration)
        state = get_journey_state(session_id)

    rs = _load_round_state(state)
    lit_now = None
    counts = None   # 规则3/点亮状态共用的累计答对数（仅作答登记时计算一次）
    if rs is None or rs['status'] == 'complete':
        # 首轮 / 上轮完成 → 新一轮（点亮状态保留）
        rs = _build_round(session_id)
        _save_round_state(session_id, rs)
        if not rs['entries']:
            # 所有叶节点已点亮
            rs['status'] = 'complete'
            _save_round_state(session_id, rs)
            return _response(session_id, state, rs, question=None, round_complete=True,
                             lit_now=lit_now, counts=counts)

    entry = rs['entries'][rs['idx']] if rs['idx'] < len(rs['entries']) else None

    # 2. 作答登记：本轮该叶计划内的题才计入（防陈旧/重复提交污染）
    if just_answered_id is not None and was_correct is not None and entry is not None:
        if just_answered_qid in entry['plan']:
            row = _progress_row(just_answered_id)
            if row:
                rs['answers'].append({'qid': row['question_id'], 'ok': bool(row['is_correct']),
                                      'ts': row['answered_at'], 'pid': just_answered_id})
                rs['answered_total'] += 1
                _refresh_answer_ts(rs['answers'])
                if _rule1_hit(rs['answers']):
                    # 规则1：连对 3 + 间隔≤2min → 点亮并跳过剩余
                    _set_lit(session_id, entry['leaf'])
                    lit_now = entry['leaf']
                else:
                    counts = _correct_counts(session_id)
                    if counts.get(entry['leaf'], 0) >= CORRECT_LIT:
                        # 规则3：跨池累计答对 10 道 → 点亮并跳过剩余
                        lit_now = entry['leaf']
                if lit_now:
                    if entry['leaf'] not in rs['lit_round']:
                        rs['lit_round'].append(entry['leaf'])
                    rs['pos'] = len(entry['plan'])
                    rs['answers'] = []
                _save_round_state(session_id, rs)

    # 3. 双 while 推进：本叶 5 题出完 → 规则2 判定 → 下一叶；全部叶完成 → 一轮结束
    while True:
        if rs['idx'] >= len(rs['entries']):
            rs['status'] = 'complete'
            _save_round_state(session_id, rs)
            return _response(session_id, state, rs, question=None, round_complete=True,
                             lit_now=lit_now, counts=counts)
        entry = rs['entries'][rs['idx']]
        if rs['pos'] >= len(entry['plan']):
            # 规则2：本轮该叶全部答对（不计间隔）→ 点亮
            if rs['answers'] and all(a['ok'] for a in rs['answers']):
                _set_lit(session_id, entry['leaf'])
                if entry['leaf'] not in rs['lit_round']:
                    rs['lit_round'].append(entry['leaf'])
            rs['idx'] += 1
            rs['pos'] = 0
            rs['answers'] = []
            _save_round_state(session_id, rs)
            continue
        qid = entry['plan'][rs['pos']]
        rs['pos'] += 1
        _save_round_state(session_id, rs)
        return _response(session_id, state, rs, question=get_question_by_id(qid),
                         round_complete=False, lit_now=lit_now, counts=counts)


# ==================== 响应组装 ====================

# 通用 ROUND 提示（标准答案涉及 ROUND 时自动注入，2026-08-05）
ROUND_HINT = '提示：此题需要用到 ROUND，例如：保留小数点后两位 ROUND(3.1415, 2) → 3.14'

def _inject_round_hint(question):
    """标准答案含 ROUND（不区分大小写）时，为填空题注入通用提示"""
    if not question:
        return question
    if question.get('options') and str(question.get('options', '')).strip():
        return question  # 选择题不注入
    if re.search(r'\bROUND\b', question.get('correct_answer', ''), re.IGNORECASE):
        question['hint'] = ROUND_HINT
    return question

def _response(session_id, state, rs, question=None, round_complete=False, lit_now=None, counts=None):
    """组装响应：保留前端兼容字段 + lights/round/round_complete；counts 复用调用方已算的累计答对数"""
    entry = rs['entries'][rs['idx']] if rs['idx'] < len(rs['entries']) else None
    question = _inject_round_hint(question)
    return {
        'action': 'advance',
        'current_node': entry['leaf'] if entry else '',
        'question': question,
        'graph': get_graph(),
        'mastery': get_mastery(session_id),
        'lights': compute_lights(session_id, counts=counts),
        'round': {
            'status': rs['status'],
            'branch': entry['branch'] if entry else None,
            'leaf': entry['leaf'] if entry else None,
            'pos': rs['pos'],
            'leaf_total': len(entry['plan']) if entry else LEAF_Q,
            'leaf_index': rs['idx'] + 1 if entry else 0,
            'leaf_count': len(rs['entries']),
            'answered_total': rs['answered_total'],
            'lit_round': rs['lit_round'],
        },
        'round_complete': round_complete,
        'lit_now': lit_now,
        'wrong_streak': state.get('wrong_streak', 0),
        'total_answered': state.get('total_answered', 0),
        'total_correct': state.get('total_correct', 0),
        'fillin_mode': False,
        'deep_mode': state.get('deep_mode', 1),
        'hint': '',
        'phase': 'complete' if round_complete else 'active',
    }


# ==================== 统计（保留原实现） ====================

def _record_answer_stats(session_id, state, was_correct, duration):
    conn = get_connection()
    if duration is not None:
        sp = state.get('speed_count', 0)
        sa = state.get('avg_speed', 0)
        new_count = sp + 1
        new_avg = (sa * sp + duration) / new_count if sp > 0 else duration
        conn.execute('UPDATE journey_state SET avg_speed=?, speed_count=? WHERE session_id=?', (new_avg, new_count, session_id))
    conn.execute('UPDATE journey_state SET total_answered=total_answered+1 WHERE session_id=?', (session_id,))
    if was_correct is True:
        conn.execute('UPDATE journey_state SET total_correct=total_correct+1, wrong_streak=0 WHERE session_id=?', (session_id,))
    elif was_correct is False:
        conn.execute('UPDATE journey_state SET wrong_streak=wrong_streak+1 WHERE session_id=?', (session_id,))
    conn.commit()
