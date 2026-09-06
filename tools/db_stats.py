"""查看题库各类别题型分布（临时统计脚本）"""
import sqlite3
import os
import sys

DB = os.path.join(os.path.dirname(__file__), '..', 'backend', 'questions.db')
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT category, "
    "SUM(CASE WHEN options IS NULL OR TRIM(options)='' THEN 1 ELSE 0 END) fill, "
    "SUM(CASE WHEN options IS NOT NULL AND TRIM(options)!='' THEN 1 ELSE 0 END) mcq, "
    "COUNT(*) total FROM questions GROUP BY category ORDER BY category"
).fetchall()
print(f"{'category':28s} {'mcq':>4s} {'fill':>4s} {'total':>5s}")
for r in rows:
    print(f"{r['category']:28s} {r['mcq']:4d} {r['fill']:4d} {r['total']:5d}")
print('\n总数:', conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0])
if len(sys.argv) > 1 and sys.argv[1] == 'sample':
    print('\n--- 填空题样例 ---')
    for r in conn.execute(
        "SELECT id, category, difficulty, title, description, table_schema, initial_data,"
        " correct_answer, expected_output FROM questions"
        " WHERE options IS NULL OR TRIM(options)='' LIMIT 2").fetchall():
        for k in r.keys():
            print(f"{k}: {repr(r[k])[:300]}")
        print('---')
conn.close()
