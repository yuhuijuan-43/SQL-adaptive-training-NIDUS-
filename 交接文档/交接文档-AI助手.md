# SQL 自适应训练平台 — 交接文档（AI 助手版）

> 交接日期：2026-08-26
> 读者定位：**后续接手的 AI 工作助手**。目标：读完全文即可协助后继开发者完成运行、排查、改代码、加功能。
> 配套文档：`交接文档-开发者.md`（面向人类开发者，讲设计意图与全貌）；本文件讲"代码事实 + 操作路径"，两份配合使用。

---

## 0 阅读约定与使用方式

- 本文件描述的是 **当前工作区状态**，不是 git 最新提交。工作区存在大量未提交改动（见 §10），**一切以代码现状为准**。
- 文件内引用的行号基于当前工作区文件（如 `app.py:122`），改动后行号会漂移，请用函数名二次定位。
- 禁止事项：`backend/oauth_config.json`、`.mcp.json`、`server_path.conf` 含真实密钥/路径，**不得写入任何文档、日志、提交**。它们已被 `.gitignore` 排除。
- 接到任务时的建议动作：先跑 §2 的测试确认基线全绿，再按 §3 代码地图定位文件，按 §11 操作手册执行。

## 1 项目一分钟速览

- 产品：SQL 练习平台，核心是"知识图谱点亮"（进度可视化）+"自适应出题"（按学习者水平出题）。
- 后端：Python Flask 3.1 + SQLite（无 ORM，手写 SQL），生产用 waitress 单进程多线程。
- 前端：原生 HTML/CSS/JS 单文件应用，无框架无构建，Flask 直接托管 `frontend/`，CDN 已离线化（可完全离线部署）。
- 题库：练习池 58 题选择题（基础 29 + 进阶 29）+ 真题池 42 题牛客风格填空题；完整备份 557 / 50 题在 `data/`。
- 判题：内存 SQLite 真实执行用户 SQL 与标准答案，比对结果集（列/行顺序无关）；环境不可用时回退字符串规范化比对。
- 测试：pytest 约 144 用例，覆盖判题、点亮规则、旅程流、种子重建、API 安全、OAuth。
- 账号：平台用户（注册/登录/GitHub OAuth）+ 管理员体系（内推码注册 + 一人一钥 + 会话 token + 密码历史回退）。

## 2 常用命令速查

```bash
# 启动（Windows 一键：探测/安装 Python → 装依赖 → 起服务 → 开浏览器）
start_server.bat

# 手动启动
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
python backend/run.py            # waitress，0.0.0.0:5000，退出时做 WAL checkpoint

# 直跑 app（等价 run.py 的初始化 + 服务；FLASK_DEBUG=1 时走 Werkzeug 热重载，仅限本机）
python backend/app.py

# 全量测试（改后端必跑）
cd backend && pytest -v

# 单文件/单用例（快反馈）
cd backend && pytest tests/test_sql_judge.py -q
cd backend && pytest tests/test_api_security.py::TestSessionLifecycle -q

# 重建题库（从 data/*.json 重灌，条数不符才触发）
python backend/seeding.py
```

启动链路（`run.py`）：`init_db()`（建表 + WAL 清理）→ `seed_questions()` / `seed_exam_questions()` / `seed_knowledge_graph()` → waitress `serve(app, host='0.0.0.0', port=5000, threads=4)`。Ctrl+C / kill 时 `_cleanup_db()` 做 checkpoint 并删 `-wal/-shm`。

## 3 代码地图（任务 → 文件 → 关键符号）

