# API 端点列表

| 端点 | 方法 | 作用 |
|---|---|---|
| `/` | GET | 首页 `index.html` |
| `/index.html` | GET | 首页 |
| `/login` | GET | 登录页 `login.html` |
| `/index_ngrok.html` | GET | ngrok 版首页 |
| `/login_ngrok.html` | GET | ngrok 版登录页 |
| `/admin` | GET | 管理后台 `admin.html` |
| `/api/diagnostic` | GET | 随机抽取3题（易/中/难各一）用于摸底小测 |
| `/api/diagnostic/complete` | POST | 提交摸底小测结果，计算正确率并存储 |
| `/api/diagnostic/result` | GET | 查询摸底小测结果（传 `session_id`） |
| `/api/questions` | GET | 获取题目列表，支持 `?category=` 和 `?difficulty=` 过滤 |
| `/api/questions/<qid>` | GET | 获取单题详情 |
| `/api/submit` | POST | 提交答案，判断对错，记录答题历史 |
| `/api/practice/derive` | POST | 选择题 → 填空题衍生（举一反三） |
| `/api/practice/recommend` | POST | 衍生题答完后推荐同知识点题目 |
| `/api/graph` | GET | 获取知识图谱（节点+边） |
| `/api/journey/start` | POST | 启动自适应模式，基于摸底结果初始化学习路径 |
| `/api/journey/next` | POST | 自适应模式下一题，提交当前答案并返回下一题 |
| `/api/journey/status` | POST | 获取当前自适应进度：状态、图谱、掌握度、解锁节点、正确率 |
| `/api/journey/toggle_deep` | POST | 切换自适应模式的深度模式 |
| `/api/login` | POST | 用户登录/注册，返回 `session_id` |
| `/api/progress/<session_id>` | GET | 查询用户的答题历史与正确率 |
| `/api/admin/stats` | GET | 管理后台统计数据 |
| `/api/admin/users` | GET | 管理后台用户列表 |
