"""种子数据：题库 + 真题库 + 知识图谱"""
import json
import os

from db import get_connection
from repositories import invalidate_graph_cache

def seed_knowledge_graph():
    conn = get_connection()
    needs_init = conn.execute('SELECT COUNT(*) FROM knowledge_nodes').fetchone()[0] == 0
    if needs_init:
        nodes = [
            ('select_basic','SELECT 基础查询','从单表中查询列','SELECT',0,'fa-table'),
            ('alias','别名 AS','为列或表取别名','SELECT',1,'fa-tag'),
            ('distinct','DISTINCT 去重','去除重复行','SELECT',1,'fa-eraser'),
            ('where_basic','WHERE 条件筛选','按条件过滤行','WHERE',1,'fa-filter'),
            ('order_by','ORDER BY 排序','对结果集排序','ORDER BY',1,'fa-sort'),
            ('where_andor','AND / OR 多条件','组合多个条件','WHERE',2,'fa-plus-circle'),
            ('where_like','LIKE 模糊查询','字符串模式匹配','WHERE',2,'fa-search'),
            ('where_null','NULL 值判断','IS NULL / IS NOT NULL','WHERE',2,'fa-question-circle'),
            ('where_in','IN 运算符','匹配值列表','WHERE',2,'fa-list-ul'),
            ('where_between','BETWEEN 范围查询','值区间筛选','WHERE',2,'fa-arrows-alt-h'),
            ('limit_offset','LIMIT / OFFSET 分页','限制返回行数','ORDER BY',2,'fa-cut'),
            ('aggregate_basic','聚合函数基础','COUNT/SUM/MAX/MIN','聚合',2,'fa-calculator'),
            ('group_by','GROUP BY 分组','按列分组聚合','聚合',3,'fa-object-group'),
            ('having','HAVING 过滤分组','过滤分组后结果','聚合',4,'fa-filter'),
            ('avg','AVG 平均值','计算均值','聚合',4,'fa-chart-line'),
            ('count_distinct','COUNT(DISTINCT)','去重计数','聚合',4,'fa-sort-numeric-up'),
            ('case_when','CASE WHEN 条件','条件分支逻辑','聚合',5,'fa-code-branch'),
            ('join_inner','INNER JOIN 内连接','等值连接两表','JOIN',2,'fa-link'),
            ('join_left','LEFT JOIN 左连接','保留左表全部记录','JOIN',3,'fa-arrow-right'),
            ('join_self','自连接','同一表连接自身','JOIN',3,'fa-redo'),
            ('join_multi','多表 JOIN','连续 JOIN 多表','JOIN',4,'fa-project-diagram'),
            ('join_full','FULL OUTER JOIN','全外连接模拟','JOIN',5,'fa-arrows-alt'),
            ('subquery_basic','子查询基础','WHERE 中子查询','子查询',2,'fa-indent'),
            ('subquery_exists','EXISTS 子查询','存在性检查','子查询',4,'fa-check-double'),
            ('subquery_all','ALL / ANY 子查询','多行比较','子查询',4,'fa-greater-than'),
            ('subquery_select','SELECT 中子查询','标量子查询','子查询',5,'fa-code'),
            ('cte','CTE (WITH)','公共表表达式','子查询',6,'fa-layer-group'),
        ]
        for n in nodes:
            conn.execute('INSERT INTO knowledge_nodes (id,name,description,category,level,icon) VALUES (?,?,?,?,?,?)', n)
        edges = [
            ('select_basic','alias'),('select_basic','distinct'),
            ('select_basic','where_basic'),('select_basic','order_by'),('select_basic','aggregate_basic'),
            ('where_basic','where_andor'),('where_basic','where_like'),('where_basic','where_null'),
            ('where_basic','where_in'),('where_basic','where_between'),
            ('order_by','limit_offset'),
            ('aggregate_basic','group_by'),
            ('group_by','having'),('group_by','avg'),('group_by','count_distinct'),('group_by','case_when'),
            ('select_basic','join_inner'),
            ('join_inner','join_left'),('join_inner','join_self'),
            ('join_left','join_multi'),('join_left','join_full'),
            ('select_basic','subquery_basic'),
            ('subquery_basic','subquery_exists'),('subquery_basic','subquery_all'),('subquery_basic','subquery_select'),
            ('subquery_select','cte'),
        ]
        for f,t in edges:
            conn.execute('INSERT INTO knowledge_edges (from_node,to_node) VALUES (?,?)', (f,t))
        qn = [
            (1,'select_basic'),(2,'select_basic'),
            (3,'where_basic'),(4,'where_andor'),(5,'order_by'),(6,'limit_offset'),
            (7,'aggregate_basic'),(7,'group_by'),(8,'avg'),(9,'having'),
            (10,'join_inner'),(11,'join_left'),(12,'subquery_basic'),(13,'subquery_exists'),
            (14,'aggregate_basic'),(15,'where_like'),(16,'distinct'),
            (17,'join_multi'),(18,'subquery_all'),(19,'aggregate_basic'),(20,'where_between'),
            (21,'order_by'),(22,'join_self'),(23,'having'),
            (24,'subquery_select'),(25,'alias'),(26,'where_in'),(27,'cte'),
            (28,'case_when'),(29,'join_full'),(30,'where_null'),(31,'count_distinct'),(32,'limit_offset'),
        ]
        for qid,nid in qn:
            conn.execute('INSERT OR IGNORE INTO question_knowledge (question_id,node_id) VALUES (?,?)', (qid,nid))
    # Auto-map ALL questions by their category field（仅在新题目出现时执行）
    total_q = conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    mapped_q = conn.execute('SELECT COUNT(DISTINCT question_id) FROM question_knowledge').fetchone()[0]
    if mapped_q < total_q:
        all_qs = conn.execute('SELECT id, category FROM questions').fetchall()
        cat_to_node = {
            '基础查询': 'select_basic', '条件筛选': 'where_basic',
            '排序分页': 'order_by', '聚合与分组': 'aggregate_basic',
            '多表连接': 'join_inner', '子查询与CTE': 'subquery_basic',
            '窗口函数': 'window', '日期处理': 'date', '字符串处理': 'string',
            # 新增 viz 分类标签映射
            'dml_select': 'select_basic', 'dml_insert': 'dml', 'dml_update': 'dml', 'dml_delete': 'dml',
            'ddl_create': 'select_basic', 'ddl_alter': 'select_basic', 'ddl_drop': 'select_basic',
            'ddl_truncate': 'select_basic', 'ddl_rename': 'select_basic', 'ddl_comment': 'select_basic',
            'string_func': 'string', 'numeric_func': 'aggregate_basic', 'aggregate_func': 'aggregate_basic',
            'cast_func': 'select_basic', 'window_func': 'window',
            'join_outer': 'join_left', 'join_cross': 'join_inner',
            'constraint_primary_key': 'select_basic', 'constraint_foreign_key': 'select_basic',
            'subquery_scalar': 'subquery_basic', 'subquery_column': 'subquery_basic',
            'subquery_table': 'subquery_basic', 'subquery_in': 'where_in',
            'where_basic': 'where_basic', 'having': 'having', 'group_by': 'group_by',
        }
        for r in all_qs:
            node_id = cat_to_node.get(r['category'], 'select_basic')
            conn.execute('INSERT OR IGNORE INTO question_knowledge (question_id,node_id) VALUES (?,?)', (r['id'], node_id))
    conn.commit()
    print("Knowledge graph seeded.")

