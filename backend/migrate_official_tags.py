"""一次性迁移：题库分类/难度对齐官方知识图谱结构（可幂等重跑）

- questions / exam_questions：category → 官方 29 标签，difficulty → 标签星级（1★简单/2★中等/3★困难）
- knowledge_nodes / knowledge_edges / question_knowledge：重建为官方结构（root + 7 大类 + 29 标签）
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from db import get_connection
from repositories import invalidate_graph_cache
from seeding import (OFFICIAL_TAGS, LEARNING_EDGES, STAR_TO_LEVEL,
                     TAG_DIFFICULTY, map_category)

conn = get_connection()

# 1. 题库与真题库：分类 → 官方标签，难度 → 星级难度
def migrate_table(table):
    rows = conn.execute(f'SELECT id, category, title FROM {table}').fetchall()
    for r in rows:
        tag = map_category(r['category'], r['title'])
        conn.execute(f'UPDATE {table} SET category=?, difficulty=? WHERE id=?',
                     (tag, TAG_DIFFICULTY[tag], r['id']))
    print(f'{table}: {len(rows)} 题已迁移')

migrate_table('questions')
migrate_table('exam_questions')

# 2. 重建知识图谱为官方结构
conn.execute('DELETE FROM question_knowledge')
conn.execute('DELETE FROM knowledge_edges')
conn.execute('DELETE FROM knowledge_nodes')

nodes = [('root', 'SQL知识图谱', '知识图谱根节点', '根', 0, 'fa-database')]
for top_id, (top_name, leaves) in OFFICIAL_TAGS.items():
    nodes.append((top_id, top_name, f'{top_name} 大类', top_name, 1, 'fa-folder-open'))
    for tag, name, stars in leaves:
        nodes.append((tag, name, f'{top_name} · {name}', top_name, STAR_TO_LEVEL[stars], 'fa-code'))
conn.executemany(
    'INSERT INTO knowledge_nodes (id,name,description,category,level,icon) VALUES (?,?,?,?,?,?)', nodes)

edges = [('root', top_id) for top_id in OFFICIAL_TAGS]
edges += [(top_id, tag) for top_id, (_, leaves) in OFFICIAL_TAGS.items() for tag, _, _ in leaves]
edges += LEARNING_EDGES
conn.executemany('INSERT INTO knowledge_edges (from_node,to_node) VALUES (?,?)', edges)

# 3. 全量重建 题目↔标签 映射
qs = conn.execute('SELECT id, category, title FROM questions').fetchall()
conn.executemany(
    'INSERT OR IGNORE INTO question_knowledge (question_id,node_id) VALUES (?,?)',
    [(r['id'], map_category(r['category'], r['title'])) for r in qs])

conn.commit()
invalidate_graph_cache()
print(f'图谱重建完成：{len(nodes)} 节点 / {len(edges)} 边 / {len(qs)} 题映射')