| 任务类型 | 文件 | 关键符号 |
|---|---|---|
| API 路由、页面托管、登录门槛、限流、admin 鉴权 | `backend/app.py` | 全部 `@app.route`；`require_admin`(122)；`_PUBLIC_API_PATHS`(143)；`_request_session_id`(155)；`before_request login_required_for_question_apis`(165) |
| 自适应出题、点亮规则、轮状态 | `backend/engine.py` | `journey_next`(232)；`compute_lights`(182)；`_build_round`(206)；`_lit_leaves`(126)；`_correct_counts`(117)；`_rule1_hit`(169)；常量 `SEQ_TYPES/LEAF_Q/STREAK/GAP_MAX/CORRECT_LIT`(21-25) |
| SQL 判题 | `backend/sql_judge.py` | `judge`(146)；`normalize_sql`(13)；`_split_statements`(50)；`_check_read_only_single_statement`(83)；`_friendly_error`(95) |
| 连接、建表、迁移 | `backend/db.py` | `get_connection`(9)；`init_db`(35)；17 张表建表 + `ALTER TABLE ADD COLUMN` 增量迁移 |
| 数据查询层 | `backend/repositories.py` | `get_all_questions`(55)；`save_answer`(238)；`get_graph`(204)；`reset_user_password`(276)；`delete_user`(376)；`delete_admin`(396) |
| 平台用户认证 | `backend/auth.py` | `login_user`(45)；`register_user`(74)；`SESSION_MAX_AGE_DAYS`(18)；内推码 `get_referral_codes`(161)；管理员体系 196-321 |
| GitHub OAuth | `backend/oauth.py` | `get_oauth_config`(26)；`find_or_create_github_user`(84)；`_resolve_unique_username`(121) |
| 题库播种 + 知识图谱定义 | `backend/seeding.py` | `OFFICIAL_TAGS`(13)；`seed_questions`/`seed_exam_questions`/`seed_knowledge_graph`(128)；数据路径 421/467 |
| 前端页面 | `frontend/*.html` | 见 §4 |
| 启动脚本 | `start_server.bat` | 见 §9 部署 |
| 题库数据 | `data/*.json`、`data/*.csv` | 见 §9 |

## 4 前端页面与路由对应

| 页面文件 | 路由 | 职责 | 主要调用 API |
|---|---|---|---|
| `index_glass.html` | `/` `/index_glass.html` | 门户入口（玻璃拟态），6 语言切换 | 无（静态） |
| `login_glass.html` | `/login` `/login_glass.html` | 登录/注册 + GitHub 一键登录 | `/api/login` `/api/register` `/api/check-username` `/api/oauth/github` `/api/oauth/github/check` |
| `index.html` | `/index.html` | 练习主界面：自适应进阶/自主练习/真题池/错题集 | `/api/journey/*` `/api/questions` `/api/submit` `/api/practice/*` `/api/progress/*` |
| `knowledge_map.html` | `/knowledge-map` | 知识图谱点亮视图（被 index.html iframe 嵌入） | `/api/graph` `/api/journey/status` |
| `diagnostic.html` | `/diagnostic-page` | 水平诊断（零外部引用） | `/api/diagnostic*` |
| `basic_select.html` `/advanced_select.html` | `/basic-select` `/advanced-select` | 基础/进阶选择题选题页 | `/api/questions?pool=...` |
| `admin_gate.html` | `/admin-gate` | 已移除（2026-09-03 融合入口，302 → `/admin-auth`） | - |
| `admin_auth.html` | `/admin-auth` | 管理后台统一入口：登录/注册（内推码），无个人密钥 | `/api/admin/login` `/api/admin/auth-login` `/api/admin/auth-register` `/api/admin/auth-check-username` |
| `admin_panel.html` | `/admin-panel` | 管理后台主面板：用户动态/系统日志（全员）+ 管理员动态（主管理员）+ 我的同事/内推码/密码管理 | `/api/admin/user-activity` `/api/admin/system-logs` `/api/admin/admin-activity` `/api/admin/colleagues`（Bearer token） |
| `admin.html` | `/admin` `/admin.html` | 旧版管理面板（兜底保留） | `/api/admin/*` |
| `about.html` | `/about` `/about.html` | 了解我们，6 语言平行 + 更新动态 | 无 |
| `format_sample.html` | `/format-sample` | 题目格式样例页 | 无 |

