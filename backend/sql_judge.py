"""SQL 判题引擎

优先在内存 SQLite 中真实执行用户 SQL 与标准答案，比较结果集；
行顺序比对跟随标准答案：标准答案含 ORDER BY 时按顺序逐行比对，否则行集无序比对；
列顺序始终不影响判定。
考察点限定（required points）：题目可显式配置必检构造（JSON），未配置时从标准答案
自动推导（ORDER BY/GROUP BY 键完整性 + HAVING/DISTINCT/OVER/EXISTS/UNION 等关键字），
用户答案缺少任一考察点即判错并返回详细解析。
环境数据缺失或无法构建时，回退到字符串规范化比对（兼容旧行为）。
"""
import re
import json
import sqlite3
import hashlib
import threading
from collections import Counter

# 允许用户提交的语句首关键字（SQLite 中只有这些不会产生写操作）
_READ_ONLY_FIRST = ('select', 'with', 'explain', 'pragma')
# 写操作/DDL 首关键字：标准答案是这类语句时，题目期望用户提交同类型语句，
# 判定方式为执行后比对全表快照（表结构 + 各表数据），而非查询结果集
_WRITE_FIRST = ('insert', 'update', 'delete', 'create', 'alter', 'drop', 'replace')

# 单条用户 SQL 的最大执行时长（秒），防止极端查询拖死判题线程
_EXEC_TIMEOUT_SECONDS = 4.0

# 标准答案结果缓存（key = 环境+标准答案摘要）：同题反复判题不必重复执行标准答案
_expected_cache = {}
_cache_lock = threading.Lock()
_MAX_CACHE = 1024


def _env_digest(correct_sql, table_schema, initial_data):
    raw = '\x1f'.join([correct_sql or '', str(table_schema or ''), str(initial_data or '')])
    return hashlib.sha1(raw.encode('utf-8', 'ignore')).hexdigest()


def _has_order_by(sql):
    """检测 SQL 是否包含 ORDER BY 子句（先去注释；字符串字面量中恰好出现该词属于极端情况，按含 ORDER BY 处理）"""
    return bool(re.search(r'\border\s+by\b', _strip_comments(sql or ''), re.IGNORECASE))


def _compute_expected(correct_sql, table_schema, initial_data):
    """在独立环境中执行标准答案，返回 (列数, 排序后的行 key 元组, 按原始顺序的行 key 元组, 全库快照)；
    写操作/DDL 无结果集时前三项为 (0, (), ())、快照为执行后的全库状态。
    执行失败/环境缺失返回 None"""
    conn = _build_env(table_schema, initial_data)
    if conn is None:
        return None
    try:
        _rows, cols = _fetch(conn, correct_sql)
        if not cols:
            # 写操作/DDL：比对执行后的全库快照（结构 + 数据）
            return (0, (), (), _snapshot(conn))
        keys = [_row_key(r) for r in _rows]
        return (len(cols), tuple(sorted(keys)), tuple(keys), None)
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _get_expected(correct_sql, table_schema, initial_data):
    """读取/计算标准答案缓存（进程内，线程安全；失败不缓存）"""
    key = _env_digest(correct_sql, table_schema, initial_data)
    with _cache_lock:
        hit = _expected_cache.get(key)
        if hit is not None:
            return hit
    exp = _compute_expected(correct_sql, table_schema, initial_data)
    if exp is not None:
        with _cache_lock:
            if len(_expected_cache) >= _MAX_CACHE:
                _expected_cache.clear()
            _expected_cache[key] = exp
    return exp


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


def _split_statements(sql):
    """按顶层分号切分语句，返回非空语句列表。

    追踪引号状态（' 字符串字面量 / " 标识符 / ` 反引号），
    引号内的分号不切分；'' 双单引号视为转义，不提前闭合。
    注释须在调用前剥离（_strip_comments），否则注释里的分号会误切。
    """
    parts, buf = [], []
    quote = None
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                if i + 1 < n and sql[i + 1] == quote:
                    buf.append(sql[i + 1]); i += 1   # '' 转义：不闭合引号
                else:
                    quote = None
        else:
            if ch in '\'"`':
                quote = ch
                buf.append(ch)
            elif ch == ';':
                parts.append(''.join(buf))
                buf = []
            else:
                buf.append(ch)
        i += 1
    parts.append(''.join(buf))
    return [p.strip() for p in parts if p.strip()]


