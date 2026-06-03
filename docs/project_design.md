# 项目设计文档

## 一、项目概述

### 1.1 项目名称
**AI 游玩日志生成系统** (AI Travel Diary Generator)

### 1.2 项目定位
基于微信小程序 + 小米 MiMo 多模态模型的智能游玩日志生成工具。用户上传 iPhone 旅行照片后，系统自动读取 EXIF 元数据（时间、GPS）、通过 AI 识别图片内容，并生成自然流畅的中文旅行日记。

### 1.3 目标用户
- 喜欢旅行、拍照记录的普通用户
- 希望快速整理旅行回忆的人
- 需要生成旅行日记作为纪念或社交分享的用户

### 1.4 核心价值
- **省时**: 自动整理照片 + 生成文字，无需手动编写游记
- **智能**: AI 理解照片内容，生成有温度的叙事
- **隐私**: 原图 GPS 不发送给 AI，保护用户位置隐私

---

## 二、系统架构

### 2.1 架构图

```
┌───────────────────────────────────────────────────────┐
│                    微信小程序 (Frontend)                 │
│  index → upload → analyzing → result → map             │
│  wx.chooseMedia → wx.uploadFile → wx.request           │
└──────────────────────┬────────────────────────────────┘
                       │ HTTP/HTTPS
┌──────────────────────▼────────────────────────────────┐
│                 FastAPI Backend (Python)                │
│                                                        │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐   │
│  │ Upload   │  │ Analyze  │  │ Diary Generation  │   │
│  │ API      │  │ API      │  │ API               │   │
│  └────┬─────┘  └────┬─────┘  └────────┬──────────┘   │
│       │              │                 │               │
│  ┌────▼─────┐  ┌─────▼──────┐  ┌──────▼──────────┐   │
│  │ EXIF     │  │ Image      │  │ Diary           │   │
│  │ Reader   │  │ Preprocess │  │ Generator       │   │
│  └──────────┘  └─────┬──────┘  └─────────────────┘   │
│                      │                                 │
│               ┌──────▼──────┐  ┌──────────────┐       │
│               │ MiMo Client │  │  Geocoder    │       │
│               │ (AI 识别)    │  │  (地点解析)   │       │
│               └─────────────┘  └──────────────┘       │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │              SQLite Database                      │ │
│  │  photos table │ diaries table                    │ │
│  └──────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────┘
```

### 2.2 技术选型

| 层级 | 技术 | 选型理由 |
|------|------|----------|
| **前端** | 微信小程序原生 | 无需额外框架，直接上架微信生态 |
| **后端** | Python FastAPI | 异步高性能、自动生成 API 文档、生态丰富 |
| **数据库** | SQLite | 零配置、轻量级，适合 MVP |
| **图片处理** | Pillow + exiftool | iPhone 照片 EXIF 兼容性最佳 |
| **AI 模型** | 小米 MiMo (OpenAI-compatible) | 多模态视觉理解 + 自然语言生成 |
| **地点解析** | 可替换模块 (mock/Nominatim/腾讯) | 灵活切换免费/付费服务 |

---

## 三、核心流程

### 3.1 完整用户流程

```
1. 用户打开小程序 → 首页
2. 点击「选择照片」→ 从相册选择
3. 查看已选照片预览 → 点击「上传」
4. 照片上传到后端 → 读取 EXIF → 识别 GPS
5. 点击「开始分析」
6. 后端: 压缩图片 → 去 EXIF → 调用 MiMo → 地点解析
7. 后端: 聚合分析结果 → 生成游玩日志 → 保存
8. 前端: 展示日志 (标题/日期/正文/关键词/照片详情)
```

### 3.2 数据处理流程

```
原始照片 (含 EXIF/GPS)
    │
    ├──→ [服务端本地] EXIF 读取 → 存入数据库
    │        时间、GPS、设备信息
    │
    ├──→ [服务端本地] 图片处理
    │        压缩到 1024px、去除 EXIF、转 JPEG
    │
    └──→ [发送 AI] 压缩后的纯图片
             不含任何 GPS/EXIF 元数据
             ↓
         MiMo 图片识别
             ↓
         结构化 JSON
             ↓
         + GPS 地点解析
             ↓
         日记生成器
             ↓
         中文游玩日志
```

---

## 四、数据库设计

### photos 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | TEXT | 用户标识 (第一版默认 'default') |
| file_path | TEXT | 服务器上原图路径 |
| original_filename | TEXT | 原始文件名 |
| file_size | INTEGER | 文件大小 (bytes) |
| taken_time | TEXT | 拍摄时间 (EXIF) |
| latitude | REAL | GPS 纬度 |
| longitude | REAL | GPS 经度 |
| has_gps | INTEGER | 是否有 GPS (0/1) |
| device_make | TEXT | 设备厂商 (如 Apple) |
| device_model | TEXT | 设备型号 (如 iPhone 15 Pro) |
| image_format | TEXT | 图片格式 (JPEG/HEIC/PNG) |
| country | TEXT | 国家 |
| city | TEXT | 城市 |
| district | TEXT | 区域 |
| address | TEXT | 地址 |
| place_name | TEXT | 地点名称 |
| location_status | TEXT | 地点状态 |
| ai_scene_type | TEXT | AI 识别的场景类型 |
| ai_activity | TEXT | AI 识别的活动 |
| ai_food | TEXT | 食物 (JSON array) |
| ai_objects | TEXT | 物体 (JSON array) |
| ai_landmark_hint | TEXT | 地标线索 |
| ai_mood | TEXT | 氛围 |
| ai_confidence | TEXT | 置信度 |
| ai_summary | TEXT | AI 摘要 |
| diary_sentence | TEXT | 日记句子 |
| status | TEXT | 处理状态 |
| created_at | TEXT | 创建时间 |

### diaries 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | TEXT | 用户标识 |
| title | TEXT | 日志标题 |
| date | TEXT | 日志日期 |
| city | TEXT | 主要城市 |
| content | TEXT | 日志正文 |
| keywords | TEXT | 关键词 (JSON array) |
| photo_ids | TEXT | 关联照片 ID (JSON array) |
| created_at | TEXT | 创建时间 |

---

## 五、安全与隐私

1. **API Key 安全**: MiMo API Key 仅存储在后端 `.env`，前端无法访问
2. **GPS 隐私**: 原图包含 GPS 的 EXIF 数据不出服务器
3. **图片发送**: 发送给 AI 的图片已去除所有 EXIF 元数据
4. **人脸保护**: AI prompt 明确要求不进行人脸身份识别
5. **数据存储**: 照片存储在服务器本地，不自动上传到第三方

---

## 六、扩展计划

### 近期
- HEIC 格式完整支持 (pillow-heif)
- 地图打点 + 旅行轨迹可视化
- AI 日记质量优化 (接入 LLM 文本生成)

### 中期
- 用户系统 + 微信登录
- 云存储 (腾讯云 COS)
- 多日旅行聚合 + 年度报告
- 社交分享 (生成精美卡片)

### 远期
- 视频日志生成
- 语音输入 + 语音播报
- 旅行推荐 (基于历史偏好)
