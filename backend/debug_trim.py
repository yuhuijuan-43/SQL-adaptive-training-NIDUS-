import json, re
qs = json.loads(re.search(r'(\[.*\])', open(r'E:\SQL自适应训练\questions.py', encoding='utf-8').read(), re.DOTALL).group(1))
for q in qs:
    data = q.get('initial_data', '')
    if not data: continue
    total = sum(line.count('(') for line in data.split(';') if line.strip().upper().startswith('INSERT'))
    if total > 10:
        print(f'{q["title"][:40]} total={total}')
        print(f'  first 200 chars: {data[:200]}')
        print()
        break