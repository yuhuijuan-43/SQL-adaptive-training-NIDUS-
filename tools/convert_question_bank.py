# -*- coding: utf-8 -*-
"""将「正式版」三个 HTML 题库转换为项目 JSON 题库。

输入（正式版备份目录）：
  nowcoder题库预览.html     → exam_questions.json（42 道牛客 SQL 填空题）
  选择题/基础选择.html       → questions.json 前半（29 道基础选择题）
  选择题/进阶选择.html       → questions.json 后半（29 道进阶选择题，含建表数据/SQL/预期输出）

字段惯例与 backend/seeding.py + frontend 渲染完全对齐：
  description     题干（填空题不含建表脚本）
  table_schema    CREATE 语句（judge 用其建环境）
  initial_data    INSERT 语句（judge 建环境 + 前端渲染数据表）
  expected_output JSON {"headers": [...], "rows": [[...]]}（前端首选格式；null 单元格→NULL）
  options         选择题 "A. xxx|B. xxx|..."（非空 → 前端按选项文本比对，不走 judge）
  difficulty      牛客按星级 *→easy **→medium ***→hard；选择题保留现库映射
  q_level         basic / advanced（基础/进阶选择题）
"""
import html as _html
import json
import re
import sys
from collections import Counter

SRC_DIR = r'E:\my normal txt\DigQuant\项目\SQL自适应训练\10vSQL自适应训练\10vSQL自适应训练\SQL自适应训练'
PROJECT_DIR = r'E:\my normal txt\DigQuant\项目\SQL自适应训练\SQL自适应训练'

STAR_TO_DIFF = {'*': 'easy', '**': 'medium', '***': 'hard'}


def unescape(s):
    return _html.unescape((s or '')).strip()


def clean_cell(s):
    """HTML 单元格 → 值；null/None 文本 → None（JSON null，前端渲染为 NULL）。"""
    v = unescape(s)
    if v.lower() in ('null', 'none'):
        return None
    return v


def split_sql_statements(sql):
    """按语句切分：分号（深度 0）或新行以 DDL/DML 关键字开头且已积累内容。
    兼容两种来源格式：';' 结尾（进阶选择）与换行分隔无分号（牛客 INSERT 行）。"""
    stmts, cur, depth, in_q, qch = [], '', 0, False, None

    def flush():
        if cur.strip():
            stmts.append(cur.strip())

    for line in sql.splitlines():
        stripped = line.strip()
        if (re.match(r'^(CREATE|DROP|ALTER|INSERT|UPDATE|DELETE|REPLACE)\b', stripped, re.I)
                and cur.strip() and depth == 0):
            flush()
            cur = ''
        for ch in line:
            if in_q:
                cur += ch
                if ch == qch:
                    in_q = False
            elif ch in "'\"":
                in_q, qch, cur = True, ch, cur + ch
            elif ch == '(':
                depth += 1
                cur += ch
            elif ch == ')':
                depth = max(0, depth - 1)
                cur += ch
            elif ch == ';' and depth == 0:
                flush()
                cur = ''
            else:
                cur += ch
        cur += '\n'
    flush()
    return stmts


def classify_sql(sql):
    """拆分建表 SQL：schema（CREATE/DROP/ALTER）+ data（其余）。"""
    schema, data = [], []
    for st in split_sql_statements(sql):
        if re.match(r'^\s*(CREATE|DROP|ALTER)\b', st, re.I):
            schema.append(st)
        else:
            data.append(st)
    return (';\n'.join(s + ';' if not s.rstrip().endswith(';') else s for s in schema),
            '\n'.join(s + ';' if not s.rstrip().endswith(';') else s for s in data))


def sanitize_schema(sql):
    """MySQL 方言建表 → SQLite 兼容（本平台判题环境是 SQLite）。
    目前仅处理 AUTO_INCREMENT（INT PRIMARY KEY 在 SQLite 需写 INTEGER PRIMARY KEY 才具自增语义）。
    选择题走文本比对，此清理只影响「建表数据」展示与环境构建的可用性。"""
    if not sql:
        return sql
    sql = re.sub(r'\bINT\s+PRIMARY KEY\s+AUTO_INCREMENT\b', 'INTEGER PRIMARY KEY AUTOINCREMENT', sql)
    sql = re.sub(r'\bINT\s+AUTO_INCREMENT\s+PRIMARY KEY\b', 'INTEGER PRIMARY KEY AUTOINCREMENT', sql)
    sql = re.sub(r'\bAUTO_INCREMENT\b', '', sql)
    return sql


