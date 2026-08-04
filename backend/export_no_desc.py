import sqlite3
conn = sqlite3.connect('questions.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, source, category, difficulty, title, description, table_schema, initial_data FROM questions WHERE description IS NULL OR description = '' OR LENGTH(description) < 10 ORDER BY id").fetchall()
with open('../no_desc_questions.txt', 'w', encoding='utf-8') as f:
    for i, r in enumerate(rows):
        desc = r['description'] or ''
        f.write(f'--- #{i+1} ID={r["id"]} [{r["source"]}] {r["difficulty"]} ---\n')
        f.write(f'  标题: {r["title"]}\n')
        f.write(f'  当前描述({len(desc)}字): "{desc}"\n')
        schema = (r['table_schema'] or '')[:200]
        data = (r['initial_data'] or '')[:200]
        if schema: f.write(f'  表结构: {schema}\n')
        if data: f.write(f'  示例数据: {data}\n')
        f.write('\n')
print(f'Total: {len(rows)} questions exported')
conn.close()
