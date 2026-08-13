#!/bin/bash
set -e

# 一键多架构构建并推送镜像到 DockerHub 脚本
#
# 用法:
#   ./build_and_push.sh              # 从 VERSION 文件读取版本号
#   ./build_and_push.sh 1.0.2        # 命令行指定版本号
#
# 前置条件:
#   1. 本机已安装 Docker 并启用 buildx（Docker Desktop 默认已启用）
#   2. 已通过 `docker login` 登录 DockerHub
#      或设置环境变量 DOCKER_HUB_USERNAME（脚本会自动登录）
#
# 多架构支持: linux/amd64 + linux/arm64

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${BLUE}[STEP]${NC} $1"; }

# DockerHub 配置（可通过环境变量覆盖）
DOCKER_HUB_USERNAME="${DOCKER_HUB_USERNAME:-migumigu}"
IMAGE_NAME="123sync"
PLATFORMS="linux/amd64,linux/arm64"

FULL_IMAGE_NAME="$DOCKER_HUB_USERNAME/$IMAGE_NAME"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  123sync 多架构镜像构建并推送到 DockerHub${NC}"
echo -e "${GREEN}========================================${NC}\n"

# 检查 Docker
if ! command -v docker &> /dev/null; then
    log_error "Docker 未安装"
    log_warn "请先安装 Docker，然后重新运行此脚本"
    exit 1
fi
log_info "Docker 已安装: $(docker --version)"

# 检查 buildx
if ! docker buildx version &> /dev/null; then
    log_error "Docker buildx 不可用"
    log_warn "请升级到 Docker Desktop 或安装 buildx 插件"
    exit 1
fi
log_info "Docker buildx 可用: $(docker buildx version)"

# 确保存在可用的多架构 builder
BUILDER_NAME="123sync-multiarch"
if ! docker buildx inspect "$BUILDER_NAME" &> /dev/null; then
    log_step "创建多架构 builder: $BUILDER_NAME"
    docker buildx create --name "$BUILDER_NAME" --use --driver docker-container --bootstrap
else
    docker buildx use "$BUILDER_NAME"
fi
log_info "使用 builder: $BUILDER_NAME"

# 读取版本号
VERSION_TAG=""
if [ $# -gt 0 ]; then
    VERSION_TAG="$1"
    log_info "命令行指定的版本号: $VERSION_TAG"
elif [ -f "VERSION" ]; then
    VERSION_TAG=$(grep -E "^VERSION=" VERSION | head -n 1 | cut -d'=' -f2 | tr -d ' \r\n')
    if [ -n "$VERSION_TAG" ]; then
        log_info "从 VERSION 文件读取的版本号: $VERSION_TAG"
    fi
fi

if [ -z "$VERSION_TAG" ]; then
    log_error "未能获取版本号"
    log_warn "用法: $0 <版本号>  或在 VERSION 文件中写入 VERSION=x.y.z"
    exit 1
fi

# 检查 Dockerfile
if [ ! -f "Dockerfile" ]; then
    log_error "当前目录不存在 Dockerfile"
    exit 1
fi

# 登录 DockerHub（若未登录则尝试交互式登录）
if ! docker info 2>/dev/null | grep -q "Username:"; then
    log_step "未检测到 DockerHub 登录态，开始登录..."
    docker login
fi

# 构建并推送（多架构 manifest 自动一并推送）
log_step "开始构建并推送多架构镜像..."
log_info "目标平台: $PLATFORMS"
log_info "镜像标签: $FULL_IMAGE_NAME:$VERSION_TAG  +  $FULL_IMAGE_NAME:latest"

docker buildx build \
    --platform "$PLATFORMS" \
    -t "$FULL_IMAGE_NAME:$VERSION_TAG" \
    -t "$FULL_IMAGE_NAME:latest" \
    --push \
    .

if [ $? -ne 0 ]; then
    log_error "镜像构建/推送失败"
    exit 1
fi

# 完成
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}✅ 多架构镜像构建并推送成功！${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "${YELLOW}镜像名:${NC}    $FULL_IMAGE_NAME"
echo -e "${YELLOW}版本标签:${NC}   $VERSION_TAG"
echo -e "${YELLOW}latest标签:${NC} latest"
echo -e "${YELLOW}目标平台:${NC}   $PLATFORMS"
echo -e "${GREEN}========================================${NC}"

echo -e "\n${YELLOW}后续操作提示:${NC}"
echo -e "${YELLOW}1. 拉取镜像: ${NC}docker pull $FULL_IMAGE_NAME:$VERSION_TAG"
echo -e "${YELLOW}2. 运行容器: ${NC}docker run -d -p 12300:5000 -v ./conf:/app/conf -v ./data:/data $FULL_IMAGE_NAME:$VERSION_TAG"
echo -e "${YELLOW}3. 查看架构: ${NC}docker manifest inspect $FULL_IMAGE_NAME:$VERSION_TAG"
