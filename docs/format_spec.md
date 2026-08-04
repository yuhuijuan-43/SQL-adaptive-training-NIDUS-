# SQL 题库前端渲染格式规范

> 本文档规定 SQL 题目在题库系统中的**数据格式**、**渲染流水线**、**CSS 样式**和**生成规则**，确保任何新增题目都能在 `frontend/index.html`（或 `index_ngrok.html`）中渲染出与现有 310 道 LeetCode 题完全一致的效果。

---

## 一、数据格式

### 1.1 题目 JSON 对象字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | number | 是 | 题目唯一标识（数据库自增） |
| `source` | string | 是 | `leetcode` / `curated` / `sqlzoo` / `pgexercises` |
| `category` | string | 是 | 知识点分类（见 `knowledge_tags.csv`） |
| `difficulty` | string | 是 | `easy` / `medium` / `hard` |
| `star_difficulty` | string | 否 | 星级难度 `*` / `**` / `***` |
| `title` | string | 是 | 题目标题，格式为 `"175. 两表合并查询"`（编号 + 中文翻译） |
| `description` | string | 是 | 题目描述，**必须含表结构信息 + 任务说明**（见 §2.2） |
| `table_schema` | string | 是 | `CREATE TABLE` 建表语句，多条用 `\n` 分隔，每条以 `;` 结尾 |
| `initial_data` | string | 是 | `INSERT` 初始化数据，**每条用 `\n` 分隔，不用分号** |
| `correct_answer` | string | 是 | 标准答案 SQL |
| `explanation` | string | 否 | 中文答案解析 |
| `options` | string | 否 | 选择题选项，用 `\|` 分隔。有值则为选择题，否则为填空题 |
| `option_explanations` | string | 否 | 每个选项的解析，用 `\|` 分隔 |
| `expected_output` | string | 否 | 预期输出（文本管道格式，见 §2.4） |
| `tags` | string[] | 否 | 分类标签数组 |

### 1.2 `table_schema` 格式规范

```sql
Create table If Not Exists Person (personId int, firstName varchar(255), lastName varchar(255));
Create table If Not Exists Address (addressId int, personId int, city varchar(255), state varchar(255));
```

- 支持 `IF NOT EXISTS` 关键字
- 每条 `CREATE TABLE` 语句用 `;` 结尾，多条之间用 `\n` 分隔
- 列定义支持 `int`、`varchar(n)`、`decimal(p,s)`、`date`、`enum(...)` 等 MySQL 类型

### 1.3 `initial_data` 格式规范

```
insert into Person (personId, lastName, firstName) values ('1', 'Wang', 'Allen')
insert into Person (personId, lastName, firstName) values ('2', 'Alice', 'Bob')
insert into Address (addressId, personId, city, state) values ('1', '2', 'New York City', 'New York')
```

- **每条 INSERT 用 `\n` 换行分隔，不用分号**（LeetCode 格式）
- INSERT 可带列名列表 `(col1, col2, ...)`，**列名顺序可以与 CREATE TABLE 中不同**
- 字符串值用单引号，数字不加引号，NULL 用 `NULL`

### 1.4 判断题型

```js
// options 字段存在且非空 → 选择题；否则 → 填空题
var hasOpts = q.options && (typeof q.options === 'string' ? q.options.trim() : q.options.length);
```

LeetCode 题目**全部是填空题**（用户手写 SQL）。

---

## 二、渲染流水线

### 2.1 渲染顺序（从上到下）

