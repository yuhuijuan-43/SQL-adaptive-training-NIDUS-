# 近期改动总结

本文件汇总近期对「SQL 自适应训练系统」及相关文件的全部改动。

---

## 2026-08-03（下午）：玻璃拟态门户体系上线（门户 → 登录 → 做题三级路径）

### 设计目标

参考 DeepSeek / Codex 等大厂前端风格，采用**浅色玻璃拟态**（磨砂卡片 + 漂浮光球 + 蓝紫渐变主色），构建完整的三级页面体系：**门户首页 → 登录/注册页 → 做题页**，并在做题页移除摸底小测功能。

### 1. 门户入口页（新增 `frontend/index_glass.html`）

| 项 | 说明 |
|---|---|
| 风格 | 浅蓝渐变背景 + 3 颗慢漂移光球 + `backdrop-filter: blur(24px)` 磨砂玻璃卡片 + 蓝紫渐变（`#4a7dff → #8b5bff`） |
| 布局演进 | 居中文案 → 双卡片入口 → 左右分栏（左文案右按钮）→ 右栏与左栏底部对齐 |
| 标题数据条 | 「356+ 精选题目 / 100% 免费使用」以**行内元素嵌入标题第一行**（修复 h1 整块宽度导致数据条被顶到右侧的问题） |
| 特性卡 | 移除「摸底小测 · 精准定级」，替换为「深度模式 · 举一反三」（平台真实特色） |
| 图标 | 页面零 Font Awesome 图标，仅保留品牌 logo |
| 页脚 | 移除技术栈与「演示版」字样，改为 `© 2026 SQL 自适应训练 · 千人千面的 SQL 学习平台` |

### 2. NIDUS logo 处理（`frontend/nidus_logo.png`）

- 原图为黑底 + 蓝色图形（264×264 JPG），与浅色页面不协调
- 用 PIL 按亮度阈值（羽化过渡）抠除黑色背景 → 透明 PNG
- 4x LANCZOS 放大 + UnsharpMask 锐化 + 对比度增强，NIDUS 文字清晰度显著提升
- 展示为白色圆角芯片内嵌，与浅色背景自然融合

### 3. 了解我们独立页（新增 `frontend/about.html`，路由 `/about`）

- **更新通知列表**：7 条真实更新记录（取自本文件历史），每页 4 条分页（上一页/下一页/页码/总数信息）
- **详情弹窗**：点击条目弹出，含「本次更新做了什么 / 实现要点 / 我们的开发思路 / 数据速览」四个区块
- **面向非技术用户**：详情内容不含文件路径、函数名、接口路径，改为思路分享式叙述（如「让机器做裁判：大模型生成、数据库验证」）
- 数据字段：`overview`（概述）/ `points`（实现要点）/ `thinking`（开发思路）/ `stats`（数据速览）
- 关闭按钮美化：右上圆形 ✕（悬停渐变 + 旋转 90°）+ 底部渐变胶囊「知道了」
- 2026-07-28 条目重写：移除摸底小测相关内容，聚焦深度模式

### 4. 登录/注册页（新增 `frontend/login_glass.html`，`/login` 指向它）

- 玻璃拟态设计，登录/注册选项卡切换，渐变胶囊高亮
- **迁移旧 login.html 的全部功能**：随机用户名（`sql_dev/data_fan/query_master/db_coder/analyst` + 4 位数字）、随机安全密码（16 位，每类字符至少一个，打乱）、密码显隐切换、密码强度条（5 项规则 + 20 个弱密码黑名单 + 12 位加分）、规则逐条 ✓/✗、注册按钮门控（用户名 ≥3 + 含大小写数字 + 两次一致 + 不重复才可点击）
- **emoji 全部替换为 Lucide 官方线性 SVG**（unpkg 获取，ISC 协议，内联零 CDN）
- 接口直连：`POST /api/login`、`POST /api/register`、`GET /api/check-username`
- 会话约定与做题页一致：`sessionStorage.sql_user` → 跳转 `index.html?new=1`；已登录用户自动跳过
- 移除游客登录入口（仅保留微信/GitHub 开发中占位）

