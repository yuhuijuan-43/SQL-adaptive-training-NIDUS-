#!/usr/bin/env python3
"""
通用网络爬虫流水线 — Web Scraper Pipeline
===========================================
可复用的自动化爬取框架，配置驱动，支持断点续抓、Cookie自动提取、多策略解析。

用法:
  python web_scraper.py config.json          # 按配置文件执行全流程
  python web_scraper.py --cookies            # 从浏览器提取Cookie
  python web_scraper.py --resume             # 从上次中断处续抓

配置文件示例 (config.json):
{
  "name": "example_scraper",
  "cookie_source": "chrome",          // chrome | file:path | manual
  "cookie_domain": "example.com",
  "rate_limit": 0.5,                  // 请求间隔(秒)
  "retry": 3,                         // 失败重试次数
  "output_dir": "./scraped_data",
  "resume_file": "./scraped_data/progress.json",

  "steps": [
    {
      "name": "获取列表",
      "type": "api_list",             // api_list | page_list | page_detail
      "url": "https://api.example.com/items?page={page}",
      "method": "GET",
      "headers": {"Referer": "https://example.com"},
      "pagination": {"param": "page", "start": 1, "end": 10},
      "result_path": "data.items",    // JSON路径
      "item_id_field": "id",
      "item_url_template": "https://example.com/item/{id}",
      "save_as": "list.json"
    },
    {
      "name": "抓取详情",
      "type": "page_detail",
      "url_source": "list.json",      // 从哪个文件读取URL列表
      "url_field": "url",
      "extractors": [
        {"name": "title",   "selector": "h1.title",      "attr": "text"},
        {"name": "content", "selector": "div.content",   "attr": "html"},
        {"name": "date",    "selector": "span.date",     "attr": "text", "regex": "\\d{4}-\\d{2}-\\d{2}"}
      ],
      "save_format": "json"           // json | csv | folders
    }
  ]
}

环境要求: pip install websocket-client
浏览器: Chrome需开启调试端口 --remote-debugging-port=9222 --remote-allow-origins=*
"""

import json, os, sys, time, re, argparse, hashlib, random, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime

# ============================================================
# 核心框架
# ============================================================

class ScraperError(Exception): pass
class RateLimitError(ScraperError): pass
class AuthError(ScraperError): pass


class CookieManager:
    """统一Cookie管理：浏览器CDP / 文件 / 手动输入"""

    @staticmethod
    def from_chrome(domain, cdp_url="http://localhost:9222"):
        """从Chrome DevTools Protocol提取Cookie"""
        try:
            import websocket
        except ImportError:
            raise ScraperError("需要 websocket-client: pip install websocket-client")

        try:
            resp = urllib.request.urlopen(f"{cdp_url}/json", timeout=5)
            pages = json.loads(resp.read())
        except Exception:
            raise ScraperError(f"无法连接Chrome调试端口 ({cdp_url})\n"
                               "请用以下命令启动Chrome:\n"
                               '"chrome.exe" --remote-debugging-port=9222 --remote-allow-origins="*"')

        for page in pages:
            ws_url = page.get("webSocketDebuggerUrl", "")
            if not ws_url: continue
            try:
                ws = websocket.create_connection(ws_url, timeout=10)
                ws.send(json.dumps({"id": 1, "method": "Network.getCookies",
                                    "params": {"urls": [f"https://{domain}"]}}))
                time.sleep(1.5)
                buf = ""
                for _ in range(5):
                    try: buf += ws.recv()
                    except: break
                ws.close()
                for line in buf.strip().split("\n"):
                    try:
                        msg = json.loads(line)
                        cookies = msg.get("result", {}).get("cookies", [])
                        if cookies:
                            return "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                    except: pass
            except: pass
        raise ScraperError(f"未在Chrome中找到 {domain} 的Cookie，请确认已登录")

    @staticmethod
    def from_file(path):
        """从文件读取Cookie字符串"""
        if not os.path.exists(path):
            raise ScraperError(f"Cookie文件不存在: {path}")
        with open(path) as f:
            return f.read().strip()

    @staticmethod
    def resolve(source, domain):
        """根据配置获取Cookie"""
        if isinstance(source, str):
            if source == "chrome":
                return CookieManager.from_chrome(domain)
            elif source.startswith("file:"):
                return CookieManager.from_file(source[5:])
            elif source == "manual":
                print(f"\n请粘贴 {domain} 的Cookie值（格式: name1=val1; name2=val2）:")
                return input().strip()
            else:
                return source  # 直接当Cookie字符串用
        elif isinstance(source, dict):
            if source.get("type") == "chrome":
                return CookieManager.from_chrome(source.get("domain", domain),
                                                  source.get("cdp_url", "http://localhost:9222"))
            elif source.get("type") == "file":
                return CookieManager.from_file(source["path"])
            elif source.get("type") == "manual":
                return input(f"Cookie for {domain}: ").strip()
        return ""


