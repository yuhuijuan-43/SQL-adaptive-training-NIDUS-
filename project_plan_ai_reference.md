# SQL 自适应学习平台 — 项目方案总览

> 本文件是项目的"AI Agent 参考手册"，汇总了所有调研结论、设计决策、技术选型与**实际实现状态**，供后续开发过程中 AI 助手理解项目全貌和关键约束。
>
> **最后更新：** 2026-08-02

---

## 1. 项目定位

**一句话概括：** 基于 BKT（贝叶斯知识追踪）+ Thompson 采样的 SQL 自适应刷题平台。正确时平滑进阶，错误时同知识点强化练习，通过选择题→填空题的"深度验证"机制确保真掌握，实现**千人千面、因错施教**。

**使用场景：** Web 端（Python Flask + SQLite，自包含 HTML 前端，零构建步骤）

**当前题库规模：** 356 题（61 道选择题 + 295 道 LeetCode 填空题），全部含标准答案与预期输出

**目标用户：**

| 用户类型 | 特征 | 需求 |
|---|---|---|
| 零基础转行小白 | 无 CS 背景，学习意愿强 | 从基础 SQL 语法开始，渐进式引导 |
| 计算机专业大学生 | 有学科基础 | 技能巩固、面试准备，有挑战性内容 |

---

## 2. 核心机制

### 2.1 实际答题流程（已实现）

```
登录 → 摸底诊断（3 题：易/中/难各一）
         ↓
    自适应主循环（Journey 模式）
         ↓
    选择题出题 → 用户作答
         ├── ✅ 正确 → 深度模式触发 → 同知识点自动弹出填空题验证
         │              ├── 填空题正确 → 该知识点标记"已掌握" → Thompson 采样选下一知识点
         │              └── 填空题错误 → 同知识点继续练习
         │
         └── ❌ 错误 → 同知识点继续推送选择题巩固
                       连错 3 题 → 降难度保护
```

### 2.2 三阶段递进策略（已实现）

| 阶段 | 做题量 | 核心策略 | 算法 |
|---|---|---|---|
| **冷启动期 (cold)** | 0-5 题 | 摸底诊断 + 低难度起步 | 规则引擎 |
| **探索-利用期 (exploration)** | 6-30 题 | 平衡"巩固已知"与"探索未知" | BKT + Thompson 采样 |
| **精熟期 (mastery)** | >30 题 | 个性化排序 + 方差稳定判断 | BKT + 安全兜底 |

**阶段切换逻辑：**
- cold → exploration：答题 ≥ 5 题
- exploration → mastery：答题 > 30 题 且 最近 10 题正确率方差 < 0.15
- mastery → exploration：连续答错 3 题（防止挫败感）

### 2.3 用户完整旅程

```
访问门户首页（index_glass.html）→ 登录/注册（login_glass.html）→ 做题主循环
  │                                                     ↓
  │                         答题 → BKT更新掌握度 → Thompson采样选知识点 → 选题 → 展示
  │                                                     ↓
  │                                                错题自动归集
  │                                                     ↓
  │                                                同知识点强化练习
  │                                                     ↓
  │                                                学习数据报表（管理后台）
  │
  └── 也支持手动选题模式（按分类/难度筛选，逐题浏览）
```

> 注：摸底小测（诊断）功能已从产品中移除（非核心特色），做题页不再包含诊断入口，后端 `/api/diagnostic*` 接口保留但前端不再调用。

---

## 3. 技术架构（实际实现）

### 3.1 技术栈

| 层面 | 技术 | 备注 |
|---|---|---|
| 后端 | Python 3.12 + Flask | 全部代码在 `backend/` 下 |
| 数据库 | **SQLite**（单文件 `questions.db`） | MVP 阶段，WAL 模式，零部署 |
| 前端 | 纯 HTML/CSS/JS（零构建） | 一个页面一个文件，CodeMirror + ECharts 通过 CDN 加载 |
| 题库存储 | `questions.py`（JSON 数组）+ `exam_questions.json` | 导入到 SQLite |
| 密码存储 | bcrypt | 兼容旧 SHA-256 格式自动升级 |
| 部署 | `start_server.bat` + ngrok | Waitress WSGI（生产）或 Flask dev server |

