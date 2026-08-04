import json, re, sqlite3

path = r'E:\SQL自适应训练\questions.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
m = re.search(r'(\[.*\])', content, re.DOTALL)
qs = json.loads(m.group(1))

def gen(schema, data, sql):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.create_function('CONCAT', 2, lambda a,b: str(a or '')+str(b or ''))
    conn.create_function('CONCAT', 3, lambda a,b,c: str(a or '')+str(b or '')+str(c or ''))
    conn.create_function('LEFT', 2, lambda s,n: str(s or '')[:int(n)])
    conn.create_function('LENGTH', 1, lambda s: len(str(s or '')))
    conn.create_function('REPLACE', 3, lambda s,f,t: str(s or '').replace(str(f or ''), str(t or '')))
    try:
        for s in re.split(r';\s*', schema.strip()):
            s = s.strip()
            if s and not s.startswith('--'): conn.execute(s)
        for s in re.split(r';\s*', data.strip()):
            s = s.strip()
            if s and not s.startswith('--'): conn.execute(s)
        try: cur = conn.execute(sql)
        except:
            sql2 = re.sub(r'> ALL\s*\(', '> (SELECT MAX(', sql)
            sql2 = re.sub(r'25000000\s*>=\s*ALL\s*\(', '25000000 >= (SELECT MAX(population) FROM (', sql2)
            sql2 = re.sub(r'population\s*>\s*ALL\s*\(', 'population > (SELECT MAX(population', sql2)
            cur = conn.execute(sql2)
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        if not rows: conn.close(); return None
        ws = [max(len(n), max((len(str(v) if v is not None else 'NULL') for v in [row[i] for row in rows]), default=0)) for i, n in enumerate(cols)]
        lines = [' | '.join(n.ljust(ws[i]) for i,n in enumerate(cols))]
        if len(cols) == 1:
            w = sum(ws) + 3 * (len(cols) - 1)
            half = w // 2
            lines.append('-' * half + '-+-' + '-' * (w - half - 3))
        else:
            lines.append('-+-'.join('-'*w for w in ws))
        for row in rows:
            vals = [str(row[i]) if row[i] is not None else 'NULL' for i in range(len(cols))]
            lines.append(' | '.join(v.ljust(ws[i]) for i,v in enumerate(vals)))
        conn.close(); return '\n'.join(lines)
    except: conn.close(); return None

def trim_to(data, sql, max_rows=10):
    """Keep up to max_rows per table, prioritizing rows that match WHERE conditions."""
    if not data: return data
    lines = [l.strip() for l in data.split(';') if l.strip()]
    
    # Extract important values from SQL
    important = set()
    for m in re.finditer(r"(['\"])([^'\"]+?)\1", sql):
        important.add(m.group(2))
    
    tables = {}
    order = []
    for line in lines:
        m = re.match(r'INSERT\s+INTO\s+(\w+)', line, re.IGNORECASE)
        if m:
            t = m.group(1)
            if t not in tables:
                tables[t] = []
                order.append(t)
            tables[t].append(line)
    
    out = []
    for t in order:
        rows = tables[t]
        imp = [r for r in rows if any(v.replace("'","") in r for v in important)]
        oth = [r for r in rows if r not in imp]
        kept = imp[:max_rows]
        rem = max_rows - len(kept)
        if rem > 0: kept.extend(oth[:rem])
        out.extend(kept if kept else rows[:max_rows])
    
    return ';'.join(out) + ';'

# Process all oversized questions
trimmed = 0
regen = 0
for q in qs:
    data = q.get('initial_data', '')
    if not data: continue
    total = sum(line.count('(') for line in data.split(';') if line.strip().upper().startswith('INSERT'))
    if total <= 15: continue
    
    sql = q.get('correct_answer', '')
    schema = q.get('table_schema', '')
    new_data = trim_to(data, sql, 10)
    
    # Verify the trimmed data still produces correct output
    out = gen(schema, new_data, sql)
    if out:
        q['initial_data'] = new_data
        q['expected_output'] = out
        trimmed += 1
        regen += 1
    else:
        # Try with 15 rows
        new_data = trim_to(data, sql, 15)
        out = gen(schema, new_data, sql)
        if out:
            q['initial_data'] = new_data
            q['expected_output'] = out
            trimmed += 1
            regen += 1
        else:
            print(f'Cannot trim: {q["title"][:50]}')

print(f'Trimmed: {trimmed}, Regenerated: {regen}')

big = sum(1 for q in qs if sum(line.count('(') for line in (q.get('initial_data','') or '').split(';') if line.strip().upper().startswith('INSERT')) > 15)
print(f'Still >15 rows: {big}')

missing = sum(1 for q in qs if not q.get('expected_output') or q['expected_output'] == '(空结果)')
print(f'Missing output: {missing}')

with open(path, 'w', encoding='utf-8') as f:
    f.write('[\n')
    for i, q in enumerate(qs):
        f.write(json.dumps(q, ensure_ascii=False, indent=4))
        if i < len(qs)-1: f.write(',\n')
        else: f.write('\n')
    f.write(']\n')
print('Done.')