class HTTPClient:
    """带重试、限速、Cookie管理的HTTP客户端"""

    def __init__(self, cookies="", rate_limit=0.5, retry=3, headers=None):
        self.cookies = cookies
        self.rate_limit = rate_limit
        self.retry = retry
        self.base_headers = headers or {}
        self._last_request = 0

    def _rate_limit(self):
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            jitter = random.uniform(0, self.rate_limit * 0.3)
            time.sleep(self.rate_limit - elapsed + jitter)
        self._last_request = time.time()

    def request(self, url, method="GET", headers=None, data=None, timeout=30):
        """发送HTTP请求，自动重试+限速"""
        h = {**self.base_headers}
        if self.cookies:
            h["Cookie"] = self.cookies
        if headers:
            h.update(headers)

        last_error = None
        for attempt in range(self.retry + 1):
            self._rate_limit()
            try:
                body = json.dumps(data).encode() if data else None
                req = urllib.request.Request(url, headers=h, data=body, method=method)
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return {
                        "status": r.status,
                        "headers": dict(r.headers),
                        "body": r.read().decode("utf-8", errors="ignore"),
                        "raw": r.read() if method == "HEAD" else None,
                    }
            except urllib.error.HTTPError as e:
                last_error = e
                if e.code == 429:
                    wait = 5 * (2 ** attempt)
                    print(f"  限流，等待 {wait}s...")
                    time.sleep(wait)
                    continue
                if e.code in (401, 403):
                    raise AuthError(f"认证失败 (HTTP {e.code})，Cookie可能已过期")
                if attempt < self.retry:
                    time.sleep(2 ** attempt)
            except Exception as e:
                last_error = e
                if attempt < self.retry:
                    time.sleep(2 ** attempt)

        raise ScraperError(f"请求失败 (已重试{self.retry}次): {url}\n  {last_error}")

    def get(self, url, **kw): return self.request(url, "GET", **kw)
    def post(self, url, data=None, **kw): return self.request(url, "POST", data=data, **kw)


class ProgressTracker:
    """断点续抓：记录进度，支持从中断处恢复"""

    def __init__(self, path):
        self.path = path
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path) as f:
                return json.load(f)
        return {"completed": [], "failed": [], "stats": {}, "last_update": None}

    def save(self):
        self.data["last_update"] = datetime.now().isoformat()
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def is_done(self, item_id):
        return item_id in self.data["completed"]

    def mark_done(self, item_id):
        if item_id not in self.data["completed"]:
            self.data["completed"].append(item_id)
        if item_id in self.data["failed"]:
            self.data["failed"].remove(item_id)

    def mark_failed(self, item_id):
        if item_id not in self.data["failed"]:
            self.data["failed"].append(item_id)

    def get_remaining(self, all_ids):
        return [i for i in all_ids if i not in self.data["completed"]]

    def set_stat(self, key, value):
        self.data["stats"][key] = value

    @property
    def completed_count(self):
        return len(self.data["completed"])

    @property
    def failed_count(self):
        return len(self.data["failed"])