```
┌─ 标签行 ────────────────────────────────┐
│  [select_basic]  [⭐⭐]  [填空题]          │
└──────────────────────────────────────────┘
┌─ 标题 h3.title-serif ───────────────────┐
│  175. 两表合并查询                       │
└──────────────────────────────────────────┘
┌─ 描述 p.question-desc ──────────────────┐
│  表结构：                                │
│  表：Person                              │
│    - personId INT                        │
│    - firstName VARCHAR(255)              │
│    - lastName VARCHAR(255)               │
│  表：Address                             │
│    - addressId INT                       │
│    - personId INT                        │
│    - city VARCHAR(255)                   │
│    - state VARCHAR(255)                  │
│                                          │
│  Report the first name, last name, ...   │
└──────────────────────────────────────────┘
┌─ 建表表格 table.data-table ─────────────┐
│  PERSON                                  │
│  ┌──────────┬──────────┬───────────┐     │
│  │personId  │ lastName │ firstName │     │
│  ├──────────┼──────────┼───────────┤     │
│  │ 1        │ Wang     │ Allen     │     │
│  │ 2        │ Alice    │ Bob       │     │
│  └──────────┴──────────┴───────────┘     │
│  ADDRESS                                 │
│  ┌───────────┬──────────┬──────────────┐ │
│  │ addressId │ personId │ city         │ │
│  ├───────────┼──────────┼──────────────┤ │
│  │ 1         │ 2        │ New York ... │ │
│  │ 2         │ 3        │ Leetcode     │ │
│  └───────────┴──────────┴──────────────┘ │
└──────────────────────────────────────────┘
┌─ 建表 SQL（可折叠）──────────────────────┐
│  [展开 SQL] ▸                            │
│  ┌─ sql-panel.open ────────────────────┐ │
│  │ CREATE TABLE Person (personId ...); │ │
│  │ INSERT INTO Person VALUES (...);    │ │
│  └─────────────────────────────────────┘ │
└──────────────────────────────────────────┘
┌─ 预期输出 table.data-table ─────────────┐
│  预期输出                                │
│  ┌───────────┬──────────┬──────────────┐ │
│  │ firstName │ lastName │ city         │ │
│  ├───────────┼──────────┼──────────────┤ │
│  │ Allen     │ Wang     │ NULL         │ │
│  │ Bob       │ Alice    │ New York ... │ │
│  └───────────┴──────────┴──────────────┘ │
└──────────────────────────────────────────┘
┌─ 输入框 / 提交按钮 ─────────────────────┐
│  ┌────────────────────────────────────┐ │
│  │ 手动输入你的 SQL 语句...            │ │
│  └────────────────────────────────────┘ │
│  [提交答案]                              │
└──────────────────────────────────────────┘
```

### 2.2 题目描述（`description`）

题目描述**必须包含表结构 + 任务说明**，格式如下：

```
表结构：
表：Person
  - personId INT
  - firstName VARCHAR(255)
  - lastName VARCHAR(255)
表：Address
  - addressId INT
  - personId INT
  - city VARCHAR(255)
  - state VARCHAR(255)

Report the first name, last name, city, and state of each person in the Person table. If the address of a personId is not present in the Address table, report null instead.
```

**生成规则：**
1. 表结构部分从 `table_schema` 解析：表名 + 每列 `列名 类型`
2. 任务说明保留原始题目描述（不含 ASCII 表格边框、示例输入/输出）
3. 若原始描述缺失，则用标题生成兜底：`请根据题目要求完成 SQL 查询：{标题}。`
4. **不能包含**原始 LeetCode 的 ASCII 表格（`+----+` 边框）、`Input:`/`Output:` 示例

### 2.3 建表数据表格渲染（`renderDataTable`）

将 `initial_data` + `table_schema` 渲染为独立 `<table class="data-table">`。

**关键解析规则（LeetCode 格式兼容）：**

```js
// 1. 语句分割：分号 AND 换行都算分隔符（LeetCode 用换行）
var stmts = dataStr.replace(/;+\s*/g, ';\n').split(/[;\n]/);

// 2. INSERT 匹配：允许列名列表，捕获列名用于表头
var m = stmt.match(/INSERT\s+INTO\s+(\w+)(?:\s*\(([^)]*)\))?\s+VALUES\s*(.*)/i);

// 3. 表头优先级：INSERT 列名列表 > CREATE TABLE 列名 > col1/col2...
var hdrs = (tableCols[tbl] && tableCols[tbl].length)
  ? tableCols[tbl]
  : ((schemaMap[tbl] && schemaMap[tbl].length) ? schemaMap[tbl] : rows[0].map(...));
```

**重要：** INSERT 的列名列表顺序可能与 CREATE TABLE 不同（如 LeetCode 中 `Person (personId, lastName, firstName)` 与建表的 `(personId, firstName, lastName)` 相反），**表头必须用 INSERT 列名列表**，否则数据错位。

### 2.4 预期输出渲染（`renderExpectedOutput`）

