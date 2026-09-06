# -*- coding: utf-8 -*-
"""存量掌握度迁移：贝叶斯(Beta) → EWMA

按 user_progress 答题历史的时间顺序回放，为每个 (session_id, node_id)
重新计算 EWMA 掌握度，写入 user_mastery.ewma。

用法:
  python tools/migrate_ewma.py            # 预览（dry-run）
  python tools/migrate_ewma.py --apply    # 写回数据库
"""
import os, sqlite3, sys, argparse

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'backend'))

from repositories import EWMA_LR, EWMA_PRIOR

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    conn = sqlite3.connect(os.path.join(ROOT, 'backend', 'questions.db'), timeout=15)
    conn.row_factory = sqlite3.Row

    # 保证列存在（等价 db.py 的迁移）
    try:
        conn.execute('ALTER TABLE user_mastery ADD COLUMN ewma REAL')
        conn.commit()
        print('已补充 user_mastery.ewma 列')
    except sqlite3.Error:
        pass

    # 题目 → 知识点 映射
    q2n = {}
    for r in conn.execute('SELECT question_id, node_id FROM question_knowledge'):
        q2n.setdefault(r['question_id'], []).append(r['node_id'])

    # 逐 session 按时间回放
    sessions = [r['session_id'] for r in conn.execute(
        'SELECT DISTINCT session_id FROM user_progress').fetchall()]
    ewma = {}   # (session, node) -> 当前 ewma
    for sid in sessions:
        rows = conn.execute(
            'SELECT question_id, is_correct FROM user_progress WHERE session_id=? ORDER BY id',
            (sid,)).fetchall()
        for r in rows:
            for nid in q2n.get(r['question_id'], []):
                key = (sid, nid)
                prev = ewma.get(key, EWMA_PRIOR)
                ewma[key] = prev + EWMA_LR * ((1.0 if r['is_correct'] else 0.0) - prev)

    print(f'回放 {len(sessions)} 个用户的答题历史，得到 {len(ewma)} 条 (用户,知识点) 掌握度')
    samples = list(ewma.items())[:8]
    for (sid, nid), v in samples:
        print(f'  {sid[:10]}… / {nid}: ewma={v:.3f}')

    if args.apply:
        n = 0
        for (sid, nid), v in ewma.items():
            cur = conn.execute(
                'UPDATE user_mastery SET ewma=? WHERE session_id=? AND node_id=?', (v, sid, nid))
            if cur.rowcount == 0:
                conn.execute(
                    'INSERT INTO user_mastery (session_id,node_id,correct_count,total_count,ewma) VALUES (?,?,0,0,?)',
                    (sid, nid, v))
            n += 1
        conn.commit()
        print(f'已写回 {n} 条 ewma')
    else:
        print('\n（以上为预览，加 --apply 写回数据库）')
    conn.close()

if __name__ == '__main__':
    main()
