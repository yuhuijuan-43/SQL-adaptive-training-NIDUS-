"""Journey 自适应引擎：BKT 掌握度建模 + Thompson 采样选题"""
import json
import random

from db import get_connection
from repositories import (get_all_questions, get_question_by_id, get_questions_by_node,
                          get_progress, get_mastery, get_graph)

def get_journey_state(session_id):
    conn = get_connection()
    row = conn.execute('SELECT * FROM journey_state WHERE session_id=?', (session_id,)).fetchone()
    return dict(row) if row else None

def init_journey(session_id, diagnostic_data=None):
    conn = get_connection()
    existing = conn.execute('SELECT * FROM journey_state WHERE session_id=?', (session_id,)).fetchone()
    if existing:
            return dict(existing)
    # Determine starting level based on diagnostic results
    start_level = 0
    phase = 'cold'
    if diagnostic_data:
        acc = diagnostic_data.get('accuracy', 0)
        skipped = diagnostic_data.get('skipped', 0)
        total = diagnostic_data.get('total', 3)
        if skipped >= 2 or total == 0:
            start_level = 0; phase = 'cold'
        elif acc >= 80:
            start_level = 2; phase = 'exploration'  # high performer
        elif acc >= 50:
            start_level = 1; phase = 'exploration'
        else:
            start_level = 0; phase = 'cold'
        # Pre-seed alpha/beta for nodes the user answered correctly/incorrectly in diagnostic
        details = diagnostic_data.get('details', [])
        for d in details:
            if d.get('skipped'): continue
            nid = d.get('node_id')
            if not nid: continue
            existing_m = conn.execute('SELECT * FROM user_mastery WHERE session_id=? AND node_id=?', (session_id, nid)).fetchone()
            if not existing_m:
                a = 2 if d.get('is_correct') else 1
                b = 1 if d.get('is_correct') else 2
                conn.execute('INSERT INTO user_mastery (session_id,node_id,correct_count,total_count,alpha,beta) VALUES (?,?,?,?,?,?)',
                             (session_id, nid, 1 if d.get('is_correct') else 0, 1, a, b))
    all_nodes = [dict(r) for r in conn.execute('SELECT id, level FROM knowledge_nodes ORDER BY level, id').fetchall()]
    first_nodes = [n['id'] for n in all_nodes if n['level'] == start_level]
    if not first_nodes:
        first_nodes = ['select_basic']
    queue_json = json.dumps(first_nodes)
    conn.execute('''INSERT INTO journey_state (session_id,current_node,node_queue,skipped_nodes,fillin_queue,fillin_pending,deep_mode,phase,recent_modules)
        VALUES (?,?,?,?,?,?,?,?,?)''',
                 (session_id, None, queue_json, json.dumps([]), json.dumps([]), 0, 1, phase, json.dumps([])))
    conn.commit()
    return get_journey_state(session_id)

def _node_has_questions(node_id):
    """节点是否挂有题目（官方图谱的大分类/根节点无题，视为自动掌握）"""
    conn = get_connection()
    return conn.execute('SELECT COUNT(*) FROM question_knowledge WHERE node_id=?', (node_id,)).fetchone()[0] > 0

def _get_unlocked_nodes(session_id):
    """Return node_ids the user has unlocked based on mastery of prerequisites.
    无题目的节点（根/大分类）自动视为已掌握，保证其下标签可解锁。"""
    conn = get_connection()
    graph = [dict(r) for r in conn.execute('SELECT * FROM knowledge_edges').fetchall()]
    mastery = {r['node_id']: dict(r) for r in conn.execute('SELECT * FROM user_mastery WHERE session_id=?', (session_id,)).fetchall()}
    all_nodes = [dict(r)['id'] for r in conn.execute('SELECT id FROM knowledge_nodes ORDER BY level').fetchall()]

    def is_mastered(nid):
        if not _node_has_questions(nid):
            return True
        return _mastery_prob(mastery.get(nid)) >= 0.7

    def node_has_unlocked_prereqs(nid):
        prereqs = [e['from_node'] for e in graph if e['to_node'] == nid]
        if not prereqs: return True
        return all(is_mastered(p) for p in prereqs)

    unlocked = [nid for nid in all_nodes if node_has_unlocked_prereqs(nid)]
    return unlocked