### 3.2 数据库表结构（12 张表，SQLite）

| 表名 | 存什么 | 重要度 |
|---|---|---|
| `questions` | 所有练习题目（题干、答案、选项、建表SQL、测试数据、预期输出） | ⭐⭐⭐ |
| `exam_questions` | 真题测试题目（独立池，结构同 questions） | ⭐⭐ |
| `derived_questions` | 衍生题（选择题自动转填空题，用于"举一反三"） | ⭐⭐ |
| `knowledge_nodes` | 知识图谱节点（37 个：1 根 + 7 分类 + 29 子节点） | ⭐⭐⭐ |
| `knowledge_edges` | 知识图谱的边（知识点间的前置依赖关系） | ⭐⭐⭐ |
| `question_knowledge` | 题目 ↔ 知识点的多对多映射 | ⭐⭐ |
| `user_progress` | 用户答题记录（每题是否答对、耗时） | ⭐⭐ |
| `user_mastery` | 用户对每个知识点的 BKT 掌握度（α/β 值） | ⭐⭐⭐ |
| `journey_state` | 用户自适应旅程的当前状态（阶段、当前节点、队列等） | ⭐⭐ |
| `users` | 用户注册信息（用户名 + bcrypt 密码哈希） | ⭐ |
| `diagnostic_results` | 摸底测试结果 | ⭐ |
| `admin_users` | 管理员账号（内推码注册，用户名全局唯一，last_login_at） | ⭐⭐ |
| `user_password_history` | 密码历史（重置前入档，每账号最多 3 条，kind 区分用户/管理员） | ⭐⭐ |

### 3.3 知识图谱（已重构）

**结构：** 三层树形，共 37 个节点

```
root [SQL知识图谱]
├─ DML (top-255)
│   ├─ SELECT (cat-2748)
│   ├─ INSERT (cat-2749)
│   ├─ UPDATE (cat-2750)
│   └─ DELETE (cat-2751)
├─ DDL (top-257)
│   ├─ CREATE / ALTER / DROP / TRUNCATE / RENAME / COMMENT
├─ 函数 (top-256)
│   ├─ 字符串函数 / 数字函数 / 聚合函数 / 转换函数 / 窗口函数
├─ 表连接 (top-264)
│   ├─ 内连接 / 外连接 / 自连接 / 交叉连接
├─ 约束 (top-265)
│   ├─ 主键 / 外键
├─ 子查询 (top-266)
│   ├─ 标量子查询 / 列子查询 / 表子查询 / IN 子查询
└─ SELECT (top-273)
    ├─ 基本SELECT / WHERE条件筛选 / 聚合函数与GROUP BY / HAVING子句
```

**与旧版区别：** 旧版为 26 个扁平知识点节点（select_basic, where_basic, join_inner...），新版为三层树形结构（根→7 分类→29 子节点），通过 `knowledge_tags.csv` 定义标签与难度星级。

### 3.4 自适应引擎核心算法（已实现）

#### BKT（贝叶斯知识追踪）
- 每个知识点用 Beta(α, β) 分布表示掌握概率
- 初始化：α=1, β=1（完全不确定）
- 更新：答对 → α+1；答错 → β+1
- 掌握概率 = α/(α+β)，阈值 0.7 判定为"已掌握"
- 不确定性（探索分）= 方差 = αβ / ((α+β)²(α+β+1))

#### Thompson 采样选题
- 综合得分 = λ × 探索分 + (1-λ) × 利用分
- 探索分 = 知识点不确定性（方差）
- 利用分 = 1 - 掌握概率（越薄弱越要练）
- 动态探索率 λ = max(0.1, 0.5 × e^(-N/15))
- 冷启动期 λ=0.6，精熟期 λ=0.1

#### 安全机制
- **同模块保护：** 连续 5 题同模块 → 强制切换分类
- **难度阻尼：** 最近 5 题正确率 > 80% → 加权偏好高难度
- **复习穿插：** 每 5 题插入一道已跳过节点的题
- **挫败感保护：** 连错 3 题 → 降难度 + 从 mastery 回退到 exploration
- **深度验证：** 选择题答对 → 自动出同知识点填空题（可开关）

---

## 4. 题库现状

### 4.1 实际题库统计

