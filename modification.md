# 近期改动总结

本文件汇总近期对「SQL 自适应训练系统」及相关文件的全部改动。

---

## 2026-08-05：自适应进阶图谱点亮逻辑 + 新出题引擎（双循环 + 叶/枝/根三级点亮）

**背景**：自适应进阶（Journey）原引擎为「三态题库 + 权重队列 + 题型解锁状态机」，与产品想要的「图谱点亮」体验脱节。本次完全替换出题逻辑，并实现知识图谱三级点亮。

### 1. 新出题引擎（`backend/engine.py` 全量重写）

- **双循环出题**：枝节点不放回（固定图谱顺序）→ 叶节点不放回 → 每叶连续 5 题（`[选择,选择,选择,填空,填空]` 选择先行）
- **题池循环复用**：该叶题池不足 5 道时同题可重复出（user_progress 按记录条数计数）；填空池为空 → 填空槽回退选择题池（题库不足降级，本次不改题库）
- **一轮规模**：29 叶 × 5 题 = 至多 145 题；全部刷完 → 保留点亮状态回到图谱界面，重新开始新一轮（已点亮叶不进新一轮）
- 旧的 `tag_unlocked`/`queue`/权重队列/60% 推进/70% 掌握逻辑全部删除；`_record_answer_stats` 计数器保留（total_answered/total_correct/wrong_streak/avg_speed）

### 2. 点亮规则

- **叶节点**（任一满足即点亮）：
  - 规则1：本轮该叶出的题中**连续答对 3 道**（相邻两题提交间隔 ≤2min，间隔取 user_progress.answered_at 差值）→ 点亮并跳过剩余题
  - 规则2：本轮该叶**全部题均答对**（不计间隔）→ 点亮
  - 规则3：**累计答对 10 道**该叶类型题（自适应+自主练习+真题测试跨池累计），每答对 2 道点亮 20%，节点内显示 `x/10`
- **枝节点**：圆圈内显示 `x/y`（点亮叶/总叶），全部叶点亮 → 枝点亮
- **根节点**：显示 `x/7`（点亮枝/总枝），全部枝点亮 → 根点亮

### 3. 数据模型与 API

- **新表 `user_lights`**（session_id + node_id PK，规则1/2 事件落库；规则3 由 user_progress 实时派生，不落库）
- **`journey_state` 加列 `round_state`**（JSON：本轮 entries/指针/段内答题记录/点亮记录）
- `/api/journey/status`、`/api/journey/next`：响应新增 `lights`（37 节点全量 {lit, correct|x, y}）、`round`（轮进度 pos/leaf_total/answered_total）、`round_complete`、`lit_now`（本次刚点亮节点）；**移除 `unlocked_nodes`**（两个前端消费点同步改造）
- `save_answer` 返回 lastrowid（引擎作答登记用）；`delete_user` 同步清理 user_lights

### 4. 前端

- `knowledge_map.html`：改消费 `lights` 全量状态；未点亮叶显示 `name + x/10`（上方）、枝/根圆圈内显示 `x/y`、`x/7`；部分点亮（有进度未点亮）淡彩 + 红色描边；已点亮保持彩色发光
- `index.html`：点亮统计改按 `lights`（root 不计入）；答题页节点名追加轮进度 `pos/leaf_total`；一轮完成显示完成面板（本轮点亮数 + 返回图谱）；答对点亮时提示「已点亮「xxx」」
- **了解我们（about.html）**：新增「自适应进阶：知识图谱点亮系统」更新动态（日期最新置顶），UPDATES / UPDATES_EN / UPDATES_EXTRA（zh-TW·hi·pt·ja）六语言平行各 +1 条 → 16 条/语言；DeepSeek 翻译四语言版本

### 5. 测试

- 新增 `backend/tests/test_journey_lights.py` **15 用例**：双循环出题序列、池不足循环复用、规则1（连对3+间隔≤2min 点亮跳叶 / 间隔>2min 阻断 / 连对被错题打断）、规则2（全对点亮 / 有错不亮）、规则3（correct 计数 / 跨池累计 10 点亮 / 未开始 journey 也有 lights）、枝/根 x/y 推导、一轮完成 + 点亮保留 + 新一轮
- `conftest.py` 追加 q5/q6（dml_select 基础选择 + 填空）；`test_journey_flow.py` 首题/答案/lights 断言更新；`test_journey_rules.py` 删除（旧引擎规则废弃）
- **pytest 111 用例全绿**；真实题库副本 + 真实 HTTP 冒烟通过（连对3 → 点亮跳叶 → 一轮 143 题 → 新一轮 28 叶）

### 6. 已知事项

- 每叶 5 题中填空不足时降级为选择题（本次未补题库；后续按「每叶 3 选择 + 2 填空」目标补题）
- 旧 `journey_state` 脏数据（queue/tag_unlocked/phase='cold'）自动忽略，无需迁移

---

## 2026-08-05：功能与操作指南 PDF

- 生成 `SQL自适应训练平台-功能与操作指南.pdf`（项目根目录，11 页，中文字体嵌入）
- 内容：平台简介 → 学员功能与操作指南（登录注册 / 门户与多语言 / 自适应进阶·图谱点亮 / 自主练习 / 真题测试 / 错题集翻页 / 图谱可视化 / 了解我们）→ 管理员指南（双重验证登录门 / 内推码管理员体系 / 重置回退删除 / 主管理员专属 / 统计）→ 部署分发（一键启动 / 打包一致性 / ngrok）→ 常见问题 → 技术概览
- 源文件保留在 `docs/功能与操作指南.html`（可改后重新转 PDF：msedge --headless --print-to-pdf）

---

## 2026-08-05：错题集翻页模式（每页 5 个错题）

- `frontend/index.html` 错题集改为可翻页：`WRONG_PAGE_SIZE = 5` 每页 5 条，`wrongPage` 当前页码
- `renderWrongList()` 分页渲染（切片当前页）+ 底部翻页控件（上一页 / 「第 x / y 页」 / 下一页，首末页按钮禁用）；页码越界自动钳制
- 重新进入错题集（loadWrongSet）重置回第 1 页；详情页「返回错题列表」改为 `renderWrongList()`——返回后停留在原页码，不再重新拉接口
- 卡片 onclick 传全局下标（`start + i`），翻页不影响详情定位
- 新增 6 语言词条 3 键：`上一页` / `下一页` / `第 {0} / {1} 页`（en/zh_tw/ja/hi/pt）
- 验证：JS 语法通过；DOM 桩模拟 12 条错题 → 第 1/2 页各 5 卡、页码与按钮禁用正确、越界钳制、空态、详情返回保持页码
- **了解我们（about.html）**：新增「错题集翻页：每页 5 题」更新动态（tag=优化，日期最新置顶），UPDATES / UPDATES_EN / UPDATES_EXTRA（zh-TW·ja·hi·pt）六语言平行各 +1 条 → 17 条/语言；DeepSeek 翻译四语言版本；校验 17=17=17=17=17=17、JS 语法与 pick 渲染通过

---

