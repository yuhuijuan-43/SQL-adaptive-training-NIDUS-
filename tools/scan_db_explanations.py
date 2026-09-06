"""扫描 questions.db 全库的解析残留问题（与 scan_explanations.py 同规则 + 标记位置校验）。"""
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
DB = r'e:\my_normal_txt\Yu_s_program\SQL自适应训练\backend\questions.db'

BAD_PATTERNS = [
    (r'同上', '残留：同上'),
    (r'吗？', '草稿问号：吗？'),
    (r'呢？', '草稿问号：呢？'),
    (r'题目里', '自指元注释：题目里'),
    (r'干扰项', '自指元注释：干扰项'),
    (r'这一项写法本身', '自指元注释'),
    (r'TODO|待补|XXX', '占位符'),
]


def split_opts(s):
    return [o.replace('\x00', '||') for o in (s or '').replace('||', '\x00').split('|') if o.strip()]


conn = sqlite3.connect(DB)
c = conn.cursor()
c.execute('SELECT id, title, options, option_explanations, explanation, correct_answer, category FROM questions ORDER BY id')
rows = c.fetchall()
conn.close()

issues = 0
for qid, title, options, optexps, exp, ans, cat in rows:
    opts = split_opts(options)
    exps = split_opts(optexps)
    found = []
    if opts:
        if not exps:
            found.append('选择题缺 option_explanations')
        elif len(opts) != len(exps):
            found.append(f'选项 {len(opts)} 个但解析 {len(exps)} 条')
        if not (exp or '').strip():
            found.append('缺总解析')
        # 标记位置校验：正确答案选项的解析应为 ✓，其余 ✗
        if len(opts) == len(exps) and len(opts) == 4:
            for j, o in enumerate(opts):
                if o == ans and not exps[j].startswith('✓'):
                    found.append(f'正确答案在第{j+1}项但解析标记是 {exps[j][:2]}')
                if o != ans and exps[j].startswith('✓'):
                    found.append(f'第{j+1}项是错误选项但解析标了 ✓: {exps[j][:40]}')
    for field, t in [('exp', exp or '')] + [(f'optexp[{j}]', e) for j, e in enumerate(exps)]:
        for pat, label in BAD_PATTERNS:
            if re.search(pat, t):
                found.append(f'{field} {label}: ...{t[:80]}...')
    if found:
        issues += len(found)
        print(f'[{qid}] {title} ({cat})')
        for f in found:
            print(f'    {f}')

print(f'\n扫描 {len(rows)} 题，发现 {issues} 处问题')
sys.exit(1 if issues else 0)
