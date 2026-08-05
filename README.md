# SQL 自适应训练平台

> 基于**知识图谱点亮机制** + **自适应出题算法**的个性化 SQL 练习平台 —— 题库 515 题，覆盖 LeetCode SQL 真题与静态选择题，让每一次练习都"照亮"一个知识点。

## ✨ 功能特性

- **🧭 知识图谱三级点亮**：知识点按「叶 → 枝 → 根」组织，答对题目逐级点亮图谱节点，学习进度可视化
- **🎯 Journey 自适应引擎**：双循环出题，按「选择 ×3 + 填空 ×2」组成 5 题序列；跨练习池累计答对即点亮节点（规则驱动，幂等落库）
- **📝 SQL 判题引擎**：SQL 规范化 + 只读单语句校验 + 沙箱环境执行 + 结果集比对，支持复杂查询等价判断
- **🗂️ 515 题题库**：LeetCode SQL 310 题（含填空变体）+ 58 道静态选择题，全部带知识点标签（q_level 标记）
- **📊 学习闭环**：水平诊断 → 自适应练习 → 错题集（支持翻页）→ 图谱点亮 → 进阶选择
- **👤 完整账号体系**：注册 / 登录 / 会话管理 / 管理员面板（统一管理员密钥 + 内推码机制）
- **⚡ 零框架前端**：纯手写 HTML/CSS/JS，ECharts 本地化离线资源，开箱即用
- **🪄 一键启动**：`start_server.bat` 自动探测/安装 Python、自动装依赖、启动服务并打开浏览器

## 🛠️ 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python · Flask · SQLite |
| 前端 | 原生 HTML/CSS/JS · ECharts |
| 判题 | 自研 SQL 规范化 + 沙箱执行比对 |
| 测试 | pytest（115 用例） |
| 其他 | 牛客/LeetCode 爬虫（独立工具） |

## 🚀 快速开始

### Windows 一键启动（推荐）

```bat
start_server.bat
```

脚本会**自动完成**：探测可用 Python（找不到则自动下载安装）→ 安装依赖 → 启动服务 → 打开浏览器 `http://localhost:5000`

### 手动启动

```bash
# 1. 安装依赖
pip install -r backend/requirements.txt

# 2. 初始化题库
python backend/seeding.py

# 3. 启动服务
python backend/run.py
# 访问 http://localhost:5000
```

## 📁 目录结构

```
├── backend/               # Flask 后端
│   ├── app.py             # 路由 / API / 鉴权
│   ├── engine.py          # Journey 自适应引擎（图谱点亮）
│   ├── sql_judge.py       # SQL 判题引擎
│   ├── seeding.py         # 题库种子重建
│   ├── scraper.py         # 题库爬虫
│   └── tests/             # pytest 测试套件（115 用例）
├── frontend/              # 前端页面（纯 HTML/CSS/JS）
│   ├── index.html         # 首页
│   ├── knowledge_map.html # 知识图谱点亮视图
│   ├── diagnostic.html    # 水平诊断
│   └── admin*.html        # 管理面板
├── docs/                  # 设计文档与规范
│   ├── knowledge_map.md   # 图谱设计
│   └── format_spec.md     # 题目格式规范
├── questions.json         # 题库数据源（515 题）
└── start_server.bat       # 一键启动脚本
```

## ✅ 测试

```bash
cd backend
pytest -v        # 115 个用例全绿
```

覆盖：SQL 判题引擎、图谱点亮规则、完整学习旅程流程、seed 重建、API 安全。

## 📄 文档

- [知识图谱设计](docs/knowledge_map.md)
- [题目格式规范](docs/format_spec.md)
- [功能与操作指南](docs/功能与操作指南.html)

## 📌 说明

- 数据库（`backend/questions.db`）由题库数据源重建，不随仓库分发
- 服务端密钥走环境变量 / DB 存储，不硬编码于代码
