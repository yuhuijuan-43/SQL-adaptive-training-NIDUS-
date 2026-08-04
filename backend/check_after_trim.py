import json, re
qs = json.loads(re.search(r'(\[.*\])', open(r'E:\SQL自适应训练\questions.py', encoding='utf-8').read(), re.DOTALL).group(1))
missing = [q for q in qs if not q.get('expected_output') or q['expected_output'] == '(空结果)']
print(f'Missing output: {len(missing)}')
for q in missing[:10]:
    print(f'  {q["title"][:50]} | {q["correct_answer"][:80]}')