| 类型 | 数量 | 说明 |
|---|---|---|
| **选择题（MCQ）** | 61 道 | 摸底 3 + 基础选择 29 + 进阶选择 29，含 4 选项 + 解析 |
| **LeetCode 填空题** | 295 道 | 含标准答案 + 预期输出（SQLite 执行验证），已翻译中文标题 |
| **合计** | **356 道** | |

> **注意：** 设计文档中规划的 640 题（力扣 323 + 牛客 277 + Kaggle 40）未全部入库。Kaggle 题库（`Kaggle题库/` 目录）和牛客题库（`网络爬虫/` 目录）的原始文件存在，但只有部分导入。当前实际可用 356 题。

### 4.2 题目格式（12 字段）

| 字段 | 类型 | 说明 |
|---|---|---|
| `source` | string | 来源：`leetcode` / `curated` / `sqlzoo` / `pgexercises` / `sql_practice` / `ai_generated` |
| `category` | string | 知识点分类标签（对应 29 个 viz 子节点） |
| `difficulty` | string | `easy` / `medium` / `hard` |
| `title` | string | 题目标题（LeetCode 格式：`"175. 两表合并查询"`） |
| `description` | string | 题目描述（含表结构 + 任务说明） |
| `table_schema` | string | CREATE TABLE 建表语句，多条用 `\n` 分隔 |
| `initial_data` | string | INSERT 测试数据，每条用 `\n` 分隔 |
| `correct_answer` | string | 标准答案 SQL |
| `explanation` | string | 中文答案解析 |
| `options` | string | 选择题选项，用 `\|` 分隔。**有值=选择题，无值=填空题** |
| `option_explanations` | string | 选项解析，用 `\|` 分隔 |
| `expected_output` | string | 文本管道格式预期输出（`列头 \| 列头\n---+\n数据`） |

### 4.3 题目来源分布

| source | 数量 | 说明 |
|---|---|---|
| `leetcode` | 295 | LeetCode SQL 题，GraphQL API 爬取，标准答案 + 预期输出 |
| `curated` | ~30 | 手工编写的原创选择题 |
| `sqlzoo` | ~109 | 爬取自 SQLZoo |
| `pgexercises` | ~57 | 爬取自 PostgreSQL Exercises |
| `sql_practice` | ~12 | 爬取自 SQL-Practice.com |
| `ai_generated` | ~50 | AI 自动生成 |
| 其他 | 少量 | curated_web, mode_analytics |

---

## 5. API 端点（已实现）

### 页面路由

| 路由 | 说明 |
|---|---|
| `/` | **门户首页**（玻璃拟态入口页，站点入口） |
| `/index.html` | 刷题主页（练习前端） |
| `/login` `/login_glass.html` | 登录/注册页（玻璃拟态） |
| `/about` `/about.html` | 了解我们（更新动态 + 详情弹窗） |
| `/index_glass.html` | 门户页直接访问 |
| `/nidus_logo.png` | 品牌 logo（透明底 PNG） |
| `/admin` | 管理后台（统计 + 用户明细含密码管理） |
| `/admin-gate` | 管理后台登录门（双重验证：管理员账号密码 + 统一密钥） |
| `/admin-auth` | 管理员账号登录/注册（内推码，页面不显示码值） |
| `/admin-panel` | 管理员自身页面（统一密钥 + 我的同事） |
| `/knowledge-map` | 知识图谱可视化页 |
| `/diagnostic-page` | 摸底诊断页（前端入口已移除，路由保留） |
| `/basic-select` | 基础选择题练习页 |
| `/advanced-select` | 进阶选择题练习页 |
| `/format-sample` | 题目格式示例页 |

### 数据 API

