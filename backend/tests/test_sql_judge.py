"""SQL 判题引擎测试：真实执行 + 结果集比对 + 错误提示 + 回退路径"""
import json

import pytest
from sql_judge import judge, derive_required_points, _check_required_points, _parse_required_points, normalize_sql, answers_match

SCHEMA = 'CREATE TABLE employees (id INT, name VARCHAR(20), dept VARCHAR(20), salary INT);'
DATA = "INSERT INTO employees VALUES (1,'张三','技术部',15000),(2,'李四','市场部',12000),(3,'王五','技术部',18000);"
CORRECT = 'SELECT name, salary FROM employees ORDER BY salary DESC'


def test_exact_match():
    ok, rows, err = judge('SELECT name, salary FROM employees ORDER BY salary DESC', CORRECT, SCHEMA, DATA)
    assert ok is True and err is None


def test_column_reorder_is_correct():
    # 列顺序不同：结果集语义相同
    ok, _, _ = judge('SELECT salary, name FROM employees ORDER BY salary DESC', CORRECT, SCHEMA, DATA)
    assert ok is True


def test_row_order_matters_when_bank_has_order_by():
    # 标准答案含 ORDER BY：去掉 ORDER BY 判错并提示（2026-09-05 修复：旧版无序比对会误放）
    ok, _, err = judge('SELECT name, salary FROM employees', CORRECT, SCHEMA, DATA)
    assert ok is False and 'ORDER BY' in err


def test_wrong_row_order_is_wrong():
    # 标准答案含 ORDER BY：行集合相同但顺序不符判错（ASC 与 DESC 相反）
    ok, rows, err = judge('SELECT name, salary FROM employees ORDER BY salary ASC', CORRECT, SCHEMA, DATA)
    assert ok is False and '顺序不匹配' in err and '第 1 行' in err
    assert rows is not None


def test_right_row_order_is_correct():
    # 顺序一致即判对（含列重排等价写法）
    ok, _, err = judge('SELECT salary, name FROM employees ORDER BY salary DESC', CORRECT, SCHEMA, DATA)
    assert ok is True and err is None


def test_row_order_free_when_bank_has_no_order_by():
    # 标准答案不含 ORDER BY：维持行集无序比对
    correct = 'SELECT name, salary FROM employees'
    ok, _, _ = judge('SELECT name, salary FROM employees ORDER BY salary DESC', correct, SCHEMA, DATA)
    assert ok is True


def test_aggregate_equivalent_forms():
    # COUNT(*) 与 COUNT(非空列) 结果集一致
    correct = 'SELECT dept, COUNT(*) FROM employees GROUP BY dept'
    ok, _, _ = judge('SELECT dept, COUNT(name) FROM employees GROUP BY dept', correct, SCHEMA, DATA)
    assert ok is True


def test_missing_column_reports_mismatch():
    ok, rows, err = judge('SELECT name FROM employees ORDER BY salary DESC', CORRECT, SCHEMA, DATA)
    assert ok is False
    assert '列数不匹配' in err
    assert rows is not None


def test_wrong_rows_reported():
    # 含 ORDER BY 以通过排序硬性检查，行数不符走顺序敏感摘要
    ok, rows, err = judge('SELECT name, salary FROM employees WHERE salary > 999999 ORDER BY salary DESC', CORRECT, SCHEMA, DATA)
    assert ok is False
    assert '预期 3 行' in err and '实际 0 行' in err


def test_syntax_error_friendly():
    ok, _, err = judge('SELECT name FROMM employees ORDER BY salary DESC', CORRECT, SCHEMA, DATA)
    assert ok is False and '语法错误' in err


def test_no_such_table_friendly():
    ok, _, err = judge('SELECT * FROM nonexist ORDER BY salary DESC', CORRECT, SCHEMA, DATA)
    assert ok is False and '表不存在' in err


def test_no_such_column_friendly():
    ok, _, err = judge('SELECT bad_col FROM employees ORDER BY salary DESC', CORRECT, SCHEMA, DATA)
    assert ok is False and '列不存在' in err


def test_write_statement_rejected():
    for bad in ('DELETE FROM employees', 'UPDATE employees SET salary=0',
                'DROP TABLE employees', 'INSERT INTO employees VALUES (9,\'x\')'):
        ok, _, err = judge(bad, CORRECT, SCHEMA, DATA)
        assert ok is False and '只提交一条 SELECT' in err, bad