静态资源：`echarts.min.js`（图谱图表）、`lib/codemirror/`（SQL 编辑器高亮）、`lib/font-awesome/`（图标）、`nidus_logo.png`（品牌 logo）。前端全部相对路径互链，同目录移动安全。

## 5 数据库模型（17 张表，`db.py`）

| 表 | 用途 | 关键字段 | 谁写入 |
|---|---|---|---|
| `questions` | 练习池题目（选择题/填空题混合） | `id/source/category/difficulty/title/description/table_schema/initial_data/correct_answer/explanation/options/option_explanations/expected_output/pool/q_level` | `seeding.py` |
| `exam_questions` | 真题池题目（独立表，id 与 questions 各自从 1 起） | 同 questions（无 pool/q_level） | `seeding.py` |
| `user_progress` | 答题记录（三池共用，pool 区分） | `session_id/question_id/user_answer/is_correct/duration/pool/answered_at` | `repositories.save_answer` |
| `knowledge_nodes` | 图谱节点（root/枝/叶） | `id/name/description/category/level/icon` | `seed_knowledge_graph` |
| `knowledge_edges` | 图谱边（依赖关系） | `from_node/to_node` | `seed_knowledge_graph` |
| `question_knowledge` | 题↔节点映射 | `question_id/node_id`（复合主键） | `seed_knowledge_graph` |
| `user_mastery` | 用户对节点的掌握度（BKT α/β） | `session_id/node_id/correct_count/total_count/alpha/beta` | `repositories.save_answer` |
| `journey_state` | 自适应旅程状态（每用户一行） | `session_id/deep_mode/phase/round_state(JSON)/total_answered/total_correct/avg_speed/wrong_streak` | `engine.py` |
| `user_lights` | 点亮落库（规则1/2 事件） | `session_id/node_id/lit/updated_at`（复合主键） | `engine._set_lit` |
| `users` | 平台用户 | `username/password(bcrypt)/session_id/github_id/last_active` | `auth.py`/`oauth.py` |
| `admin_users` | 管理员 | `username/password/referral_code/is_primary/personal_key/key_disabled(已废弃)/last_login_at` | `auth.py` |
| `user_password_history` | 密码历史（每账号 3 条，可回退） | `username/password/kind(user/admin)/created_at` | `repositories.reset_user_password` |
| `referral_codes` | 内推码（管理员注册用） | `code/note/created_at` | `auth.py` |
| `admin_settings` | 平台级设置（预留） | `key/value` | 暂无 |
| `diagnostic_results` | 摸底诊断结果（每用户一行） | `session_id/data(JSON)` | `repositories.save_diagnostic_result` |
| `admin_sessions` | 管理员会话 token | `token/username/expires_at(30天TTL)` | `auth.create_admin_session` |
| `activity_log` | 用户/管理员动态（实时监控，kind 区分） | `kind(user/admin)/actor/action/target/detail/extra/created_at` | `logs.py` + 各业务入口 |
| `system_logs` | 系统日志（异常/判题错误/失败登录/限流） | `level/source/message/detail/created_at` | `logs.py` + 全局错误处理 |
| `derived_questions` | 举一反三衍生题（由选择题原型生成） | `prototype_id/...同questions` | `repositories.get_or_create_derived_question` |

要点：
- **两表 id 重叠**：`questions` 与 `exam_questions` id 各自从 1 起，所有按池取数的代码（`get_progress`、`submit_answer`、`list_questions`）必须传 `pool` 区分，否则串池。
- **增量迁移模式**：新增列一律在 `init_db` 里 `try: ALTER TABLE ... ADD COLUMN ... except: pass`，不要重建表（见 `users.last_active`、`admin_users.personal_key` 的先例）。
- 连接管理：Flask 请求上下文内复用 `g.db`（WAL 模式 + busy_timeout=5000），请求结束 `close_db` 关闭；脚本场景用独立连接。测试通过 monkeypatch `db.DB_PATH` 指向临时文件。

