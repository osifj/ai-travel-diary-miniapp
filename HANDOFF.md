# 交接文档 — AI 游玩日志生成系统

> 最后更新: 2026-06-04
> 交接给: Codex
> GitHub: https://github.com/osifj/ai-travel-diary-miniapp
> 当前分支: `main`

---

## 一句话概述

上传照片 → MiMo 多模态识别场景/食物/物体 → DeepSeek 生成中文游记 → AI 多轮对话修改 → 导出 MD。FastAPI 后端 + 单文件 HTML 前端。

---

## 快速启动

```bash
# 方式一：双击 start_all.command（推荐，含 ngrok 公网）
open /path/to/ai-travel-diary-miniapp/start_all.command

# 方式二：手动启动后端
cd /path/to/ai-travel-diary-miniapp/backend
uvicorn app:app --host 0.0.0.0 --port 8000
```

浏览器打开 `http://127.0.0.1:8000` 即可。

---

## API Key 管理（重要）

**双重持久化，不会丢：**

| 位置 | 说明 |
|------|------|
| `backend/.env` | 项目内，`.gitignore` 已排除 |
| `~/.ai-travel-diary.env` | 家目录，**永不会丢** |

`start_all.command` 启动时自动检测：
1. `backend/.env` 存在 → 直接用
2. `backend/.env` 不存在，`~/.ai-travel-diary.env` 存在 → 自动复制恢复
3. 两个都不存在 → 交互式询问，填了就保存到两处

当前已配置的 Key：
- DeepSeek: `sk-01d78f918e...`（日记生成 + SSE 对话）
- MiMo: `sk-cp9m8r8gv7v...`（多模态图片识别）

---

## 项目结构

```
ai-travel-diary-miniapp/
├── README.md
├── HANDOFF.md                   ← 你正在读
├── start_all.command            # 一键启动（后端 + ngrok + 防睡眠）
├── .gitignore
│
├── backend/                     # Python FastAPI
│   ├── app.py                   # 入口，CORS + JSON 清理中间件 + 静态文件
│   ├── requirements.txt         # Python 依赖
│   ├── .env.example             # 环境变量模板
│   ├── api/
│   │   ├── upload.py            # POST /upload（单张/批量，EXIF 提取）
│   │   ├── analyze.py           # POST /analyze（MiMo 并发分析 + 地点解析 + 滤镜推荐 + 照片分组）
│   │   └── diary.py             # CRUD + SSE 对话 + 整合 + 风格切换 + 精修
│   ├── services/
│   │   ├── exif_reader.py       # exiftool → Pillow → macOS mdls/sips 三级回退
│   │   ├── image_preprocess.py  # 压缩到 1024px + 去 EXIF（隐私）
│   │   ├── mimo_client.py       # MiMo 视觉识别 + 全流程日记生成
│   │   ├── deepseek_client.py   # DeepSeek：日记生成/对话(SSE)/整合/风格切换
│   │   ├── geocoder.py          # Mock → Nominatim → 腾讯 三级地点解析
│   │   ├── weather_service.py   # Open-Meteo 免费天气 API
│   │   └── diary_generator.py   # 模板保底日记生成
│   ├── models/
│   │   └── database.py          # SQLite: photos + diaries 表，自动列补齐
│   ├── web/
│   │   └── index.html           # 单文件前端（~1550 行 HTML+CSS+JS）
│   ├── data/                    # uploads/ + processed/（运行时生成，gitignored）
│   └── tests/
│
├── miniapp/                     # 微信小程序（已归档到 miniapp 分支）
└── docs/                        # 设计文档
```

---

## 前端架构（web/index.html）

单文件 SPA，约 1550 行。关键全局状态：

```javascript
const state = {
  files: [],          // 本地 File 对象
  photoIds: [],       // 上传后返回的 ID
  uploadResults: [],  // 上传结果
  analyzeResults: [], // 分析结果
  diaryResult: null,  // 当前日记
  diaryPhotos: [],    // 关联照片（含 GPS）
  chatMessages: [],   // 对话历史
};

let batchMode = false, selectedDiaries = new Set();  // 批量模式
let filterState = { ... };  // 照片滤镜编辑器
let voiceRecognition = null, isVoiceActive = false;  // 语音输入
```

### 编辑 HTML 注意事项

1. **用 `edit_file` 增量改，不要 `write_file` 覆写**（超过 30KB 会被截断）
2. 改完后用 `python3` 正则提取 `<script>` 内容 → `node --check` 验证 JS 语法
3. 改 Python 后用 `python3 -m compileall backend/` 验证
4. 全局 `querySelectorAll` 要用容器限定范围（`container.querySelectorAll`）

---

## 核心数据流