class Extractor:
    """多策略内容提取器"""

    @staticmethod
    def extract(html, rules):
        """按规则从HTML提取内容。规则格式:
        [
          {"name": "title", "selector": "h1", "attr": "text"},
          {"name": "date",  "selector": ".date", "attr": "text", "regex": "..."},
          {"name": "body",  "selector": "div.content", "attr": "html"},
        ]
        也支持: {"name": "data", "regex": "pattern", "regex_group": 0}  // 从全文匹配
        """
        result = {}
        for rule in rules:
            name = rule["name"]
            val = ""
            try:
                if "selector" in rule:
                    sel = rule["selector"]
                    attr = rule.get("attr", "text")
                    # 简单CSS选择器支持 (tag, .class, #id)
                    elements = Extractor._css_select(html, sel)
                    if elements:
                        if attr == "text":
                            val = re.sub(r'<[^>]+>', '', elements[0]).strip()
                        elif attr == "html":
                            val = elements[0].strip()
                        elif attr == "src" or attr == "href":
                            m = re.search(rf'{attr}=["\']([^"\']*)["\']', elements[0])
                            val = m.group(1) if m else ""
                if "regex" in rule:
                    m = re.search(rule["regex"], val or html, re.DOTALL)
                    if m:
                        g = rule.get("regex_group", 0)
                        val = m.group(g) if g else m.group(0)
                if "default" in rule and not val:
                    val = rule["default"]
            except Exception as e:
                val = f"[EXTRACT_ERROR: {e}]"
            result[name] = val
        return result

    @staticmethod
    def _css_select(html, selector):
        """简易CSS选择器（tag, .class, #id, tag.class, parent>child）"""
        results = []
        # Parse selector
        tag = "\\w+"
        cls = None
        id_ = None
        rest = selector

        # ID
        m = re.match(r'#(\w+)', rest)
        if m:
            id_ = m.group(1)
            rest = rest[m.end():]

        # Class
        for m in re.finditer(r'\.([\w-]+)', rest):
            cls = m.group(1)
        # Tag
        m = re.match(r'^(\w+)', rest)
        if m and m.group(1) not in ('div','span','a','p','h1','h2','h3','h4','pre','table','li','ul','tr','td','th','code','textarea'):
            pass  # Not a tag
        elif m:
            tag = m.group(1)

        if id_:
            pattern = rf'<{tag}[^>]*\bid\s*=\s*["\']{id_}["\'][^>]*>(.*?)</{tag}>'
            matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            return matches
        elif cls:
            pattern = rf'<{tag}[^>]*\bclass\s*=\s*"[^"]*\b{cls}\b[^"]*"[^>]*>(.*?)</{tag}>'
            matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            return matches
        else:
            pattern = rf'<{tag}[^>]*>(.*?)</{tag}>'
            matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            return matches


