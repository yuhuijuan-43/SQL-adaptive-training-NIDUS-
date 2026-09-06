# SQL 自适应训练平台 — 部署镜像
# 基于 Python 3.13 slim，serving by waitress（生产级 WSGI）
FROM python:3.13-slim

# bcrypt / cffi / lxml 在 slim 上需要 libffi 与构建工具链；保留最小依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        libffi8 \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

WORKDIR /app

# 单独 COPY requirements 利用 Docker 缓存（依赖不变时不重装）
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt

# 拷代码与题库数据（questions.json / exam_questions.json 是题库源，库内 DB 由 seeding.py 重建）
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY data/ /app/data/

WORKDIR /app/backend

# run.py 默认 0.0.0.0:5000，由 docker-compose 映射端口
EXPOSE 5000

# 健康检查（容器启动后 waitress 起来即可访问首页）
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/', timeout=5).read()" || exit 1

CMD ["python", "run.py"]