```
用户上传照片 → POST /upload
  → EXIF 读取（exiftool → Pillow → mdls）
  → 保存到 data/uploads/，写入 SQLite

POST /analyze { photo_ids, geocode:true }
  → image_preprocess: 压缩 1024px + 去 EXIF
  → MiMo: 多模态识别（scene_type/food/objects/fun_fact/...）
  → MiMo 失败 → DeepSeek 元数据兜底
  → MiMo 未配置 → Mock（基于照片地点时间的保守描述）
  → geocoder: GPS → 地点（Nominatim/Tencent/Mock）
  → 写入 photos 表 AI 字段

POST /diary/generate { photo_ids }
  → 查询天气（Open-Meteo）
  → 模板日记生成（diary_generator.py）
  → MiMo 全流程日记（基于分析结果 + 地理知识）
  → MiMo 失败 → DeepSeek 日记生成
  → 保存到 diaries 表

POST /diary/{id}/chat → SSE 流式
  → 前端显示对话气泡
  → 对话历史存入 diaries.chat_history

POST /diary/{id}/integrate
  → DeepSeek 把对话内容整合进日记正文

POST /diary/{id}/restyle { style }
  → 轻松/正式/简短/科普 四种风格重写
```

---

## 数据库

SQLite，文件在 `backend/data/travel_diary.db`。

### photos 表关键字段
`id, user_id, file_path, original_filename, taken_time, latitude, longitude, has_gps, city, place_name, address, ai_scene_type, ai_activity, ai_food(JSON), ai_objects(JSON), ai_fun_fact, diary_sentence, status`

### diaries 表关键字段
`id, user_id, title, date, city, content, weather_summary, place_intro, keywords(JSON), photo_ids(JSON), chat_history(JSON), generator`

列补齐：`_ensure_photo_columns()` 和 `_ensure_diary_columns()` 自动为旧数据库添加新列。

---

## 关键设计决策

| 决策 | 原因 |
|------|------|
| MiMo 优先，DeepSeek 兜底 | MiMo 视觉识别更准；DeepSeek 作为文字兜底 |
| 三级 EXIF 回退 | exiftool 最准但需安装；Pillow 通用；mdls 是 macOS 最后手段 |
| 图片预处理去 EXIF | 隐私保护——不把 GPS 发给 AI |
| Mock 基于元数据 | 没配 Key 时用城市+地点+时间生成保守描述，不再是写死的香港场景 |
| JSON 清理中间件 | MiMo/DeepSeek 可能返回 Unicode 控制字符，会导致 JSON 解析失败 |
| 单文件 HTML | 开发阶段简化部署；后续可拆分 |
| SQLite + WAL 模式 | 零配置，WAL 提升并发 |
| 进度条 `await setTimeout` | 并发分析太快，加 400ms 延迟让用户看到进度填满 |

---

## 最近修复（本次 session）

| Commit | 修复内容 |
|--------|---------|
| `7ceb001` | 语音递归（stopVoice 先置 null 再 stop）、进度条可见、XSS 加固（escHtml）、地图降级、清理重复依赖 |
| `18406a8` | Mock 基于元数据（不再返回香港场景）、地图 tileerror 不用 innerHTML（避免摧毁 Leaflet DOM） |
| `c3af868` | API Key 持久化：家目录 `~/.ai-travel-diary.env` + start_all.command 自动检测恢复 |

---

## 已知注意事项

1. **exiftool 未安装时** EXIF 读取回退到 Pillow，HEIC 用 macOS `sips` 转 JPEG
2. **微信小程序上传会剥离 EXIF**，前端提供日期/地点手动输入兜底
3. **Nominatim 免费但有频率限制**（1 req/s），生产环境建议换腾讯/高德
4. **ngrok 免费隧道会不定期断连**，刷新或重启 ngrok 即可
5. **单文件 HTML 约 1550 行**，编辑时注意行号偏移
6. **沙箱 `/tmp/` 目录重启即清空**，开发在真实 Mac 上做
7. **`.env` 被 `.gitignore` 排除**，不会上传到 GitHub

---

## ngrok 配置

```bash
# 已安装并配置 authtoken
brew install ngrok
ngrok config add-authtoken <token>
# 配置在 ~/Library/Application Support/ngrok/ngrok.yml
```

---

## 给 Codex 的建议

1. **改 HTML 前先 `read_file`**，编辑用 `edit_file` 增量改
2. **改 Python 后跑 `python3 -m compileall backend/`** 验证
3. **全局选择器用容器限定**：`document.querySelectorAll` → `container.querySelectorAll`
4. **`escHtml()` 已定义**，新增 innerHTML 拼接记得用它防 XSS
5. **地图操作避免 `innerHTML`**，Leaflet 的 DOM 是程序创建的，用 `appendChild`/`createElement`
6. **前端状态在 `const state`**，视图切换通过 `switchView('new'|'history')`
7. **后端 `.env` 丢了别慌**，`~/.ai-travel-diary.env` 有备份，或运行 `start_all.command` 自动恢复