def _check_read_only_single_statement(sql):
    """校验：只能是一条只读语句（SELECT / WITH / EXPLAIN / PRAGMA）"""
    cleaned = _strip_comments(sql).strip()
    if not cleaned:
        return False
    parts = _split_statements(cleaned)
    if len(parts) != 1:
        return False
    first_word = parts[0].lstrip().split(None, 1)[0].lower()
    return first_word in _READ_ONLY_FIRST


def _single_statement_first_word(sql):
    """校验恰好一条语句，返回其首关键字（小写）；为空或多语句返回 None"""
    cleaned = _strip_comments(sql).strip()
    if not cleaned:
        return None
    parts = _split_statements(cleaned)
    if len(parts) != 1:
        return None
    return parts[0].lstrip().split(None, 1)[0].lower()


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


def _strict_row_key(row):
    """按列序保留的行 key（表快照用：同一表内列顺序由建表语句决定，需按位比较）"""
    return '(' + ', '.join(_value_key(v) for v in row) + ')'


def _snapshot(conn):
    """全库快照：{表名: (结构描述, 排序后的行 key 元组)}。
    结构描述含列名/类型/主键标记，可捕捉 CREATE/ALTER/DROP/RENAME 的结构差异。"""
    snap = {}
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for t in tables:
        cols = conn.execute(f'PRAGMA table_info("{t}")').fetchall()
        meta = ','.join(f'{c[1]}:{c[2]}:{"pk" if c[5] else ""}' for c in cols)
        keys = sorted(_strict_row_key(r) for r in conn.execute(f'SELECT * FROM "{t}"').fetchall())
        snap[t] = (meta, tuple(keys))
    return snap


def _snapshot_diff(expected, actual):
    """快照差异摘要（面向用户的一句话，最多 3 处）"""
    diffs = []
    for t in sorted(set(expected) | set(actual)):
        if t not in expected:
            diffs.append(f'多出了表 {t}')
        elif t not in actual:
            diffs.append(f'缺少表 {t}')
        else:
            (e_meta, e_keys), (a_meta, a_keys) = expected[t], actual[t]
            if e_meta != a_meta:
                diffs.append(f'表 {t} 结构不符：预期 [{e_meta}]，实际 [{a_meta}]')
            elif e_keys != a_keys:
                d = _mismatch_detail(e_keys, a_keys, limit=2)
                diffs.append(f'表 {t} 数据不符：预期 {len(e_keys)} 行，实际 {len(a_keys)} 行{d}')
        if len(diffs) >= 3:
            break
    return '；'.join(diffs)


def _run_real_judge(user_sql, correct_sql, table_schema, initial_data):
    """在独立内存环境中执行用户 SQL 并取标准答案缓存，返回过程结果 dict。
    仅在判题工作线程内调用（SQLite 连接不跨线程）。"""
    conn = _build_env(table_schema, initial_data)
    if conn is None:
        return {'fallback': True}
    try:
        try:
            u_rows, u_cols = _fetch(conn, user_sql)
        except sqlite3.Error as e:
            return {'user_error': _friendly_error(e)}
        expected = _get_expected(correct_sql, table_schema, initial_data)
        if expected is None:
            return {'bank_error': True}   # 标准答案执行失败（题库问题）
        out = {'u_rows': u_rows, 'u_cols': u_cols, 'expected': expected}
        if expected[3] is not None:
            # 快照模式：标准答案是写操作/DDL，比对用户执行后的全库状态
            out['u_snapshot'] = _snapshot(conn)
        return out
    finally:
        conn.close()


def _run_with_timeout(user_sql, correct_sql, table_schema, initial_data):
    """带超时的真实判题（工作线程内新建环境，避免 SQLite 连接跨线程）"""
    box = {}

    def _target():
        try:
            box['result'] = _run_real_judge(user_sql, correct_sql, table_schema, initial_data)
        except Exception as e:
            box['result'] = {'internal_error': str(e)}

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(_EXEC_TIMEOUT_SECONDS)
    if t.is_alive():
        return {'timeout': True}
    return box.get('result', {'internal_error': '判题进程异常退出'})


def _mismatch_detail(expected_keys, actual_keys, limit=3):
    """行差异摘要：预期有但用户没有的行 / 用户多余的行（含重复差异）"""
    missing = list((Counter(expected_keys) - Counter(actual_keys)).elements())
    extra = list((Counter(actual_keys) - Counter(expected_keys)).elements())
    detail = ''
    if missing:
        detail += f'；缺少示例行：{" | ".join(missing[:limit])}'
    if extra:
        detail += f'；多余示例行：{" | ".join(extra[:limit])}'
    return detail