def test_multi_statement_rejected():
    ok, _, err = judge('SELECT 1; SELECT 2', CORRECT, SCHEMA, DATA)
    assert ok is False and '只提交一条 SELECT' in err


def test_multi_statement_with_write_rejected():
    # 第二条是写语句同样拒绝（2026-08-12 回归：分割器重写后仍拦截）
    ok, _, err = judge('SELECT 1; DELETE FROM employees', CORRECT, SCHEMA, DATA)
    assert ok is False and '只提交一条 SELECT' in err


def test_semicolon_inside_string_literal_allowed():
    # 字符串字面量内的分号不应被误判为多语句（2026-08-12 修复）
    ok, _, err = judge("SELECT 'a;b' AS x", "SELECT 'a;b' AS x", SCHEMA, DATA)
    assert ok is True and err is None
    # 含中文分号内容的合法查询：报"结果不匹配"而非"多语句"
    ok, _, err = judge("SELECT name FROM employees WHERE name='张;三'",
                       'SELECT name FROM employees', SCHEMA, DATA)
    assert ok is False and '只提交一条' not in err and '结果不匹配' in err


def test_escaped_quote_with_semicolon_allowed():
    # '' 转义引号不提前闭合，其后的分号仍属字符串内
    ok, _, err = judge("SELECT 'it''s; fine' AS x", "SELECT 'it''s; fine' AS x", SCHEMA, DATA)
    assert ok is True and err is None


def test_empty_answer_rejected():
    ok, _, err = judge('', CORRECT, SCHEMA, DATA)
    assert ok is False and '不能为空' in err


def test_comment_wrapped_read_only_allowed():
    # 注释不影响只读校验
    ok, _, _ = judge('/* 注释 */ SELECT name, salary FROM employees ORDER BY salary DESC', CORRECT, SCHEMA, DATA)
    assert ok is True


def test_fallback_when_no_schema():
    # 环境缺失 → 回退字符串比对
    assert judge('SELECT * FROM employees', 'SELECT * FROM employees', None, None)[0] is True
    assert judge('SELECT * FROM employees', 'SELECT * FROM emp', None, None)[0] is False


def test_fallback_when_bank_sql_broken():
    # 标准答案在环境中执行失败 → 回退字符串比对（不冤枉用户）
    ok, _, err = judge('SELECT * FROM employees', 'SELECT * FROM broken', SCHEMA, DATA)
    assert ok is False and err and '标准答案执行失败' in err


def test_normalize_sql_still_works():
    assert answers_match('select a,b from t;', 'SELECT b, a FROM t')
    assert not answers_match('select a from t', 'select b from t')


def test_wrong_rows_include_missing_sample():
    # 行不匹配时给出具体差异示例，而不只是行数（用无 ORDER BY 的标准答案走无序比对路径）
    correct = 'SELECT name, salary FROM employees'
    ok, rows, err = judge('SELECT name, salary FROM employees WHERE salary > 999999', correct, SCHEMA, DATA)
    assert ok is False
    assert '缺少示例行' in err
    assert rows is not None


def test_expected_result_cached(monkeypatch):
    # 同一标准答案二次判题直接命中缓存（不再重复执行标准答案）
    import sql_judge
    sql_judge._expected_cache.clear()
    # 列数不符但含 ORDER BY（否则会先被 ORDER BY 硬性检查拦截，走不到标准答案执行）
    assert judge('SELECT name FROM employees ORDER BY salary DESC', CORRECT, SCHEMA, DATA)[0] is False
    assert sql_judge._expected_cache
    called = {'n': 0}
    orig = sql_judge._compute_expected

    def counting(*a, **kw):
        called['n'] += 1
        return orig(*a, **kw)

    monkeypatch.setattr(sql_judge, '_compute_expected', counting)
    # 语义等价但文本不同（不走字符串快速路径），命中缓存判对
    assert judge('SELECT name, salary FROM employees WHERE salary > 0 ORDER BY salary DESC', CORRECT, SCHEMA, DATA)[0] is True
    assert called['n'] == 0   # 命中缓存，未重复执行标准答案