## 2026-08-05：打包分发一致性修复（CDN 离线化 + 旧库自动重建）

**背景**：项目打包发给他人电脑解压启动后效果与本地不一致，两类表现：
- ① 页面样式不同（图标空白、代码编辑器降级为普通文本框）→ 前端依赖国外 CDN
- ② 题目/自适应行为不同 → 对方电脑残留旧版 `questions.db`，seed 因 `count>0` 跳过导入，题库永远停在旧版

### 1. CDN 资源本地化（彻底离线）

- **下载到 `frontend/lib/`**：Font Awesome 6.4.0（`font-awesome/css/all.min.css` + `webfonts/` 6 个字体）+ CodeMirror 5.65.16（`codemirror/` css + 3 个 js）
- **6 个页面引用改相对路径**（共 10 处）：`admin` / `format_sample` / `index` / `index_ngrok` / `login` / `login_ngrok`——不再依赖 cdnjs.cloudflare.com
- **新增路由 `GET /lib/<path>`**（app.py，`static_folder=None` 无默认静态目录）：`send_from_directory(frontend/lib)`
- 校验：8 个 lib 资源全部 200；6 页面外部引用残留 0

### 2. seed 题库版本校验（旧库自动重建）

- `seed_questions()` / `seed_exam_questions()`：`count>0` 跳过逻辑改为**条数比对**——库内题数与题库文件（questions.json / exam_questions.json）不一致时自动重建题库表（DELETE + 重置 `sqlite_sequence` + 重导，题目 id 从 1 按文件顺序与本地/全新库一致）
- 重建后清理指向不存在题目的答题记录（`user_progress`），用户数据保留
- **测试**：新增 `backend/tests/test_seed_rebuild.py` 4 用例（练习库重建 / 真题库重建 / 条数一致跳过不覆盖 / 答题记录保留）；E2E 模拟旧库 2 题 → 启动自动重建 515 题 + 用户数据保留
- pytest 115 用例全绿

### 3. 已知事项

- 打包分发建议：整个项目文件夹复制/压缩（含 `backend/questions.db` 或不含均可——不含则自动重建，含则数据与本地一致；对方若残留旧库，启动时会自动重建）
- 对方浏览器过旧（backdrop-filter 需 Chrome 76+）仍可能出现玻璃拟态样式差异，属浏览器能力问题

---

## 2026-08-05：做题前端导航布局跳动修复（错题集/分类筛选触发）

- **现象**：点击「错题集」或分类标签后，导航栏（自适应进阶/自主练习/真题测试/错题集一行）发生上下位移
- **根因一（嵌套被破坏）**：此前删除 langBtn 时在 header 里多留了一个 `</div>`，导致 main-wrap 提前闭合——导航与三个页面 div 变成了 body 的 flex 直接子项；内容变短时 `.main-wrap { flex: 1 0 auto }`（body 为 flex 列布局）被拉长，把导航往下顶（实测错题集视图导航下移 56px）
- **根因二（滚动条宽度导致的换行）**：header 品牌文字（SQL 自适应训练 ADAPTIVE PRACTICE）随滚动条出现/消失改变可用宽度而换行/取消换行，卡片高度 86↔62px 跳动，导航随之上下移动（实测 24px）
- **修复**：① 删掉 header 中多余的 `</div>`，恢复 main-wrap → card/导航/页面 的正确嵌套（导航回到 main-wrap 内部）；② 品牌行加 `white-space:nowrap`，卡片高度恒定
- **验证**（无头 Edge + CDP 实测，全新 profile）：导航位置在 自适应进阶 / 错题集 / 自主练习(515题) / 分类筛选(11题) 四种状态下恒定 78px；筛选栏高度恒定 34px（✕ 标签出现不换行）；0 运行时异常

---

## 2026-08-04（深夜修复）：做题前端「自主练习/真题测试」按钮无响应——恢复被误删的 API_BASE

- **现象**：index.html 的「自主练习」「真题测试」按钮点击无响应（自适应进阶/错题集正常）
- **根因**：与上一处同源——「语言切换入口仅保留在主界面」的改动把 index.html 脚本头部 `const API_BASE = '/api'` 也误删了。页面加载到 `validateSessionSilently()`（第 775 行调用）时抛 `ReferenceError: API_BASE is not defined`，脚本在此中断，后续顶层定义（`let currentPool` 等）全部未执行——两个练习按钮的 onclick 引用 `currentPool` 时直接报错，故无响应；自适应进阶/错题集走的是函数声明（已提升），不受影响
- **修复**：按 HEAD 版本恢复 `const API_BASE = '/api'`（含原注释）
- **验证**（无头 Edge + CDP 实测）：全新 profile 加载 index.html 无任何运行时异常；四个导航按钮逐一点击均正常——自主练习（515 题）、真题测试（50 题）、自适应进阶、错题集全部切换成功
- **防漏扫**：对比 HEAD 与工作区 7 个页面全部顶层声明（const/let/var/function/class），无其他「HEAD 有而工作区缺失且仍被引用」的定义

---

## 2026-08-04（深夜修复）：登录/注册/管理员页面无响应——恢复被误删的脚本头部定义

- **现象**：管理员账号页、用户登录/注册页按钮全部无响应、选项卡无法切换；管理员面板整页脚本中断
- **根因**：此前「语言切换入口仅保留在主界面」的改动误删了三个页面 `<script>` 头部的辅助定义，导致页面一加载即 ReferenceError，后续所有事件处理全部失效：
  - `login_glass.html` / `admin_auth.html`：删除 `const API_BASE = '/api'` 与 `const $ = id => document.getElementById(id)`（`$(` 全页使用 39/34 次）
  - `admin_panel.html`：除上述两项外还删了会话变量 `var ADMIN_TOKEN` / `var ADMIN_USER` 与无 token 重定向守卫（`$(` 使用 41 次）
- **修复**：按 HEAD 版本原样恢复三个页面的 `API_BASE`、`$`、ADMIN 会话变量（admin_gate/index_glass 的 `$` 未被删，未动）
- **校验**：7 页内联 JS `node --check` 通过；DOM 桩模拟完整执行 7 页脚本全部 LOAD OK（admin_panel 存在 setInterval 计时器，模拟时需强制退出，非缺陷）

---

## 2026-08-04（深夜追加）：先导页语言主导 + 全站 6 语言跟随

### 1. 语言设置主从关系（7 页统一）

- **先导页（index_glass.html）为主导**：语言下拉菜单仅保留在先导页（门户页），选择写入 `localStorage.lang`
- **其余 6 页跟随**：`const LANG = 'zh'` → `let LANG = localStorage.getItem('lang') || 'zh'`，打开即按先导页所选语言渲染（index / login_glass / about / admin_auth / admin_gate / admin_panel）
- **补 `langKey()` 定义**：admin_gate / admin_panel 此前 t() 已调用 `langKey()` 但未定义（页面加载即 ReferenceError 报错），统一补 `function langKey() { return LANG === 'zh-TW' ? 'zh_tw' : LANG; }`（index_glass 已有，其余 5 页同步补入）
- **t() 回退链统一**：`e[langKey()] || e.en || e.zh`（缺失词条回退英文→中文兜底）；`documentElement.lang` 支持 zh-TW（`zh-TW` / `zh-CN` / `en`）