def _order_mismatch_detail(expected_keys, actual_keys):
    """顺序敏感比对的差异摘要：行数不符，或首个顺序不一致的位置"""
    if len(expected_keys) != len(actual_keys):
        return f'预期 {len(expected_keys)} 行，实际 {len(actual_keys)} 行'
    for i, (e, a) in enumerate(zip(expected_keys, actual_keys)):
        if e != a:
            return f'第 {i + 1} 行顺序不符：预期 {e}，实际 {a}'
    return ''


# ==================== 考察点限定（required points） ====================
# 每题可配置 required_points（JSON 列表）；未配置时从标准答案自动推导。
# 支持的检查项 kind：
#   order_by  —— 必须使用 ORDER BY 且排序键完整（键书写顺序不限）
#   group_by  —— 必须使用 GROUP BY 且分组键完整
#   keyword   —— 必须出现指定关键字（HAVING / DISTINCT / OVER / EXISTS / UNION 等）
# 检查失败返回面向用户的详细解析（缺什么、为什么需要、怎么写）。

_KEYWORD_POINTS = {
    'HAVING':   ('使用 HAVING 对分组聚合后的结果进行筛选', '聚合条件（如 COUNT(*) > n）不能写在 WHERE 中，应在 GROUP BY 后用 HAVING'),
    'DISTINCT': ('使用 DISTINCT 去除重复行', '在 SELECT 后加 DISTINCT'),
    'OVER':     ('使用窗口函数', '窗口函数形如 ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)'),
    'EXISTS':   ('使用 EXISTS 相关子查询判断存在性', '形如 WHERE EXISTS (SELECT 1 FROM ...)'),
    'UNION':    ('使用 UNION 合并多个查询结果', '注意 UNION 去重、UNION ALL 保留重复'),
}

_IDENT_RE = re.compile(r'^[A-Za-z_][\w$]*(\.[A-Za-z_][\w$]*)*$')


def _split_top_level(s):
    """按顶层逗号切分（忽略括号内的逗号）"""
    parts, depth, buf = [], 0, ''
    for ch in s:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth = max(0, depth - 1)
        if ch == ',' and depth == 0:
            parts.append(buf)
            buf = ''
        else:
            buf += ch
    parts.append(buf)
    return [p.strip() for p in parts if p.strip()]


def _extract_clause(sql, keyword, terminators):
    """提取某子句（ORDER BY / GROUP BY）的全部片段文本（大小写不敏感，已去注释）"""
    pattern = rf'\b{keyword}\b(.*?)(?:{"|".join(terminators)}|;|$)'
    return re.findall(pattern, sql, re.IGNORECASE | re.DOTALL)


def _normalize_key(expr):
    """规整键表达式：去引号/反引号、压空白、去掉尾部 ASC/DESC，返回 (键, 方向)"""
    e = re.sub(r'[`"]', '', expr or '').strip()
    e = re.sub(r'\s+', ' ', e)
    direction = 'ASC'
    m = re.search(r'\s+(ASC|DESC)\s*$', e, re.IGNORECASE)
    if m:
        direction = m.group(1).upper()
        e = e[:m.start()].strip()
    return e, direction


def _blank_over_clauses(sql):
    """把 OVER(...) 括号块整体抹掉：窗口里的 ORDER BY 不代表输出排序，不能据此要求结果有序"""
    out, i = [], 0
    for m in re.finditer(r'\bover\s*\(', sql, re.IGNORECASE):
        out.append(sql[i:m.start()])
        depth, j = 0, m.end() - 1
        while j < len(sql):
            if sql[j] == '(':
                depth += 1
            elif sql[j] == ')':
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        i = j
    out.append(sql[i:])
    return ''.join(out)