def parse_data_tables(section):
    """解析预期输出区段里的 data-table → JSON 字符串；无数据行返回 ''. """
    tables = re.findall(r'<table class="data-table">(.*?)</table>', section, re.S)
    if not tables:
        return ''
    body = tables[0]
    headers = [clean_cell(h) for h in re.findall(r'<th\b[^>]*>(.*?)</th>', body, re.S)]
    rows = []
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', body, re.S):
        tds = [clean_cell(x) for x in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)]
        if tds:
            rows.append(tds)
    if not rows:
        return ''
    return json.dumps({'headers': headers, 'rows': rows}, ensure_ascii=False)


# ---------------------------------------------------------------
# 1. 选择题（基础/进阶）
# ---------------------------------------------------------------
def parse_choice_cards(path):
    content = open(path, encoding='utf-8').read()
    cards = []
    for m in re.finditer(r'<div class="card" data-answer="([A-Z])">(.*?)\n  </div>', content, re.S):
        answer, body = m.group(1), m.group(2)
        tag_m = re.search(r'<span class="tag">([^<]+)</span>', body)
        title = unescape(re.sub(r'<[^>]+>', '', re.search(r'<h3[^>]*>(.*?)</h3>', body, re.S).group(1)))
        desc = unescape(re.sub(r'<[^>]+>', '', re.search(r'<p class="question-desc">(.*?)</p>', body, re.S).group(1)))
        opts = re.findall(r'data-key="([A-Z])">.*?<span>(.*?)</span></div>', body, re.S)
        sql_m = re.search(r'<div class="sql-code">(.*?)</div>', body, re.S)
        sql = re.sub(r'<br\s*/?>', '\n', sql_m.group(1)) if sql_m else ''
        sql = unescape(re.sub(r'<[^>]+>', '', sql))
        table_schema, initial_data = classify_sql(sql) if sql else ('', '')
        # 预期输出：取「预期输出」区段（建表数据区段的表不参与）
        section = re.split(r'<div class="section-title">预期输出</div>', body, maxsplit=1)
        expected_output = parse_data_tables(section[1]) if len(section) > 1 else ''
        cards.append({
            'answer': answer, 'category_tag': tag_m.group(1) if tag_m else '',
            'title': title, 'desc': desc, 'options': opts,
            'table_schema': table_schema, 'initial_data': initial_data,
            'expected_output': expected_output,
        })
    return cards


def build_mcq_entries(cards, base_questions, source, q_level):
    """选择题条目：题目/选项与现库静态题一致（校验），保留现库 category/difficulty，
    进阶题补充 table_schema/initial_data/expected_output。"""
    assert len(cards) == len(base_questions), \
        f'{source}: HTML {len(cards)} 题 vs 现库 {len(base_questions)} 题，数量不一致'
    entries = []
    for i, (card, bq) in enumerate(zip(cards, base_questions)):
        optmap = dict(card['options'])
        assert bq['title'] == card['title'] and bq['description'] == card['desc'], \
            f'{source} 第{i+1}题与现库不一致: [{card["title"]}] vs [{bq["title"]}]'
        assert bq['correct_answer'] == card['answer'] + '. ' + optmap[card['answer']], \
            f'{source} 第{i+1}题答案不一致'
        entry = dict(bq)
        entry.update({
            'source': source,
            'table_schema': sanitize_schema(card['table_schema']),
            'initial_data': card['initial_data'],
            'expected_output': card['expected_output'],
            'options': '|'.join(f'{k}. {v}' for k, v in card['options']),
            'pool': 'practice',
            'q_level': q_level,
        })
        entries.append(entry)
    return entries