### 5. 做题前端改版（`frontend/index.html`）

- **风格统一**：白底 → 浅色玻璃拟态（渐变背景 + 光球、磨砂卡片、渐变胶囊导航按钮、页面宽度 720→960px、CodeMirror 半透明底）
- **摸底小测整体移除**：导航按钮、摸底页、新用户覆盖层弹窗、12 个诊断 JS 函数（`checkAndShowDiagnostic` / `loadDiagResult` / `startDiagOverlay` / `showDiagOverlayQuestion` / `submitOverlayAnswer` / `finishDiagOverlay` 等）及状态变量全部删除
- **共享函数保留**：`parseOptions` / `selectOpt` / `clearOpt` / `showOptionExplanations` / `renderQuestion`（练习/进阶模块共用）、`getNodeName`（journey 版带 graph 参数）
- 导航保留：自适应进阶 / 自主练习 / 真题测试 / 错题集，默认页改为自适应进阶
- 头部副标 `DIAGNOSTIC · PRACTICE` → `ADAPTIVE PRACTICE`；错题集文案同步清理

### 6. 路径接线（三级流转）

```
localhost:5000/  →  index_glass.html（门户）
   ├─ 导航「进入平台」/ 双卡片「进入平台」──▶ login_glass.html
   ├─ 「了解我们」──▶ about.html
   └─ 登录/注册成功 ──▶ index.html?new=1（做题页，自动登录）
```

**后端路由变更（`backend/app.py`）：**

| 路由 | 改动 |
|---|---|
| `/` | 改为返回 `index_glass.html`（原 index.html 移至 `/index.html`） |
| `/login` | 改为返回 `login_glass.html`（旧 login.html 废弃） |
| `/login_glass.html` `/index_glass.html` `/about.html` `/about` | 新增 |
| `/nidus_logo.png` | 新增（品牌 logo 静态资源） |

### 7. 问题排查记录

- **端口 5000 残留进程**：多次测试遗留的 python.exe 进程占用端口导致新路由 404 → `netstat` 定位 PID 后 `taskkill //F` 清理
- **`/api/check-username` 参数名**：后端读取 `?name=`，前端初版误传 `?username=` 导致占用检查永远返回可用 → 修正前端参数

---

## 2026-08-03：自定义级联分类筛选器（hover 切换）

### 设计目标

将分类筛选从原生 `<select>` 改为**自定义级联面板**——鼠标滑过大分类即显示子分类，自由切换，不锁定。

### 交互方式

```
分类  [SELECT基础] [条件筛选] [排序与聚合] [多表连接] [子查询与CTE] | [窗口函数] [DML] [日期处理] [字符串处理] [UNION]
      ↑ mouseenter → 下方弹出子分类面板（全部 + 具体子节点）                      ↑ 独立叶节点，点击直接筛选
      ↑ 鼠标移到另一大分类 → 面板内容即时切换
      ↑ 鼠标移出级联区域 → 200ms 后面板消失
```

选中后筛选栏右侧出现 `✕ 分类名` 标签，点击可清除筛选。

### 实现细节

| 文件 | 改动 |
|------|------|
| `frontend/index.html` | 替换 `<select id="filterCategory">` + `<select id="filterSubCategory">` 为自定义 `<div class="cat-cascade">`（含 `#catParents` 按钮行 + `#catSubPanel` 弹出面板）；新增 6 条 CSS 规则（`.cat-parent-btn` / `.cat-sub-item` / `.cat-sub-all`）；JS 端新增 `_catSelectedParent` / `_catSelectedNode` / `_catHideTimer` 状态变量；新增 `buildCategorySelect()`（构建按钮行）、`onCatParentHover()`（hover 填充并定位面板）、`buildSubItems()`（递归生成子节点）、`hideSubPanel()`、`highlightCatSelection()`、`clearCatFilter()`；移除旧的 `onCategoryChange()` / `addSubOptions()` / hover IIFE；筛选栏中题型和难度两个 `<select>` 统一样式为 `height:34px; font-size:0.75rem; min-width:90px` |

