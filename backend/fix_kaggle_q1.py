import sqlite3, json, os

SRC_DB = 'E:/my normal txt/DigQuant/项目/SQL自适应训练/Kaggle题库/sql_practice.db'
DST_DB = 'E:/my normal txt/DigQuant/项目/SQL自适应训练/SQL自适应训练/backend/questions.db'

src = sqlite3.connect(SRC_DB)
dst = sqlite3.connect(DST_DB)

# ========== 处理 ID=1 ==========
qid = 1
answer_sql = "SELECT customer_id, age, city FROM customers ORDER BY age DESC;"
table_name = 'customers'

# 1. 取源数据前8行 + 后3行，生成示例数据预览
all_rows = src.execute(f'SELECT * FROM {table_name}').fetchall()
col_names = [d[1] for d in src.execute(f'PRAGMA table_info({table_name})')]
total = len(all_rows)

# 2. 生成预期输出 JSON
result = src.execute(answer_sql).fetchall()
out_cols = ['customer_id', 'age', 'city']
# result 只有 SELECT 的3列，取前8行+后3行，省略中间
n = len(result)
if n > 15:
    display_rows = [ [str(v) for v in row] for row in list(result[:8]) ]
    display_rows.append(["...", f"共{n}行，省略中间部分", "..."])
    display_rows += [ [str(v) for v in row] for row in list(result[-3:]) ]
else:
    display_rows = [ [str(v) for v in row] for row in result ]
expected_json = json.dumps({
    "headers": out_cols,
    "rows": display_rows
}, ensure_ascii=False)

# 3. 生成描述（含表格预览）
desc = f"""现有 customers 表，包含以下列：customer_id（客户ID）、gender（性别）、age（年龄）、city（城市）、signup_date（注册日期）、loyalty_member（是否忠诚会员）。

{chr(124)} {' | '.join(col_names)}
{chr(124)} {' | '.join(['---'] * len(col_names))}"""

# 前5行
for row in all_rows[:5]:
    desc += f"\n{chr(124)} {' | '.join(str(v) for v in row)}"
# 省略号
if total > 8:
    desc += f"\n{chr(124)} ...（共 {total} 行，省略中间部分）"
# 后3行
for row in all_rows[-3:]:
    desc += f"\n{chr(124)} {' | '.join(str(v) for v in row)}"

desc += f"""

请查询所有客户的 customer_id、age 和 city，按年龄降序排列。"""

# 4. 生成示例数据 INSERT（前3+后2行）
insert_sql = ""
sample_rows = list(all_rows[:3]) + list(all_rows[-2:])
vals_list = []
for row in sample_rows:
    vals = ', '.join(f"'{v}'" if isinstance(v, str) else str(v) for v in row)
    vals_list.append(f"({vals})")
insert_sql = f"INSERT INTO {table_name} ({', '.join(col_names)}) VALUES\n  " + ',\n  '.join(vals_list) + ";"

# 5. 写入数据库
dst.execute('''UPDATE questions SET
    description = ?,
    initial_data = ?,
    expected_output = ?
    WHERE id = ?''', (desc, insert_sql, expected_json, qid))
dst.commit()

print(f'=== ID={qid} 更新完成 ===')
print(f'描述长度: {len(desc)}字')
print(f'预期输出: {len(result)}行')
print(f'示例数据: {len(sample_rows)}行')
print()
print('--- 描述预览 ---')
print(desc[:500])
print('...')
print()
print('--- 预期输出 JSON (前200字) ---')
print(expected_json[:200])

src.close()
dst.close()