# ---------------------------------------------------------------
# 2. 牛客填空题（真题）
# ---------------------------------------------------------------
def parse_nowcoder_cards(path):
    content = open(path, encoding='utf-8').read()
    cards = []
    for part in re.split(r'(?=<div class="card" id="SQL\d+">)', content)[1:]:
        cid = re.search(r'id="(SQL\d+)"', part).group(1)
        tags = [unescape(t) for t in re.findall(r'<span class="tag"[^>]*>(.*?)</span>', part)]
        category = next((t for t in tags if not re.fullmatch(r'\**', t)), '')
        stars = next((t for t in tags if re.fullmatch(r'\**', t) and t), '*')
        title = unescape(re.sub(r'<[^>]+>', '', re.search(r'<h3[^>]*>(.*?)</h3>', part, re.S).group(1)))
        desc = unescape(re.sub(r'<[^>]+>', '', re.search(r'<p class="question-desc">(.*?)</p>', part, re.S).group(1)))
        sql_m = re.search(r'<div class="sql-code">(.*?)</div>', part, re.S)
        sql = unescape(re.sub(r'<[^>]+>', '', re.sub(r'<br\s*/?>', '\n', sql_m.group(1)))) if sql_m else ''
        table_schema, initial_data = classify_sql(sql) if sql else ('', '')
        section = re.split(r'<div class="section-title">预期输出</div>', part, maxsplit=1)
        expected_output = parse_data_tables(section[1]) if len(section) > 1 else ''
        ans_section = re.split(r'<div class="answer-section">', part, maxsplit=1)
        correct_answer, explanation = '', ''
        if len(ans_section) > 1:
            am = re.search(r'<div class="sql-text">(.*?)</div>', ans_section[1], re.S)
            if am:
                correct_answer = unescape(re.sub(r'<[^>]+>', '', am.group(1)))
            em = re.search(r'解析：</div>\s*<div[^>]*>(.*?)</div>', ans_section[1], re.S)
            if em:
                explanation = unescape(re.sub(r'<[^>]+>', '', em.group(1)))
        cards.append({
            'id': cid, 'category': category, 'stars': stars,
            'difficulty': STAR_TO_DIFF.get(stars, 'easy'),
            'title': title, 'desc': desc,
            'table_schema': table_schema, 'initial_data': initial_data,
            'expected_output': expected_output,
            'correct_answer': correct_answer, 'explanation': explanation,
        })
    return cards


def to_sqlite_answer(ans, title):
    """牛客答案是 MySQL 方言且常含多语句变体；判题器（内存 SQLite）只认单条 SQLite 语句。

    处理：① 只保留第一条语句（'-- 方法2/或使用…' 变体丢弃）；
    ② MySQL 专有函数 → SQLite 等价（DAY/MONTH/YEAR→strftime、DATEDIFF→julianday、
    COUNT(DISTINCT a,b)→COUNT(DISTINCT a||b)、IF→CASE WHEN、DATE_FORMAT→strftime、
    SUBSTRING_INDEX→按题特例）。
    """
    if not ans:
        return ''
    # ① 只保留第一条语句；去掉行首注释行
    stmt = ans.split(';', 1)[0]
    lines = [ln for ln in stmt.splitlines() if not re.match(r'^\s*--', ln)]
    stmt = '\n'.join(lines).strip()
    # ② 函数转换（IF 用 iif 也能跑，但 CASE WHEN 是 SQLite 标准写法，统一转换）
    # 注意：strftime 返回文本，与数字字面量比较（= 2021）恒为假 → CAST 成 INTEGER；
    # SQLite 3.50+ 整数/整数=整数除法 → 计数相除补 * 1.0 保证浮点结果
    stmt = re.sub(r'\bDAY\(\s*([\w.]+)\s*\)', r"CAST(strftime('%d', \1) AS INTEGER)", stmt)
    stmt = re.sub(r'\bMONTH\(\s*([\w.]+)\s*\)', r"CAST(strftime('%m', \1) AS INTEGER)", stmt)
    stmt = re.sub(r'\bYEAR\(\s*([\w.]+)\s*\)', r"CAST(strftime('%Y', \1) AS INTEGER)", stmt)
    stmt = re.sub(r"\bDATE_FORMAT\(\s*([\w.]+)\s*,\s*'([^']*)'\s*\)", r"strftime('\2', \1)", stmt)
    stmt = re.sub(r'\bDATEDIFF\(\s*([\w.]+)\s*,\s*([\w.]+)\s*\)', r'julianday(\1) - julianday(\2)', stmt)
    stmt = re.sub(r'\bCOUNT\(\s*DISTINCT\s+([\w.]+)\s*,\s*([\w.]+)\s*\)',
                  r'COUNT(DISTINCT \1 || \2)', stmt)
    stmt = re.sub(r'\bIF\(\s*([^(),]+?)\s*,\s*([^(),]+?)\s*,\s*([^(),]+?)\s*\)',
                  r'CASE WHEN \1 THEN \2 ELSE \3 END', stmt)
    stmt = re.sub(r'(\b(?:SUM|COUNT)\([^;]*?\))\s*/\s*(\b(?:SUM|COUNT)\([^;]*?\))',
                  r'\1 * 1.0 / \2', stmt)
    if 'SUBSTRING_INDEX' in stmt:
        # 题目特例：数据形状固定，用等价 SQLite 表达式
        if 'SUBSTRING_INDEX(SUBSTRING_INDEX(profile' in stmt:
            # SQL35：profile 第 3 段（年龄恒为两位数字）
            stmt = re.sub(
                r'SUBSTRING_INDEX\(SUBSTRING_INDEX\(profile, \',\', 3\), \',\', -1\)',
                r"substr(profile, instr(profile, ',') + instr(substr(profile, instr(profile, ',') + 1), ',') + 1, 2)",
                stmt)
        elif 'SUBSTRING_INDEX(profile' in stmt:
            # SQL33：性别为最后一段 → 用 HTML 自带方法2（CASE WHEN + LIKE）
            stmt = ("SELECT CASE WHEN profile LIKE '%,male' THEN 'male' "
                    "WHEN profile LIKE '%,female' THEN 'female' END AS gender, "
                    "COUNT(*) AS number FROM user_submit GROUP BY gender")
        else:
            raise SystemExit(f'{title}: 未处理的 SUBSTRING_INDEX 变体:\n{stmt}')
    return stmt


