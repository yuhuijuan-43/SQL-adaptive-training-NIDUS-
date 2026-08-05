"""测试公共夹具：临时 SQLite 库 + 最小种子数据 + Flask test client

要点：
- 所有测试通过 monkeypatch db.DB_PATH 重定向到临时文件，绝不触碰真实 questions.db
- 最小种子：2 道题（1 选择 + 1 填空）+ 知识图谱（seed_knowledge_graph 会按 category 自动映射题目节点）
- RATELIMIT_ENABLED=False：关闭限流，避免测试客户端共享 IP 撞限
"""
import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

SCHEMA = 'CREATE TABLE employees (id INT, name VARCHAR(20), dept VARCHAR(20), salary INT);'
DATA = "INSERT INTO employees VALUES (1,'张三','技术部',15000),(2,'李四','市场部',12000),(3,'王五','技术部',18000);"


@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'test.db'))
    db.init_db()
    conn = db.get_connection()
    # q1: select_basic 进阶选择题（有 options、无 q_level → 非 basic）
    conn.execute(
        "INSERT INTO questions (source,category,difficulty,title,description,table_schema,initial_data,correct_answer,explanation,options) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        ('t', 'select_basic', 'easy', '查询所有', '查询所有员工', SCHEMA, DATA,
         'SELECT * FROM employees', 'SELECT * 查询所有列', 'SELECT * FROM employees;|SELECT ALL FROM employees;'))
    # q2: select_basic 填空题
    conn.execute(
        "INSERT INTO questions (source,category,difficulty,title,description,table_schema,initial_data,correct_answer,explanation) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ('t', 'select_basic', 'easy', '查询姓名', '查询所有员工姓名', SCHEMA, DATA,
         'SELECT name FROM employees', 'SELECT 指定列'))
    # q3: select_basic 基础选择题（q_level='basic'，初次进标签应优先推送）
    conn.execute(
        "INSERT INTO questions (source,category,difficulty,title,description,table_schema,initial_data,correct_answer,explanation,options,q_level) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ('static_basic', 'select_basic', 'easy', 'SELECT 概念', '选择正确的查询语句', '', '',
         'B. SELECT', 'SELECT 语句', 'A. DELETE|B. SELECT|C. UPDATE', 'basic'))
    # q4: join_inner 填空题（select_basic 掌握后解锁的新标签）
    conn.execute(
        "INSERT INTO questions (source,category,difficulty,title,description,table_schema,initial_data,correct_answer,explanation) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ('t', 'join_inner', 'medium', '内连接查询', '查询员工与部门', SCHEMA, DATA,
         'SELECT * FROM employees e JOIN departments d ON e.dept = d.dept', 'JOIN 连接'))
    # q5: dml_select 基础选择题（图谱点亮轮：top_dml 为首个活跃枝、dml_select 为第一叶）
    conn.execute(
        "INSERT INTO questions (source,category,difficulty,title,description,table_schema,initial_data,correct_answer,explanation,options,q_level) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ('static_basic', 'dml_select', 'easy', 'DML SELECT 概念', '选择正确的查询语句', '', '',
         'B. SELECT * FROM employees', 'DML SELECT 语句',
         'A. DELETE FROM employees|B. SELECT * FROM employees|C. DROP TABLE employees', 'basic'))
    # q6: dml_select 填空题
    conn.execute(
        "INSERT INTO questions (source,category,difficulty,title,description,table_schema,initial_data,correct_answer,explanation) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ('t', 'dml_select', 'easy', '查询技术部员工', '查询技术部员工姓名', SCHEMA, DATA,
         "SELECT name FROM employees WHERE dept = '技术部'", 'WHERE 条件'))
    conn.commit()
    from seeding import seed_knowledge_graph
    seed_knowledge_graph()
    return db


@pytest.fixture()
def client(test_db, monkeypatch):
    import app as app_mod
    app_mod.app.config['TESTING'] = True
    app_mod.limiter.enabled = False          # flask-limiter 3.x: enabled 是实例属性
    # 统一管理员密钥：统一密钥从 DB 读（未设置时回退 env），测试注入 env 即可生效
    monkeypatch.setenv('ADMIN_TOKEN', 'test-admin-token')
    with app_mod.app.test_client() as c:
        yield c
