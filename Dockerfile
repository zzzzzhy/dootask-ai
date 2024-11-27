# 使用 Python 3.11 作为基础镜像
FROM python:3.11-slim as builder

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# 第二阶段：运行环境
FROM python:3.11-slim

WORKDIR /app

# 复制已安装的依赖
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/gunicorn /usr/local/bin/gunicorn

# 设置环境变量
ENV PORT=5001
ENV WORKERS=4
ENV TIMEOUT=120
ENV PYTHONUNBUFFERED=1

# 复制项目文件
COPY main.py .
COPY request.py .
COPY utils.py .
COPY static/ static/
COPY requirements.txt .
COPY README.md .
COPY LICENSE .

# 创建非 root 用户
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE $PORT

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s \
    CMD curl -f http://localhost:$PORT/ || exit 1

# 使用 Gunicorn 启动应用
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers $WORKERS --timeout $TIMEOUT --access-logfile - --error-logfile - main:app"]