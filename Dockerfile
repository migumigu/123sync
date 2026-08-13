# 使用 Docker Hub 官方 Python 3.12 基础镜像
# 官方镜像原生支持 linux/amd64 + linux/arm64 多架构
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 设置 Python 不缓冲输出
ENV PYTHONUNBUFFERED=1

# 设置 pip 镜像源为阿里云（构建时加速，不影响运行时）
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_TRUSTED_HOST=mirrors.aliyun.com

# 先复制 requirements.txt，仅当依赖文件变化时才重新安装
COPY requirements.txt /app/

# 从 requirements.txt 安装所有依赖
RUN pip install -U -r requirements.txt --no-cache-dir

# 复制当前目录的其他内容到容器的 /app 目录下
COPY . /app/

# 创建运行时目录
RUN mkdir -p upload delete conf

# 运行 Python 脚本
CMD ["python", "123sync.py"]
