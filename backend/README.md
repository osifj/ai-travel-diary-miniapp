# Backend — AI 游玩日志生成系统

FastAPI 后端服务。

## 快速启动

```bash
# 1. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 MiMo API Key 和其他配置

# 4. 启动服务
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

## 运行测试

```bash
pytest tests/ -v
```

## API 文档

启动后访问: http://127.0.0.1:8000/docs (Swagger UI)

## 目录说明

```
backend/
├── app.py              # 应用入口
├── api/                # 接口层 (路由 + 请求处理)
│   ├── upload.py       # 图片上传
│   ├── analyze.py      # AI 分析
│   └── diary.py        # 日志生成
├── services/           # 业务逻辑层
│   ├── exif_reader.py      # EXIF 解析
│   ├── image_preprocess.py # 图片压缩+去元数据
│   ├── mimo_client.py      # MiMo API 客户端
│   ├── geocoder.py         # 地点解析
│   └── diary_generator.py  # 日记生成
├── models/
│   └── database.py     # SQLite 数据模型
└── tests/              # 测试
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MIMO_API_KEY` | MiMo API Key | (必填) |
| `MIMO_BASE_URL` | MiMo API Base URL | (必填) |
| `MIMO_MODEL` | 模型名称 | mimo-v2.5 |
| `GEOCODER_PROVIDER` | 地点解析提供商 | mock |
| `GEOCODER_API_KEY` | 地点解析 API Key | (可选) |
