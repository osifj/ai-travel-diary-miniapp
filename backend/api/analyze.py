"""
AI 分析接口 — POST /analyze

输入一组 photo_id，后端依次:
  1. 获取原图
  2. 压缩 + 去除 EXIF (隐私保护)
  3. 调用 MiMo API 进行图片内容识别
  4. 可选: 调用 geocoder 进行地点解析
  5. 保存分析结果到数据库
  6. 返回每张照片的结构化分析结果
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from models.database import (
    get_photo, get_photos_by_ids, update_photo_ai_result, update_photo_location
)
from services.image_preprocess import strip_exif_and_compress
from services.mimo_client import analyze_image, analyze_image_mock, is_configured
from services.geocoder import resolve_location

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["analyze"])


class AnalyzeRequest(BaseModel):
    photo_ids: list[int]
    # 如果 geocode=true，会对有 GPS 的照片进行地点解析
    geocode: bool = True


class AnalyzeResponse(BaseModel):
    success: bool
    total: int
    analyzed: int
    results: list[dict]
    errors: list[dict]


@router.post("", response_model=AnalyzeResponse)
async def analyze_photos(request: AnalyzeRequest):
    """
    批量分析照片。

    处理流程:
      1. 根据 photo_ids 获取原图
      2. 对每张照片:
         a. 压缩 + 去除 EXIF
         b. 调用 MiMo API 进行图片内容识别
         c. 如果有 GPS，进行地点解析
         d. 保存结果到数据库
      3. 返回汇总结果
    """
    photo_ids = request.photo_ids
    if not photo_ids:
        raise HTTPException(status_code=400, detail="photo_ids 不能为空")

    if len(photo_ids) > 20:
        raise HTTPException(status_code=400, detail="单次最多分析 20 张照片")

    # 检查 MiMo 配置状态
    using_mock = not is_configured()
    if using_mock:
        logger.warning(
            "⚠️  MiMo API 未配置，将使用 Mock 模式返回模拟数据。"
            "请在 backend/.env 中配置 MIMO_API_KEY 和 MIMO_BASE_URL。"
        )

    results = []
    errors = []

    for photo_id in photo_ids:
        try:
            # ---- 1. 获取原图信息 ----
            photo = get_photo(photo_id)
            if not photo:
                errors.append({"photo_id": photo_id, "error": "照片不存在"})
                continue

            file_path = photo["file_path"]

            # ---- 2. 图片预处理 (压缩 + 去 EXIF) ----
            try:
                processed_path = strip_exif_and_compress(file_path)
            except Exception as e:
                errors.append({
                    "photo_id": photo_id,
                    "error": f"图片预处理失败: {e}"
                })
                continue

            # ---- 3. AI 图片内容识别 ----
            if using_mock:
                ai_result = analyze_image_mock(processed_path)
            else:
                ai_result = analyze_image(processed_path)

            # ---- 4. 地点解析 (如果有 GPS 且 geocode=true) ----
            location = {
                "country": None, "city": None, "district": None,
                "address": None, "place_name": None, "location_status": "unknown"
            }
            if request.geocode and photo.get("has_gps"):
                lat = photo.get("latitude")
                lon = photo.get("longitude")
                if lat is not None and lon is not None:
                    try:
                        location = resolve_location(lat, lon)
                        update_photo_location(
                            photo_id=photo_id,
                            country=location.get("country"),
                            city=location.get("city"),
                            district=location.get("district"),
                            address=location.get("address"),
                            place_name=location.get("place_name"),
                            location_status=location.get("location_status", "found"),
                        )
                    except Exception as e:
                        logger.warning(f"Geocode failed for photo {photo_id}: {e}")

            # ---- 5. 保存 AI 结果到数据库 ----
            update_photo_ai_result(
                photo_id=photo_id,
                scene_type=ai_result.get("scene_type"),
                activity=ai_result.get("activity"),
                food=ai_result.get("food", []),
                objects=ai_result.get("objects", []),
                landmark_hint=ai_result.get("landmark_or_place_hint"),
                mood=ai_result.get("mood"),
                confidence=ai_result.get("confidence"),
                summary=ai_result.get("diary_sentence"),
                diary_sentence=ai_result.get("diary_sentence"),
                error_message=ai_result.get("error"),
            )

            # ---- 6. 收集结果 ----
            results.append({
                "photo_id": photo_id,
                "filename": photo["original_filename"],
                "exif": {
                    "taken_time": photo.get("taken_time"),
                    "has_gps": bool(photo.get("has_gps")),
                    "location_status": location.get("location_status"),
                },
                "location": location,
                "ai_analysis": {
                    "scene_type": ai_result.get("scene_type"),
                    "activity": ai_result.get("activity"),
                    "food": ai_result.get("food", []),
                    "objects": ai_result.get("objects", []),
                    "landmark_or_place_hint": ai_result.get("landmark_or_place_hint"),
                    "mood": ai_result.get("mood"),
                    "confidence": ai_result.get("confidence"),
                    "diary_sentence": ai_result.get("diary_sentence"),
                },
                "error": ai_result.get("error"),
            })

        except Exception as e:
            logger.error(f"Analyze error for photo {photo_id}: {e}")
            errors.append({"photo_id": photo_id, "error": str(e)})

    return AnalyzeResponse(
        success=len(errors) == 0,
        total=len(photo_ids),
        analyzed=len(results),
        results=results,
        errors=errors,
    )