### 2. 补 4 语言词条（此前仅中英的页面）

- **login_glass 61 键**、**about 19 键**、**admin_auth 52 键** 的 I18N 字典全部补 `zh_tw/ja/hi/pt` 四语言值；**index.html 97 键**（中文原文为键）同步补入——术语与 admin_gate/admin_panel/index_glass 已有翻译保持统一（管理者/アドミン/एडमिन 等）
- 多行词条（注册/登录互切链接等）保留原 HTML 结构，仅翻译锚点文案
- 词条完整性校验：7 页全部「zh=en=zh_tw=ja=hi=pt=键数」通过

### 3. 做题前端（index.html）配套

- t() 重写：zh→中文原文 / zh_tw→繁体词条 / en→英文 / ja·hi·pt→对应词条（缺失回退英文→原文）
- 新增 `KG_LABELS_TW`（23 个中文分类标签繁体版），`catLabel` 分支：繁体→繁体标签、日/印/葡→英文标签（SQL 关键字全球通用不翻译）
- about.html 的 `UPDATES_EXTRA`/`VISION_EXTRA` 键为 `'zh-TW'`，与 LANG 直接匹配，无需改动

### 4. 校验

- 7 页内联 JS `node --check` 全部通过（OK 7 / FAIL 0）；词条 6 语言键完整性逐页核对通过

---

## 2026-08-04（晚间追加）：UPDATES_EXTRA 补 date + 项目初心 VISION 4 语言

- **UPDATES_EXTRA 补 date**：4 语言 × 15 条此前缺 date 字段（切换语言后日期空白），按索引与 UPDATES 一一对应补入（`{date:"2026-08-04",title:...` 对象内正确位置）；排查修复 date 误插对象外导致的语法错误
- **项目初心 VISION 4 语言**：DeepSeek 翻译 zh-TW/ja/hi/pt（title/desc/overview/points/thinking/stats 全字段），新增 `VISION_EXTRA` 对象；新增 `pickVision()`（zh/en 走原 VISION/VISION_EN，其余查 VISION_EXTRA 回退中文），渲染调用 2 处替换
- 校验：about.html JS 通过；VISION_EXTRA 4 键齐备

## 2026-08-04（晚间追加）：了解我们新增「全站 6 语言上线」动态

- about.html 六个数组（UPDATES / UPDATES_EN / UPDATES_EXTRA 的 zh-TW·hi·pt·ja）头部各新增一条「全站 6 语言上线」动态（15 条平行，顺序一一对应，pick 按 idx 取值）
- 条目覆盖 6 语言全文（标题/简介/概述/思路/要点/数据速览：6 语言 · 7 页面 · 14 条动态）；JS 校验通过、条数一致性验证（15=15=15=15=15=15）
- 项目方案手册功能清单补「全站 6 语言」行

## 2026-08-04（晚间追加）：了解我们动态内容 6 语言 + 语言菜单修复

### 1. 了解我们更新动态多语言（frontend/about.html）

- **UPDATES 14 条动态 × 4 新语言**（繁體中文/日本語/हिन्दी/Português）由 DeepSeek 全量翻译（title/desc/overview/thinking/points/stats 六字段，技术术语与数字保留），新增 `UPDATES_EXTRA` 对象（4 语言 × 14 条平行数组）
- `pick(u, en, idx)` 升级为 6 语言选择：zh→中文 / en→英文 / 其余→`UPDATES_EXTRA[LANG][idx]`（缺失回退中文）；渲染调用处补 idx 参数
- 排查过程修复：损坏块残留（游离 ja 数组、重复块）→ 逐段定位删除，恢复单份正确数据

### 2. 语言菜单遮挡修复（7 页统一）

- **根因**：`setLang` 直接 `location.reload()` 未先关闭菜单，慢加载时菜单残留遮住下方卡片；`applyI18n` 旧逻辑把按钮文本覆盖为旧二态（English/中文）
- **修复**：`setLang` 先关闭菜单再 reload；按钮文本改为显示当前语言名（`LANGS[LANG] ▾`）

### 3. 验证

- 全站 7 页 JS 语法校验通过；UPDATES_EXTRA 4 语言 × 14 条结构与顺序验证一致；pick 6 语言分支生效

---

## 2026-08-04（晚间追加）：全站 6 语言支持（语言下拉菜单）

### 设计目标

右上角语言按钮升级为**「语言」下拉菜单**（点击/悬停展开）：英语 English · 简体中文 · 繁體中文 · 日本語 · हिन्दी · Português，7 个页面全部词条翻译并接入。

### 1. 语言下拉框架（7 页统一注入）

- `#langBtn` 替换为 `#langWrap`（按钮 + 下拉菜单 `#langMenu`，6 项，点击 `setLang(code)` 切换 + reload）
- 统一引擎注入：`LANGS` 映射、`setLang`（存 localStorage `lang`，含 `zh-TW` 代码）、`toggleLangMenu`、`langKey()`（`zh-TW` → 字典键 `zh_tw`）、点击外部关闭菜单
- 导航页 `#langBtn { margin-left:auto }` 右对齐规则转移至 `#langWrap`；`let LANG` 重复声明去重；`t()` 查表升级：`e[langKey()] || e.en || e.zh`（index.html 原文即键模式同步升级）

### 2. 词条翻译（353 条 × 4 新语言）

- 提取 7 页全部 353 个词条（key + 中英对照）→ 调 **DeepSeek 批量翻译**（6 批）→ zh_tw / ja / hi / pt 全量翻译（技术术语/占位符/HTML 标签保留）
- 程序化注入：字典每词条追加 `'zh_tw'/'ja'/'hi'/'pt'` 四语言值；页面分布：index 101 · admin_panel 66 · login_glass 61 · admin_auth 52 · admin_gate 28 · index_glass 26 · about 19

### 3. 问题排查记录

| 问题 | 根因 | 修复 |
|---|---|---|
| 注入后 JS 语法错误 | 字典注入插入点在 en 闭合引号之前，引号错乱 | 修正插入点（闭引号之后）并还原重注入 |
| 4 个词条仍错乱（foot_login 等） | 含 `\'` 转义单引号的词条在还原正则 `.*?` 处提前截断 | 手工修正 admin_auth ×2 / login_glass ×2（含 onclick="switchTab('...')" 的词条） |

### 4. 验证

- 7 页全部 JS 语法校验通过；下拉菜单与引擎注入确认（7 处 langWrap）；字典注入数与原词条数一致（353/353）

---

## 2026-08-04（晚间追加）：选择题判题修复（HTML 实体归一）

### 问题

用户反馈"选择正确的答案也算错"。定位：58 道导入的静态选择题中 **7 道（484/489/490/504/510/513/515）的选项文本在数据库里存为 HTML 实体**（如 `&gt;`）。前端选项按钮经浏览器渲染后 DOM `textContent` 已是真字符（`>`），而 `correct_answer` 仍是实体串 → 文本比对失败 → 选对判错。（后端直查比对正常，浏览器场景必现。）