| 路由 | 方法 | 用途 |
|---|---|---|
| `/api/diagnostic` | GET | 获取摸底测试题（易/中/难各 1 道） |
| `/api/diagnostic/complete` | POST | 提交摸底结果 |
| `/api/diagnostic/result` | GET | 查询摸底结果 |
| `/api/questions` | GET | 题目列表（`?pool=practice\|exam&category=&difficulty=`） |
| `/api/questions/<id>` | GET | 单题详情 |
| `/api/submit` | POST | 提交答案、判题 |
| `/api/graph` | GET | 知识图谱数据（节点+边） |
| `/api/journey/start` | POST | 开始自适应旅程 |
| `/api/journey/next` | POST | **自适应核心接口**：提交当前答案 → 返回下一题 |
| `/api/journey/status` | POST | 当前旅程状态（阶段、图谱、掌握度、解锁节点） |
| `/api/journey/toggle_deep` | POST | 开关深度模式（选择→填空验证） |
| `/api/practice/derive` | POST | 选择题 → 生成衍生填空题 |
| `/api/practice/recommend` | POST | 衍生题答完后推荐同知识点题目 |
| `/api/login` | POST | 登录 |
| `/api/register` | POST | 注册（8-16 位密码，bcrypt 存储） |
| `/api/check-username` | GET | 检查用户名是否已存在 |
| `/api/progress/<session_id>` | GET | 用户答题历史与正确率 |
| `/api/admin/stats` | GET | 后台统计（用户数、答题数、正确率、难度分布） |
| `/api/admin/users` | GET | 后台用户列表（仅平台用户，不含管理员） |
| `/api/admin/accounts` | GET | 用户+管理员合并列表（role 区分，密码管理用） |
| `/api/admin/user-progress` | GET | 单用户答题记录摘要（?session_id=） |
| `/api/admin/colleagues` | GET | 我的同事（管理员用户名 + 最后上线时间，?me= 排除自己） |
| `/api/admin/key` | GET | 当前统一管理员密钥（面板展示/复制） |
| `/api/admin/login` | POST | 管理后台登录门：账号密码 + 统一密钥双重验证 |
| `/api/admin/auth-register` | POST | 管理员内推码注册（403 错码 / 409 重名 / 400 弱密码） |
| `/api/admin/auth-login` | POST | 管理员账号登录（更新最后上线时间） |
| `/api/admin/auth-check-username` | GET | 管理员用户名预检（含平台用户同名） |
| `/api/admin/user-reset` | POST | 重置密码（用户/管理员自动识别，旧密码入历史） |
| `/api/admin/password-rollback` | POST | 回退密码（最多 3 次，kind 隔离） |

---

## 6. 前端特性（已实现）

### 6.0 页面体系（2026-08-03 重构）

```
门户首页（index_glass.html）── 了解我们（about.html）
   │
   └─▶ 登录/注册（login_glass.html）──▶ 做题页（index.html）
```

- **统一风格：浅色玻璃拟态**（DeepSeek/Codex 参考）——浅蓝渐变背景 + 3 颗漂浮光球 + `backdrop-filter` 磨砂卡片 + 蓝紫渐变主色，全站零 Font Awesome 图标（内联 SVG / 品牌 logo）
- 品牌：NIDUS logo 透明底 PNG（PIL 抠图 + 4x 锐化放大）

### 6.0.1 门户首页 (`index_glass.html`)

- 左右分栏：左栏（状态徽章 → 标题+内嵌数据条 → 简介 → 三特性卡），右栏双入口卡片（进入平台 / 了解我们，底部对齐）
- 导航：首页 / 了解我们 / 进入平台（文字链接）
- 特性聚焦：知识图谱驱动 · 自适应推荐引擎 · 深度模式举一反三（摸底小测已移除）

### 6.0.2 了解我们 (`about.html`)

- 7 条真实更新记录，分页展示（4 条/页，页码 + 上一页/下一页）
- 点击条目弹详情：概述 / 实现要点 / **开发思路**（面向非技术用户，无文件路径无函数名）/ 数据速览

### 6.0.3 登录/注册 (`login_glass.html`)

- 玻璃拟态卡片 + 登录/注册选项卡
- 随机用户名 / 随机安全密码（Lucide 线性图标）
- 密码显隐切换（眼睛/眼睛斜杠 SVG）
- 实时密码强度条（5 项规则 + 弱密码黑名单）逐条 ✓/✗
- 注册按钮门控（全部条件满足才可点击）
- 用户名占用实时检查（`/api/check-username?name=`）
- 会话 `sessionStorage.sql_user`，成功跳转 `index.html?new=1`；已登录自动跳过

### 6.1 刷题主页面 (`index.html`)

