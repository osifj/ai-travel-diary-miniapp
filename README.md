# AI 游玩日志生成器

上传 iPhone 旅行照片 → 自动读取 EXIF/GPS → AI 识别场景内容 → 生成中文游玩日记。

**可直接用手机浏览器打开**，无需安装 App。也支持微信小程序（[miniapp 分支](https://github.com/osifj/ai-travel-diary-miniapp/tree/miniapp)）。

---

## ✨ 核心功能

| 功能 | 说明 |
|------|------|
| 📷 智能照片解析 | 自动读取拍摄时间、GPS 经纬度、设备型号 |
| 🤖 AI 场景识别 | 识别场景类型、活动、美食、物体、地标、氛围 |
| 📝 自动生成游记 | 按日期/城市聚合，生成自然流畅的中文游玩日志 |
| 💬 AI 对话编辑 | 生成后可和 AI 聊天微调日记内容（SSE 流式） |
| 🗺️ 地点解析 | GPS → 国家/城市/区域/地标 |
| 🔒 隐私保护 | 原图 GPS/EXIF 不发送给 AI，仅发送去元数据的压缩图 |
| 🌙 暗色模式 | 自动适配系统主题 |

---

## 🏗️ 技术架构

```
┌──────────────────────┐     ┌─────────────────────────────┐
│   网页前端 (SPA)       │────▶│   FastAPI 后端 (Python)      │
│                      │     │                             │
│  • 照片选择/上传      │     │  • EXIF 解析 (exiftool)     │
│  • 分析进度          │     │  • 图片压缩 + 去 EXIF       │
│  • AI 对话 (SSE)     │     │  • MiMo / DeepSeek API      │
│  • 日记展示/编辑      │     │  • 地点解析 (geocoder)       │
│  • 地图打点 (Leaflet) │     │  • 天气查询                  │
│                      │     │  • 日记生成                  │
└──────────────────────┘     └──────────┬──────────────────┘
                                        │
                              ┌─────────▼──────────────────┐
                              │  SQLite 数据库              │
                              │  • photos 表               │
                              │  • diaries 表              │
                              └────────────────────────────┘
```

---

## 🚀 快速开始

### 1. 启动后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # 编辑 .env 填入 API Key
python app.py                   # 或: uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### 2. 打开浏览器

```
http://127.0.0.1:8000
```

后端自动 serve 网页前端，无需额外配置。

### 3. 配置 AI

编辑 `backend/.env`:

```env
# MiMo（图片识别）
MIMO_API_KEY=your_key
MIMO_BASE_URL=https://your-mimo-endpoint/v1
MIMO_MODEL=mimo-v2.5

# DeepSeek（日记生成 + 对话）
DEEPSEEK_API_KEY=your_key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

未配置 API Key 时自动使用 **Mock 模式**，方便开发调试。

---

## 🌍 公网访问（手机也能用）

让朋友用手机浏览器打开你的 AI 游玩日志系统。

### 一键启动

双击项目根目录的 `start_all.command`，自动启动后端 + ngrok + 防睡眠。

启动后终端显示：

```
🌍 公网: https://xxxx.ngrok-free.app
📱 把公网地址发给朋友，手机浏览器打开即可使用
```

### 手动启动

```bash
# 终端 1：后端
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000

# 终端 2：ngrok
ngrok http 8000

# 终端 3（可选）：防 Mac 睡眠
caffeinate -dimsu
```

---

## 📁 项目结构

```
ai-travel-diary-miniapp/
├── backend/                    # FastAPI 后端
│   ├── app.py                  # 入口，serve 网页 + API
│   ├── requirements.txt
│   ├── .env.example
│   ├── api/                    # 接口层
│   │   ├── upload.py           # 图片上传
│   │   ├── analyze.py          # AI 分析
│   │   └── diary.py            # 日记 CRUD + SSE 对话
│   ├── services/               # 业务逻辑
│   │   ├── exif_reader.py      # EXIF 解析 (exiftool + Pillow)
│   │   ├── image_preprocess.py # 压缩 + 去元数据
│   │   ├── mimo_client.py      # MiMo 视觉识别
│   │   ├── deepseek_client.py  # DeepSeek 对话/生成
│   │   ├── geocoder.py         # 地点解析
│   │   ├── weather_service.py  # 天气查询
│   │   └── diary_generator.py  # 日记生成
│   ├── models/
│   │   └── database.py         # SQLite
│   ├── web/
│   │   └── index.html          # 网页前端 (SPA)
│   └── tests/
├── miniapp/                    # 微信小程序（历史版本）
├── docs/                       # 设计文档
└── start_all.command           # 一键启动脚本
```

---

## 🔌 API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 网页前端 |
| `GET` | `/health` | 健康检查 |
| `POST` | `/upload` | 上传单张图片 |
| `POST` | `/upload/batch` | 批量上传 (≤20张) |
| `POST` | `/analyze` | 批量分析照片 |
| `POST` | `/diary/generate` | 生成游玩日志 |
| `GET` | `/diary/{id}` | 获取日志详情 |
| `GET` | `/diary/` | 日志列表 |
| `POST` | `/diary/chat` | AI 对话编辑 (SSE 流式) |

---

## 🔒 隐私说明

- 原图仅存储在服务器本地
- 发送给 AI 的图片已压缩至 1024px 且去除所有 EXIF
- API Key 仅存储在服务端 `.env`
- 不进行人脸身份识别

---

## 📱 分支说明

| 分支 | 说明 |
|------|------|
| `main` | 网页版（当前主线） |
| [`miniapp`](https://github.com/osifj/ai-travel-diary-miniapp/tree/miniapp) | 微信小程序版（已归档） |

---

## 📄 License

MIT