def _recommend_weak_prereq(session_id, node_id):
    """Find the weakest prerequisite of node_id that isn't mastered."""
    conn = get_connection()
    prereqs = [dict(r)['from_node'] for r in conn.execute('SELECT from_node FROM knowledge_edges WHERE to_node=?', (node_id,)).fetchall()]
    mastery = {r['node_id']: dict(r) for r in conn.execute('SELECT * FROM user_mastery WHERE session_id=?', (session_id,)).fetchall()}
    weakest = None; weakest_prob = 1.0
    for pid in prereqs:
        if not _node_has_questions(pid):
            continue   # 无题的大分类节点跳过
        prob = _mastery_prob(mastery.get(pid))
        if prob < weakest_prob:
            weakest_prob = prob
            weakest = pid
    return weakest if weakest_prob < 0.7 else None

def _mastery_prob(m):
    """BKT: Beta distribution mean."""
    if not m: return 0.5
    a = m.get('alpha', 1)
    b = m.get('beta', 1)
    return a / (a + b)

def _mastery_uncertainty(m):
    """BKT: Beta distribution variance (exploration score)."""
    if not m: return 0.5
    a = m.get('alpha', 1)
    b = m.get('beta', 1)
    s = a + b
    return (a * b) / (s * s * (s + 1))

def _is_mastered(node_id, mastery):
    """Mastered if mastery probability >= 0.7. 无题节点（根/大分类）自动视为已掌握，不会成为候选"""
    if not _node_has_questions(node_id):
        return True
    m = mastery.get(node_id)
    return _mastery_prob(m) >= 0.7

def _thompson_score(node_id, mastery, total_answered, phase='exploration'):
    """Compute Thompson sampling score for a knowledge node."""
    m = mastery.get(node_id)
    prob = _mastery_prob(m)
    unc = _mastery_uncertainty(m)
    # Exploitation: want nodes with low mastery (high learning potential)
    exploit = 1 - prob
    # Exploration: want nodes with high uncertainty
    explore = unc
    # Dynamic exploration rate λ
    lam = max(0.1, 0.5 * (2.718 ** (-total_answered / 15)))
    if phase == 'cold':
        lam = 0.6  # more exploration in cold start
    elif phase == 'mastery':
        lam = 0.1  # less exploration in mastery phase
    return lam * explore + (1 - lam) * exploit

def _record_answer_stats(session_id, state, was_correct, duration):
    """记录答题统计：速度、总答题数、连错计数"""
    conn = get_connection()
    if duration is not None:
        sp = state.get('speed_count', 0)
        sa = state.get('avg_speed', 0)
        new_count = sp + 1
        new_avg = (sa * sp + duration) / new_count if sp > 0 else duration
        conn.execute('UPDATE journey_state SET avg_speed=?, speed_count=? WHERE session_id=?', (new_avg, new_count, session_id))
    conn.execute('UPDATE journey_state SET total_answered=total_answered+1 WHERE session_id=?', (session_id,))
    if was_correct is True:
        conn.execute('UPDATE journey_state SET wrong_streak=0 WHERE session_id=?', (session_id,))
    elif was_correct is False:
        conn.execute('UPDATE journey_state SET wrong_streak=wrong_streak+1 WHERE session_id=?', (session_id,))
    conn.commit()

def _determine_phase(session_id, phase, total_answered, was_correct, state):
    """阶段切换决策：cold→exploration→mastery"""
    conn = get_connection()
    if phase == 'cold' and total_answered >= 5:
        phase = 'exploration'
        conn.execute('UPDATE journey_state SET phase=? WHERE session_id=?', (phase, session_id))
        conn.commit()
    elif phase == 'exploration' and total_answered > 30:
        recent = [dict(r) for r in conn.execute(
            'SELECT is_correct FROM user_progress WHERE session_id=? ORDER BY answered_at DESC LIMIT 10', (session_id,)).fetchall()]
        if len(recent) >= 10:
            vals = [r['is_correct'] for r in recent]
            mean = sum(vals) / len(vals)
            variance = sum((v - mean) ** 2 for v in vals) / len(vals)
            if variance < 0.15:
                phase = 'mastery'
                conn.execute('UPDATE journey_state SET phase=? WHERE session_id=?', (phase, session_id))
                conn.commit()
    if phase == 'mastery' and was_correct is False and state.get('wrong_streak', 0) >= 3:
        phase = 'exploration'
        conn.execute('UPDATE journey_state SET phase=? WHERE session_id=?', (phase, session_id))
        conn.commit()
    return phase

def _check_fillin_mode(state, just_answered_qid, deep_mode):
    """检查是否应进入填空模式（MCQ答完后触发）"""
    if not deep_mode or not just_answered_qid:
        return False, '', '', None
    jaq = get_question_by_id(just_answered_qid)
    if jaq and jaq.get('options') and jaq['options'].strip():
        current_node = state.get('current_node')
        if current_node:
            return True, '请手动输入 SQL 语句来确认你是否真正掌握了该知识点。', 'fillin', current_node
    return False, '', '', None