- **2026-08-03 改版**：白底 → 浅色玻璃拟态（与门户统一），宽度 720→960px，导航改渐变胶囊；**摸底小测功能整体移除**（导航/诊断页/覆盖层/12 个诊断 JS 函数），保留共享渲染函数
- **双模式切换：** 自适应 Journey 模式 / 手动选题模式
- **CodeMirror 5** 集成（CDN 加载），SQL 语法高亮
- **6 Token 配色：** keyword(蓝+加粗) / function(橙) / string(灰+斜体) / number(紫) / comment(灰+斜体) / variable(青+下划线)
- **色觉辅助模式：** 点击标题栏 👁 图标，蓝-橙-灰-紫 高辨识度调色板 + 形状双编码（下划线/斜体），localStorage 持久化
- **实时错误检测：** 未闭合引号、括号不匹配 → 红色加粗标记
- **数据表格渲染：** INSERT 数据自动解析为可视化表格，支持多表
- **预期输出渲染：** 文本管道格式自动转为表格
- **建表 SQL 面板：** 可折叠展开
- **ECharts 知识图谱可视化：** 力导向图，按掌握状态着色（根深→分类中→子节点浅，绿色=已掌握，红色=当前节点）
- **类别筛选下拉框：** 从 29 个 knowledge tags 动态生成
- **填空题输入框：** 横向+纵向自由拖拽 (`resize: both`)
- **选择题选项按钮：** 点击即时判分，正确/错误着色

### 6.2 登录/注册 (`login_glass.html`，替代旧 `login.html`)

- 密码显隐切换（Lucide 眼睛/眼睛斜杠 SVG）
- 实时密码强度指示器（红→橙→绿 四色条 + 弱/中/强/非常强）
- 规则逐条点亮（8-16位 ✓ 大写 ✓ 小写 ✓ 数字 ✓ 特殊字符○可选）
- 随机密码生成（16 位含大小写+数字+符号，每类至少一个）
- 随机用户名生成（5 组前缀 + 4 位数字）
- 用户名重复检测（`/api/check-username?name=`，输入防抖 350ms）
- 注册按钮强度门控（用户名 ≥3 + 密码合规 + 两次一致 + 不重复才可点击）
- 提交防重复（按钮转圈 + 禁用）
- 已登录用户访问自动跳转做题页

### 6.3 其他页面

| 页面 | 文件 | 说明 |
|---|---|---|
| 门户首页 | `index_glass.html` | 玻璃拟态入口页（站点首页） |
| 了解我们 | `about.html` | 更新动态分页 + 详情弹窗 |
| 知识图谱 | `knowledge_map.html` | ECharts 力导向图全屏展示 |
| 摸底诊断 | `diagnostic.html` | 3 题诊断测试（功能已下线，文件保留） |
| 基础选择 | `basic_select.html` | 29 道基础概念选择题 |
| 进阶选择 | `advanced_select.html` | 29 道进阶场景/SQL 选择题 |
| 管理后台 | `admin.html` | 用户统计 + 答题数据图表 |
| 格式示例 | `format_sample.html` | 前端渲染格式参考 |

---

## 7. 项目文件结构