### 修复（backend/app.py）

- 选择题判题（`/api/submit` 与 `/api/journey/next` 两处）改为**双向 `html.unescape` 归一**后比较：浏览器 textContent（真字符）与 DB 实体串统一后再比对，任何客户端提交形式均可正确判题
- 数据无需清洗（归一化覆盖）；58 题 correct_answer 与选项（unescape 后）全量校验通过

### 测试（pytest 103 → 104）

- `test_mcq_html_entity_normalization`：浏览器视角（`>`）与 DB 视角（`&gt;`）均判对；错误选项仍判错
- 排查过程中发现并修正了测试自身数据错误（correct_answer 截断），真实库 7 道实体题浏览器提交全对

---

## 2026-08-04（晚间）：自适应抽题引擎按「用户题库三态」新规则整体替换

### 设计目标

将原 BKT/Thompson 引擎替换为产品新规则：**用户题库三态（未解锁/已解锁/已完成）+ 权重待做队列 + 标签题型解锁状态机**。

### 1. 题库数据（58 静态选择题导入后端）

- **关键发现**：后端 457 题全部为填空题，58 道静态选择题只存在于前端 JS —— 新规则的前提（基础/进阶选择题）需要它们进入后端题库
- CSV（官方标签/难度）+ 前端 STATIC_QUESTIONS（题干/选项/答案）合并生成 58 题：**29 基础选择 + 29 进阶选择**（`q_level` 标记），29 个官方标签每标签恰好 1 基础 + 1 进阶；写入 `questions.json`（457→515）+ 真实库迁移（幂等），qk 全量映射
- `questions.json` 新增 `q_level` 字段；`seed_questions` 入库携带

### 2. 新引擎（backend/engine.py 全量重写）

| 规则 | 实现 |
|---|---|
| **三态题库** | 已完成 = progress 答对；已解锁 = 答错过的 + 待做队列；未解锁 = 其余（初始全部） |
| **初次进标签先给基础选择题** | `_ensure_tag_entry` 只解锁 mcq；`_rebuild_queue` 按 基础选择→进阶选择→填空 分层 |
| **基础选择做对 → 解锁全部选择+填空；做错 → 只解锁选择** | `_apply_answer_unlocks` 状态机（tag_unlocked 持久化） |
| **首次做对进阶选择 → 立即推填空** | 状态机返回 force_fillin，主流程换本标签填空题（仅一次） |
| **首次做对填空 → 解锁全部填空，题型不限** | `fillin=True` 后队列混排 |
| **做对过的选择题再推概率大大调低（×0.05）、填空略微调低（×0.5）** | 复习分支权重；答错 ×1.5 强化 |
| **刚做对的题绝对不重推** | `_update_queue` 作答即移出队列 + `_pick_question` 排除 just_answered + 复习分支排除 |
| **掌握 = 做对过 ≥70% 仅含该标签的题（正确率不设限）** | `_mastered`（多标签题不计入分母/分子） |
| **推进门槛 = 做对 ≥60% 当前标签才能推下一知识点** | `_pick_tag` 未达标强制停留；达标自动推进（未进入/完成率最低优先） |
| **多标签题** | 仅当所有涉及标签对应题型解锁才推送（当前数据无多标签题，防御逻辑） |

- 批量 qk 映射（`_qk_map` 一次查询），避免逐题查库；对外接口（journey/start、next、status 响应字段）保持兼容

### 3. 存储与判题（backend/db.py + app.py）

- `questions.q_level` 列；`journey_state.tag_unlocked`（题型解锁状态）、`queue`（权重队列）JSON 列
- **选择题判题分支**：`options` 非空 → 选项文本比对（概念题非 SQL，跳过 judge_sql）——submit 与 journey/next 均适配

### 4. 前端（frontend/index.html）

- 自主练习不再前端合并 STATIC_QUESTIONS（后端 515 题已含，避免重复）；静态概念题（source=static_*）不触发「举一反三」衍生题
- journey 选择题渲染/提交兼容（选项文本提交 → 后端文本比对）

### 5. 测试（pytest 95 → 103）

- conftest 题库扩展：q1 进阶选择 + q2 填空 + q3 基础选择（select_basic）+ q4 填空（join_inner）
- 新增 `test_journey_rules.py`（8 例）：首题必为基础选择 / 基础做错只解锁选择 / 基础做对解锁全部 / 进阶首对立即推填空 / **刚做对绝不重推** / <60% 强制停留 / 100% 掌握解锁新标签 / 答错不计掌握
- 旧用例适配：phase cold→active、第一题为基础选择、选择题文本判题、select_basic 展开 4 题（含学习边后代）

### 6. 真实库端到端验证

- start → 基础选择题（q_level=basic）→ 答错 → 下一题仍为选择题（只解锁选择题）→ 刚做的题未重推 ✓

---

## 2026-08-04（晚间追加）：练习详情页「下一题」按筛选顺序跳转

- 自主练习/真题测试**题目详情页**新增常驻「下一题」按钮（静态题与动态题渲染末尾均有），点击**按当前筛选结果顺序**（搜索/题型/难度/分类过滤后的顺序）跳转到下一道题
- `renderPracticeList()` 记录 `_filteredOrder`（当前筛选顺序的 qid 数组）；`nextPracticeQuestion()` 按 `_filteredOrder` 定位当前题并跳下一道；不在筛选结果中（筛选已变化）→ 回列表；已是最后一题 → 提示「已经是最后一题」
- **修正原「下一题」按钮行为**：答完题后结果框的「下一题」（`onPracticeNext` 非衍生分支）原为返回列表，现改为真正跳下一题；答对选择题时仍显示「举一反三 →」进入衍生题
- 双语新增词条「已经是最后一题」

---

## 2026-08-04（晚间追加）：练习列表答题状态着色（对=绿 / 错=红 / 未做=白）

- 自主练习/真题测试题目列表按答题状态着色：**已做对 → 绿色卡片 + ✓ 角标、做错 → 红色卡片 + ✗ 角标、未做 → 保持白色**
- `loadPracticeQuestions()`：并行拉取 `/api/progress/<session_id>` 构建 `_progressMap`（question_id → 1/0），每次进列表刷新
- `renderPracticeList()`：按 `_progressMap`（动态题）或 `_staticStatus`（静态题本地判分）着色，新增 `.q-done`/`.q-wrong` 卡片样式与 `.q-status` 圆形角标（绿 ✓ / 红 ✗）
- 状态即时生效：`submitPracticeAnswer` 成功后更新 `_progressMap`、`checkStaticAnswer` 记录 `_staticStatus`、`backToPracticeList` 返回时重渲染
- 真题池（exam）同样生效（progress 按题 id 匹配）；静态 58 题经本地判分记录参与着色

---

## 2026-08-04（晚间追加）：移除进阶过程中的知识图谱可视化折叠面板

