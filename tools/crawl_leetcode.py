"""LeetCode 数据库类题目爬虫（GraphQL 公开接口，无需登录）。

抓取 free 题目的题面（英文 HTML），抽取 <pre> 块中的 ASCII 表
（表结构定义 + 示例输入输出），保存为 data/leetcode_questions.json，
供后续批次改写为系统填空题（中文题面 + SQLite schema/data + 参考答案）。

用法：
    python tools/crawl_leetcode.py            # 全量抓取（约 300 题，含限速）
    python tools/crawl_leetcode.py --limit 5  # 调试用，只抓前 5 题
"""
import json
import os
import re
import sys
import time

import requests

GQL = 'https://leetcode.com/graphql'
OUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'leetcode_questions.json')
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json', 'Referer': 'https://leetcode.com/problemset/database/'}

LIST_QUERY = {
    'query': '''query questionList($categorySlug: String, $limit: Int, $skip: Int) {
      questionList(categorySlug: $categorySlug, limit: $limit, skip: $skip, filters: {}) {
        totalNum
        data { questionFrontendId titleSlug title difficulty isPaidOnly }
      }
    }''',
    'variables': {'categorySlug': 'database', 'limit': 100, 'skip': 0},
}

DETAIL_QUERY = {
    'query': '''query questionData($titleSlug: String!) {
      question(titleSlug: $titleSlug) { questionFrontendId title difficulty content }
    }''',
    'variables': {},
}


def gql(payload, retries=3):
    for i in range(retries):
        try:
            r = requests.post(GQL, json=payload, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f'  retry {i + 1}: {e}')
        time.sleep(2 * (i + 1))
    return None


def list_all():
    items, skip, total = [], 0, None
    while total is None or skip < total:
        p = dict(LIST_QUERY)
        p['variables'] = dict(LIST_QUERY['variables'], skip=skip)
        data = gql(p)
        ql = (data or {}).get('data', {}).get('questionList', {})
        total = ql.get('totalNum', 0)
        batch = ql.get('data', [])
        if not batch:
            break
        items.extend(batch)
        skip += len(batch)
        time.sleep(0.3)
    return items


def strip_html(html):
    """HTML → 纯文本（保留 pre 块的 ASCII 布局）"""
    if not html:
        return ''
    s = html
    s = re.sub(r'<sup>(.*?)</sup>', r'\1', s, flags=re.DOTALL)
    s = re.sub(r'<sub>(.*?)</sub>', r'\1', s, flags=re.DOTALL)
    s = re.sub(r'<code>(.*?)</code>', r'`\1`', s, flags=re.DOTALL)
    s = re.sub(r'<strong>(.*?)</strong>', r'\1', s, flags=re.DOTALL)
    s = re.sub(r'<em>(.*?)</em>', r'\1', s, flags=re.DOTALL)
    s = re.sub(r'<li>(.*?)</li>', r'\n- \1', s, flags=re.DOTALL)
    s = re.sub(r'<br\s*/?>', '\n', s)
    s = re.sub(r'</(p|ul|ol|div)>', '\n', s)
    s = re.sub(r'<[^>]+>', '', s)
    s = (s.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>')
         .replace('&amp;', '&').replace('&quot;', '"').replace('&#39;', "'"))
    return re.sub(r'\n{3,}', '\n\n', s).strip()


def extract_pre_blocks(html):
    """抽取 <pre> 块文本（ASCII 表所在处）"""
    blocks = re.findall(r'<pre[^>]*>(.*?)</pre>', html or '', flags=re.DOTALL)
    out = []
    for b in blocks:
        t = strip_html(b)
        t = re.sub(r'[ \t]+\n', '\n', t).strip()
        if t:
            out.append(t)
    return out


def main():
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else None
    print('拉取题目列表 ...')
    items = list_all()
    print(f'共 {len(items)} 道数据库题')
    free = [q for q in items if not q.get('isPaidOnly')]
    print(f'其中免费 {len(free)} 道')
    if limit:
        free = free[:limit]
    results = []
    for i, q in enumerate(free):
        slug = q['titleSlug']
        p = dict(DETAIL_QUERY)
        p['variables'] = {'titleSlug': slug}
        data = gql(p)
        question = (data or {}).get('data', {}).get('question') or {}
        content = question.get('content')
        if not content:
            print(f'[{i + 1}/{len(free)}] {slug} 无题面，跳过')
            continue
        results.append({
            'frontend_id': int(question.get('questionFrontendId') or q['questionFrontendId']),
            'slug': slug,
            'title': question.get('title') or q.get('title'),
            'difficulty': (question.get('difficulty') or q.get('difficulty')).lower(),
            'text': strip_html(content),
            'pre_blocks': extract_pre_blocks(content),
        })
        print(f'[{i + 1}/{len(free)}] {slug} ok')
        time.sleep(0.3)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f'已保存 {len(results)} 题 → {OUT}')


if __name__ == '__main__':
    main()