def test_sql_execution_timeout(monkeypatch):
    import sql_judge
    monkeypatch.setattr(sql_judge, '_EXEC_TIMEOUT_SECONDS', 0.05)
    monkeypatch.setattr(sql_judge, '_run_real_judge', lambda *a, **kw: __import__('time').sleep(1))
    ok, _, err = judge('SELECT name, salary FROM employees WHERE salary > 0 ORDER BY salary DESC', CORRECT, SCHEMA, DATA)
    assert ok is False and '执行超时' in err


# ==================== 考察点限定（required points） ====================

PROFILE_SCHEMA = 'CREATE TABLE user_profile (id INT, device_id INT, gender VARCHAR(10), age INT, university VARCHAR(50), gpa FLOAT);'
PROFILE_DATA = ("INSERT INTO user_profile VALUES "
                "(1,2130,'male',21,'北京大学',3.4),(2,3214,'male',23,'复旦大学',4.0),"
                "(3,6543,'female',20,'北京大学',3.2),(4,2315,'female',23,'浙江大学',3.6),"
                "(5,5432,'male',25,'山东大学',3.8),(6,2131,'male',28,'北京理工大学',3.3);")
PROFILE_CORRECT = 'SELECT device_id, gpa, age FROM user_profile ORDER BY gpa DESC, age DESC'


def test_derive_order_by_keys_with_direction():
    pts = derive_required_points(PROFILE_CORRECT)
    assert len(pts) == 1 and pts[0]['kind'] == 'order_by'
    assert [(k['expr'], k['dir']) for k in pts[0]['keys']] == [('gpa', 'DESC'), ('age', 'DESC')]
    assert 'gpa' in pts[0]['desc'] and 'age' in pts[0]['desc'] and 'ORDER BY' in pts[0]['hint']


def test_derive_group_by_and_keywords():
    pts = derive_required_points('SELECT dept, COUNT(DISTINCT name) c FROM employees GROUP BY dept HAVING c > 1')
    kinds = [p['kind'] for p in pts]
    assert 'group_by' in kinds and 'keyword' in kinds
    kw_values = [p['value'] for p in pts if p['kind'] == 'keyword']
    assert 'HAVING' in kw_values and 'DISTINCT' in kw_values


def test_derive_ignores_window_order_by():
    # 窗口 OVER(...) 内的 ORDER BY 不是输出排序考察点，但 OVER 本身是关键考察点
    pts = derive_required_points('SELECT name, ROW_NUMBER() OVER (ORDER BY salary DESC) rn FROM employees')
    assert not any(p['kind'] == 'order_by' for p in pts)
    assert any(p['kind'] == 'keyword' and p['value'] == 'OVER' for p in pts)


def test_order_keys_incomplete_is_wrong():
    # 只写一个排序键：考察点不完整，即使数据无并列、结果恰好一致也判错
    ok, _, err = judge('SELECT device_id, gpa, age FROM user_profile ORDER BY gpa DESC',
                       PROFILE_CORRECT, PROFILE_SCHEMA, PROFILE_DATA)
    assert ok is False and '缺少排序键' in err and 'age' in err


def test_order_keys_complete_passes_feature_check():
    ok, _, err = judge(PROFILE_CORRECT, PROFILE_CORRECT, PROFILE_SCHEMA, PROFILE_DATA)
    assert ok is True and err is None


def test_order_keys_with_table_prefix_accepted():
    ok, _, err = judge('SELECT device_id, gpa, age FROM user_profile u ORDER BY u.gpa DESC, u.age DESC',
                       PROFILE_CORRECT, PROFILE_SCHEMA, PROFILE_DATA)
    assert ok is True and err is None


def test_group_by_key_incomplete_is_wrong():
    correct = 'SELECT dept, COUNT(*) c FROM employees GROUP BY dept, name'
    err = _check_required_points('SELECT dept FROM employees GROUP BY dept', derive_required_points(correct))
    assert err and '缺少分组键' in err and 'name' in err


def test_keyword_point_missing_is_wrong():
    correct = 'SELECT dept, COUNT(*) c FROM employees GROUP BY dept HAVING COUNT(*) > 1'
    err = _check_required_points('SELECT dept FROM employees GROUP BY dept', derive_required_points(correct))
    assert err and 'HAVING' in err


