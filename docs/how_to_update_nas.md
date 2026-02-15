---
description: Study Helper Pro 升级指南 (NAS源码安装版)
---
# NAS 代码升级更新流程

本指南为您在 NAS 上，通过拉取源代码并本地构建的方式，进行 Study Helper Pro 的“完全更新”。

请确保您在 `/vol2/1000/work/openclaw/study-helper-pro` 目录下执行。

### 1. 拉取最新代码
将 GitHub 上的最新修改同步到本地：
```bash
git pull origin main
```

### 2. 构建新镜像 (关键步骤!)
由于 Docker 缓存机制，**必须使用 `--no-cache`** 参数，否则代码更新可能不生效！
```bash
sudo docker build --no-cache -t doge2mars/study-helper:latest .
```
> **再次强调**：一定要加 `--no-cache`，否则您可能发现改了代码也没用。

### 3. 删除旧容器
停止当前运行的服务并删除旧容器（放心，您的数据在 `volumes` 里很安全，不会丢失）。
```bash
sudo docker compose down
```

### 4. 启动新容器
使用刚刚构建好的新镜像启动服务。
```bash
sudo docker compose up -d
```

---

### 原理说明
- **为什么要 `build`？** 因为 `docker-compose.yml` 默认只引用镜像名。如果不手动 `build`，Docker 不知道本地代码变了，还会用老镜像启动。
- **为什么要 `down` 再 `up`？** 因为如果不删除旧容器，`up -d` 可能会复用旧容器配置，导致新镜像不生效。