### 与旧版对比

| | 旧版 | 新版 |
|---|---|---|
| 触发方式 | 点击 `<select>` 选中父分类 | 鼠标滑过大分类按钮 |
| 切换父分类 | 需先切换到"全部类别"再选另一个（bug：锁定） | 鼠标直接移到另一个按钮，面板即时切换 |
| 子分类呈现 | 平铺在 optgroup 中，含 `├` 线符 | 弹出面板，纯文字 + padding 缩进 |
| 当前筛选提示 | 无 | `✕ 分类名` 标签，可点击清除 |

---

## 2026-08-02（下午）：层级分类筛选 + 难度筛选修复

### 1. 难度筛选覆盖静态选择题

**问题：** `renderPracticeList()` 中搜索和题型筛选是客户端执行（覆盖所有题目），但难度筛选只通过 API 参数传给后端，58 道静态选择题（`STATIC_QUESTIONS`）被无条件合并，不受难度筛选约束。

**修复：** `frontend/index.html` — 在 `renderPracticeList()` 中增加客户端难度筛选，对全量题目（动态+静态）统一生效。

### 2. 分类筛选改为知识图谱层级结构

**问题：** 原分类下拉框是扁平列表（从题目 category 字段汇总），没有层级关系，无法按大分类→子分类精准筛选。

**实现：**

| 位置 | 改动 |
|------|------|
| `backend/database.py` | 新增 `_expand_node_to_categories(node_id)` — BFS 展开知识图谱节点为所有后代节点 ID；`get_all_questions` / `get_exam_questions` 新增 `node` 参数，支持按知识节点筛选（via `question_knowledge` + `category` 双通道匹配）；`cat_to_node` 映射扩展为 29 个 viz 标签 |
| `backend/app.py` | `/api/questions` 路由接受 `node` 参数并传递到查询函数 |
| `frontend/index.html` | 新增 `KG_HIERARCHY`（知识图谱父子关系）、`KG_LABELS`（节点→中文名）、`KG_GROUPS`（6 个 optgroup 分组）、`kgExpand()`、`KG_ROOT_EXPAND`（根节点→所有后代）、`STATIC_CAT_MAP`（静态分类→节点映射）、`resolveCategoryFilter()`、`buildCategorySelect()`（自动生成层级下拉框）、`onFilterChange()`/`onCategoryChange()` 事件处理；`loadPracticeQuestions()` 改为通过 `node=` 参数筛选；`renderPracticeList()` 新增分类筛选（含静态题映射） |

**下拉框结构：**

```
全部类别
── SELECT 基础 ──
  ▸ 全部SELECT基础类
    ├ SELECT 基础
      ├ 别名 AS
      ├ DISTINCT 去重
      ├ WHERE 条件
        ├ AND/OR 多条件
        ├ LIKE 模糊
        ...
── 条件筛选 ──
  ▸ 全部WHERE条件类
    ├ WHERE 条件
      ├ AND/OR 多条件
      ...
── 排序与聚合 ──
── 多表连接 ──
── 子查询与CTE ──
── 其他 ──
  ├ 窗口函数
  ├ DML (增删改)
  ├ 日期处理
  ├ 字符串处理
  └ UNION 合并
```

**筛选逻辑：**
- 选择「全部类别」→ 不传 `node` 参数，返回全部
- 选择「▸ 全部XXX类」→ 传 `node=rootId`，后端展开为 root + 所有后代节点
- 选择具体子节点 → 传 `node=leafId`，只匹配该节点
- 静态选择题通过 `STATIC_CAT_MAP` 映射参与筛选（如 DML→dml_*）
- 搜索框、题型、难度等筛选依然通过 `onFilterChange()` 联动

---

## 2026-08-02（上午）：牛客题库答案生成 + 导入 + 文档更新

