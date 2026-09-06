# 部署到阿里云 ECS（i-bp11xkn6rmx2nwxj7l8p · 47.114.44.138）

本文档描述从零部署到该 ECS 实例的完整步骤。架构：Docker 单容器，Flask + waitress 监听 :5000，SQLite 与备份通过 `./backend` 绑定卷持久化。

---

## 0. 前置准备（一次性）

### 0.1 安全组放行端口
在阿里云控制台 **云服务器 ECS → 实例 → i-bp11xkn6rmx2nwxj7l8p → 安全组**：

| 方向 | 协议 | 端口范围 | 源/目的 | 说明 |
|---|---|---|---|---|
| 入方向 | TCP | 5000 | 0.0.0.0/0 | Web 访问（首次部署） |
| 入方向 | TCP | 22 | 你的出口 IP | SSH（运维） |

> 生产环境建议把 5000 改为更窄的来源段，或加 nginx + 域名 + HTTPS（参见文末"后续建议"）。

### 0.2 域名解析（可选）
若以后接域名：A 记录 `sql.yourdomain.com → 47.114.44.138`。当前阶段可跳过。

---

## 1. SSH 登录服务器

```bash
ssh root@47.114.44.138
# 首次登录确认 fingerprint；之后按提示输入密码或加载私钥
```

确认是 Ubuntu/Debian 系：

```bash
cat /etc/os-release
```

---

## 2. 安装 Docker 与 Compose 插件

```bash
# Ubuntu 22.04 / Debian 12 一键安装（其他发行版见 https://docs.docker.com/engine/install/）
apt-get update
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 验证
docker --version
docker compose version
```

> 国内服务器如果 Docker 镜像拉取慢，可配镜像加速（如阿里云 `https://<你的id>.mirror.aliyuncs.com`，控制台"容器镜像服务"可拿到）。编辑 `/etc/docker/daemon.json` 后 `systemctl restart docker`。

---

## 3. 部署应用

```bash
# 推荐部署到 /opt，避免误操作覆盖系统目录
mkdir -p /opt/sql && cd /opt/sql

# 方式一：从 GitHub 拉（推荐）
git clone https://github.com/yuhuijuan-43/SQL-adaptive-training-NIDUS-.git .

# 方式二：从本机 rsync（如果有公网/内网可达）—— 在本机执行：
#   rsync -avz --exclude '.git' --exclude 'backend/questions.db*' \
#       --exclude 'backend/backups/' --exclude '.workbuddy/' \
#       ./ root@47.114.44.138:/opt/sql/
```

### 3.1 配置环境变量

```bash
cp .env.example .env
nano .env   # 或 vi .env

# 必填：
#   FLASK_SECRET_KEY  改成 32+ 位随机串，例如：
#     openssl rand -hex 32
#   GITHUB_OAUTH_CLIENT_ID / SECRET  按需填；不启用 GitHub 登录就保持空
# 其余阈值按需调整
```

### 3.2 首次部署：决定是否清空旧题库

- **全新实例**：直接启动，容器首次跑会调 `seeding.py` 自动从 `data/questions.json`（483 题）+ `data/exam_questions.json`（42 题）灌库。
- **从本地迁移**：先在本机停止服务，把本地 `backend/questions.db` 拷上来覆盖 `/opt/sql/backend/questions.db`（容器挂载该路径），再启动。

```bash
# 新建空 backend 目录占位（避免被卷挂载为不存在的目录）
mkdir -p /opt/sql/backend
# 首次部署建议清掉可能存在的旧库占位，让容器自己重建：
rm -f /opt/sql/backend/questions.db /opt/sql/backend/questions.db-wal /opt/sql/backend/questions.db-shm
```

### 3.3 构建并启动

```bash
cd /opt/sql
docker compose up -d --build
# -d = 后台；--build = 重建镜像（首次或 Dockerfile/requirements 变更时需要）
```

观察启动日志：

```bash
docker compose logs -f web
# 看到 "Press Ctrl+C to stop." 且无 traceback 即正常
# Ctrl+C 退出日志跟踪（容器继续运行）
```

### 3.4 验证

