# 123网盘同步工具


## 1. 项目简介
1. 该工具支持优先调用网盘秒传接口进行秒传。
2. 可以设置大于多少M的文件，只做秒传。支持定时尝试。
3. 小于设置大小的文件，秒传失败后会正常上传。实现刮削的封面、nfo、小视频文件等的上传。
4. 秒传成功的文件，会自动删除本地文件。对于刮削过的目录，每次同步完后，会检测一遍，删除空文件夹防止本地残留大量空文件夹。
5. 支持Cron表达式设置定时监测
6. 支持普通账号登录，或开发者账号登录。2者填一个即可
7. 支持指定多个路径同步，解决有多个硬盘多个目录需同步的需求。
8. 提供现代化的web配置界面，支持配置管理和强制同步功能
9. 兼容桌面和移动设备访问
10. 支持配置热更新，无需重启服务即可生效（除账号配置外）
11. 自动适配123云盘域名迁移（123pan.com → 123912.com），无需手动修改依赖库
12. 兼容多种部署方式（直接运行 / Docker / gunicorn / WSGI），定时调度器随模块加载自愈启动


## 2. 核心功能
1. **秒传机制**：优先调用123网盘秒传接口（非openapi，规避openapi仅支持10G以下文件的限制），直接基于文件哈希信息完成转存，无需实际上传文件内容
2. **智能重试**：当秒传失败时，自动休眠一段时间后重新尝试秒传，提高转存成功率
3. **带宽节省**：通过避免用户执行文件首传，显著减少对本地上传带宽的占用
4. **Web配置界面**：提供现代化的响应式web界面，支持配置管理和查看
5. **强制同步功能**：支持手动触发立即同步，可通过 `force_upload_large_file` 配置项控制大文件秒传失败后是否转为分片上传
6. **配置热更新**：通用配置和同步规则修改后自动生效，无需重启服务
7. **独立保存按钮**：三个配置部分（同步规则、通用配置、账号配置）独立保存，提高操作便捷性
8. **域名迁移适配**：运行时自动将 p123client 的请求重定向至新域名 123912.com，无需等待依赖库更新
9. **调度器自愈启动**：模块加载时自动启动定时同步线程，兼容 gunicorn / WSGI 等非 `__main__` 启动方式


## 3. 部署方法

镜像已发布到 DockerHub，支持 `linux/amd64` + `linux/arm64` 双架构，树莓派 / 群晖 / x86 服务器均可直接拉取。

### 3.1 使用 Docker Compose 部署（推荐）

```yaml
version: "3"
services:
  123sync:
    image: migumigu/123sync:latest
    container_name: 123sync
    environment:
      - PUID=1000
      - PGID=100
      - TZ=Asia/Shanghai
    ports:
      - "12300:5000"
    volumes:
      # 配置目录（持久化 settings.ini）
      - ./conf:/app/conf
      # 中转目录（MP 转移文件的目标目录，按 settings.ini 中的规则映射）
      - ./data:/data
    command: ["python", "123sync.py", "--web"]
    restart: always
networks: {}
```

### 3.2 使用 docker run 部署

```bash
docker run -d \
  --name 123sync \
  -p 12300:5000 \
  -v ./conf:/app/conf \
  -v ./data:/data \
  -e PUID=1000 \
  -e PGID=100 \
  -e TZ=Asia/Shanghai \
  migumigu/123sync:latest
```

### 3.3 本地构建并推送镜像（开发者）

本项目已配置多架构构建与 GitHub Actions 自动发布流水线。

#### 方式一：CI 自动发布（推荐）

1. 在 GitHub 仓库 `Settings → Secrets and variables → Actions` 中添加两个 Secret：
   - `DOCKER_HUB_USERNAME` — DockerHub 用户名
   - `DOCKER_HUB_ACCESS_TOKEN` — DockerHub Access Token（不是登录密码）
2. 修改 `VERSION` 文件中的版本号
3. 推送到 `main` 分支，GitHub Actions 会自动构建 amd64+arm64 双架构镜像并推送至 DockerHub

#### 方式二：本地手动构建推送

```bash
# 先 docker login 登录 DockerHub
./build_and_push.sh              # 从 VERSION 文件读取版本号
./build_and_push.sh 1.0.2        # 手动指定版本号
```

> 本地构建依赖 Docker buildx（Docker Desktop 默认已启用）。


## 4. 使用方法

### 4.1 访问Web配置界面

1. 部署完成后，程序启动时会自动探测本机局域网 IP 并打印访问地址
2. Docker 部署时，使用 `宿主机IP + 端口映射` 访问（如 `http://宿主机IP:12300`）
3. 本地直接运行时，访问 `http://本机IP:5000` 即可进入配置界面
4. 界面支持桌面和移动设备访问

### 4.2 配置管理

1. **同步规则配置**：
   - 可以添加、删除、修改同步规则
   - 规则格式：本地路径, 网盘路径
   - 支持多个规则配置

2. **通用配置**：
   - 设置大文件阈值（MB）
   - 配置同名文件处理策略
   - 设置Cron表达式定时同步频率
   - 设置强制同步时大文件秒传失败是否转为分片上传

3. **账号配置**：
   - 支持普通账号（手机号/邮箱+密码）
   - 支持开发者账号（client_id+client_secret）
   - 账号配置修改后需要重启服务才能生效

### 4.3 立即强制同步

1. 在Web界面点击「立即强制同步」按钮
2. 系统会立即执行同步任务
3. 强制同步模式下：
   - 大文件秒传失败后，根据 `force_upload_large_file` 配置决定行为：关闭则跳过等待下次同步，开启则转为分片上传
   - 定时同步时间到达时，如果强制同步正在运行，则会跳过此次定时同步


## 5. 配置文件说明

### 5.1 配置文件路径

```
conf/settings.ini
```

### 5.2 配置项说明

```ini
[General]
; 大文件阈值（MB），大于此值的文件只尝试秒传
seconds_upload_min_size = 500

; 处理同名文件策略: 0=跳过, 1=保留两者, 2=替换, 3=保留较大的文件
duplicate_handling = 2

; Cron表达式，配置同步频率
; 每小时执行一次,自行修改
cron_expression = 0 * * * *

; 强制同步时，大文件秒传失败是否转为分片上传
; false = 秒传失败直接跳过（默认，节省带宽）
; true  = 仅在强制同步模式下，秒传失败后转为分片上传
force_upload_large_file = false

[Account]
; 开发者账号用client_id和client_secret，普通账号用passport和password
passport = 
password = 
client_id = 
client_secret = 

[SyncRules]
; 规则格式: 本地路径, 网盘路径
rule1 = upload/AAA, 我的备份/AAA
rule2 = upload/BBB, strm/BBB
```


## 6. 致谢
- ptto123项目作者，及p123client库，易木