def derive_required_points(correct_sql):
    """从标准答案自动推导考察点限定（题目未显式配置时使用）。

    推导规则：ORDER BY/GROUP BY 的键完整性 + 关键构造（HAVING/DISTINCT/OVER/EXISTS/UNION）。
    窗口 OVER(...) 内的 ORDER BY 是窗口内排序，不作为输出排序考察点。"""
    sql = _strip_comments(correct_sql or '')
    clause_sql = _blank_over_clauses(sql)
    points = []
    order_parts = _extract_clause(clause_sql, r'ORDER\s+BY', [r'\bLIMIT\b', r'\bOFFSET\b'])
    if order_parts:
        keys = [_normalize_key(k) for k in _split_top_level(' , '.join(order_parts))]
        keys = [(e, d) for e, d in keys if e]
        if keys:
            order_desc = '、'.join(f'{e} {("降序" if d == "DESC" else "升序")}' for e, d in keys)
            points.append({
                'kind': 'order_by', 'keys': [{'expr': e, 'dir': d} for e, d in keys],
                'desc': f'结果需按 {order_desc} 排序输出',
                'hint': '使用 ORDER BY ' + ', '.join(f'{e} {d}' for e, d in keys),
            })
    group_parts = _extract_clause(sql, r'GROUP\s+BY', [r'\bHAVING\b', r'\bORDER\s+BY\b', r'\bLIMIT\b', r'\bUNION\b'])
    if group_parts:
        keys = [_normalize_key(k)[0] for k in _split_top_level(' , '.join(group_parts))]
        keys = [e for e in keys if e]
        if keys:
            points.append({
                'kind': 'group_by', 'keys': [{'expr': e} for e in keys],
                'desc': f'需按 {"、".join(keys)} 分组',
                'hint': '使用 GROUP BY ' + ', '.join(keys),
            })
    for kw, (desc, hint) in _KEYWORD_POINTS.items():
        if re.search(rf'\b{kw}\b', sql, re.IGNORECASE):
            points.append({'kind': 'keyword', 'value': kw, 'desc': desc, 'hint': hint})
    return points


def _parse_required_points(raw):
    """解析题目配置的 required_points（JSON 字符串/列表）；空或非法返回 None（走自动推导）"""
    if not raw:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return None
    if not isinstance(raw, list) or not raw:
        return None
    return [p for p in raw if isinstance(p, dict) and p.get('kind')]


def _key_in_clause(key, clause_text):
    """键表达式是否出现在子句文本中：标识符按键名/带表前缀两种形式词边界匹配，其余按去空白子串匹配"""
    text = re.sub(r'[`"]', '', clause_text or '').lower()
    text = re.sub(r'\s+', ' ', text)
    k = (key or '').lower()
    if _IDENT_RE.match(key or ''):
        for form in {k, k.split('.')[-1]}:
            if re.search(rf'(?<![\w$]){re.escape(form)}(?![\w$])', text):
                return True
        return False
    return re.sub(r'\s+', '', k) in re.sub(r'\s+', '', text)


def _check_required_points(user_sql, points):
    """逐项检查考察点；全部通过返回 None，否则返回面向用户的详细解析"""
    clean = _strip_comments(user_sql or '')
    clause_sql = _blank_over_clauses(clean)   # 窗口内 ORDER BY 不算输出排序
    user_order = ' ; '.join(_extract_clause(clause_sql, r'ORDER\s+BY', [r'\bLIMIT\b', r'\bOFFSET\b']))
    user_group = ' ; '.join(_extract_clause(clause_sql, r'GROUP\s+BY', [r'\bHAVING\b', r'\bORDER\s+BY\b', r'\bLIMIT\b', r'\bUNION\b']))
    for p in points:
        kind = p.get('kind')
        desc = p.get('desc') or ''
        hint = p.get('hint') or ''
        hint_txt = f' 提示：{hint}' if hint else ''
        if kind == 'order_by':
            if not user_order:
                return f'考察点未达成【排序】：{desc}，但你的答案没有使用 ORDER BY。{hint_txt}'
            missing = [k['expr'] for k in p.get('keys', []) if not _key_in_clause(k.get('expr', ''), user_order)]
            if missing:
                return f'考察点未达成【排序】：{desc}，但你的 ORDER BY 缺少排序键：{"、".join(missing)}。{hint_txt}'
        elif kind == 'group_by':
            if not user_group:
                return f'考察点未达成【分组】：{desc}，但你的答案没有使用 GROUP BY。{hint_txt}'
            missing = [k['expr'] for k in p.get('keys', []) if not _key_in_clause(k.get('expr', ''), user_group)]
            if missing:
                return f'考察点未达成【分组】：{desc}，但你的 GROUP BY 缺少分组键：{"、".join(missing)}。{hint_txt}'
        elif kind == 'keyword':
            value = (p.get('value') or '').strip()
            if value and not re.search(rf'\b{re.escape(value)}\b', clean, re.IGNORECASE):
                return f'考察点未达成【{value}】：{desc}。{hint_txt}'
    return None