def test_explicit_required_points_override():
    # 显式配置优先：自定义考察点与解析文案
    rp = '[{"kind":"keyword","value":"JOIN","desc":"必须使用表连接","hint":"用 JOIN ... ON 关联两表"}]'
    ok, _, err = judge('SELECT name FROM employees', 'SELECT name FROM employees', SCHEMA, DATA, rp)
    assert ok is False and '必须使用表连接' in err and 'JOIN ... ON' in err
    # 显式配置为空列表时回退自动推导
    ok2, _, err2 = judge('SELECT name, salary FROM employees', CORRECT, SCHEMA, DATA, '[]')
    assert ok2 is False and 'ORDER BY' in err2


def test_malformed_required_points_falls_back_to_derive():
    ok, _, err = judge('SELECT name, salary FROM employees', CORRECT, SCHEMA, DATA, 'not-json')
    assert ok is False and 'ORDER BY' in err


def test_parse_required_points():
    assert _parse_required_points(None) is None
    assert _parse_required_points('') is None
    assert _parse_required_points('bad') is None
    assert _parse_required_points('[]') is None
    pts = _parse_required_points('[{"kind":"keyword","value":"HAVING"}]')
    assert pts == [{'kind': 'keyword', 'value': 'HAVING'}]


# ==================== 写操作/DDL 快照判题 ====================

INSERT_CORRECT = "INSERT INTO employees VALUES (4,'赵六','技术部',16000)"


def test_insert_snapshot_correct():
    ok, _, err = judge("INSERT INTO employees VALUES (4,'赵六','技术部',16000)", INSERT_CORRECT, SCHEMA, DATA)
    assert ok is True, err


def test_insert_snapshot_wrong_value():
    ok, _, err = judge("INSERT INTO employees VALUES (4,'赵六','技术部',99999)", INSERT_CORRECT, SCHEMA, DATA)
    assert ok is False and '数据不符' in err


def test_insert_snapshot_select_rejected():
    ok, _, err = judge("SELECT * FROM employees", INSERT_CORRECT, SCHEMA, DATA)
    assert ok is False and '而不是查询' in err


def test_update_snapshot_correct():
    correct = "UPDATE employees SET salary = 20000 WHERE dept = '技术部'"
    ok, _, err = judge("update employees set salary=20000 where dept='技术部'", correct, SCHEMA, DATA)
    assert ok is True, err


def test_update_snapshot_wrong_scope():
    correct = "UPDATE employees SET salary = 20000 WHERE dept = '技术部'"
    ok, _, err = judge("UPDATE employees SET salary = 20000", correct, SCHEMA, DATA)
    assert ok is False and '数据不符' in err


def test_delete_snapshot():
    correct = "DELETE FROM employees WHERE id = 3"
    ok1, _, err1 = judge("DELETE FROM employees WHERE id = 3", correct, SCHEMA, DATA)
    assert ok1 is True, err1
    ok2, _, err2 = judge("DELETE FROM employees WHERE id = 1", correct, SCHEMA, DATA)
    assert ok2 is False and '数据不符' in err2


def test_create_table_snapshot():
    correct = "CREATE TABLE dept_backup (id INT, name VARCHAR(20))"
    ok1, _, err1 = judge("CREATE TABLE dept_backup (id INT, name VARCHAR(20))", correct, SCHEMA, DATA)
    assert ok1 is True, err1
    ok2, _, err2 = judge("CREATE TABLE dept_backup (id INT)", correct, SCHEMA, DATA)
    assert ok2 is False and '结构不符' in err2


def test_drop_table_snapshot():
    correct = "DROP TABLE employees"
    ok1, _, err1 = judge("DROP TABLE employees", correct, SCHEMA, DATA)
    assert ok1 is True, err1


def test_alter_table_snapshot():
    correct = "ALTER TABLE employees ADD COLUMN email VARCHAR(50)"
    ok1, _, err1 = judge("ALTER TABLE employees ADD COLUMN email VARCHAR(50)", correct, SCHEMA, DATA)
    assert ok1 is True, err1


def test_write_multi_statement_rejected():
    ok, _, err = judge("INSERT INTO employees VALUES (4,'a','x',1); DELETE FROM employees", INSERT_CORRECT, SCHEMA, DATA)
    assert ok is False and '一条' in err
