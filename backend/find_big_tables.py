import json, re

path = r'E:\SQL自适应训练\questions.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
m = re.search(r'(\[.*\])', content, re.DOTALL)
qs = json.loads(m.group(1))

big = []
for q in qs:
    data = q.get('initial_data', '')
    if not data:
        continue
    inserts = [l for l in data.split('\n') if l.strip().upper().startswith('INSERT')]
    if len(inserts) > 10:
        total_rows = 0
        for ins in inserts:
            # Count rows in each INSERT (count parenthesized groups)
            rows = ins.count('(')
            total_rows += rows
        big.append((q['title'], len(inserts), total_rows, q.get('source', '')))

big.sort(key=lambda x: -x[2])
print(f'Questions with >10 INSERT rows: {len(big)}')
for title, n_ins, n_rows, src in big:
    print(f'  [{src:15s}] {n_ins} inserts, {n_rows} rows: {title[:60]}')