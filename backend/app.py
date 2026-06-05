"""
AI 游玩日志生成系统 — FastAPI 后端入口。

启动方式:
    uvicorn app:app --reload --host 0.0.0.0 --port 8000
"""

import logging
import sys
import os

# 确保 backend 目录在 sys.path 中 (方便直接 python app.py)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models.database import init_db

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---- 创建应用 ----

app = FastAPI(
    title="AI 游玩日志生成系统",
    description="基于微信小程序与小米 MiMo 多模态模型的智能游玩日志生成系统",
    version="0.1.0",
)

# ---- CORS 中间件 ----
# 允许微信小程序开发工具和本地调试
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发阶段允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- JSON 响应清理中间件 ----
import unicodedata
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import json as _json

class SanitizeJSONMiddleware(BaseHTTPMiddleware):
    """移除 JSON 响应中的非法控制字符，防止 JSON 解析失败."""
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        ct = response.headers.get("content-type", "")
        if "application/json" in ct and hasattr(response, "body"):
            try:
                body = response.body
                if isinstance(body, bytes):
                    text = body.decode("utf-8", errors="replace")
                    # 移除 JSON 不兼容字符
                    cleaned = []
                    for ch in text:
                        cat = unicodedata.category(ch)
                        if cat == 'Cc' and ch not in '\n\r\t':
                            cleaned.append(' ')
                        elif ch in ('\u2028', '\u2029', '\u0085'):
                            cleaned.append(' ')
                        else:
                            cleaned.append(ch)
                    cleaned_text = ''.join(cleaned)
                    if cleaned_text != text:
                        return Response(
                            content=cleaned_text.encode("utf-8"),
                            status_code=response.status_code,
                            headers=dict(response.headers),
                            media_type="application/json",
                        )
            except Exception:
                pass  # 兼容 stream/非 bytes 响应
        return response

app.add_middleware(SanitizeJSONMiddleware)

# ---- 初始化数据库 ----
@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库."""
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized.")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理数据库连接."""
    from models.database import close_db
    close_db()
    logger.info("Database connection closed.")


# ---- 静态文件服务 (照片回看) ----
from fastapi.staticfiles import StaticFiles

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "data", "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)
app.mount("/photos", StaticFiles(directory=UPLOADS_DIR), name="photos")

# ---- 注册路由 ----
from api.upload import router as upload_router
from api.analyze import router as analyze_router
from api.diary import router as diary_router

app.include_router(upload_router)
app.include_router(analyze_router)
app.include_router(diary_router)


# ---- Health Check ----
@app.get("/health", tags=["system"])
async def health_check():
    """健康检查接口."""
    return {
        "status": "ok",
        "service": "AI 游玩日志生成系统",
        "version": "0.1.0",
    }


# ---- 根路由：网页端 ----
from fastapi.responses import HTMLResponse

WEB_HTML_PATH = os.path.join(os.path.dirname(__file__), "web", "index.html")

@app.get("/", response_class=HTMLResponse, tags=["system"])
async def root():
    """网页端入口 — 返回完整的上传/分析/日记 HTML 页面."""
    if os.path.exists(WEB_HTML_PATH):
        with open(WEB_HTML_PATH, "r", encoding="utf-8") as f:
            return f.read()
    # fallback
    return """<html><body><h2>AI 游玩日志生成系统</h2>
    <p>网页端文件未找到。请确认 backend/web/index.html 存在。</p>
    <p>API 文档: <a href="/docs">/docs</a></p></body></html>"""


# ---- 直接运行 ----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
