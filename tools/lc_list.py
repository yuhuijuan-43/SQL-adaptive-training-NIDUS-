import json
import sys

data = json.load(open('data/leetcode_parsed.json', encoding='utf-8'))
diff = sys.argv[1] if len(sys.argv) > 1 else None
for q in data:
    if diff and q['difficulty'] != diff:
        continue
    n_tables = q['schema'].count('CREATE TABLE')
    n_ins = q['data'].count('INSERT')
    print(f"{q['frontend_id']:>5} {q['difficulty']:<7} tables={n_tables} ins={n_ins:>2}  {q['slug']}")
