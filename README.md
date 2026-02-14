# Study Helper Pro (SH-Pro)

[![Version](https://img.shields.io/badge/version-1.2-blue.svg)](https://github.com/doge2mars/StudyHelper)
[![Docker](https://img.shields.io/badge/Docker-Ready-brightgreen.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Study Helper Pro** 是一款专为高效学习设计的全栈错题管理与在线练习平台。它从最初的单机版升级而来，现在已经进化为支持多用户、权限管理、试卷分发以及跨设备访问的强大教学辅助工具。

---

## ✨ 核心特性

### 1. 多角色用户系统 (RBAC)
- **管理员 (Super Admin)**：
  - **用户管理**：可创建、编辑和删除普通用户账号。
  - **试卷分发**：独有的“分发”功能，可以将整理好的试卷一键推送给指定用户，实现教学资源同步。
  - **全量权限**：管理全库学科、试卷及配置。
- **普通用户 (User)**：
  - **独立题库**：每个用户拥有私有的学科空间和题库，数据完全隔离。
  - **一键入库**：可以查看管理员分发的试卷，并将感兴趣的题目一键克隆到自己的私人题库中。
  - **个性化练习**：自定义练习范围，系统自动记录错题并支持重做。

### 2. 精准的试卷切分与导入
- **PDF 智能切片**：支持上传 PDF 试卷并进行可视化切分，快速提取题目。
- **HEIC/图片支持**：兼容多种图片格式，满足移动端拍照上传需求。
- **ZIP 备份与分享**：支持一键导出完整的试卷包（含题目数据与图片），方便离线保存或好友分享。

### 3. 先进的学习体验
- **响应式 UI**：采用现代化的深色/浅色模式切换，适配手机、平板及 PC。
- **错题追踪**：后台自动统计每道题的错误次数，通过“标记难题”和“错题重做”实现精准复习。
- **流畅动画**：基于 Vanilla CSS 的微动效，带来丝滑的交互体验。

---

## 🚀 快速部署 (小白友好指南)

推荐使用 Docker 进行一键部署。无论你是在 Linux 服务器、群晖/威联通 NAS，还是自己的电脑上，只需要按照以下三步操作即可。

### 1. 安装基础环境 (仅需一次)
如果你的电脑或服务器还没有 Docker，请先安装：
- **Windows/Mac**: 安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)。
- **Linux/NAS**: 参考官方教程安装 `docker` 和 `docker-compose`。

### 2. 获取项目代码
打开终端 (Terminal / PowerShell)，运行以下命令：
```bash
# 点击右上角绿色的 "Code" 按钮复制地址，或者直接运行这行：
git clone https://github.com/doge2mars/StudyHelper.git
cd StudyHelper
```

### 3. 一键启动
在项目目录下直接运行：
```bash
docker compose up -d --build
```

**部署成功后：**
- 访问：`http://localhost:8866` (如果是远程服务器，请将 localhost 换成服务器 IP)。
- **注意**: 如果 8866 端口被占用了，请打开 `docker-compose.yml` 文件，将 `8866:8000` 左边的 `8866` 改成其他数字。

---

## 🔐 初始凭据
| 角色 | 用户名 | 初始密码 |
| :--- | :--- | :--- |
| **超级管理员** | `admin` | `admin123` |

> [!TIP]
> **安全建议**: 首次登录后，请点击导航栏最右侧的按钮进入设置页面，立即修改初始密码。

*注意：登录后请务必前往个人设置页面修改初始密码。*

---

## 🛠 技术栈
- **后端**: FastAPI (Python 3.11)
- **数据库**: SQLite (轻量级、高可靠)
- **前端**: Jinja2 Templates + Vanilla JS + CSS (无重型框架依赖)
- **安全**: JWT + PBKDF2 密码哈希
- **部署**: Docker + Docker Compose

---

## 📝 开发者说明
本项目的代码库遵循 **[doge2mars/StudyHelper](https://github.com/doge2mars/StudyHelper)** 规范。欢迎在 Issues 中提出改进建议或提交 Pull Request。

---
*Created with ❤️ by Antigravity.*