def _select_candidate_node(session_id, unlocked, mastery, total_answered, phase, state,
                           is_fast, was_correct, recent_modules_raw, skipped_raw, progress=None):
    """Thompson采样选择下一个知识点节点"""
    recent_modules = list(recent_modules_raw)
    skipped = list(skipped_raw)
    action = ''

    # Update recent modules (for safety constraint)
    if state.get('current_node'):
        graph_nodes = get_graph()['nodes']
        current_node_obj = next((n for n in graph_nodes if n['id'] == state['current_node']), None)
        if current_node_obj:
            recent_modules.append(current_node_obj.get('category', ''))
            if len(recent_modules) > 5:
                recent_modules = recent_modules[-5:]

    # Safety: check if 5 consecutive same-module
    same_module_count = 0
    last_mod = None
    if len(recent_modules) >= 5:
        last_mod = recent_modules[-1]
        same_module_count = sum(1 for m in recent_modules if m == last_mod)

    # Collect candidates: unlocked, not mastered
    candidates = [nid for nid in unlocked if not _is_mastered(nid, mastery)]
    if same_module_count >= 5 and candidates:
        all_nodes = get_graph()['nodes']
        node_map = {n['id']: n for n in all_nodes}
        candidates = [nid for nid in candidates if node_map.get(nid, {}).get('category', '') != last_mod]
    if not candidates:
        candidates = unlocked

    # Difficulty damping
    recent_progress = (progress if progress is not None else get_progress(session_id))[-10:]
    recent_correct = sum(1 for p in recent_progress if p['is_correct'])
    difficulty_damping = (len(recent_progress) >= 5 and recent_correct / max(len(recent_progress), 1) > 0.8)
    if difficulty_damping and phase != 'cold':
        all_nodes = get_graph()['nodes']
        node_map = {n['id']: n for n in all_nodes}
        weighted = []
        for nid in candidates:
            score = _thompson_score(nid, mastery, total_answered, phase)
            level = node_map.get(nid, {}).get('level', 0)
            score *= (1 + level * 0.2)
            weighted.append((score, nid))
    else:
        weighted = [(_thompson_score(nid, mastery, total_answered, phase), nid) for nid in candidates]

    weighted.sort(key=lambda x: -x[0])
    recommend_node = weighted[0][1] if weighted else 'select_basic'
    action = 'advance' if phase != 'cold' else 'cold'

    # Fast+correct: push same-level peers to skipped
    if is_fast and was_correct is True and phase != 'cold':
        all_nodes = get_graph()['nodes']
        node_map = {n['id']: n for n in all_nodes}
        rec_level = node_map.get(recommend_node, {}).get('level', 0)
        same_level = [nid for nid in candidates if node_map.get(nid, {}).get('level', 0) == rec_level and nid != recommend_node]
        for s in same_level:
            if s not in skipped:
                skipped.append(s)

    # Review interspersion (every 5 questions)
    if total_answered > 0 and total_answered % 5 == 0 and skipped:
        review_node = random.choice(skipped)
        skipped.remove(review_node)
        if not _is_mastered(review_node, mastery):
            recommend_node = review_node
            action = 'review'
            recent_modules = []

    # Persist
    conn = get_connection()
    conn.execute('UPDATE journey_state SET skipped_nodes=?, recent_modules=? WHERE session_id=?',
                 (json.dumps(skipped), json.dumps(recent_modules), session_id))
    conn.commit()
    return recommend_node, action