```bash
# 容器状态
docker compose ps
# 应显示 sql-web   Up (healthy)

# 本机 curl 测试
curl -sI http://localhost:5000/ | head -3
# 应返回 200 / 30x

# 浏览器访问
# http://47.114.44.138:5000
```

---

## 4. 日常运维

### 4.1 查看日志

```bash
docker compose logs -f web --tail=200   # 实时跟踪
docker compose logs --since 1h web      # 最近一小时
```

日志已在 `docker-compose.yml` 里限制单文件 10MB × 3 个滚动。

### 4.2 重启 / 停机

```bash
docker compose restart web    # 重启容器
docker compose stop          # 停所有
docker compose down          # 停并移除容器（卷保留）
```

### 4.3 更新部署

```bash
cd /opt/sql
git pull                                       # 拉新代码
docker compose up -d --build                   # 重建镜像并滚动重启
# 数据库在 ./backend 挂载卷里，重建镜像不会丢；如 seeding 检测到题数一致不会动
```

### 4.4 备份管理

- 容器每次启动会自动备份 `backend/questions.db` 到 `backend/backups/`，保留最近 20 份（`DB_BACKUP_KEEP` 可调）。建议服务器侧再加一份异地备份：

```bash
# 简易异地备份（用 crontab，每天凌晨跑一次）
crontab -e
0 3 * * * rsync -az --delete /opt/sql/backend/backups/ backup-server:/path/to/sql-backups/$(date +\%Y\%m\%d)/
```

### 4.5 紧急回滚

```bash
cd /opt/sql
ls backend/backups/   # 挑一份
docker compose stop
cp backend/backups/questions-XXXXXXXX-XXXXXX-startup.db backend/questions.db
docker compose up -d
```

---

## 5. ⚠️ 安全收尾（部署后立刻做）

1. **管理员内推码**：`NIDUS_Agent` 已随仓库公开。实例启动后**第一时间**注册首个主管理员（用该默认码），登录后：
   - 进入管理后台 → 同事/内推码 → 删除 `NIDUS_Agent`
   - 新建私密内推码，分发给团队成员

2. **会话密钥**：`FLASK_SECRET_KEY` 没设等于每次重启全员下线；务必填上且定期轮换。

3. **默认密码**：注册管理员后立刻改密；平台用户若用默认测试账号也要改。

4. **IP 直访问是明文**：浏览器到服务器全裸跑，**生产场景强烈建议**域名 + HTTPS（参考"后续建议"）。

---

## 6. 后续建议（未做但建议补的）

| 项 | 收益 | 怎么做 |
|---|---|---|
| 域名 + HTTPS | 加密传输 + GitHub OAuth 回调支持 | Caddy 一键 TLS；或 nginx + certbot |
| 内置数据卷分离 | 避免 `./backend` 卷被运维误删 | 改为 `db-data:/app/backend` 命名卷 |
| 监控告警 | 容器挂了/磁盘满能收到通知 | 阿里云云监控 + `docker compose ps` 脚本 |
| CI/CD | `git push` 自动部署 | GitHub Actions SSH 到 ECS 跑 `docker compose up -d --build` |
| 迁移 PostgreSQL | 多人写 + 大体量不打架 | 当前 SQLite 单写，长驻多人场景建议迁；本项目暂无需 |

---

## 7. 故障排查速查

| 现象 | 排查 |
|---|---|
| 浏览器打不开 | ECS 安全组 → 入方向 5000；`curl localhost:5000` 本机是否能通 |
| 容器一直重启 | `docker compose logs --tail=200 web` 看 traceback |
| 数据库被锁 / busy | SQLite 单写锁，长事务会卡。检查 `system_logs` 看是否有长查询；避免外挂在 NFS |
| 题库少题 | 看 `backend/backups/` 是否被自动备份覆盖；可回滚；先确认 `data/questions.json` 是 483 题 |
| 启动报 "Port 5000 already in use" | `docker compose ps` 看是否有遗留；`netstat -tlnp | grep 5000` 查宿主占用 |
| 想清空从零开始 | `docker compose down`，`rm -rf backend/questions.db* backend/backups/*`，再 `docker compose up -d --build` |

---

*详细架构与运维设计见 `交接文档/交接文档-开发者.md` §9、§13。*