### 1. 牛客题库答案批量生成

**背景：** 牛客爬取的 182 道题（6 个分类目录）全部缺少标准答案（`solution.sql` 均为 `-- TODO`）。

**方案：** 使用 DeepSeek API 逐题生成 SQL 答案 → SQLite 执行验证 → 自动重试修正 → 写入 `solution.sql`。

**新增脚本（位于 `牛客SQL题库/牛客SQL题库/`）：**

| 脚本 | 用途 |
|------|------|
| `prepare_for_llm.py` | 读取所有题目文件（meta/schema/data/problem/expected），提取干净数据保存为 JSON |
| `generate_answers.py` | 调用 DeepSeek API 逐题生成答案，SQLite 验证，自动重试，写入 solution.sql |
| `fix_failed.py` | 修复首批失败的 12 题（schema/data 合并问题） |
| `fix_final.py` | 修复剩余 6 题（正则类型转换 bug：`DATE→TEXT` 误伤列名 `fdate→fTEXT`） |
| `fix_remaining.py` | 补充最后 33 道 SQL 必知必会题目答案 |
| `write_solutions_to_disk.py` | 从进度文件回写答案到磁盘（修复 folder 字段为空的 bug） |
| `import_with_solutions.py` | 最终导入脚本：读取所有题目+答案，生成预期输出，写入 questions.py 和 exam_questions.json |

**结果：182/182 题全部生成并通过 SQLite 执行验证。**

**关键 bug 修复：**
- **类型转换正则误伤列名：** `re.sub(r'DATE\b', 'TEXT')` 将列名 `fdate` 替换为 `fTEXT`，`hire_date` 替换为 `hire_TEXT`。修复：所有类型正则加 `\b` 前缀（`\bDATE\b`）
- **`INSERT table VALUES` 无 INTO 关键字：** SQL 必知必会部分题目使用 MySQL 方言 `INSERT \`table\` VALUES`，SQLite 不兼容。修复：自动补 `INTO`
- **`sample_data.sql` 含内联 DDL：** 部分题目（SQL40 等）的 `schema.sql` 只有首表，其余表在 `sample_data.sql` 中内联 `CREATE TABLE`。修复：合并两处 DDL
- **`os.path.basename()` 对尾随反斜杠返回空串：** Windows 路径 `'...SQL40_xxx\\'` 导致 basename 为空，solution.sql 写入失败。修复：`rstrip('/\\')` 预处理

### 2. 题库导入

**导入规则：**
- SQL 快速入门 + SQL 必知必会 + SQL 热题 → **自主练习**（questions.py）
- SQL 大厂笔试真题 → **真题测试**（exam_questions.json）
- SQL 进阶挑战 / SQL 大厂面试真题 → 空目录，无题目

**结果：**

| 文件 | 变化 |
|------|------|
| `questions.py` | 325 → **457 题**（+132 牛客） |
| `exam_questions.json` | 重建为 **50 题**（牛客笔试真题） |
| `backend/questions.db` | 已删除，重启自动重建 |
| `questions.py.bak` | 导入前备份 |

### 3. 项目文档更新

| 文件 | 改动 |
|------|------|
| `项目方案_AI参考手册.md` | **全面重写。** 更新为实际实现状态：技术栈（SQLite 而非 PostgreSQL）、知识图谱（37 节点三层结构）、题库（356→507 题）、API 端点（全部 20+ 个）、明确区分 ✅ 已实现 / ❌ 未实现（LLM/IRT/ClickHouse 等）、移除无关的医疗数据预处理章节、新增项目文件结构和开发指引 |

### 4. 关键发现

- `项目方案_AI参考手册.md` 原第 9 节「数据预处理」内容为医疗数据（新辅助治疗/术后治疗分层列），与本项目完全无关，疑似从其他项目误粘贴，已移除
- 原参考手册描述的 640 题库（力扣 323+牛客 277+Kaggle 40）与实际不符，实际可用 356 题（现增至 507 题）
- LLM 生成变式题、IRT、ClickHouse、Neo4j、Redis 等设计文档中规划的功能均未实现
- Windows 中文路径 + 尾随反斜杠导致 `os.path.basename()` 返回空串，为 Python 已知跨平台陷阱