支持两种格式，优先 JSON：

**JSON 格式：**
```json
{ "headers": ["id", "name"], "rows": [[1, "张三"], [2, "李四"]] }
```

**文本管道格式（推荐，自动生成）：**
```
firstName | lastName | city          | state
----------+----------+---------------+----------
Allen     | Wang     | NULL          | NULL
Bob       | Alice    | New York City | New York
```

- 第 1 行：列头，用 ` | ` 分隔
- 第 2 行：分隔线，`-` 和 `+` 组成（`^[-+]+$`）
- 第 3+ 行：数据行，用 ` | ` 分隔
- 渲染为 `table.data-table`，行数超过 10 截断

### 2.5 建表 SQL 面板（`renderSqlPanel`）

```js
// 点击 .sql-toggle 切换 .sql-panel 的 .open 类，文字在 "展开 SQL" / "收起 SQL" 间切换
'<div class="sql-toggle" onclick="var p=document.getElementById(\'' + id + '\');p.classList.toggle(\'open\');this.querySelector(\'span\').textContent=p.classList.contains(\'open\')?\'收起 SQL\':\'展开 SQL\'"><span>展开 SQL</span></div>'
```

内容为 `table_schema` + `initial_data` 的原始 SQL，HTML 转义 `<` → `&lt;`。

---

## 三、CSS 样式

### 3.1 CSS 变量

```css
:root {
  --bg: #f5f6f8;            /* 页面背景 */
  --card: #ffffff;           /* 卡片背景 */
  --text: #2c3e50;           /* 主文字色 */
  --text2: #7a8599;          /* 辅助文字色 */
  --border: #e4e7ed;         /* 边框色 */
  --accent: #5a7d9a;         /* 强调色（蓝灰） */
  --accent-hover: #4a6a82;
  --tag-bg: #eef1f5;         /* 标签/交替行背景 */
  --code-bg: #f0f2f5;        /* 代码块背景 */
  --success: #6b9e7a;        /* 成功绿 */
  --error: #c97a7a;          /* 错误红 */
}
```

### 3.2 核心题目样式

```css
/* 题目描述 - 左边界强调色卡片 */
.question-desc {
  white-space: pre-wrap; font-size: 0.85rem; line-height: 1.7;
  margin-bottom: 0.75rem; padding: 0.75rem 1rem;
  background: var(--tag-bg); border-left: 3px solid var(--accent);
  border-radius: 0 0.375rem 0.375rem 0;
  color: var(--text); font-weight: 500;
}

/* 数据表格（建表表格 + 预期输出共用） */
.data-table {
  margin: 0 0 0.5rem 0; border-collapse: collapse;
  font-size: 0.7rem; font-family: 'SF Mono', 'Consolas', monospace;
}
.data-table th {
  background: var(--text);      /* #2c3e50 深色表头 */
  color: #fff; padding: 0.3rem 0.5rem; text-align: left; font-weight: 600;
}
.data-table td {
  padding: 0.25rem 0.5rem; border-bottom: 1px solid var(--border); color: var(--text);
}
.data-table tr:nth-child(even) td { background: var(--tag-bg); }  /* 交替行 */

/* 表名标签（表格上方） */
.table-label {
  font-size: 0.65rem; font-weight: 600; color: var(--text2);
  margin: 0.5rem 0 0.25rem 0; text-transform: uppercase; letter-spacing: 0.04em;
}

/* 预期输出标签 */
.exp-label {
  font-size: 0.65rem; font-weight: 600; color: var(--text);
  margin: 0.75rem 0 0.25rem 0; text-transform: uppercase; letter-spacing: 0.04em;
}

/* SQL 面板 */
.sql-toggle {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 0.65rem; color: var(--accent); cursor: pointer; font-weight: 600;
  font-family: 'SF Mono', 'Consolas', monospace; user-select: none;
  padding: 2px 8px; border: 1px solid var(--border); border-radius: 0.25rem;
  background: var(--card); margin-bottom: 0.5rem;
}
.sql-toggle:hover { background: var(--tag-bg); }
.sql-panel { display: none; margin-bottom: 0.75rem; }
.sql-panel.open { display: block; }
.sql-code {
  background: var(--text); color: #d4dce8; padding: 0.75rem 1rem;
  border-radius: 0.375rem; font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 0.7rem; line-height: 1.6; white-space: pre-wrap; overflow-x: auto;
}

/* 填空题输入框 */
.code-input {
  width: 100%; min-height: 72px; padding: 0.6rem 0.75rem;
  font-family: 'SF Mono', 'Consolas', monospace; font-size: 0.8rem;
  color: var(--text); background: var(--card);
  border: 1px solid var(--border); border-radius: 0.375rem;
  outline: none; resize: vertical; transition: border-color 0.15s;
}
.code-input:focus { border-color: var(--accent); }
```