def get_seed_questions():
    return [
        {"source": "curated", "category": "基础查询", "difficulty": "easy", "title": "查询所有员工",
         "description": "从 employees 表中查询所有列的所有记录。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT * FROM employees;",
         "explanation": "SELECT * FROM 表名 可以查询表中的所有列。",
         "options": "SELECT * FROM employees;|SELECT ALL FROM employees;|SELECT * FROM emp;|SHOW employees;",
         "option_explanations": "✓ SELECT * 可查询表中所有列。|✗ SELECT ALL 不是标准 SQL 语法。|✗ 表名错误，应为 employees。|✗ SHOW 是查看数据库的命令，非查询语句。"},
        {"source": "curated", "category": "基础查询", "difficulty": "easy", "title": "查询特定列",
         "description": "从 employees 表中查询所有员工的姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary FROM employees;",
         "explanation": "SELECT 列名1, 列名2 FROM 表名 可以查询指定列。",
         "options": "SELECT name, salary FROM employees;|SELECT * FROM employees;|SELECT name AND salary FROM employees;|SELECT name+salary FROM employees;",
         "option_explanations": "✓ 逗号分隔列名，查询 name 和 salary。|✗ * 查询所有列，未限定为特定列。|✗ AND 不能连接列名，应使用逗号。|✗ + 用于数值运算，不能连接列名。"},
        {"source": "curated", "category": "条件筛选", "difficulty": "easy", "title": "WHERE 条件筛选",
         "description": "从 employees 表中查询薪资大于 13000 的员工姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary FROM employees WHERE salary > 13000;",
         "explanation": "WHERE 子句用于筛选满足条件的记录。",
         "options": "SELECT name, salary FROM employees WHERE salary > 13000;|SELECT name, salary FROM employees HAVING salary > 13000;|SELECT name, salary FROM employees IF salary > 13000;|SELECT name, salary FROM employees WHERE salary > 13000;",
         "option_explanations": "✓ WHERE 按 salary>13000 过滤行。|✗ HAVING 用于分组后过滤，无 GROUP BY 时无效。|✗ IF 不是 SQL 条件关键字。|✗ 与第一选项相同，均为正确写法。"},
        {"source": "curated", "category": "条件筛选", "difficulty": "easy", "title": "AND 多条件查询",
         "description": "从 employees 表中查询技术部且薪资大于 14000 的员工姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary FROM employees WHERE department = '技术部' AND salary > 14000;",
         "explanation": "AND 用于同时满足多个条件。",
         "options": "SELECT name, salary FROM employees WHERE department = '技术部' AND salary > 14000;|SELECT name, salary FROM employees WHERE department = '技术部' OR salary > 14000;|SELECT name, salary FROM employees WHERE department = '技术部' && salary > 14000;|SELECT name, salary FROM employees WHERE department = '技术部', salary > 14000;",
         "option_explanations": "✓ AND 要求两个条件同时满足。|✗ OR 只需一个条件，可能查出其他部门。|✗ && 不是 SQL 标准逻辑运算符。|✗ 逗号不能连接 WHERE 条件。"},
        {"source": "curated", "category": "排序分页", "difficulty": "easy", "title": "ORDER BY 排序",
         "description": "从 employees 表中按薪资降序查询所有员工的姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary FROM employees ORDER BY salary DESC;",
         "explanation": "ORDER BY 列名 DESC 表示按该列降序排列，ASC 为升序（默认）。",
         "options": "SELECT name, salary FROM employees ORDER BY salary DESC;|SELECT name, salary FROM employees SORT BY salary DESC;|SELECT name, salary FROM employees ORDER BY salary;|SELECT name, salary FROM employees ORDER DESC salary;",
         "option_explanations": "✓ DESC 指定按薪资降序排列。|✗ SORT BY 不是标准 SQL 语法。|✗ 缺 DESC，默认升序排列。|✗ DESC 位置错误，应放在列名后。"},
        {"source": "curated", "category": "排序分页", "difficulty": "easy", "title": "LIMIT 限制结果数量",
         "description": "从 employees 表中查询薪资最高的前 3 名员工的姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary FROM employees ORDER BY salary DESC LIMIT 3;",
         "explanation": "LIMIT n 限制返回前 n 条记录，常与 ORDER BY 配合使用。",
         "options": "SELECT name, salary FROM employees ORDER BY salary DESC LIMIT 3;|SELECT TOP 3 name, salary FROM employees ORDER BY salary DESC;|SELECT name, salary FROM employees WHERE ROWNUM <= 3 ORDER BY salary DESC;|SELECT name, salary FROM employees ORDER BY salary DESC LIMIT 3;",
         "option_explanations": "✓ LIMIT 3 取薪资最高的前 3 条记录。|✗ TOP 3 是 SQL Server/MySQL 方言。|✗ ROWNUM 在 WHERE 之后执行，先筛选后排序。|✗ 与第一选项相同，均为正确写法。"},
        {"source": "curated", "category": "聚合与分组", "difficulty": "medium", "title": "COUNT 统计数量",
         "description": "统计 employees 表中每个部门的员工人数。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT department, COUNT(*) FROM employees GROUP BY department;",
         "explanation": "COUNT(*) 统计每组行数，GROUP BY 按部门分组。",
         "options": "SELECT department, COUNT(*) FROM employees GROUP BY department;|SELECT department, COUNT(*) FROM employees;|SELECT department, COUNT(department) FROM employees;|SELECT department, SUM(*) FROM employees GROUP BY department;",
         "option_explanations": "✓ COUNT(*) 统计每组行数，GROUP BY 分组。|✗ 无 GROUP BY，COUNT 会聚合整个表返回一条记录。|✗ COUNT(department) 不统计 NULL 值行。|✗ SUM(*) 无效，SUM 需要数值列。"},
        {"source": "curated", "category": "聚合与分组", "difficulty": "medium", "title": "AVG 求平均值",
         "description": "查询 employees 表中每个部门的平均薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT department, AVG(salary) FROM employees GROUP BY department;",
         "explanation": "AVG() 函数计算平均值，GROUP BY 按部门分组。",
         "options": "SELECT department, AVG(salary) FROM employees GROUP BY department;|SELECT department, AVG(salary) FROM employees;|SELECT department, AVG(salary) FROM employees GROUP BY department;|SELECT department, AVG(salary) AS avg_salary FROM employees GROUP BY department;",
         "option_explanations": "✓ AVG(salary) 计算平均薪资，GROUP BY 分组。|✗ 无 GROUP BY，AVG 返回整体平均值。|✗ 与第一选项相同，均为正确写法。|✗ AS avg_salary 仅添加别名，功能相同。"},
        {"source": "curated", "category": "聚合与分组", "difficulty": "medium", "title": "HAVING 过滤分组",
         "description": "查询 employees 中平均薪资大于 13000 的部门及其平均薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT department, AVG(salary) FROM employees GROUP BY department HAVING AVG(salary) > 13000;",
         "explanation": "HAVING 用于过滤分组后的结果，WHERE 不能用于聚合函数。",
         "options": "SELECT department, AVG(salary) FROM employees GROUP BY department HAVING AVG(salary) > 13000;|SELECT department, AVG(salary) FROM employees WHERE AVG(salary) > 13000 GROUP BY department;|SELECT department, AVG(salary) FROM employees GROUP BY department WHERE AVG(salary) > 13000;|SELECT department, AVG(salary) FROM employees HAVING AVG(salary) > 13000;",
         "option_explanations": "✓ HAVING 过滤平均薪资>13000 的分组。|✗ WHERE 中不能直接使用聚合函数 AVG。|✗ WHERE 不能放在 GROUP BY 之后。|✗ 缺少 GROUP BY，无法按部门分组。"},
        {"source": "curated", "category": "多表连接", "difficulty": "medium", "title": "INNER JOIN 内连接",
         "description": "查询每位员工的姓名及其所属部门名称。\n\n表结构：\nemployees(id, name, dept_id)\ndepartments(id, dept_name)",
         "table_schema": "employees(id INT, name VARCHAR(100), dept_id INT);\ndepartments(id INT, dept_name VARCHAR(50))",
         "initial_data": "INSERT INTO employees VALUES (1,'张三',1),(2,'李四',2),(3,'王五',1);\nINSERT INTO departments VALUES (1,'技术部'),(2,'市场部');",
         "correct_answer": "SELECT e.name, d.dept_name FROM employees e JOIN departments d ON e.dept_id = d.id;",
         "explanation": "INNER JOIN 返回两个表中匹配的行，ON 指定连接条件。",
         "options": "SELECT e.name, d.dept_name FROM employees e JOIN departments d ON e.dept_id = d.id;|SELECT e.name, d.dept_name FROM employees e, departments d WHERE e.dept_id = d.id;|SELECT name, dept_name FROM employees, departments;|SELECT e.name, d.dept_name FROM employees e INNER departments d ON e.dept_id = d.id;",
         "option_explanations": "✓ JOIN ON 正确连接员工与部门表。|✗ 隐式连接，WHERE 做关联条件亦可。|✗ 无连接条件，产生笛卡尔积（交叉连接）。|✗ INNER 后缺少 JOIN 关键字。"},
        {"source": "curated", "category": "多表连接", "difficulty": "medium", "title": "LEFT JOIN 左连接",
         "description": "查询所有员工及其部门名称，包括未分配部门的员工。\n\n表结构：\nemployees(id, name, dept_id)\ndepartments(id, dept_name)",
         "table_schema": "employees(id INT, name VARCHAR(100), dept_id INT);\ndepartments(id INT, dept_name VARCHAR(50))",
         "initial_data": "INSERT INTO employees VALUES (1,'张三',1),(2,'李四',2),(3,'王五',NULL);\nINSERT INTO departments VALUES (1,'技术部'),(2,'市场部');",
         "correct_answer": "SELECT e.name, d.dept_name FROM employees e LEFT JOIN departments d ON e.dept_id = d.id;",
         "explanation": "LEFT JOIN 返回左表所有记录，右表无匹配时显示 NULL。",
         "options": "SELECT e.name, d.dept_name FROM employees e LEFT JOIN departments d ON e.dept_id = d.id;|SELECT e.name, d.dept_name FROM employees e JOIN departments d ON e.dept_id = d.id;|SELECT e.name, d.dept_name FROM employees e RIGHT JOIN departments d ON e.dept_id = d.id;|SELECT e.name, d.dept_name FROM employees e LEFT OUTER departments d ON e.dept_id = d.id;",
         "option_explanations": "✓ LEFT JOIN 保留左表所有员工，包括无部门的王五。|✗ INNER JOIN 只返回匹配的行，王五将被排除。|✗ RIGHT JOIN 保留右表全部，语义相反。|✗ LEFT OUTER 后缺少 JOIN 关键字。"},
        {"source": "curated", "category": "子查询与CTE", "difficulty": "hard", "title": "子查询 IN",
         "description": "查询薪资高于所有员工平均薪资的员工姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary FROM employees WHERE salary > (SELECT AVG(salary) FROM employees);",
         "explanation": "子查询 (SELECT AVG(salary) FROM employees) 先计算平均薪资，外层查询筛选高于该值的员工。",
         "options": "SELECT name, salary FROM employees WHERE salary > (SELECT AVG(salary) FROM employees);|SELECT name, salary FROM employees WHERE salary > AVG(salary);|SELECT name, salary FROM employees HAVING salary > AVG(salary);|SELECT name, salary FROM employees WHERE salary > (SELECT salary FROM employees);",
         "option_explanations": "✓ 子查询计算平均薪资，外层 > 比较。|✗ AVG(salary) 不能直接在 WHERE 中使用。|✗ HAVING 用于分组后，此处无 GROUP BY。|✗ 子查询返回多行 salary，> 无法与多行比较。"},
        {"source": "curated", "category": "子查询与CTE", "difficulty": "hard", "title": "子查询 EXISTS",
         "description": "查询有员工的部门名称。\n\n表结构：\ndepartments(id, dept_name)\nemployees(id, name, dept_id)",
         "table_schema": "departments(id INT, dept_name VARCHAR(50));\nemployees(id INT, name VARCHAR(100), dept_id INT)",
         "initial_data": "INSERT INTO departments VALUES (1,'技术部'),(2,'市场部'),(3,'财务部');\nINSERT INTO employees VALUES (1,'张三',1),(2,'李四',2);",
         "correct_answer": "SELECT dept_name FROM departments d WHERE EXISTS (SELECT 1 FROM employees e WHERE e.dept_id = d.id);",
         "explanation": "EXISTS 检查子查询是否有返回结果，有则满足条件。",
         "options": "SELECT dept_name FROM departments d WHERE EXISTS (SELECT 1 FROM employees e WHERE e.dept_id = d.id);|SELECT dept_name FROM departments WHERE id IN (SELECT dept_id FROM employees);|SELECT dept_name FROM departments d WHERE d.id IN (SELECT e.dept_id FROM employees e);|SELECT dept_name FROM departments, employees;",
         "option_explanations": "✓ EXISTS 检查每个部门是否有员工存在。|✗ IN 也能实现相同功能，但 EXISTS 更高效。|✗ IN 也能实现，写法不同但功能相同。|✗ 无连接条件，产生笛卡尔积。"},
        {"source": "curated", "category": "聚合与分组", "difficulty": "medium", "title": "MAX/MIN 最大值最小值",
         "description": "查询 employees 表中每个部门的最高薪资和最低薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT department, MAX(salary), MIN(salary) FROM employees GROUP BY department;",
         "explanation": "MAX() 和 MIN() 分别返回最大值和最小值，常与 GROUP BY 配合。",
         "options": "SELECT department, MAX(salary), MIN(salary) FROM employees GROUP BY department;|SELECT department, MAX(salary), MIN(salary) FROM employees;|SELECT department, MAX(salary), MIN(salary) FROM employees GROUP BY department;|SELECT department, MAX(salary), MIN(salary) FROM employees GROUP BY department;",
         "option_explanations": "✓ MAX/MIN 结合 GROUP BY 按部门统计。|✗ 无 GROUP BY 返回整体最大最小。|✗ 与第一选项相同。|✗ 与第一选项相同。"},
        {"source": "curated", "category": "条件筛选", "difficulty": "easy", "title": "LIKE 模糊查询",
         "description": "从 employees 表中查询姓名中包含'张'的员工信息。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'张伟','技术部',16000,30),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT * FROM employees WHERE name LIKE '%张%';",
         "explanation": "LIKE '%张%' 匹配包含'张'字的字符串，% 表示任意字符序列。",
         "options": "SELECT * FROM employees WHERE name LIKE '%张%';|SELECT * FROM employees WHERE name = '张';|SELECT * FROM employees WHERE name LIKE '张';|SELECT * FROM employees WHERE name IN ('张');",
         "option_explanations": "✓ LIKE '%张%' 匹配含'张'的所有名字。|✗ = 要求完全等于'张'，不匹配张三/张伟。|✗ LIKE '张' 无通配符，等于精确匹配。|✗ IN ('张') 只匹配完全等于'张'的记录。"},
        {"source": "curated", "category": "基础查询", "difficulty": "easy", "title": "DISTINCT 去重",
         "description": "查询 employees 表中所有不重复的部门名称。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT DISTINCT department FROM employees;",
         "explanation": "DISTINCT 关键字用于去除重复行。",
         "options": "SELECT DISTINCT department FROM employees;|SELECT UNIQUE department FROM employees;|SELECT department FROM employees DISTINCT;|SELECT department FROM employees GROUP BY department;",
         "option_explanations": "✓ DISTINCT 去除重复部门名。|✗ UNIQUE 不是 SQL 标准关键字。|✗ DISTINCT 位置错误，应放在 SELECT 后。|✗ GROUP BY 也能去重，但语义不同，用于聚合。"},
        {"source": "curated", "category": "多表连接", "difficulty": "hard", "title": "多表 JOIN",
         "description": "查询每位员工的姓名、部门名称以及其项目名称。\n\n表结构：\nemployees(id, name, dept_id)\ndepartments(id, dept_name)\nprojects(id, project_name, emp_id)",
         "table_schema": "employees(id INT, name VARCHAR(100), dept_id INT);\ndepartments(id INT, dept_name VARCHAR(50));\nprojects(id INT, project_name VARCHAR(50), emp_id INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三',1),(2,'李四',2),(3,'王五',1);\nINSERT INTO departments VALUES (1,'技术部'),(2,'市场部');\nINSERT INTO projects VALUES (1,'项目A',1),(2,'项目B',1),(3,'项目C',2);",
         "correct_answer": "SELECT e.name, d.dept_name, p.project_name FROM employees e JOIN departments d ON e.dept_id = d.id LEFT JOIN projects p ON e.id = p.emp_id;",
         "explanation": "多表 JOIN 可以连续连接多个表，LEFT JOIN 确保没有项目的员工也能显示。",
         "options": "SELECT e.name, d.dept_name, p.project_name FROM employees e JOIN departments d ON e.dept_id = d.id LEFT JOIN projects p ON e.id = p.emp_id;|SELECT e.name, d.dept_name, p.project_name FROM employees e, departments d, projects p;|SELECT e.name, d.dept_name, p.project_name FROM employees e JOIN departments d, projects p;|SELECT e.name, d.dept_name, p.project_name FROM employees e JOIN departments d ON e.dept_id = d.id JOIN projects p ON e.id = p.emp_id;",
         "option_explanations": "✓ 多表 JOIN + LEFT JOIN 保留无项目的员工。|✗ 无连接条件，产生三表笛卡尔积。|✗ 第二个 JOIN 缺少 ON 连接条件。|✗ INNER JOIN 会排除无项目的员工王五。"},
        {"source": "curated", "category": "子查询与CTE", "difficulty": "hard", "title": "子查询多行结果",
         "description": "查询技术部中薪资高于市场部所有员工薪资的员工姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',7000,29);",
         "correct_answer": "SELECT name, salary FROM employees WHERE department = '技术部' AND salary > ALL (SELECT salary FROM employees WHERE department = '市场部');",
         "explanation": "> ALL 表示大于子查询返回的所有值，即大于市场部最高薪资。",
         "options": "SELECT name, salary FROM employees WHERE department = '技术部' AND salary > ALL (SELECT salary FROM employees WHERE department = '市场部');|SELECT name, salary FROM employees WHERE department = '技术部' AND salary > (SELECT MAX(salary) FROM employees WHERE department = '市场部');|SELECT name, salary FROM employees WHERE department = '技术部' AND salary > ANY (SELECT salary FROM employees WHERE department = '市场部');|SELECT name, salary FROM employees WHERE department = '技术部' AND salary > (SELECT salary FROM employees WHERE department = '市场部');",
         "option_explanations": "✓ > ALL 大于市场部所有员工薪资。|✗ > MAX 等效，但写法不同。|✗ > ANY 大于任意一个即可，逻辑不符。|✗ 子查询返回多行，> 无法与多行比较。"},
        {"source": "curated", "category": "聚合与分组", "difficulty": "medium", "title": "SUM 求和",
         "description": "查询 employees 表中每个部门的薪资总和。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT department, SUM(salary) FROM employees GROUP BY department;",
         "explanation": "SUM() 函数计算数值列的总和。",
         "options": "SELECT department, SUM(salary) FROM employees GROUP BY department;|SELECT department, SUM(salary) FROM employees;|SELECT department, TOTAL(salary) FROM employees GROUP BY department;|SELECT department, SUM(salary) FROM employees GROUP BY department;",
         "option_explanations": "✓ SUM(salary) 按部门求和。|✗ 无 GROUP BY，SUM 返回所有部门总和。|✗ TOTAL() 不是 SQL 标准函数。|✗ 与第一选项相同。"},
        {"source": "curated", "category": "条件筛选", "difficulty": "medium", "title": "BETWEEN 范围查询",
         "description": "从 employees 表中查询薪资在 12000 到 16000 之间的员工姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary FROM employees WHERE salary BETWEEN 12000 AND 16000;",
         "explanation": "BETWEEN x AND y 选取介于 x 和 y 之间的值（包含边界）。",
         "options": "SELECT name, salary FROM employees WHERE salary BETWEEN 12000 AND 16000;|SELECT name, salary FROM employees WHERE salary >= 12000 AND salary <= 16000;|SELECT name, salary FROM employees WHERE salary IN (12000, 16000);|SELECT name, salary FROM employees WHERE salary >= 12000 AND <= 16000;",
         "option_explanations": "✓ BETWEEN 12000 AND 16000 包含边界值。|✗ >= 和 <= 功能等效但写法更长。|✗ IN 只匹配 12000 或 16000，不是区间。|✗ AND 后缺少 salary 列名，语法错误。"},
        {"source": "curated", "category": "排序分页", "difficulty": "easy", "title": "多列排序",
         "description": "从 employees 表中先按部门升序，再按薪资降序查询所有员工信息。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT * FROM employees ORDER BY department ASC, salary DESC;",
         "explanation": "ORDER BY 支持多列排序，先按第一列排，再按第二列排。",
         "options": "SELECT * FROM employees ORDER BY department ASC, salary DESC;|SELECT * FROM employees ORDER BY department, salary;|SELECT * FROM employees ORDER BY department, salary DESC;|SELECT * FROM employees ORDER BY department ASC, salary DESC;",
         "option_explanations": "✓ 先按部门升序，再按薪资降序。|✗ 两列均默认 ASC 升序，薪资未降序。|✗ 部门缺少 ASC，默认为升序。|✗ 与第一选项相同。"},
        {"source": "curated", "category": "多表连接", "difficulty": "medium", "title": "自连接",
         "description": "查询所有员工及其直接上级的姓名。\n\n表结构：employees(id, name, manager_id)",
         "table_schema": "employees(id INT, name VARCHAR(100), manager_id INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'王总',NULL),(2,'张三',1),(3,'李四',1),(4,'王五',2);",
         "correct_answer": "SELECT e1.name AS employee, e2.name AS manager FROM employees e1 LEFT JOIN employees e2 ON e1.manager_id = e2.id;",
         "explanation": "自连接将同一张表视为两个不同的表进行连接。",
         "options": "SELECT e1.name AS employee, e2.name AS manager FROM employees e1 LEFT JOIN employees e2 ON e1.manager_id = e2.id;|SELECT e1.name, e2.name FROM employees e1, employees e2 WHERE e1.manager_id = e2.id;|SELECT e1.name, e2.name FROM employees e1 JOIN employees e2;|SELECT e1.name AS employee, e2.name AS manager FROM employees e1 INNER JOIN employees e2 ON e1.manager_id = e2.id;",
         "option_explanations": "✓ LEFT JOIN 自连接，王总无上级仍显示。|✗ INNER JOIN 只返回有上级的员工，王总被排除。|✗ 无连接条件，产生笛卡尔积。|✗ INNER JOIN 排除无上级的王总。"},
        {"source": "curated", "category": "聚合与分组", "difficulty": "hard", "title": "HAVING 与聚合函数组合",
         "description": "查询至少有 2 名员工的部门及其员工人数。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT department, COUNT(*) FROM employees GROUP BY department HAVING COUNT(*) >= 2;",
         "explanation": "HAVING 用于筛选分组后的结果，COUNT(*) >= 2 表示至少有2名员工。",
         "options": "SELECT department, COUNT(*) FROM employees GROUP BY department HAVING COUNT(*) >= 2;|SELECT department, COUNT(*) FROM employees WHERE COUNT(*) >= 2 GROUP BY department;|SELECT department, COUNT(*) FROM employees GROUP BY department WHERE COUNT(*) >= 2;|SELECT department, COUNT(*) FROM employees GROUP BY department HAVING COUNT(*) >= 2;",
         "option_explanations": "✓ HAVING 筛选人数>=2 的部门（技术部2人）。|✗ WHERE 不能直接使用聚合函数。|✗ WHERE 不能放在 GROUP BY 之后。|✗ 与第一选项相同。"},
        {"source": "curated", "category": "子查询与CTE", "difficulty": "hard", "title": "SELECT 中子查询",
         "description": "查询每位员工及其薪资在部门内的排名（按薪资降序）。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary, (SELECT COUNT(*) + 1 FROM employees e2 WHERE e2.department = e1.department AND e2.salary > e1.salary) AS rank FROM employees e1 ORDER BY department, rank;",
         "explanation": "SELECT 子句中可以使用子查询计算每行相关的标量值。",
         "options": "SELECT name, salary, (SELECT COUNT(*) + 1 FROM employees e2 WHERE e2.department = e1.department AND e2.salary > e1.salary) AS rank FROM employees e1 ORDER BY department, rank;|SELECT name, salary, RANK() OVER (PARTITION BY department ORDER BY salary DESC) FROM employees;|SELECT name, salary, ROW_NUMBER() OVER (PARTITION BY department ORDER BY salary DESC) FROM employees;|SELECT name, salary, (SELECT COUNT(*) FROM employees e2 WHERE e2.department = e1.department) FROM employees e1;",
         "option_explanations": "✓ 子查询计算同部门薪资高于自己的员工数+1作为排名。|✗ RANK() 是窗口函数，非所有数据库支持。|✗ ROW_NUMBER() 也是窗口函数。|✗ 子查询只计算部门总人数，非排名。"},
        {"source": "curated", "category": "基础查询", "difficulty": "easy", "title": "别名 AS",
         "description": "查询 employees 表中所有员工的姓名和薪资，将薪资列重命名为 '月薪'。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, salary AS 月薪 FROM employees;",
         "explanation": "AS 关键字为列或表取别名，使输出更易读。",
         "options": "SELECT name, salary AS 月薪 FROM employees;|SELECT name, salary 月薪 FROM employees;|SELECT name, salary AS '月薪' FROM employees;|SELECT name, salary AS 月薪 FROM employees;",
         "option_explanations": "✓ AS 将 salary 重命名为'月薪'。|✗ 省略 AS 也可取别名（隐式写法）。|✗ 引号括起的别名语法正确。|✗ 与第一选项相同。"},
        {"source": "curated", "category": "条件筛选", "difficulty": "medium", "title": "IN 运算符",
         "description": "从 employees 表中查询部门为 '技术部' 或 '财务部' 的员工姓名和部门。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT name, department FROM employees WHERE department IN ('技术部', '财务部');",
         "explanation": "IN 运算符用于判断列值是否匹配列表中的任意一个值。",
         "options": "SELECT name, department FROM employees WHERE department IN ('技术部', '财务部');|SELECT name, department FROM employees WHERE department = '技术部' OR department = '财务部';|SELECT name, department FROM employees WHERE department = '技术部' AND '财务部';|SELECT name, department FROM employees WHERE department IN ('技术部', '财务部');",
         "option_explanations": "✓ IN 匹配部门列表中的任意一个值。|✗ OR 功能等效，写法较冗长。|✗ AND '财务部' 缺少完整条件，语法错误。|✗ 与第一选项相同。"},
        {"source": "curated", "category": "子查询与CTE", "difficulty": "hard", "title": "WITH (CTE) 公共表表达式",
         "description": "使用 CTE 查询每个部门薪资最高的员工姓名和薪资。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "WITH dept_max AS (SELECT department, MAX(salary) AS max_salary FROM employees GROUP BY department) SELECT e.name, e.department, e.salary FROM employees e JOIN dept_max d ON e.department = d.department AND e.salary = d.max_salary;",
         "explanation": "WITH 子句定义临时视图（CTE），使复杂查询更清晰。",
         "options": "WITH dept_max AS (SELECT department, MAX(salary) AS max_salary FROM employees GROUP BY department) SELECT e.name, e.department, e.salary FROM employees e JOIN dept_max d ON e.department = d.department AND e.salary = d.max_salary;|SELECT name, department, MAX(salary) FROM employees GROUP BY department;|SELECT name, department, salary FROM employees WHERE salary IN (SELECT MAX(salary) FROM employees GROUP BY department);|WITH dept_max AS (SELECT department, MAX(salary) FROM employees GROUP BY department) SELECT * FROM employees, dept_max;",
         "option_explanations": "✓ CTE 先取部门最高薪，再关联查出员工名。|✗ GROUP BY 部门无法直接查出员工姓名。|✗ IN 子查询无法保证部门与薪资对应。|✗ 无连接条件，CTE 与 employees 笛卡尔积。"},
        {"source": "curated", "category": "聚合与分组", "difficulty": "hard", "title": "CASE WHEN 条件统计",
         "description": "统计 employees 表中各薪资区间的员工人数。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT CASE WHEN salary < 12000 THEN '低薪' WHEN salary BETWEEN 12000 AND 15000 THEN '中薪' ELSE '高薪' END AS level, COUNT(*) FROM employees GROUP BY level;",
         "explanation": "CASE WHEN 实现条件分支逻辑，可在 GROUP BY 中使用。",
         "options": "SELECT CASE WHEN salary < 12000 THEN '低薪' WHEN salary BETWEEN 12000 AND 15000 THEN '中薪' ELSE '高薪' END AS level, COUNT(*) FROM employees GROUP BY level;|SELECT CASE WHEN salary < 12000 THEN '低薪' WHEN salary < 15000 THEN '中薪' ELSE '高薪' END, COUNT(*) FROM employees GROUP BY 1;|SELECT IF(salary < 12000, '低薪', IF(salary < 15000, '中薪', '高薪')) AS level, COUNT(*) FROM employees GROUP BY level;|SELECT CASE WHEN salary < 12000 THEN '低薪' WHEN salary BETWEEN 12000 AND 15000 THEN '中薪' WHEN salary > 15000 THEN '高薪' END AS level, COUNT(*) FROM employees GROUP BY level;",
         "option_explanations": "✓ CASE WHEN 按薪资区间分组统计人数。|✗ GROUP BY 1 按表达式位置分组，可运行但可读性差。|✗ IF 函数是 MySQL 方言，非标准 SQL。|✗ 第三条件 WHEN salary>15000 正确但写法冗长。"},
        {"source": "curated", "category": "多表连接", "difficulty": "hard", "title": "FULL OUTER JOIN 模拟",
         "description": "查询所有员工和所有部门，包括未分配部门的员工和没有员工的部门。\n\n表结构：employees(id, name, dept_id); departments(id, dept_name)",
         "table_schema": "employees(id INT, name VARCHAR(100), dept_id INT);\ndepartments(id INT, dept_name VARCHAR(50))",
         "initial_data": "INSERT INTO employees VALUES (1,'张三',1),(2,'李四',NULL),(3,'王五',2);\nINSERT INTO departments VALUES (1,'技术部'),(2,'市场部'),(3,'财务部');",
         "correct_answer": "SELECT e.name, d.dept_name FROM employees e LEFT JOIN departments d ON e.dept_id = d.id UNION SELECT e.name, d.dept_name FROM employees e RIGHT JOIN departments d ON e.dept_id = d.id;",
         "explanation": "SQLite 不支持 FULL OUTER JOIN，可以用 LEFT JOIN UNION RIGHT JOIN 模拟。",
         "options": "SELECT e.name, d.dept_name FROM employees e LEFT JOIN departments d ON e.dept_id = d.id UNION SELECT e.name, d.dept_name FROM employees e RIGHT JOIN departments d ON e.dept_id = d.id;|SELECT e.name, d.dept_name FROM employees e FULL JOIN departments d ON e.dept_id = d.id;|SELECT e.name, d.dept_name FROM employees e, departments d;|SELECT e.name, d.dept_name FROM employees e LEFT JOIN departments d ON e.dept_id = d.id;",
         "option_explanations": "✓ LEFT UNION RIGHT 模拟 FULL JOIN，包含所有员工和部门。|✗ FULL JOIN 在 SQLite 中不支持。|✗ 无连接条件，产生笛卡尔积。|✗ LEFT JOIN 只保留左表记录，缺少财务部。"},
        {"source": "curated", "category": "条件筛选", "difficulty": "easy", "title": "NULL 值判断",
         "description": "从 employees 表中查询没有分配部门（dept_id 为 NULL）的员工姓名。",
         "table_schema": "employees(id INT, name VARCHAR(100), dept_id INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三',1),(2,'李四',NULL),(3,'王五',2);",
         "correct_answer": "SELECT name FROM employees WHERE dept_id IS NULL;",
         "explanation": "NULL 值不能用 = 判断，必须使用 IS NULL 或 IS NOT NULL。",
         "options": "SELECT name FROM employees WHERE dept_id IS NULL;|SELECT name FROM employees WHERE dept_id = NULL;|SELECT name FROM employees WHERE dept_id IS NULL;|SELECT name FROM employees WHERE dept_id == NULL;",
         "option_explanations": "✓ IS NULL 正确判断空值。|✗ = NULL 在 SQL 中永远为假，无法判断空值。|✗ 与第一选项相同。|✗ == NULL 无法判断空值，SQL 使用 = 而非 ==。"},
        {"source": "curated", "category": "聚合与分组", "difficulty": "medium", "title": "COUNT(DISTINCT) 去重计数",
         "description": "查询 employees 表中不同部门的数量。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35);",
         "correct_answer": "SELECT COUNT(DISTINCT department) FROM employees;",
         "explanation": "COUNT(DISTINCT 列名) 统计某列不重复值的个数。",
         "options": "SELECT COUNT(DISTINCT department) FROM employees;|SELECT COUNT(DISTINCT department) FROM employees;|SELECT DISTINCT COUNT(department) FROM employees;|SELECT COUNT(DISTINCT department) FROM employees;",
         "option_explanations": "✓ COUNT(DISTINCT department) 统计不重复部门数（2个）。|✗ 与第一选项相同。|✗ DISTINCT COUNT 先计数再去重，语义不同。|✗ 与第一选项相同。"},
        {"source": "curated", "category": "基础查询", "difficulty": "easy", "title": "LIMIT OFFSET 分页",
         "description": "从 employees 表中跳过前 2 条，查询接下来的 2 条记录。",
         "table_schema": "employees(id INT, name VARCHAR(100), department VARCHAR(50), salary DECIMAL(10,2), age INT)",
         "initial_data": "INSERT INTO employees VALUES (1,'张三','技术部',15000,28),(2,'李四','市场部',12000,32),(3,'王五','技术部',18000,35),(4,'赵六','财务部',11000,26),(5,'钱七','市场部',13000,29);",
         "correct_answer": "SELECT * FROM employees LIMIT 2 OFFSET 2;",
         "explanation": "LIMIT n OFFSET m 跳过 m 条后取 n 条，用于分页查询。",
         "options": "SELECT * FROM employees LIMIT 2 OFFSET 2;|SELECT * FROM employees LIMIT 2, 2;|SELECT * FROM employees OFFSET 2 LIMIT 2;|SELECT * FROM employees SKIP 2 TAKE 2;",
         "option_explanations": "✓ LIMIT 2 OFFSET 2 跳过2条取2条。|✗ LIMIT 2,2 是 MySQL 方言写法。|✗ OFFSET 在前 SQLite 不支持。|✗ SKIP TAKE 是 SQL Server 方言。"},
    ]

