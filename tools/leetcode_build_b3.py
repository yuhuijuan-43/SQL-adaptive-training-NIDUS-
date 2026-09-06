"""批次2：函数+子查询组 LeetCode 填空题生成器（窗口函数/子查询/聚合）。

复用 leetcode_build.py 的机制：
  1. 参考答案在题目环境中可执行（judge 自检）
  2. 参考答案结果与官方示例 Output 一致（数值感知比对：4.0 与 '4.00' 视为相等）

输出 data/batches/b3_lc_fill.json（配合手写选择题一起导入）。
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
 # ---------------- 窗口函数 ----------------
 'rank-scores': (
  'window_func', '【填空】分数排名（蓝客178）',
  '表 Scores(id, score)。\n'
  '请为每个分数输出 score 和 rank：分数降序排名，相同分数名次相同且不留空位\n'
  '（如 4.00,4.00 都是第 1 名，下一个是第 2 名）。结果按分数降序。',
  'SELECT score, DENSE_RANK() OVER (ORDER BY score DESC) AS "rank" FROM Scores ORDER BY score DESC',
  'DENSE_RANK() OVER (ORDER BY score DESC) 按分数降序生成连续排名；'
  'RANK 会跳号、ROW_NUMBER 不并列，本题要求并列不跳号，必须用 DENSE_RANK。'),
 'consecutive-numbers': (
  'window_func', '【填空】至少连续三次的数字（蓝客180）',
  '表 Logs(id, num)，id 递增。\n'
  '请查询至少连续出现三次的数字 num（输出列 ConsecutiveNums，每个数字只输出一次），结果顺序不限。',
  "SELECT DISTINCT num AS ConsecutiveNums FROM ("
  "SELECT num, LAG(num, 1) OVER (ORDER BY id) AS p1, LAG(num, 2) OVER (ORDER BY id) AS p2 FROM Logs"
  ") WHERE num = p1 AND num = p2",
  'LAG(num,1)/LAG(num,2) 把前 1 行、前 2 行的 num 拉到当前行；当前行与前两行都相等即连续出现三次；'
  'DISTINCT 保证每个数字只输出一次。'),
 'department-top-three-salaries': (
  'window_func', '【填空】部门工资前三高（蓝客185）',
  '表 Employee(id, name, salary, departmentId)、Department(id, name)。\n'
  '请查询每个部门工资前三高的员工：输出 Department、Employee、Salary；\n'
  '并列名次不影响入选（同一部门最多 3 人入榜可能因并列多于 3 人），结果顺序不限。',
  "SELECT Department, Employee, Salary FROM ("
  "SELECT d.name AS Department, e.name AS Employee, e.salary AS Salary, "
  "DENSE_RANK() OVER (PARTITION BY e.departmentId ORDER BY e.salary DESC) AS rk "
  "FROM Employee e JOIN Department d ON e.departmentId = d.id"
  ") WHERE rk <= 3",
  'DENSE_RANK() OVER (PARTITION BY departmentId ...) 在每个部门内部独立排名，'
  '并列不跳号；外层取 rk<=3 即部门前三。'),
 'human-traffic-of-stadium': (
  'window_func', '【填空】体育馆人流量（蓝客601）',
  '表 Stadium(id, visit_date, people)。\n'
  '请查询这样的日期记录：该记录人流量大（people >= 100），且它和相邻记录构成至少三个\n'
  '「人流量都 >= 100 的连续 id」（如 id 5、6、7 三行都 >=100，则三行都输出）。\n'
  '输出 id、visit_date、people，结果按 id 升序。',
  "SELECT id, visit_date, people FROM ("
  "SELECT id, visit_date, people, "
  "LAG(id, 1) OVER (ORDER BY id) AS p1, LAG(people, 1) OVER (ORDER BY id) AS pv1, "
  "LAG(id, 2) OVER (ORDER BY id) AS p2, LAG(people, 2) OVER (ORDER BY id) AS pv2, "
  "LEAD(id, 1) OVER (ORDER BY id) AS n1, LEAD(people, 1) OVER (ORDER BY id) AS nv1, "
  "LEAD(id, 2) OVER (ORDER BY id) as n2, LEAD(people, 2) OVER (ORDER BY id) AS nv2 "
  "FROM Stadium"
  ") WHERE people >= 100 AND ("
  "(id - p1 = 1 AND p1 - p2 = 1 AND pv1 >= 100 AND pv2 >= 100) "
  "OR (n1 - id = 1 AND id - p1 = 1 AND nv1 >= 100 AND pv1 >= 100) "
  "OR (n2 - n1 = 1 AND n1 - id = 1 AND nv1 >= 100 AND nv2 >= 100)) ORDER BY id",
  'LAG/LEAD 把前两行、后两行的 id 和 people 拉到当前行；当前行作为连续三组的'
  '起点/中间点/终点三种情况分别判断，且三行的 people 都必须 >= 100。'),
 'last-person-to-fit-in-the-bus': (
  'window_func', '【填空】最后一个能上巴士的人（蓝客1204）',
  '表 Queue(person_id, person_name, weight, turn)，turn 是上车顺序。\n'
  '乘客按 turn 顺序依次上车，累计体重一旦超过 1000 就不再让后面的人上。\n'
  '请查询最后一个成功上车的人的姓名（输出列 person_name）。',
  "SELECT person_name FROM ("
  "SELECT person_name, SUM(weight) OVER (ORDER BY turn) AS total FROM Queue"
  ") WHERE total <= 1000 ORDER BY total DESC LIMIT 1",
  'SUM(weight) OVER (ORDER BY turn) 生成按上车顺序的累计体重；'
  '累计 <=1000 中 total 最大的一条就是最后一个上车的人。'),
 'product-price-at-a-given-date': (
  'window_func', '【填空】指定日期的产品价格（蓝客1164）',
  '表 Products(product_id, new_price, change_date)，每行是一次改价。\n'
  '请查询每个产品在 2019-08-16 这一天的价格 price：取该日期之前（含当天）最近一次改价；\n'
  '若该产品在此之前从未改价，价格为 10。输出 product_id、price，结果顺序不限。',
  "SELECT p.product_id, COALESCE(t.new_price, 10) AS price FROM ("
  "SELECT DISTINCT product_id FROM Products"
  ") p LEFT JOIN ("
  "SELECT product_id, new_price, ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY change_date DESC) AS rn "
  "FROM Products WHERE change_date <= '2019-08-16'"
  ") t ON p.product_id = t.product_id AND t.rn = 1",
  'ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY change_date DESC) 给截止日期前的改价记录'
  '按时间倒序编号，rn=1 即最近一次价格；从未改价的产品用 COALESCE 补默认价 10。'),

 # ---------------- 标量子查询 ----------------
 'nth-highest-salary': (
  'subquery_scalar', '【填空】第二高的工资（蓝客177）',
  '表 Employee(id, salary)。\n'
  '请查询第二高的工资（输出列名 SecondHighestSalary）；如果不存在，输出一行 NULL。\n'
  '要求：整条查询无论是否存在结果都恰好返回一行。',
  "SELECT (SELECT DISTINCT salary FROM Employee ORDER BY salary DESC LIMIT 1 OFFSET 1) AS SecondHighestSalary",
  '标量子查询放在 SELECT 列表里：内层 ORDER BY+LIMIT/OFFSET 取第 2 高；'
  '内层无结果时返回 NULL，外层仍输出一行——这正是标量子查询「单行单列」的用途。'),
 'rising-temperature': (
  'subquery_scalar', '【填空】气温上升的日期（蓝客197）',
  '表 Weather(id, recordDate, temperature)，日期可能不连续。\n'
  '请查询比前一天（recordDate 前一天）气温更高的日期 id，结果顺序不限。',
  "SELECT w.id FROM Weather w "
  "WHERE w.temperature > (SELECT t.temperature FROM Weather t WHERE t.recordDate = date(w.recordDate, '-1 day'))",
  '相关子查询：对每一行 w，子查询去找「w 的前一个日期」的温度；'
  '找不到时子查询返回 NULL，比较结果为假自动排除，天然处理了日期不连续的情况。'),
 'customers-who-bought-all-products': (
  'subquery_scalar', '【填空】买齐所有商品的客户（蓝客1045）',
  '表 Customer(customer_id, product_key) 是购买记录，Product(product_key) 是商品清单。\n'
  '请查询购买了 Product 表中所有商品的 customer_id，结果顺序不限。',
  "SELECT customer_id FROM Customer GROUP BY customer_id "
  "HAVING COUNT(DISTINCT product_key) = (SELECT COUNT(*) FROM Product)",
  '标量子查询 (SELECT COUNT(*) FROM Product) 返回商品总数，'
  '与每位客户购买的不同商品数比较——买齐即相等；这种「总数=子查询计数」是关系除法的经典写法。'),

 # ---------------- 列子查询 ----------------
 'department-highest-salary': (
  'subquery_column', '【填空】部门最高工资（蓝客184）',
  '表 Employee(id, name, salary, departmentId)、Department(id, name)。\n'
  '请查询每个部门工资最高的员工：输出 Department、Employee、Salary；并列最高都要输出，结果顺序不限。',
  "SELECT d.name AS Department, e.name AS Employee, e.salary AS Salary "
  "FROM Employee e JOIN Department d ON e.departmentId = d.id "
  "WHERE (e.departmentId, e.salary) IN (SELECT departmentId, MAX(salary) FROM Employee GROUP BY departmentId)",
  '子查询按部门分组返回 (departmentId, MAX(salary)) 组合，'
  '外层用 (列, 列) IN (两列子查询) 行值匹配部门+最高工资；并列最高的行都能匹配上。'),
 'product-sales-analysis-iii': (
  'subquery_column', '【填空】产品首次销售的年份（蓝客1070）',
  '表 Sales(sale_id, product_id, year, quantity, price)。\n'
  '请查询每个产品第一次销售当年的记录：输出 product_id、first_year、quantity、price，结果顺序不限。',
  "SELECT product_id, year AS first_year, quantity, price FROM Sales "
  "WHERE (product_id, year) IN (SELECT product_id, MIN(year) FROM Sales GROUP BY product_id)",
  '子查询返回每个产品的 (product_id, MIN(year))，外层 (product_id, year) IN 行值匹配即首次销售记录。'),
 'managers-with-at-least-5-direct-reports': (
  'subquery_column', '【填空】至少有 5 名下属的经理（蓝客570）',
  '表 Employee(id, name, department, managerId)，managerId 为 NULL 表示没有上级。\n'
  '请查询直接下属至少 5 人的员工姓名 name，结果顺序不限。',
  "SELECT name FROM Employee WHERE id IN "
  "(SELECT managerId FROM Employee GROUP BY managerId HAVING COUNT(*) >= 5)",
  '子查询按 managerId 分组统计每组人数，HAVING 筛出下属>=5 的经理 id；'
  '外层 id IN (...) 找出这些经理的名字。'),

 # ---------------- 表子查询 / EXISTS ----------------
 'game-play-analysis-iv': (
  'subquery_table', '【填空】次日留存比例（蓝客550）',
  '表 Activity(player_id, device_id, event_date, games_played)。\n'
  '安装日期定义为首日登录。请查询「首次登录后第二天也登录过」的玩家占全部玩家的比例，\n'
  '输出列 fraction，四舍五入保留两位小数。',
  "SELECT ROUND(1.0 * COUNT(*) / (SELECT COUNT(DISTINCT player_id) FROM Activity), 2) AS fraction "
  "FROM Activity WHERE (player_id, date(event_date, '+1 day')) IN (SELECT player_id, event_date FROM Activity)",
  '分母用标量子查询统计全部玩家数；分子统计「(玩家, 次日) 也出现在登录表里」的行；'
  '1.0 * 保证浮点除法避免整数除法截断。'),
 'immediate-food-delivery-ii': (
  'subquery_table', '【填空】首次订单即时配送比例（蓝客1174）',
  '表 Delivery(delivery_id, customer_id, order_date, customer_pref_delivery_date)。\n'
  '首单定义为客户最早的 order_date。请查询首单中「期望配送日等于下单日」的比例，\n'
  '输出列 immediate_percentage，四舍五入保留两位小数。',
  "SELECT ROUND(100.0 * COUNT(*) / (SELECT COUNT(DISTINCT customer_id) FROM Delivery), 2) AS immediate_percentage FROM ("
  "SELECT customer_id, order_date, customer_pref_delivery_date FROM Delivery "
  "WHERE (customer_id, order_date) IN (SELECT customer_id, MIN(order_date) FROM Delivery GROUP BY customer_id)"
  ") WHERE order_date = customer_pref_delivery_date",
  'FROM 后的派生表先取出每位客户的首单（行值 IN 匹配 MIN(order_date)），'
  '外层再统计其中即时配送的比例；分母用标量子查询取客户总数。'),
 'investments-in-2016': (
  'subquery_table', '【填空】2016 年投资额（蓝客585）',
  '表 Insurance(pid, tiv_2015, tiv_2016, lat, lon)。\n'
  '请对满足以下两个条件的保单求 2016 年投资额之和（列名 tiv_2016，保留两位小数）：\n'
  '1) 2015 年投资额 tiv_2015 与其他至少一张保单相同；\n'
  '2) 所在城市坐标 (lat, lon) 与任何其他保单都不同。',
  "SELECT ROUND(SUM(tiv_2016), 2) AS tiv_2016 FROM Insurance i "
  "WHERE EXISTS (SELECT 1 FROM Insurance j WHERE j.tiv_2015 = i.tiv_2015 AND j.pid <> i.pid) "
  "AND NOT EXISTS (SELECT 1 FROM Insurance k WHERE k.lat = i.lat AND k.lon = i.lon AND k.pid <> i.pid)",
  'EXISTS：存在其他 2015 年投资额相同的保单；NOT EXISTS：不存在坐标相同的其他保单；'
  '两个条件同时满足才计入求和。'),

 # ---------------- IN 子查询 ----------------
 'tree-node': (
  'subquery_in', '【填空】树的节点类型（蓝客608）',
  '表 Tree(id, p_id)，p_id 指向父节点，根节点 p_id 为 NULL。\n'
  '请给每个节点输出 id 和 type：无父节点为 Root、没有孩子的为 Leaf、其余为 Inner。结果顺序不限。\n'
  '注意：子查询结果里含 NULL 时 NOT IN 的行为。',
  "SELECT id, CASE WHEN p_id IS NULL THEN 'Root' "
  "WHEN id NOT IN (SELECT p_id FROM Tree WHERE p_id IS NOT NULL) THEN 'Leaf' "
  "ELSE 'Inner' END AS type FROM Tree",
  'NOT IN 遇到 NULL 是经典陷阱：子查询结果含 NULL 时 x NOT IN (...) 永远不为真；'
  '必须先在子查询里过滤 NULL（WHERE p_id IS NOT NULL）再判断哪些 id 没有孩子。'),
 'sales-analysis-iii': (
  'subquery_in', '【填空】只在春季卖出的产品（蓝客1084）',
  '表 Sales(seller_id, product_id, buyer_id, sale_date, quantity, price)、Product(product_id, product_name, unit_price)。\n'
  '请查询只在 2019 年春季（2019-01-01 至 2019-03-31，含边界）卖出过的产品，\n'
  '输出 product_id、product_name，结果顺序不限。',
  "SELECT product_id, product_name FROM Product "
  "WHERE product_id NOT IN (SELECT product_id FROM Sales "
  "WHERE sale_date NOT BETWEEN '2019-01-01' AND '2019-03-31')",
  '「只在春季卖出」= 排除掉在春季之外还有销售记录的产品；'
  'NOT IN 子查询返回出界销售的产品号，外层取反。'),
 'employees-whose-manager-left-the-company': (
  'subquery_in', '【填空】上级已离职的员工（蓝客1978）',
  '表 Employees(employee_id, name, manager_id, salary)，manager_id 为 NULL 表示没有上级。\n'
  '请查询工资低于 30000 且上级不在本公司（manager_id 不指向任何现有员工）的员工 employee_id，结果顺序不限。',
  "SELECT employee_id FROM Employees WHERE salary < 30000 "
  "AND manager_id NOT IN (SELECT employee_id FROM Employees)",
  '子查询返回所有在职员工的 employee_id（不含 NULL，NOT IN 安全）；'
  'manager_id 不在其中即上级已离职；manager_id 为 NULL 的行经 NOT IN 比较得 NULL 被自然排除。'),
 'customers-who-never-order': (
  'subquery_in', '【填空】从未下单的客户（蓝客183）',
  '表 Customers(id, name)、Orders(id, customerId)。\n'
  '请查询从未下过单的客户姓名（输出列名 Customers），结果顺序不限。',
  "SELECT name AS Customers FROM Customers "
  "WHERE id NOT IN (SELECT customerId FROM Orders)",
  '子查询返回所有下过单的客户 id，外层 NOT IN 取反即从未下单的客户——NOT IN 最典型的用法。'),

 # ---------------- 聚合函数 ----------------
 'odd-and-even-transactions': (
  'aggregate_func', '【填空】奇偶金额分组求和（蓝客3220）',
  '表 transactions(transaction_id, amount, transaction_date)。\n'
  '请按日期统计：奇数金额之和 odd_sum、偶数金额之和 even_sum（没有记 0），\n'
  '输出 transaction_date、odd_sum、even_sum，结果按日期升序。',
  "SELECT transaction_date, "
  "SUM(CASE WHEN amount % 2 = 1 THEN amount ELSE 0 END) AS odd_sum, "
  "SUM(CASE WHEN amount % 2 = 0 THEN amount ELSE 0 END) AS even_sum "
  "FROM transactions GROUP BY transaction_date ORDER BY transaction_date",
  '聚合函数里嵌 CASE WHEN 做条件求和：amount 是奇数计入 odd_sum、偶数计入 even_sum；'
  'ELSE 0 保证某类不存在时合计为 0 而不是 NULL。'),
 'average-time-of-process-per-machine': (
  'aggregate_func', '【填空】每台机器的平均处理时长（蓝客1661）',
  '表 Activity(machine_id, process_id, activity_type, timestamp)，每行是 start 或 end 事件。\n'
  '处理时长 = end 时间戳 - start 时间戳。请查询每台机器所有进程的平均处理时长，\n'
  '输出 machine_id、processing_time，四舍五入保留三位小数，结果顺序不限。',
  "SELECT machine_id, ROUND(AVG(end_ts - start_ts), 3) AS processing_time FROM ("
  "SELECT machine_id, process_id, "
  "MAX(CASE WHEN activity_type = 'start' THEN timestamp END) AS start_ts, "
  "MAX(CASE WHEN activity_type = 'end' THEN timestamp END) AS end_ts "
  "FROM Activity GROUP BY machine_id, process_id"
  ") GROUP BY machine_id",
  'MAX(CASE WHEN ... THEN timestamp END) 把 start/end 事件透视为两列，'
  '派生表里先得到每个进程的时长，外层再 AVG 求机器平均——聚合嵌套必须分两层做。'),
 'queries-quality-and-percentage': (
  'aggregate_func', '【填空】查询质量与差评率（蓝客1211）',
  '表 Queries(query_name, result, position, rating)。\n'
  'quality = rating 与 position 之比的平均值；poor_query_percentage = rating 低于 3 的比例（百分数）。\n'
  '请按 query_name 分组，输出 query_name、quality、poor_query_percentage，均保留两位小数，结果顺序不限。',
  "SELECT query_name, ROUND(AVG(rating * 1.0 / position), 2) AS quality, "
  "ROUND(AVG(CASE WHEN rating < 3 THEN 1 ELSE 0 END) * 100, 2) AS poor_query_percentage "
  "FROM Queries GROUP BY query_name",
  'rating * 1.0 / position 先转浮点再除，避免整数除法截断；'
  'AVG(CASE WHEN rating<3 THEN 1 ELSE 0 END) 把布尔统计转成 0/1 平均值再乘 100 得百分比。'),
 'count-salary-categories': (
  'aggregate_func', '【填空】工资区间人数统计（蓝客1907）',
  '表 Accounts(account_id, income)。\n'
  '请统计三个工资区间的账户数（输出列 category、accounts_count）：\n'
  'Low Salary：income < 20000；Average Salary：20000 <= income <= 50000；High Salary：income > 50000。',
  "SELECT 'Low Salary' AS category, COUNT(*) AS accounts_count FROM Accounts WHERE income < 20000 "
  "UNION ALL SELECT 'Average Salary', COUNT(*) FROM Accounts WHERE income BETWEEN 20000 AND 50000 "
  "UNION ALL SELECT 'High Salary', COUNT(*) FROM Accounts WHERE income > 50000",
  '三个区间分别统计再 UNION ALL 拼接；COUNT(*) 数的是行数，空区间自然得 0。'),
}

TAG_DIFFICULTY = {
    'aggregate_func': 'medium', 'cast_func': 'medium', 'window_func': 'hard',
    'subquery_scalar': 'medium', 'subquery_column': 'medium',
    'subquery_table': 'hard', 'subquery_in': 'hard',
}


def vals_equal(a, b):
    if a == b:
        return True
    if isinstance(a, str) and isinstance(b, str) and a.lower() == b.lower() == 'null':
        return True
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return False


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


def verify(q, ref_sql):
    out = q.get('output')
    if not out:
        return '无 Output 可校验'
    conn, rows, cols = run_sql(q['schema'], q['data'], ref_sql)
    conn.close()
    actual = [tuple(norm(v) for v in r) for r in rows]
    expected = [tuple(str(v) for v in r) for r in out['rows']]
    if len(actual) != len(expected):
        return f'与官方示例不符：行数 预期 {len(expected)} 实际 {len(actual)}：{actual[:4]}'
    used = [False] * len(expected)
    for a in actual:
        hit = False
        for i, e in enumerate(expected):
            if not used[i] and len(e) == len(a) and all(vals_equal(x, y) for x, y in zip(a, e)):
                used[i] = True
                hit = True
                break
        if not hit:
            return f'与官方示例不符：多出/不匹配行 {a}，预期集合 {expected[:5]}'
    return None


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
        v = verify(q, ref_sql)
        if v:
            errors.append(f'{slug}: {v}')
            continue
        out.append(entry)
        print(f'OK  {slug} -> {cat}')
    path = os.path.join(DATA_DIR, 'batches', 'b3_lc_fill.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(out, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n生成 {len(out)} 题 -> {path}')
    if errors:
        print('\n失败项:')
        for e in errors:
            print(' -', e)
        sys.exit(1)


if __name__ == '__main__':
    main()