### 3.3 标签样式

```css
.tag {
  display: inline-block; background: var(--tag-bg); color: var(--text2);
  font-size: 0.65rem; font-weight: 600;
  padding: 0.15rem 0.5rem; border-radius: 0.25rem;
}
/* 难度标签 */
.tag-easy   { background: #eaf4ee; color: #5a8f6a; }
.tag-medium { background: #f0eddf; color: #8a7a4a; }
.tag-hard   { background: #f0e4e4; color: #b06060; }
```

题型标签（内联样式）：
- **选择题**：`background: rgba(52,119,191,0.15); color: #3477bf;`
- **填空题**：`background: rgba(193,124,74,0.20); color: #a8683e;`

---

## 四、预期输出生成脚本逻辑

```python
def generate_expected_output(table_schema, initial_data, correct_answer):
    """在内存 SQLite 中建表、插数、执行答案，生成文本管道格式输出。"""

def split_sql_statements(s):
    """按 ; 和换行分割 SQL 语句（兼容 LeetCode 换行分隔格式）。"""
    # 按行分割，遇到 CREATE/INSERT/TRUNCATE 开头开启新语句
```

**关键步骤：**
1. 建表：逐条执行 `CREATE TABLE`（需将 MySQL 类型映射到 SQLite：`varchar→TEXT`、`decimal→REAL`、`enum(...)→TEXT`、去掉 `AUTO_INCREMENT`/`PRIMARY KEY`/`NOT NULL`）
2. 插数：**按换行分割**逐条执行 INSERT（不能只按 `;` 分割）
3. 执行答案 SQL（SELECT / DELETE / UPDATE）
4. 格式化为 `列头 | 列头\n---+---\n数据 | 数据`
5. SELECT 列名来自 `cursor.description`
6. NULL 显示为 `NULL`，行数超过 10 截断

---

## 五、题目标准化规则（引用自《前端题目标准化检查.md》）

| 规则 | 要求 | 当前状态 |
|------|------|---------|
| 规则 6 | 英文标题翻译为中文 | ✅ 已完成 |
| 规则 1 | 描述含表结构 + 任务，不与标题重复 | ✅ 已完成 |
| 规则 2 | 建表/预期输出表格行数 ≤ 10 | ✅ 生成时截断 |
| 规则 3 | 预期输出必须有数据行（非空） | ✅ 257/310 |
| 规则 4 | DML 题预期输出为新表格 | ✅ 已处理 DELETE/UPDATE |
| 规则 9 | 建表 SQL 必须可执行、列名正确 | ✅ 已修复 `IF NOT EXISTS` 解析 |
| 规则 14 | 描述 = 正确答案 = 预期输出 三者一致 | ✅ 生成时校验 |

---

## 六、已知注意事项

1. **`initial_data` 必须用换行分隔**，不能只用分号（前端按 `[;\n]` 分割）
2. **INSERT 列名顺序可能与 CREATE TABLE 不同**，表头必须取 INSERT 列名列表
3. **`CREATE TABLE IF NOT EXISTS`** 会被前端正则正确解析（`IF` 不会被误当表名）
4. MySQL 特有类型（`ENUM`、`DECIMAL`、`VARCHAR(n)`）在 SQLite 中生成预期输出时需映射
5. 难度星级映射：`easy→*`、`medium→**`、`hard→***`
6. 标题格式：`"{LeetCode题号}. {中文翻译}"`，如 `"175. 两表合并查询"`
7. 目前 310 题中有 1 题（动态逆透视表）无答案、52 题无预期输出（MySQL 专用语法无法在 SQLite 执行）