## 一、前端文件修改

### 1. viz-standalone.html（SQL 知识图谱可视化）

| 改动 | 说明 |
|------|------|
| 节点位置固定 | 将 `layout: 'force'` 改为 `layout: 'none'`，移除 `draggable: true`，节点不可拖动 |
| 树形布局（已撤销） | 尝试改为叶子权重树形布局避免节点/连线重叠，后按要求完全恢复原始版本 |

### 2. frontend/index.html（主前端）

| 改动 | 说明 |
|------|------|
| 摸底小测入口 | 新增「开始摸底小测」按钮，游客也可作答 |
| 加载提示 | 摸底小测请求期间显示"正在加载"旋转提示，隐藏"跳过"按钮防误操作 |
| 表头解析修复 | `parseSchemaToMap` 支持裸表结构（无 `CREATE TABLE` 前缀），修复表头显示为 col1/col2 的问题 |
| 类别筛选 | 「全部类别」下拉框改为从题目 knowledge tags 汇总生成（29 个标签） |
| Knowledge Map 图形化 | 引入 `echarts.min.js`，知识图谱改为 ECharts 力导向图展示（根→分类→子节点），按状态着色 |
| 图谱配色渐变 | 根节点 `#1a1a2e`（最深）→ 分类 `#3a5a7a` → 子节点 `#7a9aba`（最浅），已掌握/当前节点用绿/红区分 |
| 图谱高度 | 从 320px 增至 420px |
| ECharts 回退机制 | echarts 不可用时自动回退到简单标签渲染，避免白屏 |
| 脚本标签修复 | 修复损坏的 `<script src=" echarts.min.js></script>` 标签（缺引号导致全白页） |

### 3. 题库练习 HTML 文件（新增）

| 文件 | 内容 |
|------|------|
| `基础选择.html` | 29 道基础选择题（概念记忆题），点击选项即时判分 |
| `进阶选择.html` | 29 道进阶选择题（场景/SQL 语句题，含建表数据、建表 SQL、预期输出、语句选项） |
| `摸底小测.html` | 3 道基础选择题（查询员工、WHERE 筛选、ORDER BY 排序） |

## 二、数据文件（新增/修改）

| 文件 | 内容 |
|------|------|
| `knowledge_tags.csv` | 29 个 viz 图谱子节点标签 + 难度星级（1~3★），GBK 编码 |
| `LeetcodeSQL310.csv` | 310 道 LeetCode SQL 题：序号、英文题名、tags（1-3 个）、difficulty |
| `基础选择.csv` | 29 题：序号、题名、tag、difficulty（全部 Easy） |
| `进阶选择.csv` | 29 题：序号、题名、tag、difficulty（按星级 Easy/Medium/Hard） |
| `knowledge map.md` | viz-standalone.html 节点树结构文档 |
| `modification.md` | 本文件 |

## 三、后端系统改造

### 1. 摸底小测固定题目（backend/database.py + app.py）

- 新增 `_DIAGNOSTIC_QUESTIONS` 固定题库数据（3 题）
- `/api/diagnostic` 接口改为固定返回这 3 题（不再随机挑选）
- `ensure_diagnostic_questions()` / `get_diagnostic_questions()` 保证题目存在

### 2. 题库导入

- **基础选择 + 进阶选择 58 题**：解析 HTML 导入题库（含建表、选项、预期输出）
- **LeetCode 310 题**：按 CSV 更新 tag 和 difficulty（匹配 LeetCode 题号）

### 3. 标签/难度同步

- 更新 371 题的 `difficulty` 列和 `tags` 列与三个 CSV 一致
- 修复 tags 分隔符：CSV 用 `;`，数据库需用 `,`（272 题修复）
- `knowledge_tags.csv` 转为 GBK 编码，修复后端 `_load_star_difficulty` 读取星级
- 移除 `seed_knowledge_graph` 中的 `cat_to_node` 旧映射，只保留 tags 列，使类别筛选精确显示 29 个标签