def build_exam_entries(cards):
    entries = []
    for c in cards:
        converted = to_sqlite_answer(c['correct_answer'], c['title'])
        if converted != c['correct_answer']:
            print(f'  [转换] {c["title"]} 答案转 SQLite 方言')
        entries.append({
            'source': 'niuke',
            'category': c['category'],
            'difficulty': c['difficulty'],
            'title': c['title'],
            'description': c['desc'],
            'table_schema': c['table_schema'],
            'initial_data': c['initial_data'],
            'correct_answer': converted,
            'explanation': c['explanation'],
            'options': '',
            'option_explanations': '',
            'expected_output': c['expected_output'],
        })
    return entries


# ---------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------
def main():
    # 现库静态题（保留 category/difficulty/q_level 映射）
    with open(PROJECT_DIR + r'\data\questions.json', encoding='utf-8') as f:
        old_qs = json.load(f)
    basic_old = [q for q in old_qs if q['source'] == 'static_basic']
    advanced_old = [q for q in old_qs if q['source'] == 'static_advanced']

    basic_cards = parse_choice_cards(SRC_DIR + r'\选择题\基础选择.html')
    advanced_cards = parse_choice_cards(SRC_DIR + r'\选择题\进阶选择.html')

    mcq_entries = (
        build_mcq_entries(basic_cards, basic_old, 'static_basic', 'basic') +
        build_mcq_entries(advanced_cards, advanced_old, 'static_advanced', 'advanced')
    )

    nowcoder_cards = parse_nowcoder_cards(SRC_DIR + r'\nowcoder题库预览.html')
    exam_entries = build_exam_entries(nowcoder_cards)

    # SQL30：正式版 HTML 自身的预期输出瑕疵——表头写 age_cut/number，但 7 行全是明细行
    # （device_id/gender/age_cut 残留），与官方答案（按 age_cut 聚合，3 行）不符。
    # 预期输出是用户判题对照的参考，修正为正确答案的实际结果：
    for e in exam_entries:
        if e['title'].startswith('SQL30'):
            e['expected_output'] = json.dumps(
                {'headers': ['age_cut', 'number'],
                 'rows': [['20-24岁', 3], ['25岁及以上', 3], ['其他', 1]]},
                ensure_ascii=False)
            print('  [修正] SQL30 预期输出对齐为聚合结果（正式版 HTML 明细行残留）')

    # 统计
    print('选择题:', len(mcq_entries), '（基础', len(basic_cards), '+ 进阶', len(advanced_cards), '）')
    print('  进阶含建表数据:', sum(1 for q in mcq_entries if q['q_level'] == 'advanced' and q['initial_data']),
          '含预期输出:', sum(1 for q in mcq_entries if q['q_level'] == 'advanced' and q['expected_output']))
    print('真题:', len(exam_entries))
    print('  真题分类:', dict(Counter(q['category'] for q in exam_entries)))
    print('  真题难度:', dict(Counter(q['difficulty'] for q in exam_entries)))
    print('  真题缺答案:', [q['title'] for q in exam_entries if not q['correct_answer']])
    print('  真题缺建表:', [q['title'] for q in exam_entries if not q['table_schema']])
    print('  真题缺预期输出:', len([q for q in exam_entries if not q['expected_output']]))

    out_q = PROJECT_DIR + r'\data\questions.json'
    out_exam = PROJECT_DIR + r'\data\exam_questions.json'
    with open(out_q, 'w', encoding='utf-8') as f:
        json.dump(mcq_entries, f, ensure_ascii=False, indent=1)
    with open(out_exam, 'w', encoding='utf-8') as f:
        json.dump(exam_entries, f, ensure_ascii=False, indent=1)
    print(f'\n已写入 {out_q}（{len(mcq_entries)} 题）')
    print(f'已写入 {out_exam}（{len(exam_entries)} 题）')


if __name__ == '__main__':
    main()
