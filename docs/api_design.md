# API 接口文档

Base URL: `http://127.0.0.1:8000` (开发环境)

---

## 1. 系统接口

### `GET /health` — 健康检查

**响应:**
```json
{
  "status": "ok",
  "service": "AI 游玩日志生成系统",
  "version": "0.1.0"
}
```

### `GET /` — API 信息

**响应:**
```json
{
  "service": "AI 游玩日志生成系统 API",
  "docs": "/docs",
  "health": "/health",
  "endpoints": {
    "upload": "POST /upload",
    "upload_batch": "POST /upload/batch",
    "analyze": "POST /analyze",
    "generate_diary": "POST /diary/generate",
    "get_diary": "GET /diary/{id}",
    "list_diaries": "GET /diary/"
  }
}
```

---

## 2. 上传接口

### `POST /upload` — 上传单张图片

**Content-Type:** `multipart/form-data`

**参数:**
| 参数 | 类型 | 说明 |
|------|------|------|
| file | file | 图片文件 (JPG/PNG/HEIC/HEIF/WEBP) |

**响应:**
```json
{
  "success": true,
  "photo_id": 1,
  "filename": "IMG_1234.HEIC",
  "file_size": 2456789,
  "exif": {
    "taken_time": "2025-06-08 10:20:00",
    "latitude": 22.3193,
    "longitude": 114.1694,
    "has_gps": true,
    "device_make": "Apple",
    "device_model": "iPhone 15 Pro",
    "image_format": "HEIC",
    "location_status": "found"
  },
  "exif_error": null
}
```

**限制:**
- 文件 ≤ 30 MB
- 支持格式: .jpg, .jpeg, .png, .heic, .heif, .webp, .bmp, .tiff

### `POST /upload/batch` — 批量上传

**Content-Type:** `multipart/form-data`

**参数:**
| 参数 | 类型 | 说明 |
|------|------|------|
| files | file[] | 最多 20 张图片 |

**响应:**
```json
{
  "success": true,
  "uploaded": 3,
  "results": [
    { "photo_id": 2, "filename": "photo1.jpg", "exif": {...} }
  ],
  "errors": []
}
```

---

## 3. 分析接口

### `POST /analyze` — 批量分析照片

**Content-Type:** `application/json`

**请求体:**
```json
{
  "photo_ids": [1, 2, 3],
  "geocode": true
}
```

**响应:**
```json
{
  "success": true,
  "total": 3,
  "analyzed": 3,
  "results": [
    {
      "photo_id": 1,
      "filename": "IMG_1234.HEIC",
      "exif": {
        "taken_time": "2025-06-08 10:20:00",
        "has_gps": true,
        "location_status": "found"
      },
      "location": {
        "country": "中国",
        "city": "香港",
        "district": "油尖旺区",
        "address": "香港油尖旺区附近",
        "place_name": "维多利亚港",
        "location_status": "approximate"
      },
      "ai_analysis": {
        "scene_type": "tourist_attraction",
        "activity": "sightseeing",
        "food": [],
        "objects": ["building", "sky", "harbour"],
        "landmark_or_place_hint": "harbour view",
        "mood": "happy",
        "confidence": "medium",
        "diary_sentence": "这张照片看起来是在海港附近观光。"
      },
      "error": null
    }
  ],
  "errors": []
}
```

**限制:** 单次最多分析 20 张照片

**说明:**
- 前置条件: 照片已通过 `/upload` 上传
- 如果 MiMo API 未配置，自动使用 Mock 模式
- `geocode: true` 时自动对有 GPS 的照片进行地点解析

---

## 4. 日志接口

### `POST /diary/generate` — 生成游玩日志

**Content-Type:** `application/json`

**请求体:**
```json
{
  "photo_ids": [1, 2, 3],
  "custom_title": "可选的自定义标题"
}
```

**响应:**
```json
{
  "success": true,
  "diary_id": 1,
  "title": "香港城市游玩记录",
  "date": "2025-06-08",
  "city": "香港",
  "content": "2025年06月08日，你在香港记录了3张照片。\n\n上午的照片显示你可能在观光游览，主要是在观光...",
  "keywords": ["香港", "景点打卡", "城市漫步", "美食", "轻松"],
  "photo_count": 3,
  "photo_summaries": [
    {
      "taken_time": "2025-06-08 10:20:00",
      "city": "香港",
      "address": "尖沙咀附近",
      "scene_type": "tourist_attraction",
      "activity": "sightseeing",
      "diary_sentence": "这张照片看起来是在海港附近观光。",
      "mood": "happy"
    }
  ],
  "error": null
}
```

### `GET /diary/{id}` — 获取日志详情

**响应:**
```json
{
  "success": true,
  "diary": {
    "id": 1,
    "title": "香港城市游玩记录",
    "date": "2025-06-08",
    "city": "香港",
    "content": "...",
    "keywords": ["香港", "景点打卡"],
    "photo_ids": [1, 2, 3],
    "created_at": "2025-06-08 14:30:00"
  },
  "photos": [
    {
      "photo_id": 1,
      "filename": "IMG_1234.HEIC",
      "taken_time": "2025-06-08 10:20:00",
      "city": "香港",
      "scene_type": "tourist_attraction",
      "diary_sentence": "这张照片看起来是在海港附近观光。"
    }
  ]
}
```

### `GET /diary/` — 日志列表

**参数:**
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| user_id | string | "default" | 用户标识 |
| limit | int | 20 | 返回数量 |

**响应:**
```json
{
  "success": true,
  "count": 2,
  "diaries": [
    {
      "id": 2,
      "title": "...",
      "date": "2025-06-09",
      "city": "北京",
      "content": "...",
      "keywords": [...],
      "photo_ids": [...],
      "created_at": "..."
    }
  ]
}
```

---

## 5. 错误响应格式

所有接口在出错时返回:
```json
{
  "detail": "错误描述信息"
}
```

HTTP 状态码:
- `400` — 请求参数错误
- `404` — 资源不存在
- `500` — 服务器内部错误

---

## 6. Swagger 文档

启动后端后访问: `http://127.0.0.1:8000/docs` (自动生成的交互式 API 文档)
