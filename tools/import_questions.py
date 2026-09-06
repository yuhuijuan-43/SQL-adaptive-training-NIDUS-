# -*- coding: utf-8 -*-
"""题库扩充批次导入工具

用法:
  python tools/import_questions.py data/questions_batch1.json --check   # 仅校验
  python tools/import_questions.py data/questions_batch1.json --import  # 校验 + 入库 + 追加进 data/questions.json

校验规则（与 backend 现有逻辑对齐）:
  - category 必须属于官方 29 个标签；difficulty 与标签星级一致
  - options 按 | 分隔（|| 视为 SQL 连接符，不当分隔符）后必须 4 项且非空
  - correct_answer 必须与某个选项文本完全一致（服务端按选项文本比对判分）
  - option_explanations 数量与选项一致
  - q_level: easy -> basic，其余 -> advanced
  - 与现有题库 (title, description) 不重复
入库:
  - 备份 questions.db 到 backend/backups/
  - 写入 questions 表 + question_knowledge 关联（node_id = category）
  - 追加到 data/questions.json（保持文件与库内数量一致，避免触发重建）
"""
import json, os, sqlite3, sys, argparse, glob, time

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.join(os.path.dirname(__file__), '..')

# 官方标签 -> 难度（与 backend/seeding.py 的 TAG_DIFFICULTY 保持一致；★易 ★★中 ★★★难）
TAG_DIFFICULTY = {
    'dml_select': 'easy', 'dml_insert': 'easy', 'dml_update': 'easy', 'dml_delete': 'easy',
    'select_basic': 'easy', 'where_basic': 'easy', 'group_by': 'medium', 'having': 'hard',
    'string_func': 'easy', 'numeric_func': 'easy', 'aggregate_func': 'medium',
    'cast_func': 'medium', 'window_func': 'hard',
    'subquery_scalar': 'medium', 'subquery_column': 'medium', 'subquery_table': 'hard', 'subquery_in': 'hard',
    'join_inner': 'medium', 'join_outer': 'medium', 'join_self': 'hard', 'join_cross': 'medium',
    'constraint_primary_key': 'easy', 'constraint_foreign_key': 'medium',
    'ddl_create': 'easy', 'ddl_alter': 'medium', 'ddl_drop': 'easy', 'ddl_truncate': 'easy',
    'ddl_rename': 'easy', 'ddl_comment': 'easy',
}

def backup_db(db_path, tag):
    """在线备份（等价 backend/backup.py 的逻辑，独立实现以避免 flask 依赖）"""
    os.makedirs(os.path.join(ROOT, 'backend', 'backups'), exist_ok=True)
    target = os.path.join(ROOT, 'backend', 'backups', f"questions-{time.strftime('%Y%m%d-%H%M%S')}-{tag}.db")
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(target)
    src.backup(dst)
    dst.close(); src.close()
    return target

def split_opts(s):
    # 与 app.py shuffle_options 一致：|| 是 SQL 连接符（转义保护），切分后需还原
    return [o.replace('\x00', '||') for o in (s or '').replace('||', '\x00').split('|') if o.strip()]

def load_json(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)