```
SQL自适应训练/
├── 项目方案_AI参考手册.md          ← 【本文件】项目蓝图 + AI Agent 参考
├── 新人接手指南.md                 ← 新人快速上手文档
├── 自适应算法指引.md               ← 自适应引擎设计文档（调研阶段产物）
├── 填空题题目格式规范.md            ← 题目 12 字段详细规范
├── modification.md                ← 近期改动汇总
│
├── questions.py                   ← 题库（JSON 大数组）
├── exam_questions.json            ← 真题测试题库
├── knowledge_tags.csv             ← 29 个知识标签 + 难度星级
├── 基础选择.csv / 进阶选择.csv     ← 选择题数据
├── LeetcodeSQL310.csv/json        ← LeetCode 题目元数据
│
├── start_server.bat               ← 一键启动（Windows）
│
├── backend/                       ← 后端代码
│   ├── run.py                     ← 入口：初始化和启动 Flask 服务
│   ├── app.py                     ← Flask 路由（所有 API 接口）
│   ├── database.py                ← 数据库操作 + 自适应引擎核心（journey_next）
│   ├── scraper.py                 ← 爬虫（w3resource，未成功）
│   ├── requirements.txt           ← Python 依赖
│   ├── questions.db               ← SQLite 数据库（运行时自动生成）
│   └── trim_*.py / fix_*.py ...  ← 数据维护工具脚本
│
├── frontend/                      ← 前端页面（纯 HTML/CSS/JS）
│   ├── index_glass.html          ← 【新增】门户入口页（玻璃拟态，站点首页 /）
│   ├── login_glass.html          ← 【新增】登录/注册页（玻璃拟态，/login）
│   ├── about.html                ← 【新增】了解我们（更新动态 + 详情弹窗，/about）
│   ├── nidus_logo.png            ← 【新增】品牌 logo（透明底 PNG，PIL 抠图）
│   ├── index.html                ← 主刷题页（玻璃拟态改版，已移除摸底小测）
│   ├── login.html                ← 旧登录页（已废弃，路由指向 login_glass.html）
│   ├── admin.html                ← 管理后台
│   ├── diagnostic.html           ← 摸底诊断页（功能已下线，文件保留）
│   ├── knowledge_map.html        ← 知识图谱可视化
│   ├── basic_select.html         ← 基础选择题
│   ├── advanced_select.html      ← 进阶选择题
│   ├── echarts.min.js            ← ECharts 本地副本
│   ├── index_ngrok.html          ← ngrok 版本（与普通版高度重复，待合并）
│   └── login_ngrok.html          ← ngrok 版本
│
├── docs/
│   ├── format_spec.md             ← 前端渲染格式规范（CSS + 渲染流水线）
│   ├── knowledge_map.md           ← 知识图谱节点树文档
│   └── 题目格式规范.md             ← 题目格式规范（早期版本）
│
├── ngrok/
│   └── ngrok.exe                  ← 内网穿透工具
│
├── Kaggle题库/                    ← Kaggle 原始题库（.sql + .db，未完全入库）
├── 网络爬虫/                      ← 牛客/网页爬虫相关
├── 文件/                          ← 调研阶段产物
│   ├── 调研初版.html / 全面版.html / 删减版.html / 极简版.html
│   ├── 调研全面版.docx
│   ├── API list.md
│   ├── framework_agent guidance.md
│   ├── 自适应算法指引.md
│   └── SQL知识图谱可视化.html
│
└── sample/                        ← 单题示例 HTML/JSON
```

---

## 8. 关键设计原则

1. **零构建：** 所有页面为自包含 HTML，CodeMirror/ECharts/Font Awesome 等通过 CDN 加载
2. **个体建模优先：** BKT 基于单用户答题数据即可工作，不依赖群体协同过滤
3. **渐进式架构：** MVP 阶段 SQLite 单文件数据库，无需 PostgreSQL/Redis/Neo4j
4. **可解释性：** 深度模式触发时显示提示文案（"请手动输入 SQL 确认掌握"）
5. **情感保护：** 连错 3 题自动降难度 + 阶段回退，防止挫败感
6. **深度验证：** 选择题答对不等于真掌握 → 自动弹出同知识点填空题二次验证
7. **安全兜底：** 禁止连续 5 题同模块、难度阻尼、每 5 题复习穿插
8. **无障碍设计：** 内置色觉辅助模式，SQL 高亮采用颜色+形状双编码

---

## 9. 实现状态总览

### ✅ 已实现