class DataSaver:
    """统一的输出保存器"""

    @staticmethod
    def save(data, fmt, output_dir, item_id):
        os.makedirs(output_dir, exist_ok=True)
        if fmt == "json":
            path = os.path.join(output_dir, f"{item_id}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return path
        elif fmt == "folders":
            folder = os.path.join(output_dir, str(item_id))
            os.makedirs(folder, exist_ok=True)
            for key, val in data.items():
                ext = ".json" if isinstance(val, (dict, list)) else ".txt"
                with open(os.path.join(folder, f"{key}{ext}"), "w", encoding="utf-8") as f:
                    if isinstance(val, (dict, list)):
                        json.dump(val, f, ensure_ascii=False, indent=2)
                    else:
                        f.write(str(val))
            return folder
        elif fmt == "csv":
            path = os.path.join(output_dir, "data.csv")
            import csv
            existed = os.path.exists(path)
            with open(path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=data.keys())
                if not existed: writer.writeheader()
                writer.writerow(data)
            return path
        else:
            raise ScraperError(f"不支持的输出格式: {fmt}")


# ============================================================
# 步骤执行器
# ============================================================

class PipelineRunner:
    """按配置执行爬取流水线"""

    def __init__(self, config):
        self.config = config
        self.name = config.get("name", "unnamed")
        self.output_dir = config.get("output_dir", "./output")
        self.resume_file = config.get("resume_file", os.path.join(self.output_dir, "progress.json"))
        self.progress = ProgressTracker(self.resume_file)

        # 初始化HTTP客户端
        cookies = CookieManager.resolve(
            config.get("cookie_source", "chrome"),
            config.get("cookie_domain", "")
        )
        self.http = HTTPClient(
            cookies=cookies,
            rate_limit=config.get("rate_limit", 0.5),
            retry=config.get("retry", 3),
            headers=config.get("headers"),
        )
        print(f"[{self.name}] 初始化完成, Cookie: {'已获取' if cookies else '无'}")

    def run(self):
        """执行所有步骤"""
        steps = self.config.get("steps", [])
        print(f"[{self.name}] 共 {len(steps)} 个步骤\n")

        ctx = {}  # 步骤间共享上下文
        for i, step in enumerate(steps):
            name = step.get("name", f"step_{i+1}")
            stype = step.get("type", "")
            print(f"[{i+1}/{len(steps)}] {name}")
            try:
                if stype == "api_list":
                    result = self._run_api_list(step, ctx)
                elif stype == "page_list":
                    result = self._run_page_list(step, ctx)
                elif stype == "page_detail":
                    result = self._run_page_detail(step, ctx)
                else:
                    print(f"  未知步骤类型: {stype}，跳过")
                    continue

                ctx[name] = result
                print(f"  完成: {self._summarize(result)}")
            except Exception as e:
                print(f"  失败: {e}")
                if step.get("critical", False):
                    raise
        print(f"\n[{self.name}] 流水线结束")

    def _run_api_list(self, step, ctx):
        """API列表步骤：分页调用API获取列表"""
        pagination = step.get("pagination", {})
        param = pagination.get("param", "page")
        start = pagination.get("start", 1)
        end = pagination.get("end", 1)
        url_tpl = step["url"]
        result_path = step.get("result_path", "")

        all_items = []
        for page in range(start, end + 1):
            url = url_tpl.replace("{page}", str(page))
            resp = self.http.get(url, headers=step.get("headers"))
            data = json.loads(resp["body"])

            # 按路径提取数据
            items = data
            for key in result_path.split("."):
                if key: items = items.get(key, items) if isinstance(items, dict) else items

            if isinstance(items, list):
                all_items.extend(items)
                print(f"  page {page}: {len(items)} items")
            else:
                print(f"  page {page}: unexpected format")
                break

            # 检查是否有更多页
            if len(items) == 0 or (step.get("max_pages") and page >= step["max_pages"]):
                break

        # 保存
        save_as = step.get("save_as")
        if save_as:
            path = os.path.join(self.output_dir, save_as)
            os.makedirs(self.output_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(all_items, f, ensure_ascii=False, indent=2)

        return {"items": all_items, "total": len(all_items)}

    def _run_page_list(self, step, ctx):
        """页面列表步骤：从HTML页面提取列表"""
        url = step["url"]
        extractors = step.get("extractors", [])

        resp = self.http.get(url, headers=step.get("headers"))
        extracted = Extractor.extract(resp["body"], extractors)

        return {"extracted": extracted}

    def _run_page_detail(self, step, ctx):
        """详情页步骤：从列表批量抓取详情"""
        url_source = step.get("url_source")
        url_field = step.get("url_field", "url")
        id_field = step.get("id_field", url_field)
        extractors = step.get("extractors", [])
        save_fmt = step.get("save_format", "json")
        detail_dir = step.get("detail_dir", os.path.join(self.output_dir, "details"))

        # 加载URL列表
        if url_source:
            path = url_source if os.path.isabs(url_source) else os.path.join(self.output_dir, url_source)
            with open(path, encoding="utf-8") as f:
                items = json.load(f)
            if isinstance(items, dict) and "items" in items:
                items = items["items"]
        else:
            items = ctx.get("list", {}).get("items", [])

        if not items:
            print("  列表为空"); return {"processed": 0}

        stats = {"total": len(items), "processed": 0, "skipped": 0, "failed": 0}

        for i, item in enumerate(items):
            item_url = item.get(url_field, "") if isinstance(item, dict) else str(item)
            item_id = str(item.get(id_field, item_url)) if isinstance(item, dict) else str(i)
            item_id_hash = hashlib.md5(item_id.encode()).hexdigest()[:12]

            # 断点续抓：跳过已完成的
            if self.progress.is_done(item_id_hash):
                stats["skipped"] += 1; continue

            try:
                resp = self.http.get(item_url, headers=step.get("headers"))
                extracted = Extractor.extract(resp["body"], extractors)

                # 添加元数据
                extracted["_url"] = item_url
                extracted["_id"] = item_id
                extracted["_scraped_at"] = datetime.now().isoformat()

                DataSaver.save(extracted, save_fmt, detail_dir, item_id_hash)
                self.progress.mark_done(item_id_hash)
                stats["processed"] += 1

                if stats["processed"] % 20 == 0:
                    self.progress.save()
                    print(f"  ...{stats['processed']}/{stats['total']}")

            except Exception as e:
                self.progress.mark_failed(item_id_hash)
                stats["failed"] += 1
                print(f"  [{i+1}] {item_id[:40]} 失败: {e}")

        self.progress.set_stat("detail_stats", stats)
        self.progress.save()
        return stats

    @staticmethod
    def _summarize(result):
        if isinstance(result, dict):
            if "total" in result: return f"共 {result['total']} 条"
            if "processed" in result: return f"处理 {result['processed']}/{result['total']}，跳过 {result.get('skipped',0)}，失败 {result.get('failed',0)}"
            return f"{len(result)} 个字段"
        return str(type(result))


# ============================================================
# 命令行入口
# ============================================================

def print_config_guide():
    """打印JSON配置文件的完整编写指南"""
    print("""
+==============================================================+
|         web_scraper.py — JSON 配置文件编写指南               |
+==============================================================+

【最简示例】3步写出一个爬虫配置：

  {
    "name": "我的爬虫",              // 必填：爬虫名称
    "cookie_domain": "example.com", // 必填：目标网站域名
    "output_dir": "./output",       // 输出目录

    "steps": [
      {
        "type": "api_list",         // 步骤1：调API拿列表
        "url": "https://api.example.com/v1/items?page={page}",
        "pagination": {"param": "page", "start": 1, "end": 5},
        "result_path": "data.items"
      },
      {
        "type": "page_detail",      // 步骤2：逐条抓详情
        "extractors": [
          {"name": "title", "selector": "h1", "attr": "text"}
        ]
      }
    ]
  }


+--------------------------------------------------------------+
| 顶层配置字段                                                  |
|--------------------------------------------------------------|
| name            爬虫名称（用于日志）                           |
| cookie_source   认证方式: "chrome" | "file:cookies.txt"       |
|                 | "manual" | "key1=val1; key2=val2"         |
| cookie_domain   目标域名（chrome模式需要）                     |
| rate_limit      请求间隔秒数（默认0.5）                        |
| retry           失败重试次数（默认3）                          |
| headers         全局请求头 {"User-Agent":"...", "Referer":"..."}|
| output_dir      输出目录（默认./output）                       |
| resume_file     断点续抓进度文件                                |
+--------------------------------------------------------------+


+--------------------------------------------------------------+
| 步骤类型                                                     |
|--------------------------------------------------------------|
|                                                              |
| (1) api_list — 调用API获取列表                                  |
|   必须: type, url                                              |
|   可选: pagination, result_path, item_id_field, save_as       |
|                                                              |
|   {                                                          |
|     "type": "api_list",                                      |
|     "name": "获取列表",             // 步骤名（可选）          |
|     "url": "https://api.example.com/items?page={page}",      |
|     "method": "GET",               // GET 或 POST             |
|     "headers": {"X-Token": "xxx"}, // 本步骤专用请求头         |
|                                                              |
|     // 分页配置：                                               |
|     "pagination": {                                           |
|       "param": "page",             // 页码参数名               |
|       "start": 1,                  // 起始页码                 |
|       "end": 10                    // 结束页码                 |
|     },                                                        |
|                                                              |
|     // JSON数据路径（用 . 分隔）：                              |
|     "result_path": "data.items",   // 响应体 → data → items    |
|                                                              |
|     // 保存到文件：                                             |
|     "save_as": "list.json"         // 存到 output_dir 下      |
|   }                                                          |
|                                                              |
| (2) page_detail — 批量抓取详情页                                  |
|   必须: type, extractors                                       |
|   可选: url_source, url_field, detail_dir, save_format       |
|                                                              |
|   {                                                          |
|     "type": "page_detail",                                    |
|     "name": "抓取详情",                                        |
|     "url_source": "list.json",     // 从哪个列表文件读URL      |
|     "url_field": "url",            // 用列表项的哪一列作为URL   |
|     "detail_dir": "./details",     // 详情保存目录             |
|     "save_format": "json",         // json | folders | csv   |
|                                                              |
|     // 内容提取规则（核心）：                                   |
|     "extractors": [                                           |
|       {"name": "标题",  "selector": "h1.title", "attr":"text"},|
|       {"name": "正文",  "selector": "div.content","attr":"html"}|
|       {"name": "日期",  "regex": "\\\\d{4}-\\\\d{2}-\\\\d{2}"},|
|     ]                                                        |
|   }                                                          |
|                                                              |
| (3) page_list — 从HTML页面提取列表                                |
|   必须: type, url, extractors                                  |
|                                                              |
|   {                                                          |
|     "type": "page_list",                                      |
|     "url": "https://example.com/archive",                    |
|     "extractors": [{"name": "items", "regex": "..."}]        |
|   }                                                          |
|                                                              |
+--------------------------------------------------------------+


+--------------------------------------------------------------+
| Extractor 提取规则（关键！）                                    |
|--------------------------------------------------------------|
|                                                              |
| 每一条规则包含: name（字段名）+ 至少一种匹配方式                 |
|                                                              |
| 方式1: CSS选择器                                               |
|   {"name": "标题", "selector": "h1.title", "attr": "text"}   |
|   {"name": "链接", "selector": "a.btn",   "attr": "href"}    |
|   {"name": "内容", "selector": "div#main","attr": "html"}    |
|                                                              |
|   支持的 selector 格式:                                        |
|     h1           → <h1>...</h1>                              |
|     div.content  → <div class="content">...</div>           |
|     div#main     → <div id="main">...</div>                 |
|     table        → <table>...</table>                       |
|     pre          → <pre>...</pre>                           |
|                                                              |
|   支持的 attr:                                                 |
|     text → 提取文字内容（去HTML标签）                          |
|     html → 保留HTML标签                                       |
|     href → 提取链接地址                                       |
|     src  → 提取图片/资源地址                                   |
|                                                              |
| 方式2: 正则表达式                                                |
|   {"name": "日期", "regex": "\\\\d{4}-\\\\d{2}-\\\\d{2}"}       |
|   {"name": "ID",   "regex": "id=(\\\\d+)", "regex_group": 1}   |
|                                                              |
|   可选 regex_group: 捕获组编号（默认0=整个匹配）                 |
|                                                              |
| 方式3: 组合使用                                                  |
|   {"name": "简介", "selector": "div.content", "attr":"text", |
|    "regex": "^.{10,100}$"}                                   |
|   // 先CSS提取 → 再正则过滤                                     |
|                                                              |
| 方式4: 默认值                                                    |
|   {"name": "作者", "selector": "span.author",                 |
|    "default": "佚名"}                                         |
|   // 提取失败时用默认值                                         |
|                                                              |
+--------------------------------------------------------------+


+--------------------------------------------------------------+
| 完整流程示例：从零爬取一个博客网站                               |
|--------------------------------------------------------------|
|                                                              |
| 第1步: 先取Cookie（一次性，之后cookie存文件）                      |
|   python web_scraper.py --cookies                            |
|   → 输入域名 blog.example.com                                 |
|   → 得到 cookies_blog_example_com.txt                        |
|                                                              |
| 第2步: 写配置文件 blog_scraper.json:                             |
| {                                                            |
|   "name": "博客爬虫",                                          |
|   "cookie_source": "file:cookies_blog_example_com.txt",       |
|   "cookie_domain": "blog.example.com",                        |
|   "rate_limit": 0.5,                                         |
|   "output_dir": "./blog_data",                                |
|   "resume_file": "./blog_data/progress.json",                 |
|   "headers": {"User-Agent": "Mozilla/5.0"},                   |
|   "steps": [                                                  |
|     {                                                        |
|       "name": "获取文章列表",                                   |
|       "type": "api_list",                                     |
|       "url": "https://blog.example.com/api/posts?page={page}",|
|       "pagination": {"param": "page", "start": 1, "end": 5},  |
|       "result_path": "data.posts",                             |
|       "save_as": "posts_list.json"                             |
|     },                                                        |
|     {                                                        |
|       "name": "抓取文章正文",                                   |
|       "type": "page_detail",                                   |
|       "url_source": "posts_list.json",                         |
|       "url_field": "url",                                     |
|       "detail_dir": "./blog_data/articles",                   |
|       "save_format": "json",                                   |
|       "extractors": [                                          |
|         {"name": "标题",  "selector": "h1.post-title",        |
|                          "attr": "text"},                     |
|         {"name": "正文",  "selector": "article.content",      |
|                          "attr": "html"},                     |
|         {"name": "日期",  "selector": "time.date",            |
|                          "attr": "text"}                      |
|       ]                                                        |
|     }                                                        |
|   ]                                                          |
| }                                                            |
|                                                              |
| 第3步: 执行                                                     |
|   python web_scraper.py blog_scraper.json                     |
|                                                              |
| 第4步: 断点续抓（如果中断了）                                       |
|   python web_scraper.py blog_scraper.json --resume            |
|                                                              |
+--------------------------------------------------------------+


+--------------------------------------------------------------+
| 排错指南                                                     |
|--------------------------------------------------------------|
|                                                              |
| Q: Cookie过期了怎么办？                                          |
| A: 删除cookies_*.txt，重跑 --cookies                          |
|                                                              |
| Q: 爬了一半断了怎么办？                                          |
| A: 加 --resume 参数，自动跳过已完成项                             |
|                                                              |
| Q: 提取不到内容？                                               |
| A: 1) 先确认页面结构：curl | head 看HTML                        |
|    2) 调整 selector: div.class-name 匹配实际class              |
|    3) 用 regex 兜底：{"name":"x", "regex": "pattern"}         |
|                                                              |
| Q: 被限流/封IP？                                               |
| A: 调大 rate_limit: 1.0 或 2.0                                |
|                                                              |
| Q: selector 没匹配到？                                          |
| A: 本框架用正则模拟CSS，复杂选择器不支持。请用简单的 tag.class  |
|    或直接用 regex 代替。                                       |
|                                                              |
+--------------------------------------------------------------+
""")

def main():
    parser = argparse.ArgumentParser(description="通用网络爬虫流水线")
    parser.add_argument("config", nargs="?", help="JSON配置文件路径")
    parser.add_argument("--cookies", action="store_true", help="仅提取Cookie")
    parser.add_argument("--resume", action="store_true", help="从上次中断处续抓")
    parser.add_argument("--help-config", action="store_true", help="查看JSON配置文件编写指南")
    args = parser.parse_args()

    if args.help_config:
        print_config_guide()
        return

    if args.cookies:
        domain = input("域名 (如 nowcoder.com): ").strip()
        try:
            ck = CookieManager.from_chrome(domain)
            path = f"cookies_{domain.replace('.','_')}.txt"
            with open(path, "w") as f: f.write(ck)
            print(f"Cookie已保存到 {path}")
        except ScraperError as e:
            print(f"错误: {e}")
        return

    if not args.config:
        parser.print_help()
        return

    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)

    if args.resume:
        config["resume_file"] = config.get("resume_file", os.path.join(config.get("output_dir", "./output"), "progress.json"))
        print(f"续抓模式，将跳过已完成项")

    runner = PipelineRunner(config)
    runner.run()


if __name__ == "__main__":
    main()
