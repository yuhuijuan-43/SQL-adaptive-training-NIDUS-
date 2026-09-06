# -*- coding: utf-8 -*-
"""考察点限定（required_points）批量生成工具

从每道填空题的标准答案自动推导必检考察点（ORDER BY/GROUP BY 键完整性 +
HAVING/DISTINCT/OVER/EXISTS/UNION 等关键字），生成含详细解析的 JSON 配置。

用法:
  python tools/gen_required_points.py                # 预览（dry-run，打印全部推导结果）
  python tools/gen_required_points.py --apply        # 写回数据库（仅覆盖填空题、且当前无显式配置的行）
  python tools/gen_required_points.py --table questions --apply
"""
import json, os, sqlite3, sys, argparse

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'backend'))

from sql_judge import derive_required_points

def point_summary(p):
    if p['kind'] == 'order_by':
        keys = ', '.join(f"{k['expr']} {k['dir']}" for k in p['keys'])
        return f"[排序] 要求 ORDER BY {keys}"
    if p['kind'] == 'group_by':
        keys = ', '.join(k['expr'] for k in p['keys'])
        return f"[分组] 要求 GROUP BY {keys}"
    return f"[关键字] 要求出现 {p['value']}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='写回数据库（默认仅预览）')
    ap.add_argument('--table', choices=['questions', 'exam_questions', 'all'], default='all')
    ap.add_argument('--force', action='store_true', help='覆盖已有的显式配置')
    args = ap.parse_args()

    tables = ['questions', 'exam_questions'] if args.table == 'all' else [args.table]
    conn = sqlite3.connect(os.path.join(ROOT, 'backend', 'questions.db'), timeout=15)
    conn.row_factory = sqlite3.Row

    for table in tables:
        try:
            rows = conn.execute(f"SELECT id, title, options, correct_answer, required_points FROM {table}").fetchall()
        except sqlite3.Error as e:
            print(f"跳过 {table}：{e}（可能是旧库缺少 required_points 列，请先启动一次后端完成迁移）")
            continue
        fill_blanks = [r for r in rows if not (r['options'] or '').strip()]
        print(f"\n===== {table}：共 {len(rows)} 题，填空题 {len(fill_blanks)} 道 =====")
        n_written = n_skip = 0
        for r in fill_blanks:
            if r['required_points'] and not args.force:
                n_skip += 1
                continue
            points = derive_required_points(r['correct_answer'])
            if not points:
                continue
            print(f"\n#{r['id']} {r['title']}")
            for p in points:
                print(f"   {point_summary(p)}")
                print(f"      解析: {p.get('desc','')} | 提示: {p.get('hint','')}")
            if args.apply:
                conn.execute(f"UPDATE {table} SET required_points=? WHERE id=?",
                             (json.dumps(points, ensure_ascii=False), r['id']))
                n_written += 1
        if args.apply:
            conn.commit()
            print(f"\n[{table}] 已写入 {n_written} 题，跳过已有配置 {n_skip} 题")
    conn.close()
    if not args.apply:
        print("\n（以上为预览，加 --apply 写回数据库）")

if __name__ == '__main__':
    main()
