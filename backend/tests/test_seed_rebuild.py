"""seed 题库版本校验测试：旧库残留（题数不符）自动重建；条数一致跳过导入

背景：.gitignore 排除 questions.db，依赖启动时从 questions.json 重建；
旧版残留库 count>0 会跳过导入 → 对方机器题库永远是旧版。
修复：seed_* 按「库内条数 vs 题库文件条数」比对，不一致自动重建题库表（保留用户数据）。
"""
import json
import os

import db


def _json_count(name):
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'data', name)
    with open(p, encoding='utf-8') as f:
        return len(json.load(f))


def _json_qlevel(name='questions.json'):
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'data', name)
    with open(p, encoding='utf-8') as f:
        return sum(1 for q in json.load(f) if q.get('q_level'))


class TestSeedRebuild:
    def test_rebuilds_stale_practice_bank(self, test_db):
        """库内题数与 questions.json 不符（旧库残留）→ seed_questions 自动重建"""
        conn = db.get_connection()
        conn.execute('DELETE FROM questions WHERE id > 2')   # 模拟旧库只剩 2 题
        conn.commit()
        from seeding import seed_questions
        seed_questions()
        assert conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0] == _json_count('questions.json')
        # 关键字段同步（q_level 选择题标记）
        q_level = conn.execute('SELECT COUNT(*) FROM questions WHERE q_level IS NOT NULL').fetchone()[0]
        assert q_level == _json_qlevel()

    def test_rebuilds_stale_exam_bank(self, test_db):
        """真题库题数不符 → 自动重建"""
        conn = db.get_connection()
        conn.execute('DELETE FROM exam_questions')            # 模拟旧真题库为空
        conn.commit()
        from seeding import seed_exam_questions
        seed_exam_questions()
        assert conn.execute('SELECT COUNT(*) FROM exam_questions').fetchone()[0] == _json_count('exam_questions.json')

    def test_skips_when_counts_match(self, test_db):
        """条数一致 → 跳过导入（不覆盖本地手改内容）"""
        from seeding import seed_questions
        seed_questions()                                     # 首次：手插 6 题 ≠ 515 → 重建
        conn = db.get_connection()
        first = conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
        assert first == _json_count('questions.json')
        conn.execute("UPDATE questions SET title='本地手改标题' WHERE id=1")
        conn.commit()
        seed_questions()                                     # 条数一致 → 跳过，不覆盖
        title = conn.execute('SELECT title FROM questions WHERE id=1').fetchone()[0]
        assert title == '本地手改标题'
        assert conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0] == first

    def test_rebuild_keeps_user_progress_valid(self, test_db):
        """重建后 user_progress 保留有效记录（指向仍存在的题目）"""
        conn = db.get_connection()
        # 预置一条答题记录（指向题库中实际存在的题，如 id=1）
        conn.execute("INSERT INTO user_progress (session_id,question_id,user_answer,is_correct) VALUES ('s1',1,'x',1)")
        conn.execute('DELETE FROM questions WHERE id > 2')   # 模拟旧库残留
        conn.commit()
        from seeding import seed_questions
        seed_questions()
        rows = conn.execute('SELECT COUNT(*) AS c FROM user_progress').fetchone()[0]
        assert rows == 1                                     # 有效记录保留