| 功能 | 状态 | 位置 |
|---|---|---|
| Flask + SQLite 后端 | ✅ 完成 | `backend/app.py` + `database.py` |
| 知识图谱（37 节点三层结构） | ✅ 完成 | `database.py` → `seed_knowledge_graph()` |
| BKT 自适应引擎（三阶段） | ✅ 完成 | `database.py` → `journey_next()` |
| Thompson 采样选题 | ✅ 完成 | `database.py` → `_thompson_score()` |
| 深度模式（MCQ→填空验证） | ✅ 完成 | `database.py` → `_check_fillin_mode()` |
| 前端刷题页（双模式） | ✅ 完成 | `frontend/index.html` |
| 登录系统（bcrypt + 强度检测 + 记住输入） | ✅ 完成 | `frontend/login_glass.html` + `/api/login` `/api/register` |
| 登录保护（游客禁止读题） | ✅ 完成 | `app.py` before_request 守卫 |
| 摸底诊断测试 | ✅ 完成 | `frontend/diagnostic.html` + `/api/diagnostic` |
| 管理后台（玻璃拟态） | ✅ 完成 | `frontend/admin.html` + `/api/admin/*` |
| 管理后台登录门（双重验证） | ✅ 完成 | `frontend/admin_gate.html` + `/api/admin/login` |
| 管理员账号体系（内推码注册） | ✅ 完成 | `frontend/admin_auth.html` + `/api/admin/auth-*` |
| 管理员自身页面（密钥 + 同事） | ✅ 完成 | `frontend/admin_panel.html` + `/api/admin/colleagues` `/key` |
| 密码管理（重置 + 回退 3 次 + 复制） | ✅ 完成 | `/api/admin/user-reset` `/password-rollback` + 历史表 |
| **真实 SQL 判题引擎** | ✅ 完成 | `backend/sql_judge.py`（内存库真实执行 + 结果集比对） |
| 后端分层架构 | ✅ 完成 | `db.py` / `repositories.py` / `auth.py` / `engine.py` / `seeding.py` |
| 中英双语（4 组页面） | ✅ 完成 | 轻量 i18n 引擎 + 右上角切换 |
| 知识图谱可视化 | ✅ 完成 | `frontend/knowledge_map.html`（ECharts） |
| CodeMirror 语法高亮 + 色觉辅助 | ✅ 完成 | `frontend/index.html` |
| 数据表格 + 预期输出渲染 | ✅ 完成 | `frontend/index.html` |
| 题库（457 练习 + 50 真题，含答案） | ✅ 完成 | `questions.json` + `exam_questions.json` |
| MySQL→SQLite 翻译层 | ✅ 完成 | 批量生成预期输出脚本 |
| 选择题 + 填空题混合 | ✅ 完成 | 457 practice + 50 exam |
| **单元测试 / 集成测试** | ✅ 完成 | `backend/tests/`（pytest 67 用例，临时 SQLite 隔离） |
| **git 版本控制** | ✅ 完成 | 基线快照 + 按功能拆分提交 |

### ❌ 未实现（设计文档中规划）

| 功能 | 状态 | 备注 |
|---|---|---|
| **LLM 生成同源变式题** | ❌ 未实现 | 核心设计中的"双引擎"之生成式 AI 部分，完全未做 |
| **IRT（项目反应理论）** | ❌ 未实现 | 仅使用了 BKT，IRT 的用户能力值 θ 估计未实现 |
| **ClickHouse 交互分析** | ❌ 未实现 | MVP 阶段全用 SQLite |
| **Neo4j 图数据库** | ❌ 未实现 | 知识图谱用 SQLite 表存储 |
| **Redis 缓存** | ❌ 未实现 | 所有状态存 SQLite |
| **LightGBM 精熟期排序** | ❌ 未实现 | 精熟期目前仍用 Thompson 采样 |
| **艾宾浩斯遗忘干预** | ❌ 未实现 | 没有遗忘曲线计算 |
| **Celery 异步任务队列** | ❌ 未实现 | 无异步任务 |
| **gunicorn/nginx 生产部署** | ❌ 未实现 | 当前是 Waitress/Flask dev server 裸跑 |
| **牛客/Kaggle 全量入库** | ❌ 部分未做 | 原始文件存在但未全部导入 |

---

## 10. 竞品参照

| 类型 | 项目/产品 | 核心特点 | 对我们的启发 |
|---|---|---|---|
| 学术 | ADAPT2 框架（匹兹堡大学） | 支持 SQL 等 CS 教育通用自适应框架 | 参考其框架设计思路 |
| 学术 | AI 知识图谱系统（伊利诺伊大学） | 基于知识图谱分析错误根因，已处理 1000+ 提交 | 错误归因的设计参考 |
| 学术 | DBLearn | 学习风格分类 + 自动出题 + 评分 | 学习风格适配思路 |
| 商业 | SQL Academy / SQL Prep | 题库型 + AI 辅助，遇错时 AI 提供解释 | 传统方案，作为 baseline |
| 商业 | ChatSQL | 自然语言转 SQL，以用户表达习惯为中心 | NL2SQL 能力参考 |
| 商业 | Khan Academy / Duolingo | 成熟自适应学习平台 | 自适应机制设计参考 |

---

## 11. 项目里程碑