- 知识图谱已独立为自适应进阶入口视图（图谱树点亮小灯），做题区（journeyQuiz）内重复的「📊 知识图谱可视化」折叠面板删除：
  - HTML：`#journeyVizPanel` 卡片（标题/折叠按钮/420px iframe）
  - JS：`toggleJourneyViz()`、`journeyVizExpanded` 变量
  - CSS：`#journeyVizPanel` 下移 0.75em 规则；I18N '📊 知识图谱可视化' 词条
- **保留**：自适应进阶入口的图谱 iframe（`#journeyMapFrame`，560px 点亮版）与「开始适应」流程不受影响；独立页 `/knowledge-map` 仍可访问

---

## 2026-08-04（晚间追加）：自适应图谱独立为入口视图（知识图谱树点亮小灯）

### 设计目标

**把现有「知识图谱可视化」（ECharts 力导向树图）作为自适应进阶的第一步入口**：每次点进自适应训练，先展示知识图谱树与已点亮（解锁）的全部节点；初始默认 0 点亮，总节点数为 **36**（29 子标签 + 7 大分类之和）；点击「开始适应」按钮进入自适应刷题状态。

### 1. 后端（backend/app.py）

- `/api/journey/status` 不再对未开始的用户返回 404：未开始时返回 200（`state=null`、`unlocked_nodes=[]`、graph 仍完整返回），供图谱入口视图渲染"初始 0 点亮"；已开始时行为不变（返回解锁节点）

### 2. 图谱点亮（frontend/knowledge_map.html）

- 支持 URL 参数 `?session_id=`（入口 iframe 传入）：调 `/api/journey/status` 拉取解锁节点，**在 ECharts 力导向树上点亮小灯**——解锁节点彩色 + 发光（shadowBlur 光晕），未解锁节点暗灰
- **官方标签 id → 图内节点 id 映射表** `TAG_TO_NODE_ID`（36 项：`dml_select`→`cat-2748`…`top_dml`→`top-255`…，图中节点为 modb 内部 id）
- **点亮规则**：仅子标签（`cat-*`）参与点亮（unlocked 含 root/大分类，因无题自动掌握，直接映射会导致初始全亮）；**父节点点亮 = 其下全部子标签点亮**（推导）
- header 新增统计 `点亮 X / 36`（有 session_id 时显示）；无参数独立访问保持原全彩样式

### 3. 前端图谱入口视图（frontend/index.html）

- **移除**旧 `#journeyStart` 介绍卡，**新增** `#journeyMapView`：顶部说明 + **点亮统计** `点亮 X / 36 节点` + **图谱 iframe**（`/knowledge-map?session_id=<sid>&t=<时间戳>`，560px 高）+ **「开始适应」**按钮 → 进入刷题
- `loadJourneyMap()`：进 journey 页时调 status 计算点亮数（**只计子标签，父节点按子全亮推导**，与图内规则一致；未开始 = 0），并刷新 iframe（时间戳防缓存）
- 刷题全部掌握后新增**「返回图谱」**按钮（`backToJourneyMap()`）；做题区的「知识图谱可视化」折叠面板保留不动
- 双语：新增 4 个词条（图谱说明/节点已点亮/开始适应/返回图谱），说明段落含 HTML 的 data-i18n 键按完整文本定义

### 4. 测试（pytest 94 → 95）

- `test_status_before_start_returns_map_data`：未开始 status 200 + state=null + unlocked 空 + 图谱 37 节点仍可获取
- 验证：TAG_TO_NODE_ID 36 项全部映射且目标存在于图数据；模拟点亮计算（已开始用户 15 子 + 2 父 = 17/36）规则正确

---

## 2026-08-04（晚间追加）：刷题前端中英双语（index.html）

### 设计目标

做题前端（自适应进阶/自主练习/真题测试/错题集）支持中英切换，与门户/登录/了解我们/管理员面板语言体系打通（localStorage `lang` 全局共享偏好）。

### 实现（frontend/index.html）

- **原文即键的 i18n 引擎**：`I18N` 字典（96 键，只存英文译文，中文为默认原文）+ `t()`/`tf()`（模板参数）+ `applyI18n()`（data-i18n/-placeholder/-title 处理）+ `toggleLang()`（切语言后全量 reload 重渲染）
- **语言按钮**：header 右侧胶囊按钮（English/中文），偏好存 localStorage，全站共享
- **覆盖范围**：导航/品牌/筛选栏（题型/难度/分类）/Journey（说明/特性/动作标签/结果框）/题卡（类型标签/占位符/提交按钮/回答结果/举一反三提示）/衍生题/错题集（统计/明细/空态）/CodeMirror 校验提示/用户区（登录注册/切换用户）—— 24 处 data-i18n + 61 处 t()
- **分类标签双语**：新增 `KG_LABELS_EN`（官方 29 标签 + 7 大分类英文名），`catLabel()` 按语言返回，级联筛选面板/题干标签/筛选 ✕ 标签同步双语；`KG_GROUPS` 大类按钮走 t()
- **不翻译**：题库数据（题干/选项/解析/答案，数据层双语需双语题库，超 UI 范围）；静态题库（STATIC_QUESTIONS）内容

### 验证

- JS 语法校验通过；残留中文扫描确认仅剩字典/数据/注释
- 交叉检查：全部 t() 调用与 data-i18n 中文键均有字典映射（0 缺失）
- 语言切换后 `location.reload()` 全量重渲染，题目卡/分类标签统一按新语言展示

---

## 2026-08-04（晚间追加）：主管理员可管理平台密钥与内推码

### 设计目标

主管理员两项新能力：① 编辑（更换）新的管理平台密码——即**统一管理员密钥**，更换后同步到所有子管理员（新密钥立即对登录门与 Bearer 鉴权生效）；② 查看全部内推码并编辑（新增/删除）新内推码——与注册校验**实时同步**（新增即可用、删除即失效）。

### 1. 存储层（backend/db.py + auth.py）

| 项 | 说明 |
|---|---|
| `referral_codes` 表（新） | code（唯一）+ note 备注 + created_at；**惰性种入默认码 `NIDUS_Agent`**（首次读取时），保证注册入口始终存在 |
| `admin_settings` 表（新） | 键值设置；`admin_key` 存统一管理员密钥 |
| `get_admin_key()` | DB 优先 → env `ADMIN_TOKEN` 兜底（运行时读取 env，测试可注入）；`set_admin_key()` UPSERT 更换 |
| 内推码增删查 | `get_referral_codes()` / `add_referral_code()`（1-32 字符，重复 409）/ `delete_referral_code()`（**最后一个不允许删除**，404 不存在） |

### 2. 鉴权改造（backend/app.py）

- `_check_admin_token`、管理后台登录门第二重验证、`/api/admin/key`、auth-register/auth-login 返回的 token —— 全部改读 `get_admin_key()`（原模块常量 ADMIN_TOKEN 移除）
- 管理员注册校验：`REFERRAL_CODE` 常量 → **DB 内推码列表实时比对**

### 3. 新接口（全部主管理员 operator 校验，非主 403）

