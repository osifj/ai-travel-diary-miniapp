# AI 游玩日志生成系统

基于**微信小程序**与**小米 MiMo 多模态模型**的智能游玩日志生成系统。

上传 iPhone 旅行照片 → 自动读取 EXIF/GPS → AI 识别场景内容 → 生成中文游玩日记。

---

## ✨ 核心功能

| 功能 | 说明 |
|------|------|
| 📷 智能照片解析 | 自动读取拍摄时间、GPS 经纬度、设备型号 |
| 🤖 AI 场景识别 | 识别场景类型、活动、美食、物体、地标、氛围 |
| 📝 自动生成游记 | 按日期/城市聚合，生成自然流畅的中文游玩日志 |
| 🗺️ 地点解析 | GPS → 国家/城市/区域/地标 (支持多 API 切换) |
| 🔒 隐私保护 | 原图 GPS/EXIF 不发送给 AI，仅发送去元数据的压缩图 |

---

## 🏗️ 技术架构

```
┌──────────────────────┐     ┌─────────────────────────────┐
│   微信小程序 (原生)    │────▶│   FastAPI 后端 (Python)      │
│                      │     │                             │
│  • 照片选择/上传      │     │  • EXIF 解析 (exiftool)     │
│  • 分析进度          │     │  • 图片压缩 + 去 EXIF       │
│  • 日志展示          │     │  • MiMo API 调用             │
│  • 地图打点 (可选)    │     │  • 地点解析 (geocoder)       │
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
cp .env.example .env            # 编辑 .env 填入 MiMo API Key
python app.py                   # 或: uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

验证:
```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","service":"AI 游玩日志生成系统","version":"0.1.0"}
```

### 2. 配置 MiMo API

编辑 `backend/.env`:

```env
MIMO_API_KEY=your_real_api_key
MIMO_BASE_URL=https://your-mimo-endpoint/v1
MIMO_MODEL=mimo-v2.5
```

如果暂未配置 API Key，系统会自动使用 **Mock 模式** 返回模拟数据，方便前端开发调试。

### 3. 打开微信开发者工具

1. 导入项目目录 `miniapp/`
2. 在「详情 → 本地设置」勾选 **不校验合法域名**
3. 编译运行

### 4. 测试流程

```
首页 → 选择照片 → 上传 → AI 分析 → 生成日志 → 查看结果
```

---

## 📁 项目结构

```
ai-travel-diary-miniapp/
├── backend/                    # FastAPI 后端
│   ├── app.py                  # 应用入口
│   ├── requirements.txt
│   ├── .env.example
│   ├── api/                    # 接口层
│   │   ├── upload.py           # POST /upload
│   │   ├── analyze.py          # POST /analyze
│   │   └── diary.py            # POST /diary/generate, GET /diary/{id}
│   ├── services/               # 业务逻辑
│   │   ├── exif_reader.py      # EXIF 解析 (exiftool + Pillow)
│   │   ├── image_preprocess.py # 图片压缩 + 去元数据
│   │   ├── mimo_client.py      # MiMo API 客户端
│   │   ├── geocoder.py         # 地点解析 (mock / nominatim / 腾讯)
│   │   └── diary_generator.py  # 游玩日志生成
│   ├── models/
│   │   └── database.py         # SQLite 数据库模型
│   └── tests/
├── miniapp/                    # 微信小程序
│   ├── app.js / .json / .wxss
│   ├── pages/
│   │   ├── index/              # 首页
│   │   ├── upload/             # 照片上传
│   │   ├── analyzing/          # 分析进度
│   │   ├── result/             # 日志结果
│   │   └── map/                # 地图 (占位)
│   └── utils/
│       └── request.js          # HTTP 请求工具
└── docs/                       # 文档
    ├── project_design.md
    ├── api_design.md
    └── demo_script.md
```

---

## 🔌 API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `GET` | `/` | API 信息 |
| `POST` | `/upload` | 上传单张图片 |
| `POST` | `/upload/batch` | 批量上传 (≤20张) |
| `POST` | `/analyze` | 批量分析照片 |
| `POST` | `/diary/generate` | 生成游玩日志 |
| `GET` | `/diary/{id}` | 获取日志详情 |
| `GET` | `/diary/` | 日志列表 |

详细文档: [docs/api_design.md](docs/api_design.md)

---

## ⚙️ 配置说明

### EXIF 解析

- 优先使用系统 `exiftool` (对 iPhone HEIC 照片更稳定)
- 如不可用，自动回退到 Pillow
- HEIC 支持需安装 `pillow-heif` 或系统 `libheif`

### 地点解析

在 `.env` 中切换:

```env
GEOCODER_PROVIDER=mock        # mock / nominatim / tencent
GEOCODER_API_KEY=             # 使用真实 API 时需要
```

支持: OpenStreetMap Nominatim (免费) / 腾讯位置服务 / 高德地图 / 百度地图

### 真机调试

微信小程序真机调试需要 **HTTPS 后端**。推荐方案:
- 使用内网穿透工具 (ngrok, frp) 暴露本地 8000 端口
- 或部署到云服务器并配置 HTTPS

---

## 🌍 公网访问（朋友手机也能用）

让不在同一 Wi-Fi 的朋友也能使用你的 AI 游玩日志系统。Mac 做服务器，ngrok 做公网穿透。

### 适用场景

- 几个朋友/测试用户想体验
- Mac 可以一直开着
- 暂时不想买云服务器

### 启动步骤

**方式一：一键启动（推荐）**

双击项目根目录的 `start_all.command`，自动启动后端 + ngrok 公网穿透 + 防 Mac 睡眠。

```bash
# 双击即可，或者终端执行:
./start_all.command
```

启动成功后终端会显示公网地址，例如：

```
🌍 公网: https://xxxx.ngrok-free.app
📱 把公网地址发给朋友，手机浏览器打开即可使用
```

**方式二：手动启动**

```bash
# 终端 1：启动后端
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000

# 终端 2：启动 ngrok（需先 brew install ngrok）
ngrok http 8000

# 终端 3（可选）：防止 Mac 睡眠
caffeinate -dimsu
```

### 验证

```bash
# 本地
curl http://127.0.0.1:8000/health

# 公网（替换成你的 ngrok 地址）
curl https://xxxx.ngrok-free.app/health

# 两个都返回 {"status":"ok"} 即成功
```

### 注意事项

- ngrok 免费版每次重启域名会变，需把新地址发给朋友
- 如需固定域名：注册 ngrok 免费账号 → `ngrok config add-authtoken <token>` → 获得 `xxx.ngrok-free.app` 固定地址
- Mac 合上盖子可能睡眠 → 用 `caffeinate -dimsu` 或系统设置关闭睡眠
- 正式上线需要自己的域名 + HTTPS 服务器

---

## 🔒 隐私说明

- 原图 (含 EXIF/GPS 元数据) **仅存储在服务器本地**
- 发送给 AI 的图片 **已压缩且去除所有 EXIF 信息**
- API Key **仅存储在服务端 `.env` 文件**，不暴露给前端
- AI 分析不进行人脸身份识别

---

## 🗺️ 路线图

- [x] Phase 1: 后端基础 (上传 + EXIF)
- [x] Phase 2: AI 图片识别
- [x] Phase 3: 游玩日志生成
- [x] Phase 4: 微信小程序
- [ ] HEIC 格式完整支持
- [ ] 地图打点 + 旅行轨迹
- [ ] 用户系统 + 云存储
- [ ] 年度旅行报告
- [ ] 社交分享

---

## 📄 License

MIT
