"""SQL 判题引擎

优先在内存 SQLite 中真实执行用户 SQL 与标准答案，比较结果集（列、行均与顺序无关）；
环境数据缺失或无法构建时，回退到字符串规范化比对（兼容旧行为）。
"""
import re
import sqlite3

# 允许用户提交的语句首关键字（SQLite 中只有这些不会产生写操作）
_READ_ONLY_FIRST = ('select', 'with', 'explain', 'pragma')


def normalize_sql(sql):
    """Normalize SQL for flexible comparison, handling column reordering, aliases, etc."""
    s = sql.strip().rstrip(';').strip().lower()
    s = re.sub(r'\s+', ' ', s)
    # Remove quotes around aliases
    s = s.replace("'", '').replace('"', '')
    # Handle SELECT: sort columns alphabetically
    m = re.match(r'(select\s+)(.*?)(\s+from\s+.*)', s, re.DOTALL)
    if m:
        prefix = m.group(1)
        cols = m.group(2)
        rest = m.group(3)
        # Split columns by comma, strip each, sort
        col_list = [c.strip() for c in cols.split(',')]
        # Normalize each column: remove AS keyword for sorting
        def sort_key(col):
            c = re.sub(r'\s+as\s+.*', '', col).strip()
            c = re.sub(r'\s+.*', '', c).strip()
            return c
        col_list.sort(key=sort_key)
        cols_sorted = ', '.join(col_list)
        s = prefix + cols_sorted + rest
    return s


def answers_match(user_answer, correct_answer):
    """字符串规范化比对（仅作判题回退 / 快速路径）"""
    return normalize_sql(user_answer) == normalize_sql(correct_answer)


def _strip_comments(sql):
    """去掉 SQL 中的块注释和行注释（仅用于语句合法性检查，不改变语义）"""
    s = re.sub(r'/\*.*?\*/', ' ', sql, flags=re.DOTALL)
    s = re.sub(r'(?m)--.*$', ' ', s)
    return s


def _check_read_only_single_statement(sql):
    """校验：只能是一条只读语句（SELECT / WITH / EXPLAIN / PRAGMA）"""
    cleaned = _strip_comments(sql).strip()
    if not cleaned:
        return False
    parts = [p.strip() for p in cleaned.split(';') if p.strip()]
    if len(parts) != 1:
        return False
    first_word = parts[0].lstrip().split(None, 1)[0].lower()
    return first_word in _READ_ONLY_FIRST


def _friendly_error(e):
    """把 sqlite3 错误映射为对学习友好的中文提示"""
    msg = str(e)
    m = re.search(r'no such table: (\S+)', msg)
    if m:
        return f'表不存在：{m.group(1)}（检查表名拼写）'
    m = re.search(r'no such column: (\S+)', msg)
    if m:
        return f'列不存在：{m.group(1)}（检查列名拼写或别名）'
    m = re.search(r'near "([^"]*)": syntax error', msg)
    if m:
        return f'SQL 语法错误：{m.group(1)!r} 附近有误'
    if 'misuse of aggregate' in msg:
        return '聚合函数用法有误（如 WHERE 中直接使用 COUNT/AVG 等）'
    return f'SQL 执行错误：{msg}'


def _build_env(table_schema, initial_data):
    """在内存库中构建题目环境（表结构 + 初始数据），失败返回 None"""
    if not (table_schema and str(table_schema).strip()):
        return None
    conn = sqlite3.connect(':memory:')
    try:
        conn.executescript(str(table_schema))
        if initial_data and str(initial_data).strip():
            conn.executescript(str(initial_data))
        return conn
    except sqlite3.Error:
        conn.close()
        return None


def _fetch(conn, sql):
    cur = conn.execute(sql)
    rows = [tuple(r) for r in cur.fetchall()]
    cols = [d[0].lower() for d in (cur.description or [])]
    return rows, cols


def _value_key(v):
    """值规范化：float 整数值与 int 视为相同（15000.0 == 15000）"""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _row_key(row):
    """行内值排序后转字符串（列顺序不影响比较）；值先转字符串避免 int/str 混排报错"""
    return str(sorted(_value_key(v) for v in row))


def judge(user_sql, correct_sql, table_schema, initial_data):
    """执行 SQL 判题。

    返回 (is_correct, result_rows, error_message)：
    - is_correct: 布尔
    - result_rows: 用户查询返回的行（环境可用时），否则 None
    - error_message: 用户 SQL 执行失败时的友好提示，成功时为 None
    """
    user_sql = (user_sql or '').strip()
    correct_sql = (correct_sql or '').strip()

    if not user_sql:
        return False, None, '答案不能为空'
    if not _check_read_only_single_statement(user_sql):
        return False, None, '请只提交一条 SELECT 查询语句'
    # 快速路径：字符串规范化一致时无需执行
    if answers_match(user_sql, correct_sql):
        return True, None, None

    conn = _build_env(table_schema, initial_data)
    if conn is None:
        # 环境不可用 → 回退字符串比对（旧行为）
        return answers_match(user_sql, correct_sql), None, None

    try:
        try:
            u_rows, u_cols = _fetch(conn, user_sql)
        except sqlite3.Error as e:
            return False, None, _friendly_error(e)
        try:
            c_rows, c_cols = _fetch(conn, correct_sql)
        except sqlite3.Error as e:
            # 标准答案本身执行失败（题库数据问题）→ 回退字符串比对
            return answers_match(user_sql, correct_sql), None, f'标准答案执行失败（题库问题）：{e}'

        # 列数比对（列名不参与：COUNT(*) 与 COUNT(非空列) 等语义等价写法应判对）
        if len(u_cols) != len(c_cols):
            return False, u_rows, f'列数不匹配：预期 {len(c_cols)} 列，实际 {len(u_cols)} 列'
        # 行集比对：列顺序、行顺序均不影响（保留重复行）
        if sorted(_row_key(r) for r in u_rows) == sorted(_row_key(r) for r in c_rows):
            return True, u_rows, None
        return False, u_rows, f'结果不匹配：预期 {len(c_rows)} 行，实际 {len(u_rows)} 行'
    finally:
        conn.close()
