# -*- coding: utf-8 -*-
"""来源名称脱敏：把爬取来源的真实站点名替换为谐音站名

source 字段映射:
  crawl_leetcode#<id>              -> 蓝客#<id>   (LeetCode)
  crawl_w3resource                 -> 三资学堂    (w3resource)
  牛客 / 牛客网 / nowcoder / crawl_nowcoder -> 纽客

文本字段(title/description/explanation/option_explanations)站名替换:
  LeetCode/力扣 -> 蓝客;  w3resource -> 三资学堂;  牛客/nowcoder -> 纽客

用法:
  python tools/rename_sources.py            # 预览（dry-run）
  python tools/rename_sources.py --apply    # 写库 + 同步 JSON
"""
import json, os, re, sqlite3, sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.join(os.path.dirname(__file__), '..')
DB = os.path.join(ROOT, 'backend', 'questions.db')

JSON_FILES = [
    'data/questions.json',
    'data/exam_questions.json',
    'data/questions_batch1.json',
    'data/batches/b2_all.json',
    'data/batches/b2_lc_fill.json',
    'data/batches/b2_dml_insert.json',
    'data/batches/b2_dml_ops.json',
    'data/batches/b2_group_having.json',
    'data/batches/b2_select_where.json',
]

TEXT_RULES = [
    ('LeetCode', '蓝客'), ('leetcode', '蓝客'), ('力扣', '蓝客'),
    ('W3Resource', '三资学堂'), ('w3resource', '三资学堂'),
    ('NowCoder', '纽客'), ('nowcoder', '纽客'), ('牛客网', '纽客'), ('牛客', '纽客'),
]
TEXT_FIELDS = ('title', 'description', 'explanation', 'option_explanations')


def map_source(s):
    if not s:
        return s
    m = re.match(r'^crawl_leetcode(#.*)?$', s or '')
    if m:
        return '蓝客' + (m.group(1) or '')
    if s == 'crawl_w3resource':
        return '三资学堂'
    if s in ('牛客', '牛客网', 'nowcoder', 'crawl_nowcoder'):
        return '纽客'
    return s


def map_text(s):
    if not s:
        return s
    for old, new in TEXT_RULES:
        s = s.replace(old, new)
    return s


def rename_in_db(apply):
    conn = sqlite3.connect(DB)
    src_changed, text_changed = {}, {}
    for table in ('questions', 'exam_questions'):
        try:
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info({table})')]
        except sqlite3.OperationalError:
            continue
        if 'source' in cols:
            pk = 'id' if 'id' in cols else cols[0]
            for qid, src in conn.execute(f'SELECT {pk}, source FROM {table}'):
                new = map_source(src)
                if new != src:
                    src_changed.setdefault(table, []).append((qid, src, new))
                    if apply:
                        conn.execute(f'UPDATE {table} SET source=? WHERE {pk}=?', (new, qid))
        fields = [f for f in TEXT_FIELDS if f in cols]
        if fields:
            pk = 'id' if 'id' in cols else cols[0]
            sel = f'SELECT {pk}, {", ".join(fields)} FROM {table}'
            for row in conn.execute(sel):
                qid, vals = row[0], row[1:]
                updates = {}
                for f, v in zip(fields, vals):
                    nv = map_text(v or '')
                    if nv != (v or ''):
                        updates[f] = nv
                if updates:
                    text_changed.setdefault(table, []).append((qid, updates))
                    if apply:
                        sets = ', '.join(f'{f}=?' for f in updates)
                        conn.execute(f'UPDATE {table} SET {sets} WHERE {pk}=?',
                                     (*updates.values(), qid))
    if apply:
        conn.commit()
    conn.close()
    return src_changed, text_changed


def sync_json(rel, apply):
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return 0
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    n = 0
    for q in data:
        before = dict(q)
        q['source'] = map_source(q.get('source', ''))
        for f in TEXT_FIELDS:
            if q.get(f):
                q[f] = map_text(q[f])
        if q != before:
            n += 1
    if apply and n:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return n


def main():
    apply = '--apply' in sys.argv
    src_changed, text_changed = rename_in_db(apply)
    if not src_changed:
        print('[DB] source 无需改名')
    for table, items in src_changed.items():
        print(f'[DB {table}] source {len(items)} 条改名')
    if not text_changed:
        print('[DB] 文本字段无站名残留')
    for table, items in text_changed.items():
        print(f'[DB {table}] 文本字段 {len(items)} 条含站名:')
        for qid, updates in items[:6]:
            for f, nv in updates.items():
                print(f'  #{qid} {f}: ...{nv[:70]}')
        if len(items) > 6:
            print(f'  ... 共 {len(items)} 条')
    for rel in JSON_FILES:
        n = sync_json(rel, apply)
        if n:
            print(f'[{rel}] {n} 条同步')
    print('=== 已应用 ===' if apply else '=== 预览模式，加 --apply 生效 ===')


if __name__ == '__main__':
    main()