| 接口 | 用途 |
|---|---|
| `POST /api/admin/key-update` | 更换统一密钥（8-64 字符、不得与当前相同）；返回新 key，前端本地 token 同步 |
| `GET /api/admin/referral-codes?me=` | 主管理员查看全部内推码（码+备注+创建时间） |
| `POST /api/admin/referral-add` | 新增内推码（注册校验即时生效） |
| `POST /api/admin/referral-delete` | 删除内推码（409 最后一个不允许删） |

### 4. 前端（frontend/admin_panel.html，主管理员专属，双语）

- 密钥卡片新增「更换密钥」按钮 → 弹窗（输入/随机生成/复制 + 确认）→ 成功后**本地 token 同步为新密钥**并刷新显示
- 新增「内推码管理」卡片：全部内推码列表（码/备注/创建时间/删除）+ 新增行（码+备注）；删除用 confirm 确认
- 错误提示统一解析后端 `error` 文案（`toastServerError` helper）；i18n 字典 +18 键

### 5. 测试（pytest 85 → 94）

| 新用例 | 覆盖点 |
|---|---|
| TestAdminKeyUpdate（4 个） | 401 / 非主 403 / 400（过短、与当前相同）/ **更换后新 Bearer 生效、旧密钥 401、登录门与注册返回新 token** |
| TestReferralCodes（5 个） | 401 / 非主 403 / 默认码惰性种入 / **新增→注册可用、删除→注册 403（实时同步）** / 最后一个 409 |

- conftest：`monkeypatch.setattr(ADMIN_TOKEN)` → `monkeypatch.setenv('ADMIN_TOKEN')`（密钥改 DB 存储后 env 注入方式调整）

---

## 2026-08-04（晚间追加）：做题分类标签对齐官方知识图谱（7 大分类 × 29 标签 + 星级难度）

> 数据源：微信官方版 `knowledge_tags.csv`（29 标签 + 1~3★ 难度）+ `knowledge map.md`（7 大分类层级树），与项目现有文件字节一致，据此把**做题前端分类标签**与**题目难度**整体对齐。

### 1. 官方结构落地（backend/seeding.py 重写图谱种子）

- **37 节点**：root（level 0）→ 7 大分类（DML/DDL/函数/表连接/约束/子查询/SELECT，level 1）→ **29 标签**（level = 2 + 星级-1，即 ★→2 / ★★→3 / ★★★→4），官方中文名（如「基本 SELECT：字段、别名、常量」「WHERE 条件筛选」）
- **64 条边**：root→大类→标签的官方层级边 + 保序学习边（保留旧引擎进阶顺序：基础 SELECT → WHERE/聚合/连接/子查询 → DML/DDL/约束）
- **星级→难度**（knowledge_tags.csv）：1★=简单 / 2★=中等 / 3★=困难（**仅用于难度计算，界面不显示星级**）
- `CATEGORY_TO_TAG` 旧分类→官方标签全量映射（含旧节点 ID、`dml` 按标题细分 INSERT/DELETE）；`seed_questions`/`seed_exam_questions` 入库时即转换分类 + 按星级定难度；auto-map 同步更新 `questions.category` 兜底

### 2. 真实库迁移（backend/migrate_official_tags.py，可幂等重跑）

- questions 457 题 / exam_questions 50 题：category → 官方标签，difficulty → 星级难度（easy 272→302 / medium 148→137 / hard 37→18）
- question_knowledge 全量重建（457/457 映射）；图谱重建 37 节点 / 64 边
- 迁移前已备份 `questions.db.bak`；`invalidate_graph_cache` 失效

### 3. 引擎兼容（backend/engine.py）

- 官方结构引入无题节点（root/大分类）后，`_is_mastered` 与 `_get_unlocked_nodes` 将**无题节点自动视为已掌握**（`_node_has_questions` 判定），保证大分类不成为候选、其下标签可正常解锁；`_recommend_weak_prereq` 同步跳过无题前置

### 4. 前端分类标签（frontend/index.html）

- `KG_HIERARCHY`/`KG_LABELS`/`KG_GROUPS` 整体替换为官方 7×29 结构；`KG_LEAF` 清空（29 标签全部归属 7 大分类，移除独立叶节点按钮与分隔符）
- 级联子面板不再重复渲染顶层大分类（"全部XX"已覆盖）；选中标签/大分类后按官方名显示 ✕ 标签
- 题卡 `q.category` 直接显示官方标签（如「内连接」「窗口函数」）

### 5. 测试（pytest 82 → 85）

| 新用例 | 覆盖点 |
|---|---|
| TestOfficialTaxonomy（3 个） | 图谱 37 节点/7 大类/29 标签 + 官方层级边 + 星级→level（1★2 / 2★3 / 3★4）/ 难度按星级（select_basic 题 easy）/ 官方标签筛选（有题 2 题、无题 0 题不报错、大类 top_dml 展开） |

### 6. 问题排查记录

| 问题 | 根因 | 修复 |
|---|---|---|
| 新库 seed 后题目分类仍是旧值 | auto-map 只写 question_knowledge 不更新 questions.category（真实库由迁移脚本更新，测试库未覆盖） | auto-map 循环同步 UPDATE questions.category |

---

## 2026-08-04（晚间追加）：做题页移除 KNOWLEDGE MAP 徽章面板

- `frontend/index.html` 自适应进阶：删除「KNOWLEDGE MAP」折叠徽章面板（27 个知识点状态标签 + 解锁计数 `0/27`）及其全部支撑代码：
  - HTML：`#journeyGraphPanel`（`unlockedCount` / `journeyMapToggle` / `journeyGraph`）
  - JS：`renderJourneyBadges()`、`toggleJourneyMap()`、`journeyMapExpanded` 变量及 `showJourneyQuestion` 内的调用点
  - CSS：`.graph-node` 系列样式（mastered/current/locked）
- **保留**：「📊 知识图谱可视化」折叠面板（iframe 嵌入 `/knowledge-map` 的 ECharts 图）与 `toggleJourneyViz()`、`getNodeName()`、独立页面 `/knowledge-map`、`/api/graph` 接口、`echarts.min.js` 均不动；后端引擎对图谱数据的依赖不受影响
- **面板位置微调**：`#journeyVizPanel { transform: translateY(0.75em); }` 下移 0.75 字符高度（与导航按钮/页面模块的 translateY 位移方式一致），填补徽章面板移除后的视觉间距

## 2026-08-04（晚间追加）：题干分类标签显示官方中文子标签

- `frontend/index.html`：题卡上的分类标签由官方标签 **ID（英文，如 `join_inner`）** 替换为**官方中文子标签名**（如「内连接」「窗口函数」）
  - 新增 `catLabel(cat)` helper：`KG_LABELS[cat] || cat` 映射，未知 ID 原样回退
  - 6 处渲染点替换：练习列表题卡 ×3、衍生题题卡 ×1、错题集 ×2
  - 搜索框升级为**双通道匹配**：中文子标签名 + 原始 ID 均可命中（搜「内连接」或 `join_inner` 都行）
- 客户端分类筛选（`nodeIds.indexOf(q.category)`）保持 ID 匹配不变，后端筛选链路无改动

---

## 2026-08-04（晚间）：删除用户功能 + 主管理员体系