def judge(user_sql, correct_sql, table_schema, initial_data, required_points=None):
    """执行 SQL 判题。

    required_points：题目级考察点限定（JSON 字符串或列表），为空时从标准答案自动推导。

    返回 (is_correct, result_rows, error_message)：
    - is_correct: 布尔
    - result_rows: 用户查询返回的行（环境可用时），否则 None
    - error_message: 用户 SQL 执行失败时的友好提示，成功时为 None
    """
    user_sql = (user_sql or '').strip()
    correct_sql = (correct_sql or '').strip()

    if not user_sql:
        return False, None, '答案不能为空'
    expected_is_write = _single_statement_first_word(correct_sql) in _WRITE_FIRST
    user_first = _single_statement_first_word(user_sql)
    if user_first is None:
        return False, None, ('请只提交一条 SQL 语句' if expected_is_write
                             else '请只提交一条 SELECT 查询语句')
    if expected_is_write:
        if user_first not in _WRITE_FIRST:
            return False, None, '题目要求执行数据修改/结构变更语句（INSERT/UPDATE/DELETE/DDL），而不是查询'
    elif user_first not in _READ_ONLY_FIRST:
        return False, None, '请只提交一条 SELECT 查询语句'
    # 考察点限定：用户答案必须真实出现题目考察的构造（显式配置优先，否则从标准答案推导）
    points = _parse_required_points(required_points)
    if points is None:
        points = derive_required_points(correct_sql)
    needs_order = any(p.get('kind') == 'order_by' for p in points)
    point_err = _check_required_points(user_sql, points)
    if point_err:
        return False, None, point_err
    # 快速路径：字符串规范化一致时无需执行
    if answers_match(user_sql, correct_sql):
        return True, None, None
    # 无表结构/数据 → 环境不可用，回退字符串比对（旧行为）
    if not (table_schema and str(table_schema).strip()):
        return answers_match(user_sql, correct_sql), None, None

    result = _run_with_timeout(user_sql, correct_sql, table_schema, initial_data)
    if result.get('timeout'):
        return False, None, f'执行超时（超过 {_EXEC_TIMEOUT_SECONDS:.0f} 秒），请检查查询是否过于复杂'
    if result.get('fallback'):
        return answers_match(user_sql, correct_sql), None, None
    if result.get('user_error'):
        return False, None, result['user_error']
    if result.get('bank_error'):
        # 标准答案在环境里执行失败（题库问题）→ 不冤枉用户，回退字符串比对
        return answers_match(user_sql, correct_sql), None, '标准答案执行失败（题库问题）：环境执行异常'
    if result.get('internal_error'):
        return False, None, f'SQL 执行错误：{result["internal_error"]}'

    u_rows = result['u_rows']
    u_cols = result['u_cols']
    exp_col_count, exp_keys_sorted, exp_keys_ordered, exp_snapshot = result['expected']
    if exp_snapshot is not None:
        # 写操作/DDL：比对执行后的全库快照（表结构 + 各表数据）
        u_snapshot = result.get('u_snapshot', {})
        if u_cols:
            return False, u_rows, '题目要求执行数据修改/结构变更语句（INSERT/UPDATE/DELETE/DDL），而不是查询'
        if u_snapshot == exp_snapshot:
            return True, None, None
        return False, None, f'执行结果与预期不符：{_snapshot_diff(exp_snapshot, u_snapshot)}'
    # 列数比对（列名不参与：COUNT(*) 与 COUNT(非空列) 等语义等价写法应判对）
    if len(u_cols) != exp_col_count:
        return False, u_rows, f'列数不匹配：预期 {exp_col_count} 列，实际 {len(u_cols)} 列'
    # 行比对：列顺序不影响（保留重复行）；标准答案含 ORDER BY 时行顺序必须一致，否则行集无序比对
    if needs_order:
        act_keys_ordered = [_row_key(r) for r in u_rows]
        if act_keys_ordered == list(exp_keys_ordered):
            return True, u_rows, None
        detail = _order_mismatch_detail(exp_keys_ordered, act_keys_ordered)
        return False, u_rows, f'结果顺序不匹配：{detail}'
    act_keys = sorted(_row_key(r) for r in u_rows)
    if act_keys == list(exp_keys_sorted):
        return True, u_rows, None
    detail = _mismatch_detail(exp_keys_sorted, act_keys)
    return False, u_rows, f'结果不匹配：预期 {len(exp_keys_sorted)} 行，实际 {len(act_keys)} 行{detail}'
