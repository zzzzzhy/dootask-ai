# 使用 Python 3.11 作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PORT=5001
ENV PYTHONUNBUFFERED=1

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY requirements.txt .
COPY main.py .
COPY test_main.py .
COPY README.md .

# 安装 Python 依赖和 Gunicorn
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# 暴露端口
EXPOSE $PORT

# 使用 Gunicorn 启动应用
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "4", "--timeout", "120", "main:app"] 