### 设计目标

管理后台可直接删除平台用户（警告 → 确认 → 删除完毕，数据从数据库同步清除）；将 **Yuhuijuan 设为主管理员**，主管理员可在「管理员面板 → 我的同事」修改其他管理员密码（防遗忘），流程与管理后台重置用户密码完全一致。

### 1. 删除用户（backend/repositories.py + app.py + frontend/admin.html）

| 项 | 说明 |
|---|---|
| `delete_user(username)` | **单事务同步删除**：users + 答题记录（user_progress）+ 掌握度（user_mastery）+ 旅程状态（journey_state）+ 诊断结果（diagnostic_results）+ 密码历史（user_password_history, kind='user'） |
| `/api/admin/user-delete` | POST，Bearer 鉴权 + **confirm=true 显式确认**（缺省 400）；管理员账号返回 400 拒绝（先查管理员表拦截，因用户名全局唯一）；用户不存在 404 |
| 前端交互流 | 用户明细操作列「删除用户」→ 警告弹窗（列出将删除的数据明细 + 红色不可恢复警告条）→「确认删除」（红色渐变按钮）→ toast「删除完毕」+ 统计卡/明细立即刷新 |
| 删除后效果 | 该用户无法登录（登录返回 404），用户名可重新注册；`/admin/stats` 用户数同步减少 |

### 2. 主管理员体系（Yuhuijuan）

| 项 | 说明 |
|---|---|
| `admin_users.is_primary` | db.py 新增列（ALTER 迁移，默认 0）；**真实库已执行：Yuhuijuan = 1** |
| `get_admin_profile(username)` | auth.py 新增：返回 username + is_primary（同事接口的 me 字段） |
| `/api/admin/colleagues` | 响应新增 `me`（当前管理员资料），列表项新增 `is_primary`；`get_admin_accounts` 管理员行同步带出 |
| **权限收紧** | `/api/admin/user-reset` 与 `password-rollback`：目标为**管理员账号**时，仅主管理员可操作（请求体 `operator` 声明操作者，非主管理员 403）；**平台用户不受限**（任意管理员可重置，行为不变） |

### 3. 管理员面板修改同事密码（frontend/admin_panel.html）

- 同事表格新增「操作」列：**仅主管理员**可见「修改密码」按钮（不对主管理员账号本身操作）；主管理员身份由同事接口 `me.is_primary` 判定
- 弹窗流程与管理后台一致：新密码输入 + 生成 + 复制 + 确认修改（密码规则 8-64 位含大小写数字），请求带 `operator=当前管理员`
- 同事名旁新增琥珀色「主管理员」徽章（badge-primary）；表格下方主管理员专属提示行
- 全部新增文案中英双语（i18n 字典 +12 键）

### 4. 主管理员：同事回退密码 + 删除管理员（追加）

- **回退密码**：同事列表新增「回退(n)」按钮（`rollback_count>0` 时显示，来自同事接口新字段，统计 kind='admin' 历史条数）；确认弹窗与管理后台一致，请求带 `operator`；成功后即时刷新回退次数
- **删除管理员**：
  - `delete_admin(username, operator)`（repositories.py）：防护三层——操作者须主管理员（否则 `not_primary`）/ 不能删自己（`self`）/ 主管理员账号不可删除（`is_primary`，唯一主管理员保护）；同步删除该管理员密码历史（kind='admin'），删除后其无法再登录管理后台（登录返回 404）
  - `/api/admin/admin-delete`：POST，Bearer + `confirm=true` + `operator`；403 非主管理员 / 400 删自己或主管理员 / 404 不存在
  - 前端交互流与删除用户一致：警告弹窗（列出删除内容 + 红色不可恢复警示条）→「确认删除」→ toast「删除完毕」+ 同事列表即时刷新
- 同事接口 `/api/admin/colleagues` 每项新增 `rollback_count`；`get_admin_accounts` 不受影响

### 5. 测试（pytest 75 → 82）

| 新用例 | 覆盖点 |
|---|---|
| TestPrimaryAdmin 追加（1 个） | 同事列表 rollback_count：重置前 0 → 重置后 1 |
| TestAdminDelete（6 个） | 401 无 token / 400 缺 confirm / 非主管理员 403、主管理员 200 + 删除后登录 404 / 删自己（主管理员）400 / **账号+密码历史同步清除、同事列表消失** / 不存在 404 |

### 6. 问题排查记录

| 问题 | 根因 | 修复 |
|---|---|---|
| 删除管理员账号返回 404 而非 400 | `delete_user` 先查 users 表，用户名全局唯一导致管理员分支成死代码 | 调整顺序：先查 admin_users 拦截，再查 users |

---

## 2026-08-04（全天）：后端重构 + 真实判题 + 管理员体系 + 双语支持 + 多项修复

### 设计目标

将项目从"可运行原型"推进到"可维护产品"：后端分层解耦、判题真实化、建立测试与版本控制；构建完整管理员体系（管理后台登录门双重验证 → 内推码注册 → 管理员面板 → 密码管理）；门户、登录、了解我们、管理员页面全面支持中英双语。

### 1. 后端架构重构（backend/）

| 文件 | 职责 | 说明 |
|---|---|---|
| `db.py` | 连接管理 + schema | 新增 `admin_users`、`user_password_history` 表（kind 区分用户/管理员），共 **12 张表** |
| `repositories.py` | 查询层 | 题库/进度/掌握度/管理员统计；`get_admin_users`（仅平台用户）与 `get_admin_accounts`（用户+管理员）分离 |
| `auth.py` | 认证 | bcrypt 登录注册 + 管理员账号（内推码注册、同事列表）+ **用户名全局唯一**（两表互查） |
| `engine.py` | 自适应引擎 | BKT + Thompson 采样（原 database.py 的 journey 部分） |
| `seeding.py` | 种子数据 | 题库 + 知识图谱 |
| `sql_judge.py` | **真实 SQL 判题引擎** | 见下 |

- 原 `database.py`（1297 行单文件）按 AST 精确切分为 5 个模块 + 判题引擎，**行为零变更**（冒烟验证通过）
- 题库 `questions.py`（6399 行）→ `questions.json`（457 题），删除 .py/.bak；seed 优先读 JSON

### 2. 真实 SQL 判题引擎（backend/sql_judge.py）

- 内存 SQLite 重建题目环境（表结构 + initial_data），**真实执行**用户 SQL 与标准答案，结果集比对：列顺序、行顺序无关；`COUNT(*)`≡`COUNT(非空列)`；`15000.0`≡`15000`
- 仅允许单条只读语句（SELECT/WITH/EXPLAIN/PRAGMA）；执行错误给中文提示（表不存在 / 列不存在 / 语法错误）
- 环境缺失回退字符串比对（兼容旧行为）；实测 Kaggle 大数据题判题 0-2ms
- `submit` 响应新增 `judge_error` 字段（前端可展示具体错误）

### 3. Journey 性能优化（backend/engine.py）

