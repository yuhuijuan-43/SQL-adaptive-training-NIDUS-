"""把选定的 LeetCode 题组装成系统填空题（中文题面 + 参考答案），并实判校验。

校验内容：
  1. 参考答案在题目环境中可执行（judge 自检）
  2. 参考答案的执行结果与 LeetCode 官方示例 Output 一致
     - SELECT 题：行集合比对（含 ORDER BY 的题按顺序比对）
     - 写操作题：执行后比对目标表全表内容与 Output 一致

输出 data/batches/b2_lc_fill.json（配合手工编写的选择题一起导入）。
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from sql_judge import judge  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

# slug: (category, title, description_zh, reference_sql, explanation_zh)
SPECS = {
 'swap-sex-of-employees': (
  'dml_update', '【填空】交换性别值（蓝客627）',
  '表 Salary(id, name, sex, salary)，sex 取值只有 \'m\'/\'f\'。\n'
  '请用一条 UPDATE 语句（不得借助临时表）把所有 \'f\' 改成 \'m\'、所有 \'m\' 改成 \'f\'。',
  "UPDATE Salary SET sex = CASE WHEN sex = 'f' THEN 'm' ELSE 'f' END",
  'CASE WHEN 按当前值决定新值：f→m、m→f，一条 UPDATE 完成全表交换。'),
 'fix-names-in-a-table': (
  'dml_update', '【填空】修复名字大小写（蓝客1667）',
  '表 Users(user_id, name)，name 由大小写字母组成。\n'
  '请用一条 UPDATE 语句把每个名字修复为：首字母大写、其余字母小写（如 aLice→Alice、bOB→Bob）。',
  "UPDATE Users SET name = UPPER(SUBSTR(name, 1, 1)) || LOWER(SUBSTR(name, 2))",
  'SUBSTR(name,1,1) 取首字母转大写，SUBSTR(name,2) 取剩余部分转小写，|| 拼接。'),
 'delete-duplicate-emails': (
  'dml_delete', '【填空】删除重复邮箱（蓝客196）',
  '表 Person(id, email)，email 可能重复。\n'
  '请写一条 DELETE 语句：删除所有重复邮箱，每个邮箱只保留 id 最小的那一行。',
  'DELETE FROM Person WHERE id NOT IN (SELECT MIN(id) FROM Person GROUP BY email)',
  '子查询按 email 分组找出每个邮箱的最小 id（要保留的行），其余行删除。'),
 'recyclable-and-low-fat-products': (
  'dml_select', '【填空】可回收且低脂的产品（蓝客1757）',
  '表 Products(product_id, low_fats, recyclable)，low_fats/recyclable 取值 Y/N。\n'
  '请查询：既是低脂（low_fats=Y）又可回收（recyclable=Y）的产品 id，结果顺序不限。',
  "SELECT product_id FROM Products WHERE low_fats = 'Y' AND recyclable = 'Y'",
  '两个条件必须同时成立，用 AND 连接。'),
 'find-customer-referee': (
  'dml_select', '【填空】推荐人不是 2 号客户的客户（蓝客584）',
  '表 Customer(id, name, referee_id)，referee_id 是推荐人 id，可能为 NULL。\n'
  '请查询：没有被推荐（referee_id 为 NULL）或推荐人 id 不等于 2 的客户姓名，结果顺序不限。',
  'SELECT name FROM Customer WHERE referee_id IS NULL OR referee_id <> 2',
  '经典 NULL 陷阱：NULL 与任何值比较结果都不是真，必须用 IS NULL 单独处理；'
  '只写 referee_id <> 2 会漏掉所有未被推荐的客户。'),
 'big-countries': (
  'dml_select', '【填空】大国筛选（蓝客595）',
  '表 World(name, continent, area, population, gdp)。\n'
  '大国定义：面积至少 3000000，或人口至少 25000000。\n'
  '请查询所有大国的 name、population、area，结果顺序不限。',
  'SELECT name, population, area FROM World WHERE area >= 3000000 OR population >= 25000000',
  '满足任一条件即算大国，用 OR 连接；注意输出列顺序为 name, population, area。'),
 'invalid-tweets': (
  'select_basic', '【填空】无效推文（蓝客1683）',
  '表 Tweets(tweet_id, content)。\n'
  '请查询：内容字符数严格大于 15 的推文 id（即无效推文），结果顺序不限。',
  'SELECT tweet_id FROM Tweets WHERE LENGTH(content) > 15',
  'LENGTH() 返回字符数；标准 SQL 对应函数为 CHAR_LENGTH/CHARACTER_LENGTH。'),
 'calculate-special-bonus': (
  'select_basic', '【填空】计算特殊奖金（蓝客1873）',
  '表 Employees(employee_id, name, salary)。\n'
  '奖金规则：employee_id 为奇数 且 姓名不以 M 开头 → 奖金等于全部工资；否则为 0。\n'
  '请查询每个员工的 employee_id 和 bonus（奖金），结果按 employee_id 升序。',
  "SELECT employee_id, CASE WHEN employee_id % 2 = 1 AND name NOT LIKE 'M%' THEN salary ELSE 0 END AS bonus "
  'FROM Employees ORDER BY employee_id',
  'CASE 表达式在 SELECT 列表中做条件计算；% 取模判断奇数，NOT LIKE \'M%\' 排除 M 开头。'),
 'triangle-judgement': (
  'select_basic', '【填空】三角形判定（蓝客610）',
  '表 Triangle(x, y, z)，每行是三条线段的长度。\n'
  '请对每行输出 x、y、z 及 triangle 列：能构成三角形输出 Yes，否则输出 No，结果顺序不限。',
  "SELECT x, y, z, CASE WHEN x + y > z AND x + z > y AND y + z > x THEN 'Yes' ELSE 'No' END AS triangle FROM Triangle",
  '三角形条件：任意两边之和大于第三边，三个不等式用 AND 同时满足。'),
 'not-boring-movies': (
  'where_basic', '【填空】有趣的电影（蓝客620）',
  '表 Cinema(id, movie, description, rating)。\n'
  '请查询：id 为奇数 且 description 不等于 \'boring\' 的电影（全部列），结果按 rating 降序。',
  "SELECT id, movie, description, rating FROM Cinema WHERE id % 2 = 1 AND description <> 'boring' ORDER BY rating DESC",
  '两个筛选条件用 AND；结果要求按评分降序，必须写 ORDER BY rating DESC。'),
 'patients-with-a-condition': (
  'where_basic', '【填空】查询 I 型糖尿病患者（蓝客1527）',
  '表 Patients(patient_id, patient_name, conditions)，conditions 是该患者所有病症的空格分隔列表，可能为 NULL。\n'
  'I 型糖尿病病症代码以 DIAB1 开头。请查询：患有任一以 DIAB1 开头病症的患者（全部列），结果顺序不限。',
  "SELECT patient_id, patient_name, conditions FROM Patients "
  "WHERE conditions LIKE 'DIAB1%' OR conditions LIKE '% DIAB1%'",
  '病症可能在列表开头（DIAB1%）或中间（% DIAB1%，前面有空格），两个 LIKE 用 OR 覆盖两种情况。'),
 'find-followers-count': (
  'group_by', '【填空】关注者数量统计（蓝客1729）',
  '表 Followers(user_id, follower_id)，每行表示 follower_id 关注了 user_id。\n'
  '请统计每个 user_id 的关注者数量 followers_count，结果按 user_id 升序。',
  'SELECT user_id, COUNT(follower_id) AS followers_count FROM Followers GROUP BY user_id ORDER BY user_id',
  '按 user_id 分组后 COUNT 计数；结果要求有序，补 ORDER BY user_id。'),
 'daily-leads-and-partners': (
  'group_by', '【填空】每日线索与合作商去重统计（蓝客1693）',
  '表 DailySales(date_id, make_name, lead_id, partner_id)。\n'
  '请按日期和品牌分组，统计每组不同的 lead_id 数量 unique_leads 和不同的 partner_id 数量 unique_partners，结果顺序不限。',
  'SELECT date_id, make_name, COUNT(DISTINCT lead_id) AS unique_leads, COUNT(DISTINCT partner_id) AS unique_partners '
  'FROM DailySales GROUP BY date_id, make_name',
  '同一线索/合作商在同一天同一品牌下可能重复出现，必须用 COUNT(DISTINCT 列) 去重计数。'),
 'number-of-unique-subjects-taught-by-each-teacher': (
  'group_by', '【填空】每位教师讲授的不同课程数（蓝客2356）',
  '表 Teacher(teacher_id, subject_id, dept_id)，同一教师可能在不同院系讲授同一门课。\n'
  '请统计每位教师讲授的不同课程数量 cnt，结果顺序不限。',
  'SELECT teacher_id, COUNT(DISTINCT subject_id) AS cnt FROM Teacher GROUP BY teacher_id',
  '同一课程在多院系重复记录，COUNT 必须配 DISTINCT subject_id。'),
 'find-total-time-spent-by-each-employee': (
  'group_by', '【填空】员工每日总工时（蓝客1741）',
  '表 Employees(emp_id, event_day, in_time, out_time)，每行是一次进出记录（分钟数）。\n'
  '请按天和员工分组，计算每人每天的总停留时间 total_time（= out_time - in_time 之和），结果顺序不限。',
  'SELECT event_day AS day, emp_id, SUM(out_time - in_time) AS total_time FROM Employees GROUP BY event_day, emp_id',
  '同一天同一员工可能有多条进出记录，先算每条时长再按 (event_day, emp_id) 分组求和。'),
 'duplicate-emails': (
  'having', '【填空】查找重复邮箱（蓝客182）',
  '表 Person(id, email)。\n'
  '请查询：出现过至少两次的邮箱地址（每个只输出一次），结果顺序不限。',
  'SELECT email FROM Person GROUP BY email HAVING COUNT(*) > 1',
  '去重输出用 GROUP BY；筛选分组后的统计条件（出现次数>1）必须用 HAVING，不能写在 WHERE 中。'),
 'classes-with-at-least-5-students': (
  'having', '【填空】至少有 5 名学生的班级（蓝客596）',
  '表 Courses(student, class)，同一学生可能在多个班级，同一班级也可能有重复记录。\n'
  '请查询：学生数至少为 5 的班级名（每个只输出一次），结果顺序不限。',
  'SELECT class FROM Courses GROUP BY class HAVING COUNT(DISTINCT student) >= 5',
  '按 class 分组，HAVING 筛选组内人数；DISTINCT 防止同一学生重复选课被重复计数。'),
 'actors-and-directors-who-cooperated-at-least-three-times': (
  'having', '【填空】合作至少三次的演员与导演（蓝客1050）',
  '表 ActorDirector(actor_id, director_id, timestamp)，timestamp 是主键。\n'
  '请查询：合作过至少 3 次的 (actor_id, director_id) 组合，结果顺序不限。',
  'SELECT actor_id, director_id FROM ActorDirector GROUP BY actor_id, director_id HAVING COUNT(*) >= 3',
  '按 (actor_id, director_id) 组合分组，HAVING COUNT(*) >= 3 筛选合作次数。'),
 'biggest-single-number': (
  'having', '【填空】只出现一次的最大数字（蓝客619）',
  '表 MyNumbers(num)，数字可能重复出现。\n'
  '请查询：只出现一次的数字中最大的那个（输出列名 num）；如果不存在，结果为 0 行，结果顺序不限。',
  'SELECT MAX(num) AS num FROM MyNumbers WHERE num IN (SELECT num FROM MyNumbers GROUP BY num HAVING COUNT(*) = 1)',
  '内层用 GROUP BY + HAVING COUNT(*)=1 找出只出现一次的数字，外层取 MAX；'
  '若没有符合条件的行，MAX 返回 NULL（单行），与 LeetCode 预期一致。'),
}

TAG_DIFFICULTY = {
    'dml_select': 'easy', 'dml_insert': 'easy', 'dml_update': 'easy', 'dml_delete': 'easy',
    'select_basic': 'easy', 'where_basic': 'easy', 'group_by': 'medium', 'having': 'hard',
}


def norm(v):
    if v is None:
        return 'Null'
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def run_sql(schema, data, sql):
    conn = sqlite3.connect(':memory:')
    conn.executescript(schema)
    if data.strip():
        conn.executescript(data)
    cur = conn.execute(sql)
    rows = [tuple(r) for r in cur.fetchall()]
    cols = [d[0] for d in (cur.description or [])]
    return conn, rows, cols


def verify(slug, q, ref_sql):
    """参考答案结果 vs LeetCode 示例 Output"""
    out = q.get('output')
    if not out:
        return '无 Output 可校验'
    conn, rows, cols = run_sql(q['schema'], q['data'], ref_sql)
    is_write = not cols
    if is_write:
        # 写操作：对单表题，比对执行后目标表全表内容
        table = q['schema'].split('CREATE TABLE ')[1].split(' ')[0]
        rows = [tuple(r) for r in conn.execute(f'SELECT * FROM {table}').fetchall()]
    conn.close()
    actual = sorted(tuple(norm(v) for v in r) for r in rows)
    expected = sorted(tuple(str(v) for v in r) for r in out['rows'])
    if actual == expected:
        return None
    return f'与官方示例不符：预期 {expected[:3]}... 实际 {actual[:3]}...'


def main():
    parsed = json.load(open(os.path.join(DATA_DIR, 'leetcode_parsed.json'), encoding='utf-8'))
    by_slug = {q['slug']: q for q in parsed}
    out, errors = [], []
    for slug, (cat, title, desc, ref_sql, expl) in SPECS.items():
        q = by_slug.get(slug)
        if not q:
            errors.append(f'{slug}: 未在解析结果中')
            continue
        diff = TAG_DIFFICULTY[cat]
        entry = {
            'source': f'蓝客#{q["frontend_id"]}',
            'category': cat,
            'difficulty': diff,
            'title': title,
            'description': desc + '\n\n（题目素材来源于蓝客题库，经翻译改写）',
            'table_schema': q['schema'],
            'initial_data': q['data'],
            'correct_answer': ref_sql,
            'explanation': expl,
            'options': '',
            'option_explanations': '',
            'expected_output': json.dumps(q['output'], ensure_ascii=False) if q['output'] else '',
            'pool': 'practice',
            'q_level': 'basic' if diff == 'easy' else 'advanced',
        }
        ok, _, err = judge(ref_sql, ref_sql, q['schema'], q['data'])
        if not ok:
            errors.append(f'{slug}: judge 自检失败 {err}')
            continue
        v = verify(slug, q, ref_sql)
        if v:
            errors.append(f'{slug}: {v}')
            continue
        out.append(entry)
        print(f'OK  {slug} -> {cat}')
    path = os.path.join(DATA_DIR, 'batches', 'b2_lc_fill.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(out, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n生成 {len(out)} 题 → {path}')
    if errors:
        print('\n失败项:')
        for e in errors:
            print(' -', e)
        sys.exit(1)


if __name__ == '__main__':
    main()