def validate(batch, existing):
    sys.path.insert(0, os.path.join(ROOT, 'backend'))
    from sql_judge import judge  # 填空题自校验：标准答案必须能被自己的环境判对
    errors, warnings = [], []
    seen = {(q['title'], q['description']) for q in existing}
    cats = set()
    for i, q in enumerate(batch, 1):
        tag = f"#{i} [{q.get('category')}] {q.get('title','')[:20]}"
        # 必填字段
        for k in ('source','category','difficulty','title','description','correct_answer'):
            if not str(q.get(k, '')).strip():
                errors.append(f"{tag}: 字段 {k} 为空")
        cat = q.get('category','')
        cats.add(cat)
        if cat not in TAG_DIFFICULTY:
            errors.append(f"{tag}: 非法类别 {cat}")
        elif q.get('difficulty') != TAG_DIFFICULTY[cat]:
            errors.append(f"{tag}: 难度 {q.get('difficulty')} 与类别要求 {TAG_DIFFICULTY[cat]} 不一致")
        is_fill = not str(q.get('options', '')).strip()
        if is_fill:
            # 填空题：必须有表结构，且标准答案能在自身环境中实判通过
            if not str(q.get('table_schema', '')).strip():
                errors.append(f"{tag}: 填空题缺少 table_schema")
            else:
                ok, _, err = judge(q['correct_answer'], q['correct_answer'],
                                   q.get('table_schema'), q.get('initial_data'))
                if not ok:
                    errors.append(f"{tag}: 标准答案实判失败：{err}")
        else:
            # 选择题：选项格式校验
            opts = split_opts(q.get('options',''))
            if len(opts) != 4:
                errors.append(f"{tag}: 选项数 {len(opts)} != 4")
            if q.get('correct_answer','').strip() not in [o.strip() for o in opts]:
                errors.append(f"{tag}: correct_answer 不在选项中")
            exps = split_opts(q.get('option_explanations',''))
            if exps and len(exps) != len(opts):
                errors.append(f"{tag}: 选项解析数 {len(exps)} 与选项数 {len(opts)} 不一致")
        # q_level
        expect_level = 'basic' if q.get('difficulty') == 'easy' else 'advanced'
        if q.get('q_level') != expect_level:
            errors.append(f"{tag}: q_level 应为 {expect_level}")
        # 去重
        key = (q.get('title'), q.get('description'))
        if key in seen:
            errors.append(f"{tag}: 与现有题目重复")
        seen.add(key)
    return errors, cats

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('batch_file')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--import', dest='do_import', action='store_true')
    args = ap.parse_args()

    batch = load_json(args.batch_file)
    existing_path = os.path.join(ROOT, 'data', 'questions.json')
    existing = load_json(existing_path)
    print(f"批次题数: {len(batch)}  现有题数: {len(existing)}")

    errors, cats = validate(batch, existing)
    if errors:
        print("\n❌ 校验失败:")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print(f"✅ 校验通过，覆盖类别 {len(cats)} 个")
    if not args.do_import:
        return

    # 备份 + 入库
    db_path = os.path.join(ROOT, 'backend', 'questions.db')
    bp = backup_db(db_path, 'batch1-import')
    print(f"数据库备份: {bp}")
    conn = sqlite3.connect(db_path, timeout=15)
    conn.execute("PRAGMA busy_timeout=15000")
    cur = conn.cursor()
    before = cur.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    if before != len(existing):
        print(f"⚠️ 库内题数 {before} 与 questions.json 题数 {len(existing)} 不一致，中止（避免与 seed 重建逻辑冲突）")
        sys.exit(2)
    for q in batch:
        cur.execute('''INSERT INTO questions (source,category,difficulty,title,description,table_schema,initial_data,
                       correct_answer,explanation,options,option_explanations,expected_output,pool,q_level)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (q['source'], q['category'], q['difficulty'], q['title'], q['description'],
                     q.get('table_schema',''), q.get('initial_data',''), q['correct_answer'],
                     q.get('explanation',''), q.get('options',''), q.get('option_explanations',''),
                     q.get('expected_output',''), 'practice', q.get('q_level')))
        qid = cur.lastrowid
        cur.execute('INSERT OR IGNORE INTO question_knowledge (question_id,node_id) VALUES (?,?)',
                    (qid, q['category']))
    conn.commit()
    after = cur.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    conn.close()
    print(f"入库完成: {before} -> {after}")

    # 追加到 data/questions.json
    with open(existing_path, 'w', encoding='utf-8') as f:
        json.dump(existing + batch, f, ensure_ascii=False, indent=2)
    print(f"questions.json 已更新: {len(existing)} -> {len(existing)+len(batch)}")

if __name__ == '__main__':
    main()
