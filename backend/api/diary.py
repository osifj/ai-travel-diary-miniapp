"""
游玩日志接口 — POST /generate_diary, GET /diary/{id}

功能:
  - 根据照片分析结果生成游玩日志
  - 获取已生成的日志
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from models.database import (
    get_photos_by_ids, insert_diary, get_diary, get_diaries_by_user
)
from services.diary_generator import generate_diary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diary", tags=["diary"])


class GenerateDiaryRequest(BaseModel):
    photo_ids: list[int]
    # 可选：手动指定标题，否则自动生成
    custom_title: Optional[str] = None


class GenerateDiaryResponse(BaseModel):
    success: bool
    diary_id: Optional[int] = None
    title: str
    date: str
    city: str
    content: str
    keywords: list[str]
    photo_count: int
    photo_summaries: list[dict]
    error: Optional[str] = None


@router.post("/generate", response_model=GenerateDiaryResponse)
async def create_diary(request: GenerateDiaryRequest):
    """
    根据一组已分析的照片生成游玩日志。

    前置条件: 这些照片必须已经过分析 (POST /analyze)。
    如果照片尚未分析，日志质量会下降 (缺少 AI 内容识别结果)。

    处理流程:
      1. 从数据库获取照片信息
      2. 调用 diary_generator 生成日志
      3. 保存到数据库
      4. 返回日志内容
    """
    if not request.photo_ids:
        raise HTTPException(status_code=400, detail="photo_ids 不能为空")

    if len(request.photo_ids) > 50:
        raise HTTPException(status_code=400, detail="单次最多使用 50 张照片生成日志")

    # ---- 1. 获取照片数据 ----
    photos = get_photos_by_ids(request.photo_ids)
    if not photos:
        raise HTTPException(status_code=404, detail="未找到任何照片")

    # 检查是否有照片缺失
    found_ids = {p["id"] for p in photos}
    missing_ids = set(request.photo_ids) - found_ids
    if missing_ids:
        logger.warning(f"Some photos not found: {missing_ids}")

    # ---- 2. 转换为 diary_generator 需要的格式 ----
    photo_data = []
    for p in photos:
        photo_data.append({
            "photo_id": p["id"],
            "taken_time": p.get("taken_time"),
            "latitude": p.get("latitude"),
            "longitude": p.get("longitude"),
            "city": p.get("city"),
            "address": p.get("address"),
            "scene_type": p.get("ai_scene_type"),
            "activity": p.get("ai_activity"),
            "food": p.get("ai_food", []),
            "objects": p.get("ai_objects", []),
            "landmark_or_place_hint": p.get("ai_landmark_hint"),
            "mood": p.get("ai_mood"),
            "confidence": p.get("ai_confidence"),
            "diary_sentence": p.get("diary_sentence"),
        })

    # ---- 3. 生成日志 ----
    try:
        diary_data = generate_diary(photo_data)
    except Exception as e:
        logger.error(f"Diary generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"日志生成失败: {e}")

    # ---- 4. 保存到数据库 ----
    title = request.custom_title or diary_data["title"]
    try:
        diary_id = insert_diary(
            title=title,
            date=diary_data["date"],
            city=diary_data.get("city", "未知"),
            content=diary_data["content"],
            keywords=diary_data["keywords"],
            photo_ids=request.photo_ids,
        )
    except Exception as e:
        logger.error(f"Failed to save diary: {e}")
        raise HTTPException(status_code=500, detail=f"日志保存失败: {e}")

    return GenerateDiaryResponse(
        success=True,
        diary_id=diary_id,
        title=title,
        date=diary_data["date"],
        city=diary_data.get("city", "未知"),
        content=diary_data["content"],
        keywords=diary_data["keywords"],
        photo_count=diary_data["photo_count"],
        photo_summaries=diary_data["photo_summaries"],
    )


@router.get("/{diary_id}")
async def read_diary(diary_id: int):
    """获取已生成的游玩日志."""
    diary = get_diary(diary_id)
    if not diary:
        raise HTTPException(status_code=404, detail=f"日志 {diary_id} 不存在")

    # 可选：附带关联照片信息
    photo_ids = diary.get("photo_ids", [])
    photos = get_photos_by_ids(photo_ids) if photo_ids else []

    return {
        "success": True,
        "diary": diary,
        "photos": [
            {
                "photo_id": p["id"],
                "filename": p["original_filename"],
                "taken_time": p.get("taken_time"),
                "city": p.get("city"),
                "scene_type": p.get("ai_scene_type"),
                "diary_sentence": p.get("diary_sentence"),
            }
            for p in photos
        ],
    }


@router.get("/")
async def list_diaries(user_id: str = "default", limit: int = 20):
    """获取用户的所有日志列表."""
    diaries = get_diaries_by_user(user_id=user_id, limit=min(limit, 50))
    return {
        "success": True,
        "count": len(diaries),
        "diaries": diaries,
    }