### 4. 知识图谱重构（backend/database.py）

- 新增 viz 结构节点：根节点 + 7 个分类（DML、DDL、函数、表连接、约束、子查询、SELECT）+ 29 个子节点
- 移除旧的边，仅用 viz 结构作为学习路径
- `_get_unlocked_nodes`：无题目的分类/根节点自动视为已掌握
- `init_journey` / `journey_next`：只选有题目的节点作为起始和推荐目标
- `/echarts.min.js` 路由（修复 ECharts 404）

## 四、自适应进阶（Journey）逻辑调整

### 1. 权重调整（backend/database.py）

| 情形 | 权重 |
|------|------|
| 做对过的选择题 | 0.05（大大调低） |
| 做对过的填空题 | 0.5（略微调低） |
| 未做过的选择题 | 1.2（优先推送） |
| 答错过的题 | ×1.5（强化练习） |

### 2. 解锁规则

- 首次答对**基础选择题** → 只解锁全部选择题（不解锁、不推送填空题）
- 首次答对**进阶选择题** → 解锁全部选择题 + 全部填空题，并立即推送一道填空题（LeetCode）
- 答错选择题 → 只解锁全部选择题
- 首次答对填空题 → 解锁全部填空题
- **60% 规则**：当前知识标签答对率 < 60% 时强制停留在该标签，达到 60% 才推送下一个知识点

### 3. 修复的问题

- **解锁链断裂**：原逻辑答对选择题只解锁"配对填空题"（不存在），导致填空题永不解锁，用户刷不到 LeetCode 题 → 改为首次答对进阶选择题直接解锁并推送

## 五、数据质量修复

### 1. 单题修复

| 题号 | 问题 | 修复 |
|------|------|------|
| 2127 经理已离职的员工 | 答案错、输出错 | 改为 NOT IN 子查询，输出 employee_id=11 |
| 3574 查找重叠班次 | 答案错（`SELECT * FROM if`）、无输出 | 改为自连接重叠检测，输出 1/2/4 |
| 3253 对称坐标 | 答案错（表扫描）、输出错 | 改为 EXISTS 对称检测，输出 6 行对称坐标 |

### 2. 批量标准答案更新（LeetcodeSQL310-答案.html）

- 解析 310 道题的标准 SQL 答案，按题号匹配更新 `correct_answer`
- 通过 SQLite 执行翻译后的 SQL 生成预期输出表格（295 题成功）
- MySQL→SQLite 翻译层：ENUM、AUTO_INCREMENT、DATE_FORMAT、DATEDIFF、IFNULL、LEAST/GREATEST、DAYOFWEEK、HOUR/MINUTE/SECOND 等
- **删除 15 道无法生成预期输出的题**（涉及 REGEXP、CREATE FUNCTION、FIND_IN_SET 等 SQLite 不支持的功能）

## 六、问题排查记录

### 1. ngrok 页面全白

- **根因**：插入 echarts 脚本标签时损坏（`<script src=" echarts.min.js></script>` 缺右引号），导致浏览器解析整个 HTML 结构错乱
- **修复**：更正标签为 `<script src="echarts.min.js"></script>`
- 辅助修复：首页路由加 `Cache-Control: no-cache`、echarts 加载失败回退

### 2. LeetCode 题刷不到

- **根因**：解锁链断裂，填空题永不解锁
- **修复**：进阶选择题答对后直接解锁全部填空题并推送

## 当前题库状态

| 项目 | 数量 |
|------|------|
| 总题数 | 356（371 - 15 删除） |
| 选择题 | 61（摸底 3 + 基础 29 + 进阶 29） |
| LeetCode 填空题 | 295（全部有标准答案 + 预期输出） |
| 知识标签 | 29 个 viz 子节点标签 |