def _select_question_for_node(recommend_node, fillin_mode, session_id, just_answered_qid, progress=None):
    """为指定知识点节点选择一道合适的题目，返回 (question, fillin_mode, action, hint)"""
    action = ''
    hint = ''
    node_qs = get_questions_by_node(recommend_node)
    if fillin_mode:
        node_qs = [q for q in node_qs if not q.get('options') or not q['options'].strip()]
    else:
        mcq = [q for q in node_qs if q.get('options') and q['options'].strip()]
        if mcq:
            node_qs = mcq

    if progress is None:
        progress = get_progress(session_id)
    answered_ids = set(p['question_id'] for p in progress)
    correct_ids = set(p['question_id'] for p in progress if p['is_correct'])

    unanswered = [q for q in node_qs if q['id'] not in answered_ids]
    if not unanswered:
        unanswered = [q for q in node_qs if q['id'] not in correct_ids]
    if not unanswered:
        unanswered = node_qs

    # 填空模式下该节点无题 → 回退到普通选择
    if not unanswered:
        if fillin_mode:
            node_qs = get_questions_by_node(recommend_node)
            mcq = [q for q in node_qs if q.get('options') and q['options'].strip()]
            if mcq:
                node_qs = mcq
            unanswered = [q for q in node_qs if q['id'] not in answered_ids]
            if not unanswered:
                unanswered = [q for q in node_qs if q['id'] not in correct_ids]
            if not unanswered:
                unanswered = node_qs
            if not unanswered:
                fallback = [q for q in get_all_questions() if q.get('options') and q['options'].strip()]
                unanswered = fallback if fallback else get_all_questions()
            fillin_mode = False
            action = ''
            hint = ''
        else:
            fallback = [q for q in get_all_questions() if q.get('options') and q['options'].strip()]
            unanswered = fallback if fallback else get_all_questions()
    if not unanswered:
        unanswered = get_all_questions()

    # 填空模式：不重复刚刚做过的MCQ
    if fillin_mode and unanswered and just_answered_qid:
        alt = [q for q in unanswered if q['id'] != just_answered_qid]
        if alt:
            unanswered = alt
        else:
            fillin_mode = False
            action = ''
            hint = ''
            node_qs = get_questions_by_node(recommend_node)
            mcq = [q for q in node_qs if q.get('options') and q['options'].strip()]
            if mcq:
                node_qs = mcq
            unanswered = [q for q in node_qs if q['id'] not in answered_ids]
            if not unanswered:
                unanswered = [q for q in node_qs if q['id'] not in correct_ids]
            if not unanswered:
                unanswered = node_qs
            if not unanswered:
                fallback = [q for q in get_all_questions() if q.get('options') and q['options'].strip()]
                unanswered = fallback if fallback else get_all_questions()

    return random.choice(unanswered) if unanswered else None, fillin_mode, action, hint

def journey_next(session_id, just_answered_qid=None, was_correct=None, duration=None):
    """自适应选题引擎：基于BKT+Thompson采样选择下一道题"""
    state = get_journey_state(session_id)
    if not state:
        state = init_journey(session_id)

    # 1. 记录答题统计
    if was_correct is not None:
        _record_answer_stats(session_id, state, was_correct, duration)

    # 2. 重新加载状态
    state = get_journey_state(session_id)
    total_answered = state.get('total_answered', 0)
    phase = state.get('phase', 'cold')
    deep_mode = state.get('deep_mode', 1)
    wrong_streak = state.get('wrong_streak', 0)

    # 3. 阶段切换
    phase = _determine_phase(session_id, phase, total_answered, was_correct, state)

    # 3.5 一次性加载本请求所需数据（避免重复全表查询）
    progress = get_progress(session_id)
    mastery = get_mastery(session_id)
    unlocked = _get_unlocked_nodes(session_id)

    # 4. 检查填空模式触发
    is_fast = duration is not None and duration < 10
    fillin_mode, hint, fillin_action, recommend_node = _check_fillin_mode(
        state, just_answered_qid, deep_mode)

    # 5. 非填空模式：Thompson采样选节点
    if not fillin_mode:
        recent_modules = json.loads(state.get('recent_modules', '[]'))
        skipped = json.loads(state.get('skipped_nodes', '[]'))
        recommend_node, action = _select_candidate_node(
            session_id, unlocked, mastery, total_answered, phase, state,
            is_fast, was_correct, recent_modules, skipped, progress=progress)
    else:
        action = fillin_action

    # 6. 持久化当前节点
    conn = get_connection()
    conn.execute('UPDATE journey_state SET current_node=? WHERE session_id=?', (recommend_node, session_id))
    conn.commit()

    # 7. 选题
    question, fillin_mode, returned_action, returned_hint = _select_question_for_node(
        recommend_node, fillin_mode, session_id, just_answered_qid, progress=progress)
    if returned_action:
        action = returned_action
    if returned_hint:
        hint = returned_hint

    # 8. 组装响应
    graph_data = get_graph()
    mastery_data = mastery

    return {
        'action': action,
        'current_node': recommend_node,
        'question': question,
        'graph': graph_data,
        'mastery': mastery_data,
        'unlocked_nodes': unlocked,
        'wrong_streak': wrong_streak,
        'total_answered': total_answered,
        # progress 已包含本次提交的答案（调用方先 save_answer 再进引擎），不再重复 +1
        'total_correct': sum(1 for p in progress if p['is_correct']),
        'fillin_mode': fillin_mode,
        'deep_mode': deep_mode,
        'hint': hint,
        'phase': phase
    }
