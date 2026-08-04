import json, re

path = r'E:\SQL自适应训练\questions.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
m = re.search(r'(\[.*\])', content, re.DOTALL)
qs = json.loads(m.group(1))

empty = [q for q in qs if q.get('expected_output') == '(空结果)']
total_no_data = [q for q in qs if not q.get('initial_data')]

print(f'Total questions: {len(qs)}')
print(f'Expected output is "(空结果)": {len(empty)}')
print(f'Missing initial_data: {len(total_no_data)}')

print('\n=== Questions with (空结果) ===')
for q in empty:
    print(f'\n[{q["source"]:15s}] {q["title"][:60]}')
    print(f'  SQL: {q["correct_answer"][:120]}')
    if q.get('initial_data'):
        print(f'  data: {q["initial_data"][:100]}...')
    else:
        print(f'  NO DATA')

print('\n=== Questions missing initial_data ===')
for q in total_no_data:
    print(f'\n[{q["source"]:15s}] {q["title"][:60]}')
    print(f'  SQL: {q["correct_answer"][:120]}')