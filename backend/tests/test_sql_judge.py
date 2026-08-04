"""SQL 判题引擎测试：真实执行 + 结果集比对 + 错误提示 + 回退路径"""
import pytest

from sql_judge import judge, normalize_sql, answers_match

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


def test_row_order_is_correct():
    # 行顺序不同（去掉 ORDER BY 但恰好一致的多集）
    ok, _, _ = judge('SELECT name, salary FROM employees', CORRECT, SCHEMA, DATA)
    assert ok is True


def test_aggregate_equivalent_forms():
    # COUNT(*) 与 COUNT(非空列) 结果集一致
    correct = 'SELECT dept, COUNT(*) FROM employees GROUP BY dept'
    ok, _, _ = judge('SELECT dept, COUNT(name) FROM employees GROUP BY dept', correct, SCHEMA, DATA)
    assert ok is True


def test_missing_column_reports_mismatch():
    ok, rows, err = judge('SELECT name FROM employees', CORRECT, SCHEMA, DATA)
    assert ok is False
    assert '列数不匹配' in err
    assert rows is not None


def test_wrong_rows_reported():
    ok, rows, err = judge('SELECT name, salary FROM employees WHERE salary > 999999', CORRECT, SCHEMA, DATA)
    assert ok is False
    assert '预期 3 行' in err and '实际 0 行' in err


def test_syntax_error_friendly():
    ok, _, err = judge('SELECT name FROMM employees', CORRECT, SCHEMA, DATA)
    assert ok is False and '语法错误' in err


def test_no_such_table_friendly():
    ok, _, err = judge('SELECT * FROM nonexist', CORRECT, SCHEMA, DATA)
    assert ok is False and '表不存在' in err


def test_no_such_column_friendly():
    ok, _, err = judge('SELECT bad_col FROM employees', CORRECT, SCHEMA, DATA)
    assert ok is False and '列不存在' in err


def test_write_statement_rejected():
    for bad in ('DELETE FROM employees', 'UPDATE employees SET salary=0',
                'DROP TABLE employees', 'INSERT INTO employees VALUES (9,\'x\')'):
        ok, _, err = judge(bad, CORRECT, SCHEMA, DATA)
        assert ok is False and '只提交一条 SELECT' in err, bad


def test_multi_statement_rejected():
    ok, _, err = judge('SELECT 1; SELECT 2', CORRECT, SCHEMA, DATA)
    assert ok is False and '只提交一条 SELECT' in err


def test_empty_answer_rejected():
    ok, _, err = judge('', CORRECT, SCHEMA, DATA)
    assert ok is False and '不能为空' in err


def test_comment_wrapped_read_only_allowed():
    # 注释不影响只读校验
    ok, _, _ = judge('/* 注释 */ SELECT name, salary FROM employees', CORRECT, SCHEMA, DATA)
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
