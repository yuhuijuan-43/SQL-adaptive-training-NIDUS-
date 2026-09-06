import json
import sys

slugs = sys.argv[1:]
data = json.load(open('data/leetcode_parsed.json', encoding='utf-8'))
for slug in slugs:
    q = next((x for x in data if x['slug'] == slug), None)
    if not q:
        print(f'== {slug} NOT FOUND')
        continue
    print(f"== {q['frontend_id']} {slug} [{q['difficulty']}]")
    print('-- SCHEMA:'); print(q['schema'])
    print('-- DATA:'); print(q['data'][:600])
    print('-- OUTPUT:', json.dumps(q['output'], ensure_ascii=False)[:260])
    txt = q['text'].replace('\n\n', '\n')
    print('-- TEXT:', txt[:900])
    print()
