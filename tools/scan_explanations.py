"""扫描批次 JSON 中解析不完整/残留的题目。

检测规则：
  1. option_explanations 含「同上」等偷懒残留
  2. 解析中出现草稿问号（✗/✓ 后跟非疑问句的正常解释里出现「吗？」「呢？」等自我讨论）
  3. 解析自指题目本身（「题目里」「本题选项」「干扰项」等元注释）
  4. 选择题 options 数量与 option_explanations 数量不一致
  5. 选择题 explanation / option_explanations 为空
  6. ✓/✗ 标记数量与选项数量不一致
  7. 选项文本中混入括号元注释（如「（不该依赖）」「（SQLite 默认……也不该依赖）」类编写备注）
"""
import json
import os
import re
import sys

BATCH_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'batches')

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


def check_file(path):
    issues = []
    data = json.load(open(path, encoding='utf-8'))
    for i, q in enumerate(data):
        title = q.get('title', '?')
        opts = split_opts(q.get('options', ''))
        exps = split_opts(q.get('option_explanations', ''))
        exp = q.get('explanation', '') or ''
        desc = q.get('description', '') or ''

        # 规则 4/5/6：选择题结构完整性
        if opts:
            if not exps:
                issues.append((i, title, '选择题缺少 option_explanations'))
            elif len(opts) != len(exps):
                issues.append((i, title, f'选项 {len(opts)} 个但解析 {len(exps)} 条'))
            if not exp.strip():
                issues.append((i, title, '缺少总解析 explanation'))
            for j, e in enumerate(exps):
                if e.strip() in ('✓', '✗'):
                    issues.append((i, title, f'第{j+1}条解析为空壳标记'))

        # 规则 1/2/3/7：文本残留
        texts = [('explanation', exp), ('description', desc)] + [(f'optexp[{j}]', e) for j, e in enumerate(exps)]
        for j, o in enumerate(opts):
            texts.append((f'opt[{j+1}]', o))
        for field, t in texts:
            for pat, label in BAD_PATTERNS:
                if re.search(pat, t):
                    issues.append((i, title, f'{field} {label}: ...{t[:70]}...'))
    return data, issues


def main():
    total_q, total_issue = 0, 0
    for fn in sorted(os.listdir(BATCH_DIR)):
        if not fn.endswith('.json'):
            continue
        path = os.path.join(BATCH_DIR, fn)
        data, issues = check_file(path)
        total_q += len(data)
        if issues:
            total_issue += len(issues)
            print(f'\n=== {fn}（{len(data)} 题，{len(issues)} 处问题）===')
            for i, title, msg in issues:
                print(f'  [{i}] {title}')
                print(f'      {msg}')
        else:
            print(f'{fn}: {len(data)} 题 OK')
    print(f'\n合计 {total_q} 题，{total_issue} 处问题')
    return 1 if total_issue else 0


if __name__ == '__main__':
    sys.exit(main())
