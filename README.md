# SQL 自适应训练平台

基于知识图谱点亮机制与自适应出题算法的 SQL 练习平台。题库共 515 题，覆盖基础语法、连接查询、子查询、聚合、窗口函数等常见知识点，练习进度通过知识图谱可视化呈现。

## 功能

- 知识图谱三级点亮：知识点按叶 / 枝 / 根组织，答对题目点亮节点，进度可视化
- 自适应出题：每轮按「选择题 ×3 + 填空题 ×2」组织 5 题序列，跨练习池累计答对即点亮节点（幂等落库）
- SQL 判题：SQL 规范化、只读单语句校验、沙箱执行、结果集比对
- 题库：515 题（310 道经典 SQL 题及填空题变体 + 58 道静态选择题），均带知识点标签
- 学习闭环：水平诊断 → 自适应练习 → 错题集 → 图谱点亮 → 进阶选题
- 账号体系：注册 / 登录 / 会话管理 / 管理员面板（统一密钥 + 邀请码）
- 前端无框架依赖，图表库本地化，支持离线部署
- 一键启动：自动探测并安装 Python、安装依赖、启动服务并打开浏览器

## 技术栈

- 后端：Python / Flask / SQLite
- 前端：原生 HTML / CSS / JS，ECharts（本地化资源）
- 判题：自研 SQL 规范化 + 沙箱执行比对
- 测试：pytest（115 用例）

## 快速开始

### Windows 一键启动

```bat
start_server.bat
```

脚本自动完成：探测可用 Python（缺失时自动下载安装）→ 安装依赖 → 启动服务 → 打开浏览器 `http://localhost:5000`

### 手动启动

```bash
# 安装依赖
pip install -r backend/requirements.txt

# 初始化题库
python backend/seeding.py

# 启动服务
python backend/run.py
# 访问 http://localhost:5000
```

## 目录结构

```
├── backend/               # Flask 后端
│   ├── app.py             # 路由 / API / 鉴权
│   ├── engine.py          # 自适应出题引擎（图谱点亮）
│   ├── sql_judge.py       # SQL 判题引擎
│   ├── seeding.py         # 题库种子重建
│   ├── scraper.py         # 题库抓取工具
│   └── tests/             # pytest 测试套件（115 用例）
├── frontend/              # 前端页面（原生 HTML/CSS/JS）
│   ├── index.html         # 首页
│   ├── knowledge_map.html # 知识图谱点亮视图
│   ├── diagnostic.html    # 水平诊断
│   └── admin*.html        # 管理面板
├── docs/                  # 设计文档与规范
├── questions.json         # 题库数据源（515 题）
└── start_server.bat       # 一键启动脚本
```

## 测试

```bash
cd backend
pytest -v        # 115 个用例全绿
```

覆盖：SQL 判题、图谱点亮规则、学习流程、种子重建、API 安全。

## 文档

- [知识图谱设计](docs/knowledge_map.md)
- [题目格式规范](docs/format_spec.md)

## 说明

- 数据库（`backend/questions.db`）由题库数据源重建，不随仓库分发
- 服务端密钥走环境变量 / 数据库存储，不硬编码于代码