## 6 核心算法一：知识图谱与自适应出题（`engine.py` + `seeding.py`）

### 6.1 图谱结构（`seeding.OFFICIAL_TAGS`，7 大类 × 29 叶标签）

| 枝（大类） | 叶标签（29 个） |
|---|---|
| DML | dml_select, dml_insert, dml_update, dml_delete |
| SELECT | select_basic, where_basic, group_by, having |
| 函数 | string_func, numeric_func, aggregate_func, cast_func, window_func |
| 子查询 | subquery_scalar, subquery_column, subquery_table, subquery_in |
| 表连接 | join_inner, join_outer, join_self, join_cross |
| 约束 | constraint_primary_key, constraint_foreign_key |
| DDL | ddl_create, ddl_alter, ddl_drop, ddl_truncate, ddl_rename, ddl_comment |

层级：根 `root`（level 0）→ 7 枝（level 1）→ 29 叶（level 2 + 星级-1）。星级映射难度：★=easy / ★★=medium / ★★★=hard（`STAR_TO_DIFFICULTY`）。`LEARNING_EDGES` 保留旧引擎的进阶学习顺序。`CATEGORY_TO_TAG` 把历史分类/旧节点 ID 映射到官方 29 标签。

### 6.2 出题规则

- 题目源白名单：`JOURNEY_SOURCES = ('static_basic', 'static_advanced', 'nowcoder_preview')`（已明确排除牛客/LeetCode/Kaggle 旧题）。
- 每叶节点一轮 5 题序列 `SEQ_TYPES = ['mcq','mcq','mcq','fillin','fillin']`（选择先行，基础选择优先：`q_level != 'basic'` 排序）。
- 池不足循环复用；填空池为空回退选择题池（`_leaf_plan`）。
- 一轮 = 枝→叶固定图谱顺序（`TOP_ORDER`/`LEAF_ORDER`，不放回），跳过已点亮/无题叶，把未点亮且有题的叶刷完（至多 29×5=145 题）。

### 6.3 点亮规则（叶节点，任一满足即点亮并跳过剩余）

| 规则 | 条件 | 落库 |
|---|---|---|
| 规则1 | 本轮该叶**连续答对 3 道**且相邻两题提交间隔 ≤2min（`GAP_MAX=120`） | `user_lights` 落库 |
| 规则2 | 本轮该叶**全部 5 题答对**（不计间隔） | `user_lights` 落库 |
| 规则3 | **跨池累计答对 10 道**该叶题（practice 池计数，`CORRECT_LIT=10`） | 不落库，由 `_correct_counts` 派生 |

枝节点：x/y = 点亮叶/叶总数，全部叶点亮才点亮；根节点：x/7 = 点亮枝/枝总数，全亮才点亮。`compute_lights` 输出的 `lit/correct/x/y` 就是前端图谱渲染的数据源。

### 6.4 journey_next 主流程（`engine.py:232`）

```
journey_next(session_id, just_answered_qid, was_correct, duration, just_answered_id)
  ├─ 若 was_correct 非 None：_record_answer_stats（journey_state 计数/速度）
  ├─ 轮状态 rs = round_state(JSON)；无/complete → _build_round 开新一轮
  ├─ 若本轮提交了计划内题目（qid in entry['plan']）：
  │    ├─ 登记 answers（从 user_progress 刷新真实时间戳）
  │    ├─ _rule1_hit → _set_lit（规则1）
  │    └─ 否则查 _correct_counts ≥10 → 点亮（规则3）
  ├─ 双 while 推进：
  │    ├─ 本叶出完 → 全部答对则 _set_lit（规则2）→ 下一叶
  │    └─ 全部叶完成 → status=complete，保留点亮状态
  └─ 返回 _response：question + lights + round + graph + mastery
```