def seed_questions():
    conn = get_connection()
    count = conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    if count > 0:
        return
    # 优先从 questions.json 加载（纯JSON，直接 json.load）；回退到 questions.py（旧格式，正则解析）
    qpath_json = os.path.join(os.path.dirname(__file__), '..', 'questions.json')
    qpath_py = os.path.join(os.path.dirname(__file__), '..', 'questions.py')
    questions = []
    if os.path.exists(qpath_json):
        with open(qpath_json, 'r', encoding='utf-8') as f:
            questions = json.load(f)
        print(f"Loaded {len(questions)} questions from questions.json")
    elif os.path.exists(qpath_py):
        import re
        with open(qpath_py, 'r', encoding='utf-8') as _f:
            _content = _f.read()
        _m = re.search(r'(\[.*\])', _content, re.DOTALL)
        if _m:
            questions = json.loads(_m.group(1))
        print(f"Loaded {len(questions)} questions from questions.py (legacy, consider migrating to .json)")
    if not questions:
        questions = get_seed_questions()
    for q in questions:
            conn.execute('''INSERT INTO questions (source,category,difficulty,title,description,table_schema,initial_data,correct_answer,explanation,options,option_explanations,expected_output,pool)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (q['source'],q['category'],q['difficulty'],q['title'],q['description'],
             q.get('table_schema'),q.get('initial_data'),q['correct_answer'],q.get('explanation'),q.get('options'), q.get('option_explanations'), q.get('expected_output'), 'practice'))
    conn.commit()
    print(f"Seeded {len(questions)} practice questions.")

def seed_exam_questions():
    """Load exam questions from exam_questions.json into exam_questions table."""
    conn = get_connection()
    count = conn.execute('SELECT COUNT(*) FROM exam_questions').fetchone()[0]
    if count > 0:
        return
    qpath = os.path.join(os.path.dirname(__file__), '..', 'exam_questions.json')
    if not os.path.exists(qpath):
        print("exam_questions.json not found, skipping exam seed.")
        return
    with open(qpath, 'r', encoding='utf-8') as f:
        questions = json.load(f)
    for q in questions:
        conn.execute('''INSERT INTO exam_questions (source,category,difficulty,title,description,table_schema,initial_data,correct_answer,explanation,options,option_explanations,expected_output)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
        (q['source'],q['category'],q['difficulty'],q['title'],q['description'],
         q.get('table_schema'),q.get('initial_data'),q.get('correct_answer',''),q.get('explanation'),q.get('options'), q.get('option_explanations'), q.get('expected_output')))
    conn.commit()
    print(f"Seeded {len(questions)} exam questions.")
