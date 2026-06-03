# 交接文档 — AI 游玩日志生成系统

## 当前状态

**网页版（main 分支）** 为当前主力开发线。  
微信小程序版已归档至 `miniapp` 分支。

**运行方式**：启动后端后浏览器打开 `http://127.0.0.1:8000` 即可使用。

---

## 项目位置

```
/Users/dep/Desktop/ai-travel-diary-miniapp/
```

GitHub: `https://github.com/osifj/ai-travel-diary-miniapp`

---

## 项目结构

```
ai-travel-diary-miniapp/
├── README.md
├── HANDOFF.md
├── start_all.command            # 一键启动（后端 + ngrok + 防睡眠）
├── .gitignore
│
├── backend/                     # Python FastAPI
│   ├── app.py                   # 入口，serve 网页 + API
│   ├── requirements.txt
│   ├── .env / .env.example
│   ├── api/
│   │   ├── upload.py            # 图片上传
│   │   ├── analyze.py           # AI 分析
│   │   └── diary.py             # 日记 CRUD + SSE 对话
│   ├── services/
│   │   ├── exif_reader.py       # exiftool + Pillow
│   │   ├── image_preprocess.py  # 压缩 1024px + 去 EXIF
│   │   ├── mimo_client.py       # MiMo 视觉识别
│   │   ├── deepseek_client.py   # DeepSeek 日记生成/对话 (SSE)
│   │   ├── geocoder.py          # Mock / Nominatim / 腾讯
│   │   ├── weather_service.py   # 天气查询
│   │   └── diary_generator.py   # 日记模板生成
│   ├── models/
│   │   └── database.py          # SQLite: photos + diaries
│   ├── web/
│   │   └── index.html           # 网页前端 SPA（790 行）
│   ├── data/                    # 上传图片 + 处理后图片
│   └── tests/
│
├── miniapp/                     # 微信小程序（归档，见 miniapp 分支）
│
└── docs/
    ├── project_design.md
    ├── api_design.md
    └── demo_script.md
```

---

## 后端启动

```bash
cd backend
source .venv/bin/activate
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

或双击根目录 `start_all.command` 一键启动（含 ngrok 公网穿透）。

---

## 环境变量 (.env)

```env
# MiMo 图片识别
MIMO_API_KEY=***
MIMO_BASE_URL=https://your-mimo-endpoint/v1
MIMO_MODEL=mimo-v2.5

# DeepSeek 日记生成 + AI 对话
DEEPSEEK_API_KEY=***
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

# 天气
WEATHER_API_KEY=***

# 地点解析
GEOCODER_PROVIDER=mock
```

未配置时自动 Mock 模式。

---

## 网页前端功能

- 照片上传/预览
- 日期 + 地点手动输入（或从 EXIF 自动读取）
- AI 分析进度展示
- 日志生成 + 展示
- AI 对话编辑（SSE 流式，带完整照片上下文）
- Leaflet 地图打点
- 聊天持久化（localStorage）
- 暗色模式
- 移动端适配（max-width 480px）

---

## 分支说明

| 分支 | 说明 |
|------|------|
| `main` | 网页版（当前主线） |
| `miniapp` | 微信小程序版（已归档） |