注意：作答只登记**计划内**题（防陈旧/重复提交污染）；`counts` 参数（2026-08-12 优化）让规则3与点亮状态复用同一次聚合，避免重复查库。

## 7 核心算法二：SQL 判题（`sql_judge.py`）

`judge(user_sql, correct_sql, table_schema, initial_data)` 返回 `(is_correct, result_rows, error_message)`：

```
1. 空答案 → (False, None, '答案不能为空')
2. _check_read_only_single_statement：注释剥离 → 引号感知分句（_split_statements）
   → 必须恰好 1 条，且首关键字 ∈ ('select','with','explain','pragma')
3. 快速路径：normalize_sql 字符串一致 → 直接判对（免执行）
4. 内存 SQLite 建环境（table_schema + initial_data）；失败 → 回退字符串比对
5. 执行用户 SQL（报错 → _friendly_error 中文提示）
6. 执行标准答案（失败 → 题库数据问题，回退字符串比对）
7. 比对：列数一致 + 行集 multiset 一致（sorted(_row_key)）→ 判对
```

比对细节：列名不参与（`COUNT(*)` 与 `COUNT(非空列)` 等价判对）；行内值排序后比（列序无关）；保留重复行；float 整数值与 int 归一（`_value_key`）。`_split_statements` 追踪 `'`/`"`/`` ` `` 引号状态与 `''` 转义，字符串字面量内的分号不会误切（2026-08-12 修复）。

## 8 认证与安全模型

### 8.1 平台用户会话
- 注册/登录：用户名白名单 `^[\w一-龥]{2,32}$`，密码 8-64 字符，bcrypt 存储；旧 sha256:盐 / 明文格式登录时自动升级 bcrypt。
- 会话：`users.session_id`（UUID）+ `last_active`；`_is_authenticated` 校验未过期（`SESSION_MAX_AGE_DAYS=90`，NULL 视为有效）。登录/注册/复用时刷新，`/api/logout` 置为 `2000-01-01` 立即失效（幂等）。
- 登录门槛：`before_request` 钩子，除 `_PUBLIC_API_PATHS` 白名单外，所有 `/api/*` 都要求有效 session_id，否则 401。

### 8.2 管理员体系
- 注册：内推码（`referral_codes` 表，默认 `NIDUS_Agent` 惰性种入，最后一个不允许删）+ 用户名全局唯一（含平台用户同名）+ 密码规则同平台；**个人密钥体系已于 2026-09-03 移除**（旧列 `personal_key/key_disabled` 保留但不再使用）。
- 登录：管理后台统一入口 `/admin-auth`（账号密码或内推码注册），签发 Bearer token；旧 `/admin-gate` 302 跳转。
- 会话：`/api/admin/*` 用 `Authorization: Bearer <token>`，token 绑定用户名（`admin_sessions`，30 天 TTL）；`require_admin` 装饰器统一鉴权并注入 `g.admin_username`（2026-08-12 重构，替代旧的自报 operator 模式）。
- 实时监控（2026-09-03）：所有管理员可查用户动态（`activity_log.kind='user'`：注册/登录/答题/摸底）与系统日志（`system_logs`）；主管理员（Yuhuijuan，`is_primary=1`）额外可见管理员动态（`activity_log.kind='admin'`，登录/注册/改密/删除/内推码等），前端每 6s 轮询。
- 权限分级：主管理员（`is_primary=1`）独享：查看/增删内推码、删管理员、改/回退管理员密码；普通管理员只能重置平台用户密码。
- 密码历史：每次重置前旧密码入 `user_password_history`（每账号 3 条，`kind` 区分 user/admin），可回退 3 次；管理员密码被重置/回退后其全部会话立即失效。
- 风险操作需 `confirm: true` 显式确认（删用户/删管理员）。

### 8.3 GitHub OAuth（`oauth.py`）
- 配置优先级：环境变量 `GITHUB_OAUTH_CLIENT_ID/SECRET` > `backend/oauth_config.json`。
- 流程：`/api/oauth/github` 生成 state 存 Flask session（防 CSRF）→ 跳 GitHub（刻意不传 redirect_uri，用 GitHub 注册的回调）→ callback 校验 state（`hmac.compare_digest` + 单次使用）→ 换 token → 拉用户 → 按 `github_id` 查/建 `users` 行。
- 用户名冲突：`原名` → `原名_gh` → `原名_ghNN` → `uuid` 后缀；GitHub 账号密码为随机 bcrypt（不可密码登录，管理员可重置转双通道）。并发双回调由唯一索引拦截。

### 8.4 限流（flask-limiter，`memory://`）
写接口/登录注册/admin 限流，读题与练习接口不限流。用户接口按 `session_id` 或用户名计数（`_user_rate_key`），admin 按 Bearer 解析的管理员计数（`_admin_rate_key`），避免 ngrok 下全班共享 IP 误伤。要点：login 8/min、register 5/min、submit 30/min、admin/login 5/min、auth-register 5/min、auth-login 8/min、admin 高危写接口 30-60/min、admin 只读接口 120/min、oauth 60/30 per min。

## 9 题库数据、重建与部署

### 9.1 数据文件（`data/`）

| 文件 | 内容 |
|---|---|
| `questions.json` | 练习池当前源（58 题，`q_level` 标记 basic/advanced） |
| `exam_questions.json` | 真题池当前源（42 题填空题） |
| `questions_full.json` / `exam_questions_full.json` | 完整备份（557 / 50），不入库 |
| `knowledge_tags.csv` | 29 标签难度映射（注意：文件内中文星级在 Windows 下显示为乱码，代码以 `OFFICIAL_TAGS` 硬编码为准） |
| `basic_select.csv` / `advanced_select.csv` | 人工编写题库原始稿 |

### 9.2 重建流程
`seed_questions()`（`seeding.py:421` 读 `data/questions.json`）与 `seed_exam_questions()`（`seeding.py:467`）在**库内条数不符时**自动清表重灌；`seed_knowledge_graph()` 在 `knowledge_nodes` 为空时播种。改数据文件后删掉 `backend/questions.db` 重启即可强制重建。

### 9.3 题目字段格式
选择题：`options`（`|` 分隔选项，`||` 为 SQL 连接符转义）+ `option_explanations` + `correct_answer`。填空题：`table_schema`（CREATE TABLE）+ `initial_data`（INSERT）+ `correct_answer`（标准 SQL）+ `expected_output`。选择题判对用**双向 HTML 实体归一**（`html.unescape`，DB 存 `&gt;` 浏览器是 `>`），新写判对 handler 必须沿用。

### 9.4 启动脚本（`start_server.bat`）
读 `server_path.conf`（第 1 行 Python 路径、第 2 行版本）→ 5 种策略探测可用 Python（过滤 Store 存根，逐个 `--version` 验证）→ 找不到则自动下载安装 Python 3.13.x → `pip install -r backend/requirements.txt` → 启动 `backend/run.py` 并打开 `http://localhost:5000`。注意 `%~dp0` 锚定脚本自身目录，`backend/` 相对位置不可变。

### 9.5 OAuth 部署注意
GitHub OAuth App **只支持一个回调 URL**：本地用 `http://localhost:5000/api/oauth/github/callback`；上 ngrok/正式域名要同步改 GitHub 应用回调 + 本地启动地址。服务端可用环境变量覆盖密钥（优先级高于 json 文件）；`FLASK_SECRET_KEY` 让 session cookie 跨重启稳定。

## 10 当前未提交改动（交接时点快照，务必了解）

`git status` 显示 20 个文件改动（+315/-147）+ 未跟踪的 `项目文件架构.md`。这批是上一轮功能的半成品，**功能完整且带回归测试**，但尚未提交。逐条：

| 文件 | 改动内容 |
|---|---|
| `backend/app.py` | 新增 `require_admin` 装饰器（122）并迁移全部 admin 路由；新增 `POST /api/logout`（552）；`_PUBLIC_API_PATHS` 加 `/api/logout`；删除 `/index_ngrok.html`、`/login_ngrok.html` 301 路由；注册 woff2/ttf MIME；`diagnostic_complete` 正确率只基于已作答（跳过不进分母，278）；选择题判对改 `html.unescape`；`__main__` 补 `seed_exam_questions()`（976） |
| `backend/auth.py` | `SESSION_MAX_AGE_DAYS=90`；`_is_authenticated` 校验 last_active；`login_user` 重构 ok 分支并登录刷新 last_active；`register_user` 插入 last_active |
| `backend/db.py` | `users` 表 `ALTER TABLE ADD COLUMN last_active TIMESTAMP`（125） |
| `backend/oauth.py` | `find_or_create_github_user` 复用/建档时刷新 last_active |
| `backend/sql_judge.py` | 新增 `_split_statements`（50）引号感知分句；`_check_read_only_single_statement` 改用它（修复字符串内分号误判） |
| `backend/engine.py` | `compute_lights(session_id, counts=None)`；`journey_next`/`_response` 支持 counts 复用（2026-08-12 性能优化） |
| `backend/tests/test_api_security.py` | 新增 `TestSessionLifecycle` 4 用例（登出失效/幂等/重登恢复/90 天过期） |
| `backend/tests/test_sql_judge.py` | 新增 3 用例（多语句含写拒、字符串内分号、转义引号） |
| `backend/tests/test_seed_rebuild.py` | 数据路径加 `data/` 前缀（配合仓库重组） |
| `frontend/index.html` | 错题集翻页、导航布局、图谱入口视图等（带 2026-08-12 注释） |
| `frontend/about.html` | 六语言平行 + 更新动态新增条目 |
| `frontend/admin.html` `format_sample.html` `knowledge_map.html` `index_glass.html` `login_glass.html` | 小改（多为 2026-08-12 同步） |
| `tools/*.py` | convert_question_bank / verify_exam_bank 小修 |
| `.gitignore` | 忽略规则调整 |

建议：接手第一个任务前，先 `pytest` 确认全绿，再推动交接人补提交这批改动，避免在未提交基线上继续叠加。

## 11 常见任务操作手册（AI 被要求做 X 时）

### 11.1 加一道题
编辑 `data/questions.json`（选择题，含 `options`）或 `data/exam_questions.json`（填空题，含 `table_schema`/`initial_data`/`correct_answer`），字段参考 `docs/sample/` 与 `docs/format_spec.md`。选择题 `options` 用 `|` 分隔（SQL 的 `||` 连接符要保留原样），难度字段用 `easy/medium/hard`，`category` 用官方 29 标签之一（`seeding.CATEGORY_TO_TAG` 可做旧分类映射）。之后删 `backend/questions.db` 重启，或跑 `python backend/seeding.py` 重建。

### 11.2 新增/修改 API
在 `app.py` 加 `@app.route`；数据逻辑放 `repositories.py`（路由不直接拼 SQL）。若接口需登录，确保它**不在** `_PUBLIC_API_PATHS` 里，`before_request` 会自动拦游客。写接口记得加 `@limiter.limit(...)`。若涉及跨域（如 file:// 打开 admin.html），CORS 白名单在 `app.py:36`。

### 11.3 改判题逻辑
改 `sql_judge.py`，直接跑 `cd backend && pytest tests/test_sql_judge.py -q`（最快反馈，无需起服务）。改完跑全量 `pytest`。注意不要放开写语句（`_READ_ONLY_FIRST` 之外的首关键字会被拒）。

### 11.4 改点亮/出题规则
改 `engine.py` 常量（`STREAK`/`GAP_MAX`/`CORRECT_LIT`/`SEQ_TYPES`）或 `journey_next` 逻辑；新增测试参考 `tests/test_journey_lights.py` / `test_journey_flow.py`。改图谱结构（增删标签）要同时改 `seeding.OFFICIAL_TAGS` 和 `data/knowledge_tags.csv`，并注意 `test_seed_rebuild.py` 对节点数的断言。

### 11.5 排查启动失败
- 端口占用：5000 被占，`netstat -ano | findstr :5000` 查 PID。
- 依赖缺失：`pip install -r backend/requirements.txt -r backend/requirements-dev.txt`。
- 数据库损坏/重建：删 `backend/questions.db*`（含 -wal/-shm）重启，数据会自动重灌（用户数据会丢，生产先备份）。
- WAL 残留：`run.py` 退出清理，异常 kill 可能残留 `-wal`，`init_db` 的 `_cleanup_stale_wal` 会处理。

### 11.6 排查"判题不对"
按 `judge` 流程定位：先看 `_check_read_only_single_statement` 是否误拒（如多语句/字符串内分号）；再看是否走了字符串回退（环境构建失败）；最后看比对差异（列数/行集）。测试夹具 `conftest.SCHEMA/DATA` 是现成的判题环境。

### 11.7 加测试
后端测试放 `backend/tests/`，夹具在 `conftest.py`（`test_db` 建临时库 + 6 道最小种子题；`client` 是 Flask test client 且关闭限流；`admin_session` 注册主管理员拿 Bearer token）。判题类直接调 `judge()` 原子函数；API 类走 `client.post('/api/...')`。

## 12 红线与陷阱（改代码前必读）

1. **路径依赖是软肋**：`seeding.py:421/467` 与 `tests/test_seed_rebuild.py` 的数据路径基于 `__file__` 相对定位；`app.py:134 FRONTEND_DIR` 锚定 `frontend/`；`start_server.bat` 用 `%~dp0`。这些相对位置一动就挂。
2. **判题安全红线**：只接受单条只读语句（select/with/explain/pragma）→ 内存 SQLite 执行。别放开写语句。
3. **HTML 实体归一**：选择题判对必须 `html.unescape` 双向归一，否则格式略异判错。
4. **六语言平行**：改 `about.html` / 门户文案时检查该页平行语言版本，避免只改中文。
5. **题目源白名单**：自适应进阶只用 `JOURNEY_SOURCES` 三源；加题源要改白名单。
6. **密钥与敏感文件**：`oauth_config.json`、`.mcp.json`、`server_path.conf` 不得写入文档/提交；OAuth 回调 URL 唯一。
7. **性能**：`get_graph()` 进程内缓存（`_graph_cache`），改了种子数据要调 `invalidate_graph_cache()`。
8. **数据库并发**：生产是单进程多线程 waitress + WAL，不要引入多进程写 SQLite（会增加写锁争用）。
9. **内部文档部分过时**：`docs/新人接手指南.md` 等内部文档是早期版本（提到 `questions.py`/`database.py`/BKT 三阶段算法），与当前代码不符，以本文件与代码为准。
10. **knowledge_tags.csv 乱码**：Windows 下中文星级显示为 `бя` 乱码，代码以 `seeding.OFFICIAL_TAGS` 硬编码为准，勿据此改代码。

## 13 与开发者协作建议

- 开发者让你"看代码改 X"时：先 `pytest` 基线 → 按 §3 定位 → 改完跑相关测试 → 用 `python backend/run.py` 起服务自验（若需 HTTP 验证）。
- 开发者让你"解释 Y 为什么这样"时：以本文件 §5-8 为骨架，结合代码现场回答；涉及历史决策可查 `git log` 与 `docs/modification.md`（本地保留）。
- 产出代码时遵守现有风格：中文注释、函数 docstring、`db.py` 增量迁移模式、路由层薄 + repositories 层厚、测试夹具复用。

---

*本文件为交接时刻的工作区快照。重大改动（schema、路径、判题语义、图谱结构、题库格式）请在交接文档（开发者版）§15 回填，保证下一棒不丢上下文。*