- `progress`/`mastery`/`unlocked` 每请求只加载一次并下传子函数（原 3×/2×/2× 重复全表查询）
- `get_graph()` 进程内缓存（`invalidate_graph_cache` 失效）
- 修复 `total_correct` 答对后重复 +1 的 bug（progress 已含本次记录，前端进度条此前偏高）

### 4. 安全加固（backend/app.py + auth.py）

| 项 | 改动 |
|---|---|
| Admin Bearer token | `/api/admin/*` 需 `Authorization: Bearer <token>`（env `ADMIN_TOKEN` 可配，默认值需替换） |
| 登录门槛 | before_request 守卫：`/api/*` 除公开端点外需注册用户 session_id，游客 401 禁止读题 |
| CORS | 收紧至本机来源 + `null`（支持 file:// 直开后台） |
| 密码策略 | 注册 8-64 字符（原 8-16），前端强度条/规则文案同步 |
| 限流 | 移除全局默认限流（200/天误伤练习），仅保留登录/注册/提交/admin 显式限流 |
| 内推码 | 仅存后端 `REFERRAL_CODE` 常量，前端页面与源码零出现（占位符/JS 比对全部移除） |

### 5. 管理员体系（新增 3 页面 + 10 接口）

**页面：**

| 页面 | 路由 | 功能 |
|---|---|---|
| `admin_gate.html` | `/admin-gate` | 管理后台登录门：**双重验证**（管理员账号密码 + 统一管理员密钥），密码/密钥显隐切换 |
| `admin_auth.html` | `/admin-auth` | 管理员账号登录/注册：内推码（后端校验）+ 用户名唯一 + 密码规则与平台一致（无随机按钮） |
| `admin_panel.html` | `/admin-panel` | 管理员自身页面：统一管理员密钥（掩码+复制）、我的同事（用户名+最后上线时间，15s 自动刷新） |
| `admin.html` | `/admin` | 管理后台：统计卡、难度分布、用户答题排行（前 5，点击看答题记录）、用户明细（含密码管理操作列）、分页 |

**接口（Bearer 鉴权 + 显式限流）：**

| 接口 | 用途 |
|---|---|
| `/api/admin/auth-register` | 内推码注册（错码 403 / 重名 409 / 弱密码 400） |
| `/api/admin/auth-login` | 管理员账号登录（自动更新最后上线时间） |
| `/api/admin/auth-check-username` | 注册预检（含平台用户同名） |
| `/api/admin/login` | 管理后台登录门：账号密码 + 密钥双重验证（`hmac.compare_digest` 常量时间比较，统一模糊报错） |
| `/api/admin/colleagues` | 我的同事（`?me=` 排除自己） |
| `/api/admin/key` | 返回当前统一管理员密钥（面板展示/复制，与服务端实时一致） |
| `/api/admin/accounts` | 用户+管理员合并列表（role 区分，仅供面板密码管理） |
| `/api/admin/user-reset` | 重置密码（自动识别用户/管理员表；旧密码入历史，最多 3 条） |
| `/api/admin/password-rollback` | 回退密码（最多 3 次，kind 隔离互不干扰） |

### 6. 密码管理（重置 + 回退 + 复制）

- 重置前旧密码入 `user_password_history`（每账号最多 3 条，`kind` 区分用户/管理员，同名也不串）
- 回退还原最近一条历史并消费该条 → **最多回退 3 次**；重置/回退成功后立即刷新，按钮即时出现
- 管理后台「用户明细」表格操作列：重置密码（弹窗：新密码 + 生成 + 复制 + 确认）+ 回退(n)
- 复制功能兼容 file://（非安全上下文自动回退 `execCommand`）

### 7. 前端中英双语（门户/登录/了解我们/管理员 3 页）

- 轻量 i18n 引擎：`I18N` 字典 + `data-i18n`(-html/-placeholder/-title) 标记 + `t()` 函数，偏好存 `localStorage`
- 导航右上角语言切换按钮（English/中文），全站共享偏好，切换即时生效
- 了解我们更新数据**双轨**：中文数组原样保留 + 新增 `UPDATES_EN` 平行数组（全量翻译，顺序一一对应）
- 动态文案（校验提示/强度标签/toast）统一走 `t()`；密码策略同步 8-64

### 8. 了解我们页更新（2026-08-04）

- 新增 4 条公开动态：真实 SQL 判题引擎 / 全站中英双语 / 团队管理后台（邀请方式与密钥**不公开**）/ 安全加固登录保护
- **数据速览悬停提示**：stats 支持可选第三字段（提示文本），CSS 气泡展示（如「3 类常见错误提示」→ 表不存在 · 列不存在 · 语法错误），中英各自携带
- 修复 `UPDATES` 数组 `},,` 双逗号空洞（length 9→8，第三页按钮无响应 bug）；渲染函数防御性跳过空洞

### 9. 管理后台 UI 与修复

- 玻璃拟态改版（与门户统一：光球 + 毛玻璃 + 渐变）；用户答题排行前 5 + 用户明细每页 5 条分页
- 排行榜柱子和明细行可点击查看答题记录弹窗
- 「正确/错误比例」环形图删除（与正确率统计重复），难度分布与答题排行等比例放大填充
- 用户答题排行与难度分布图表尺寸对齐（统一 240×160 视口）
- 右上角时间显示替换为「← 返回首页」按钮

### 10. 工程化

- **git 仓库建立**（此前无版本控制），基线快照 + 按功能拆分 30+ 提交，每步可回滚
- **pytest 测试体系**：67 个用例（判题引擎/鉴权/登录门槛/管理员体系/回退/全局唯一/图表数据），临时 SQLite 隔离，不碰真实库
- 清理 backend 下 10 个一次性调试脚本；新增 `requirements-dev.txt`

### 11. 问题排查记录

| 问题 | 根因 | 修复 |
|---|---|---|
| 管理后台登录后跳转 404 | 跳转目标 `admin.html` 无路由（只有 `/admin`） | 改跳 `/admin` + 补 `/admin.html` 别名路由 |
| 登录进入后立即闪回 /login | 会话校验走 apiGet，401 触发硬跳转（sessionStorage 残留旧会话） | 校验改静默：清会话 + 原地显示登录提示 |
| 切换用户闪回登录页 | 登录页"已登录自动跳转" IIFE 拦截 | 切换先清会话再进登录页，两场景区分 |
| 重置密码前端无响应 | admin.html 缺 `toast` 函数（ReferenceError） | 补齐玻璃拟态 toast 组件 |
| 重置密码失败 | `adminFetch` 单参数，POST 的 method/body 被丢弃 → 发成 GET → 405 | 支持 opts 并合并 Authorization 头 |
| 回退按钮需手动刷新 | 重置成功后未刷新用户表 | 补 `loadAdmin()` 立即刷新 |
| 了解我们第三页按钮无响应 | UPDATES 数组 `},,` 空洞（length 9） | 删多余逗号 + 防御性跳过 |
| 内推码泄露 | 占位符/JS 源码含码值 | 全部移除，仅后端校验 |
| 管理后台混入管理员 | users 接口合并了两类账号 | `/users`（仅用户）与 `/accounts`（用户+管理员）分离 |

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
