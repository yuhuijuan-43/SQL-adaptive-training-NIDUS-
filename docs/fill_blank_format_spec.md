# SQL 题库题目格式规范

## 概述

每道题目是一个 JSON 对象，包含 12 个字段。题库文件 `questions.py` 以 JSON 数组形式存储所有题目。

---

## 字段定义

### 1. `source`（字符串）
题目来源标识，用于追溯题目出处。

| 值 | 说明 |
|----|------|
| `"curated"` | 手工编写的原创题目（43 题） |
| `"sqlzoo"` | 爬取自 [SQLZoo](https://sqlzoo.net)（109 题） |
| `"pgexercises"` | 爬取自 [PostgreSQL Exercises](https://pgexercises.com)（57 题） |
| `"sql_practice"` | 爬取自 [SQL-Practice](https://www.sql-practice.com)（12 题） |
| `"curated_web"` | 补充编写的网络风格题目（7 题） |
| `"mode_analytics"` | 爬取自 [Mode Analytics](https://mode.com/sql-tutorial)（4 题） |
| `"ai_generated"` | 🤖 AI 自动生成的题目（50 题） |
| `"niuke"` | 爬取自 [牛客网](https://www.nowcoder.com) SQL 题库（42 题） |

### 2. `category`（字符串）
知识点分类，与知识图谱节点对应。

| 分类 | 说明 |
|------|------|
| `select_basic` | SELECT 基础查询 |
| `where_basic` | WHERE 条件筛选 |
| `where_andor` | AND / OR 多条件组合 |
| `where_like` | LIKE 模糊查询 |
| `where_null` | IS NULL 空值判断 |
| `where_in` | IN 值列表匹配 |
| `where_between` | BETWEEN 范围查询 |
| `order_by` | ORDER BY 排序 |
| `limit_offset` | LIMIT / OFFSET 分页 |
| `aggregate_basic` | 聚合函数（COUNT/SUM/MAX/MIN） |
| `group_by` | GROUP BY 分组 |
| `having` | HAVING 分组过滤 |
| `avg` | AVG 平均值 |
| `count_distinct` | COUNT(DISTINCT) 去重计数 |
| `alias` | AS 别名 |
| `distinct` | DISTINCT 去重 |
| `case_when` | CASE WHEN 条件分支 |
| `join_inner` | INNER JOIN 内连接 |
| `join_left` | LEFT JOIN 左连接 |
| `join_self` | 自连接 |
| `join_multi` | 多表 JOIN |
| `join_full` | FULL OUTER JOIN |
| `subquery_basic` | 子查询基础 |
| `subquery_exists` | EXISTS 子查询 |
| `subquery_all` | ALL / ANY 子查询 |
| `subquery_select` | SELECT 中子查询 |
| `cte` | CTE (WITH) 公共表表达式 |
| `window` | 窗口函数 |
| `dml` | INSERT / UPDATE / DELETE |
| `string` | 字符串函数 |
| `date` | 日期函数 |
| `union` | UNION 合并查询 |

### 3. `difficulty`（字符串）

| 值 | 说明 |
|----|------|
| `"easy"` | 简单（单表、基础 SELECT/WHERE） |
| `"medium"` | 中等（JOIN、聚合、子查询） |
| `"hard"` | 困难（窗口函数、CTE、FULL JOIN） |

### 4. `title`（字符串）
题目标题。简洁明了，不超过 80 字符。

```
"查询所有员工"
```

### 5. `description`（字符串）
题目描述/题干。可包含多行文本，使用 `\n` 换行。如需说明多表结构，在末尾追加。

```
"查询 employees 表中所有员工的全部信息。"
```

多表时：
```
"查询每位员工的姓名及其所属部门名称。\n\n表结构：\nemployees(id, name, dept_id)\ndepartments(id, dept_name)"
```

### 6. `table_schema`（字符串）
CREATE TABLE 语句。支持单表或多表（用 `\n` 分隔）。

**单表：**
```
"CREATE TABLE employees (id INT, name VARCHAR(50), department VARCHAR(50), salary DECIMAL(10,2), age INT);"
```

**多表：**
```
"CREATE TABLE orders (id INT, customer_id INT, product_id INT, quantity INT, order_date DATE);\nCREATE TABLE customers (id INT, name VARCHAR(50), city VARCHAR(50));\nCREATE TABLE products (id INT, name VARCHAR(50), category VARCHAR(50), price DECIMAL(10,2), stock INT);"
```

支持的 SQL 数据类型（执行时自动映射到 SQLite）：

| 原类型 | SQLite 映射 |
|--------|-------------|
| `INT`, `INTEGER`, `BIGINT`, `SMALLINT` | `INTEGER` |
| `VARCHAR(n)`, `CHAR(n)`, `TEXT` | `TEXT` |
| `DECIMAL(p,s)`, `FLOAT`, `DOUBLE` | `REAL` |
| `DATE`, `DATETIME`, `TIMESTAMP` | `TEXT` |
| `BOOLEAN` | `INTEGER` |

### 7. `initial_data`（字符串）
INSERT 语句，用于初始化测试数据。多表时用 `\n` 分隔。

**单表：**
```
"INSERT INTO employees VALUES (1, '张三', '技术部', 12000, 28), (2, '李四', '市场部', 9000, 35), (3, '王五', '技术部', 15000, 32);"
```

**多表：**
```
"INSERT INTO orders VALUES (1, 1, 1, 2, '2024-01-01'), (2, 2, 2, 1, '2024-01-02');\nINSERT INTO customers VALUES (1, '张三', '北京'), (2, '李四', '上海');\nINSERT INTO products VALUES (1, '键盘', '电子产品', 150, 100), (2, '鼠标', '电子产品', 30, 200);"
```

**约束：**
- 字符串值使用**单引号**
- NULL 值使用 `NULL`（无引号）
- 日期使用 `'YYYY-MM-DD'` 格式

### 8. `correct_answer`（字符串）
标准答案 SQL。需是完整、可执行的 SQL 语句，以分号结尾。

```
"SELECT * FROM employees WHERE department = '技术部' AND salary > 10000;"
```

### 9. `explanation`（字符串）
答案解析，解释 SQL 语句的执行逻辑和语法要点。

```
"AND 表示两个条件同时满足，筛选出技术部中工资大于 10000 的员工。"
```

### 10. `options`（字符串）
选择题选项，用竖线 `|` 分隔。第一项必须是正确答案（与 `correct_answer` 一致）。

```
"SELECT * FROM employees WHERE department = '技术部' AND salary > 10000;|SELECT * FROM employees WHERE department = '技术部' OR salary > 10000;|SELECT * FROM employees WHERE department = '技术部' && salary > 10000;|SELECT * FROM employees WHERE department = '技术部' AND salary > 10000"
```

**格式规则：**
- 选项数量固定为 **4 个**
- 第一项 = 正确答案
- 第 2~4 项 = 常见错误写法（语法错误、逻辑错误、运算符混淆等）

### 11. `option_explanations`（字符串）
每个选项的解析，用竖线 `|` 分隔，数量与 `options` 一致。每项以 `✓` 或 `✗` 开头。

```
"✓ 正确，使用 AND 同时满足两个条件。|✗ OR 只要满足一个条件即可，会包含市场部高薪员工。|✗ SQL 中不识别 && 运算符。|✗ 缺少分号结尾。"
```

### 12. `expected_output`（字符串）
执行 `correct_answer` 后的预期查询结果，以 ASCII 表格形式呈现。

**格式规则：**
- 第 1 行：列标题，用 ` | ` 分隔
- 第 2 行：分隔线，列间用 `-+-`
- 第 3+ 行：数据行，用 ` | ` 分隔

```
"id | name | department | salary  | age\n---+------+------------+---------+----\n1  | 张三   | 技术部        | 12000.0 | 28 \n2  | 李四   | 市场部        | 9000.0  | 35 \n3  | 王五   | 技术部        | 15000.0 | 32 "
```

**执行规则：**
- 由后端 `generate_expected_output.py` 脚本自动生成
- 在内存 SQLite 中执行 `table_schema` → `initial_data` → `correct_answer` 后抓取结果
- 需要额外处理 SQLite 不支持的语法（如 `> ALL` 转为 `> (SELECT MAX(...))`）

---

## 完整示例

```json
{
    "source": "curated",
    "category": "where_andor",
    "difficulty": "easy",
    "title": "AND 条件查询",
    "description": "查询 employees 表中技术部且工资大于 10000 的员工。",
    "table_schema": "CREATE TABLE employees (id INT, name VARCHAR(50), department VARCHAR(50), salary DECIMAL(10,2), age INT);",
    "initial_data": "INSERT INTO employees VALUES (1, '张三', '技术部', 12000, 28), (2, '李四', '市场部', 9000, 35), (3, '王五', '技术部', 15000, 32), (4, '赵六', '技术部', 8000, 25);",
    "correct_answer": "SELECT * FROM employees WHERE department = '技术部' AND salary > 10000;",
    "explanation": "AND 表示两个条件同时满足，筛选出技术部中工资大于 10000 的员工。",
    "options": "SELECT * FROM employees WHERE department = '技术部' AND salary > 10000;|SELECT * FROM employees WHERE department = '技术部' OR salary > 10000;|SELECT * FROM employees WHERE department = '技术部' && salary > 10000;|SELECT * FROM employees WHERE department = '技术部' AND salary > 10000",
    "option_explanations": "✓ 正确，使用 AND 同时满足两个条件。|✗ OR 只要满足一个条件即可，会包含市场部高薪员工。|✗ SQL 中不识别 && 运算符。|✗ 缺少分号结尾。",
    "expected_output": "id | name | department | salary  | age\n---+------+------------+---------+----\n1  | 张三   | 技术部        | 12000.0 | 28 \n3  | 王五   | 技术部        | 15000.0 | 32 "
}
```

---

## 前端渲染顺序

刷题页面中，每道题的渲染顺序如下：

```
┌─ 难度/分类标签 ──────────────────────────┐
│  select_basic  [简单]                      │
├─ 标题 ────────────────────────────────────┤
│  查询所有员工                              │
├─ 描述 ────────────────────────────────────┤
│  查询 employees 表中所有员工的全部信息。     │
├─ 建表 SQL + 测试数据 ─────────────────────┤
│  [展开 SQL]                                │
│  CREATE TABLE employees (...);             │
│  INSERT INTO employees VALUES (...);       │
├─ 预期输出 ────────────────────────────────┤
│  id │ name │ department │ salary  │ age   │
│  ───┼──────┼────────────┼─────────┼────   │
│  1  │ 张三   │ 技术部      │ 12000.0 │ 28    │
│  2  │ 李四   │ 市场部      │ 9000.0  │ 35    │
│  3  │ 王五   │ 技术部      │ 15000.0 │ 32    │
├─ 选择题选项 / 填空题输入框 ──────────────┤
│  ○ SELECT * FROM employees;               │
│  ○ SELECT id,name FROM employees;         │
│  ○ SELECT ALL FROM employees;             │
│  ○ SELECT employees FROM employees;       │
│  ┌──────────────────────────────────────┐ │
│  │ 或者在此输入你的 SQL 语句...            │ │
│  └──────────────────────────────────────┘ │
├─ 提交按钮 ───────────────────────────────┤
│  [提交答案]                               │
└───────────────────────────────────────────┘
```

---

## 新增题目的步骤

### 步骤 1：定义题目 JSON
按上述规范在 `questions.py` 的数组中追加新对象。

### 步骤 2：生成预期输出
```bash
python backend/generate_expected_output.py
```
脚本解析 `questions.py`，在内存 SQLite 中执行每道题的 SQL，自动生成 `expected_output` 字段。

### 步骤 3：重新播种数据库
```bash
python -c "import sys; sys.path.insert(0, 'backend'); from database import init_db, seed_questions, seed_knowledge_graph; init_db(); seed_questions(); seed_knowledge_graph()"
```

### 步骤 4：验证
```bash
python backend/verify_db.py
```

---

## 多表题目规范

当题目涉及多张表时，按以下约定：

**表名：** 使用有意义的英文名（`employees`, `customers`, `orders`, `products`, `departments` 等）。

**主键：** 每张表的第一列约定为 `id INT` 作为主键。

**外键：** 使用 `表名_id INT` 命名约定（如 `customer_id`, `product_id`, `dept_id`）。

**初始数据：** 按外键依赖顺序书写 INSERT（先插入被引用的表）。

**示例：**

```json
{
    "title": "多表连接查询",
    "table_schema": "CREATE TABLE orders (id INT, customer_id INT, product_id INT, quantity INT, order_date DATE);\nCREATE TABLE customers (id INT, name VARCHAR(50), city VARCHAR(50));\nCREATE TABLE products (id INT, name VARCHAR(50), category VARCHAR(50), price DECIMAL(10,2), stock INT);",
    "initial_data": "INSERT INTO customers VALUES (1, '张三', '北京'), (2, '李四', '上海');\nINSERT INTO products VALUES (1, '键盘', '电子产品', 150, 100), (2, '鼠标', '电子产品', 30, 200);\nINSERT INTO orders VALUES (1, 1, 1, 2, '2024-01-01'), (2, 2, 2, 1, '2024-01-02');",
    "correct_answer": "SELECT o.id, c.name, p.name FROM orders o JOIN customers c ON o.customer_id = c.id JOIN products p ON o.product_id = p.id;"
}
```

---

## 错误选项编写原则

每道题提供 4 个选项，按以下策略构造错误选项：

| 策略 | 示例（正确答案） | 错误选项 |
|------|-----------------|----------|
| 错误的比较运算符 | `salary > 10000` | `salary < 10000` |
| 错误的逻辑运算符 | `AND` | `OR` |
| 省略关键子句 | `WHERE` | 无 WHERE |
| 错误的函数 | `AVG(salary)` | `SUM(salary)` |
| 错误的 JOIN 类型 | `LEFT JOIN` | `INNER JOIN` |
| 语法错误 | `BETWEEN 50 AND 200` | `BETWEEN 50, 200` |
| 缺少分号 | `SELECT * FROM t` | `SELECT * FROM t`（无 `;`） |
| 列名/表名错误 | `employees` | `employee` |
