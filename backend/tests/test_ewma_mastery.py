# -*- coding: utf-8 -*-
"""EWMA 掌握度更新测试（取代原贝叶斯 Beta 分布更新）

模型：ewma ← ewma + λ·(outcome − ewma)，λ=0.3，无历史时先验 0.5。
特性：近期作答权重更高，早期错误会被后续表现"冲淡"（Beta 做不到）。
"""
import uuid

import pytest

import db
from repositories import save_answer, get_mastery, EWMA_LR, EWMA_PRIOR


def _register(client):
    name = f'u{uuid.uuid4().hex[:8]}'
    r = client.post('/api/register', json={'username': name, 'password': 'password123'})
    assert r.status_code == 200
    return r.get_json()['session_id']


def _node_of(qid):
    conn = db.get_connection()
    return conn.execute('SELECT node_id FROM question_knowledge WHERE question_id=?', (qid,)).fetchone()['node_id']


def _mastery_row(sid, nid):
    conn = db.get_connection()
    return dict(conn.execute('SELECT * FROM user_mastery WHERE session_id=? AND node_id=?', (sid, nid)).fetchone())


def test_first_answer_uses_neutral_prior(client):
    sid = _register(client)
    nid = _node_of(1)
    save_answer(sid, 1, 'A', True)
    row = _mastery_row(sid, nid)
    # 0.5 + 0.3×(1−0.5) = 0.65
    assert row['ewma'] == pytest.approx(EWMA_PRIOR + EWMA_LR * (1 - EWMA_PRIOR))
    # 旧的 alpha/beta 列保留但不再更新
    assert row['alpha'] == 1.0 and row['beta'] == 1.0


def test_ewma_tracks_recent_performance(client):
    sid = _register(client)
    nid = _node_of(1)
    save_answer(sid, 1, 'A', True)     # 0.65
    save_answer(sid, 1, 'A', True)     # 0.755
    save_answer(sid, 1, 'A', False)    # 0.5285
    row = _mastery_row(sid, nid)
    e = EWMA_PRIOR + EWMA_LR * (1 - EWMA_PRIOR)
    e = e + EWMA_LR * (1 - e)
    e = e + EWMA_LR * (0 - e)
    assert row['ewma'] == pytest.approx(e)
    assert row['correct_count'] == 2 and row['total_count'] == 3


def test_ewma_forgets_early_mistakes(client):
    """早期连续答错后持续答对，EWMA 能恢复到高位（Beta 均值做不到）"""
    sid = _register(client)
    nid = _node_of(1)
    for _ in range(3):
        save_answer(sid, 1, 'A', False)
    low = _mastery_row(sid, nid)['ewma']
    assert low < 0.25
    for _ in range(6):
        save_answer(sid, 1, 'A', True)
    high = _mastery_row(sid, nid)['ewma']
    assert high > 0.75   # 同期 Beta 均值 = 6/9 ≈ 0.67，EWMA 更高且持续趋近 1


def test_get_mastery_score_fallback_for_legacy_row(client):
    """存量行 ewma 为空时，get_mastery 回退 Beta 均值"""
    sid = _register(client)
    nid = _node_of(1)
    conn = db.get_connection()
    conn.execute('INSERT INTO user_mastery (session_id,node_id,correct_count,total_count,alpha,beta,ewma) VALUES (?,?,?,?,?,?,NULL)',
                 (sid, nid, 3, 4, 3.0, 1.0))
    conn.commit()
    m = get_mastery(sid)
    assert m[nid]['score'] == pytest.approx(0.75)


def test_get_mastery_score_prefers_ewma(client):
    sid = _register(client)
    nid = _node_of(1)
    save_answer(sid, 1, 'A', True)
    m = get_mastery(sid)
    assert m[nid]['score'] == pytest.approx(0.65, abs=1e-4)
