"""把 LeetCode 爬取的题面（data/leetcode_questions.json）解析为系统可用的结构化素材。

解析 pre_blocks 中的 ASCII 表：
  - 表结构表（含 "Column Name" 表头）→ CREATE TABLE（类型映射到 SQLite）
  - Input 段中的数据表 → INSERT 初始数据
  - Output 段中的数据表 → expected_output（JSON）

输出 data/leetcode_parsed.json：
  [{frontend_id, slug, title, difficulty, text, schema, data, output, notes}]

无法干净解析的题目会在 notes 中标记，供人工（AI）改写时留意。
"""
import json
import os
import re

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

TYPE_MAP = {
    'int': 'INT', 'integer': 'INT', 'bigint': 'INT', 'smallint': 'INT',
    'varchar': 'VARCHAR(255)', 'char': 'VARCHAR(255)', 'text': 'TEXT', 'string': 'TEXT',
    'date': 'TEXT', 'datetime': 'TEXT', 'timestamp': 'TEXT',
    'float': 'REAL', 'double': 'REAL', 'decimal': 'REAL', 'numeric': 'REAL', 'money': 'REAL',
    'boolean': 'INT', 'bool': 'INT',
}


def parse_ascii_table(block_lines, start):
    """从 start 行（+---+ 边框）开始解析一个 ASCII 表，返回 (headers, rows, 结束行)"""
    rows = []
    i = start
    n = len(block_lines)
    while i < n:
        line = block_lines[i]
        if line.startswith('+'):
            i += 1
            continue
        if line.startswith('|'):
            cells = [c.strip() for c in line.strip('|').split('|')]
            rows.append(cells)
            i += 1
            continue
        break
    if not rows:
        return None, [], i
    return rows[0], rows[1:], i


def sqlite_type(t):
    t = t.lower().strip()
    base = re.split(r'[(\s]', t)[0]
    return TYPE_MAP.get(base, 'TEXT')


def sql_literal(v):
    v = v.strip()
    if v.lower() in ('null', ''):
        return 'NULL'
    if re.fullmatch(r'-?\d+', v):
        return v
    if re.fullmatch(r'-?\d+\.\d+', v):
        return v
    return "'" + v.replace("'", "''") + "'"


def parse_problem(q):
    """解析一题，返回 dict(schema, data, output, notes)"""
    notes = []
    schemas = {}   # table -> CREATE 语句
    inserts = {}   # table -> [INSERT 语句]
    output = None
    text = q.get('text', '')

    # 1) 表结构：pre 块中含 Column Name 的 ASCII 表
    for block in q.get('pre_blocks', []):
        lines = [l for l in block.split('\n')]
        for i, line in enumerate(lines):
            if line.startswith('+') and i + 1 < len(lines) and 'Column Name' in lines[i + 1]:
                headers, rows, _ = parse_ascii_table(lines, i)
                if not headers:
                    continue
                cols = [(r[0], sqlite_type(r[1] if len(r) > 1 else 'text')) for r in rows if r and r[0]]
                # 表名：在该 pre 块前的 text 中寻找 "Table: Xxx" 过于复杂；
                # 由调用方按出现顺序对齐（LeetCode 惯例：text 里 Table: Name 与 pre 块顺序一致）
                schemas.setdefault('__order__', []).append(cols)

    # 表名按 text 中 "Table: Name" 出现顺序对齐
    table_names = re.findall(r'Table:\s*`?([A-Za-z_]\w*)`?', text)
    ordered = schemas.pop('__order__', [])
    tables = {}
    for idx, cols in enumerate(ordered):
        name = table_names[idx] if idx < len(table_names) else f'table{idx + 1}'
        tables[name] = cols

    # 2) 示例数据：LeetCode pre 块顺序 = schema 表（各表）→ Input 数据表（每个表一个）→ Output 表
    #    因此先收集全部数据表（含可选的 "Xxx table:" 标签），前 N 个归 Input，下一个归 Output
    pre = q.get('pre_blocks', [])
    data_blocks = pre[len(ordered):]
    found = []  # [(name_hint, headers, rows)]
    for b in data_blocks:
        lines = b.split('\n')
        name_hint = None
        i = 0
        while i < len(lines):
            line = lines[i]
            m = re.match(r'\s*([A-Za-z_]\w*)\s+table\s*:?\s*$', line)
            if m:
                name_hint = m.group(1)
                i += 1
                continue
            if line.startswith('+'):
                headers, rows, end = parse_ascii_table(lines, i)
                if headers and headers[0].lower() != 'column name':
                    found.append((name_hint, headers, rows))
                name_hint = None
                i = max(end, i + 1)
                continue
            i += 1
    n_input = len(tables)
    for idx, (hint, headers, rows) in enumerate(found):
        if idx < n_input:
            target = hint if hint in tables else list(tables)[idx]
            stmts = inserts.setdefault(target, [])
            for r in rows:
                vals = ', '.join(sql_literal(v) for v in r)
                stmts.append(f"INSERT INTO {target} ({', '.join(headers)}) VALUES ({vals});")
        elif output is None:
            output = {'headers': headers, 'rows': rows}

    if not tables:
        notes.append('NO_SCHEMA')
    if not inserts:
        notes.append('NO_DATA')
    if output is None:
        notes.append('NO_OUTPUT')

    schema_sql = []
    for name, cols in tables.items():
        col_def = ', '.join(f'{c} {t}' for c, t in cols)
        schema_sql.append(f'CREATE TABLE {name} ({col_def});')
    data_sql = []
    for name in tables:
        data_sql.extend(inserts.get(name, []))

    return {
        'schema': '\n'.join(schema_sql),
        'data': '\n'.join(data_sql),
        'output': output,
        'notes': notes,
    }


def main():
    src = os.path.join(DATA_DIR, 'leetcode_questions.json')
    dst = os.path.join(DATA_DIR, 'leetcode_parsed.json')
    questions = json.load(open(src, encoding='utf-8'))
    out = []
    from collections import Counter
    stat = Counter()
    for q in questions:
        parsed = parse_problem(q)
        item = {k: q[k] for k in ('frontend_id', 'slug', 'title', 'difficulty', 'text')}
        item.update(parsed)
        out.append(item)
        stat.update(parsed['notes'] or ['OK'])
    json.dump(out, open(dst, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'解析 {len(out)} 题 → {dst}')
    print(dict(stat))


if __name__ == '__main__':
    main()