| 里程碑 | 状态 | 交付物 |
|---|---|---|
| M1 调研完成 | ✅ 已完成 | 调研报告 · 竞品分析 · 技术可行性评估 |
| M2 方案定稿 & 图谱 V1 | ✅ 已完成 | 系统架构设计 · 技术选型文档 · 知识图谱 37 节点 |
| M3 核心引擎可运行 | ✅ 已完成 | BKT 引擎 · Thompson 采样 · 三阶段递进 · 前端刷题页 |
| M4 题库建设 | ✅ 已完成 | 356 题（61 MCQs + 295 fill-in），含标准答案 + 预期输出 |
| M5 联调 & 内测 | 🔄 进行中 | 深度模式验证 · 知识图谱重构 · 数据质量修复 |
| M5.1 工程化 + 管理后台体系 | ✅ 已完成 | 后端分层重构 · 真实判题引擎 · 登录保护 · 管理员体系（双重验证/内推码注册/密码管理）· 中英双语 · pytest 67 用例 · git 版本控制 |
| M6 LLM 集成 | ⏳ 未开始 | LLM 变式题生成 · 错误诊断 |
| M7 正式上线 | ⏳ 未开始 | 生产环境部署 · 灰度方案 · 监控告警 |

---

## 12. 风险与应对策略

### 12.1 算法层

| 风险 | 当前状态 | 应对策略 |
|---|---|---|
| **BKT 冷启动精度不足** | 已缓解 | 摸底诊断预填充 α/β + Thompson 采样快速收敛 + 冷启动期高 λ |
| **知识图谱覆盖不全** | 已改进 | 已重构为 37 节点三层结构，29 个细粒度标签 |
| **选择题猜测正确** | 已缓解 | 深度模式强制填空题二次验证 |

### 12.2 工程层

| 风险 | 当前状态 | 应对策略 |
|---|---|---|
| **SQLite 并发瓶颈** | 当前可接受 | WAL 模式 + busy_timeout，后续可迁移 PostgreSQL |
| **ngrok 页面维护成本** | 存在 | `index_ngrok.html` / `login_ngrok.html` 与普通版高度重复，建议合并 |
| **数据质量** | 已大幅改善 | 批量修复标准答案 + SQLite 执行验证预期输出 |

### 12.3 体验层

| 风险 | 当前状态 | 应对策略 |
|---|---|---|
| **"自适应"感知不强** | 部分实现 | 深度模式有提示文案；建议加成长曲线/雷达图 |
| **挫败感与流失** | 已实现 | 连错 3 题降难度 + 阶段回退 + 复习穿插 |

---

## 13. 开发指引

- **要改题库：** 编辑 `questions.py`，删掉 `backend/questions.db` 重启服务即可重新播种
- **要改自适应逻辑：** 改 `backend/database.py` → `journey_next()` 函数（约 70 行，是整个项目的核心）
- **要改页面：** 改 `frontend/index.html`（主刷题页，约 2000+ 行）
- **要加 API：** 在 `backend/app.py` 加路由，逻辑放 `backend/database.py`
- **要改知识图谱：** 改 `database.py` → `seed_knowledge_graph()` 中的节点/边定义，同步更新 `knowledge_tags.csv`
- **要改前端渲染：** 参考 `docs/format_spec.md`（CSS 变量、渲染流水线、表格生成规则）
- **题目格式规范：** 参考 `填空题题目格式规范.md`（12 字段定义 + 示例）
- **项目启动：** `python backend/run.py` 或双击 `start_server.bat`
- **公网访问：** 用 ngrok 暴露 5000 端口

---

## 14. 参考资料

| 文档 | 路径 |
|---|---|
| 新人接手指南 | `新人接手指南.md` |
| 自适应算法设计大纲 | `自适应算法指引.md` / `文件/自适应算法指引.md` |
| 题目格式规范（详细版） | `填空题题目格式规范.md` |
| 前端渲染格式规范 | `docs/format_spec.md` |
| 知识图谱节点树 | `docs/knowledge_map.md` |
| 近期改动汇总 | `modification.md` |
| API 端点列表 | `文件/API list.md` |
| 框架 Agent 指引 | `文件/framework_agent guidance.md` |
| 调研报告 | `文件/调研全面版.html` |
