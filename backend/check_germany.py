import json, re
qs = json.loads(re.search(r'(\[.*\])', open(r'E:\SQL自适应训练\questions.py', encoding='utf-8').read(), re.DOTALL).group(1))
for q in qs:
    if 'population of Germany' in q['title']:
        print('Title:', q['title'])
        print('Description:', repr(q.get('description', '')))
        print('表结构 in desc:', '表结构' in q.get('description', ''))
        break