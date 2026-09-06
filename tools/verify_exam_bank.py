# -*- coding: utf-8 -*-
"""校验 exam_questions.json：标准答案能否在内存 SQLite 执行，结果是否与预期输出一致。

数值归一化：'3.200' == 3.2 == '3.2'、'4' == 4.0（MySQL 显示格式 vs SQLite 实际值差异）。
"""
import json
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r'E:\my normal txt\DigQuant\项目\SQL自适应训练\SQL自适应训练\backend')

with open(r'E:\my normal txt\DigQuant\项目\SQL自适应训练\SQL自适应训练\data\exam_questions.json',
          encoding='utf-8') as f:
    questions = json.load(f)


def norm(v):
    """数值归一化：str/float/int → 统一规范字符串"""
    if v is None:
        return '<NULL>'
    if isinstance(v, float):
        return f'{v:.6f}'.rstrip('0').rstrip('.')
    if isinstance(v, int):
        return str(v)
    s = str(v).strip()
    try:
        fv = float(s)
        return f'{fv:.6f}'.rstrip('0').rstrip('.')
    except ValueError:
        return s


def build_env(table_schema, initial_data):
    conn = sqlite3.connect(':memory:')
    conn.executescript(table_schema)
    if initial_data:
        conn.executescript(initial_data)
    return conn


fails, exec_fails = [], []
n_checked = 0
for q in questions:
    title, ans = q['title'], q['correct_answer']
    try:
        conn = build_env(q['table_schema'], q['initial_data'])
    except sqlite3.Error as e:
        fails.append((title, '环境构建失败', str(e)))
        continue
    try:
        rows = [tuple(r) for r in conn.execute(ans).fetchall()]
    except sqlite3.Error as e:
        exec_fails.append((title, str(e)))
        conn.close()
        continue
    conn.close()

    expected = json.loads(q['expected_output']) if q['expected_output'] else None
    if expected is None:
        continue  # 无预期输出题：只保证可执行
    n_checked += 1
    exp_rows = [tuple(norm(x) for x in r) for r in expected['rows']]
    got_rows = [tuple(norm(x) for x in r) for r in rows]
    if sorted(exp_rows) != sorted(got_rows):
        fails.append((title, f'结果不一致: 预期{len(exp_rows)}行 vs 实际{len(got_rows)}行',
                      f'预期={expected["rows"][:3]}... 实际={rows[:3]}...'))
    elif len(exp_rows) != len(got_rows):
        fails.append((title, f'行数不一致: 预期{len(exp_rows)} vs 实际{len(got_rows)}', ''))

print(f'共 {len(questions)} 题，{n_checked} 题有预期输出')
print(f'标准答案执行失败: {len(exec_fails)}')
for t, e in exec_fails:
    print(f'  ✗ {t}: {e}')
print(f'结果比对失败: {len(fails)}')
for t, kind, detail in fails:
    print(f'  ✗ {t}: {kind}')
    if detail:
        print(f'      {detail}')
if not exec_fails and not fails:
    print('全部通过 ✓')
