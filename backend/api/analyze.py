"""
照片分析接口 — POST /analyze

功能:
  - 并发调用 MiMo 分析照片（ThreadPoolExecutor）
  - 逐张进度推送（SSE 可选）
  - MiMo 失败时 DeepSeek 兜底
"""

import logging, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from models.database import (
    get_photos_by_ids, update_photo_ai_result, update_photo_location,
)
from services.mimo_client import analyze_image, analyze_image_mock, is_configured as mimo_configured
from services.deepseek_client import generate_photo_fallback, is_configured as deepseek_configured
from services.geocoder import resolve_location
from services.image_preprocess import strip_exif_and_compress

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["analyze"])

# 进度存储 (key: session_id, value: {total, completed, current})
_progress_store: dict[str, dict] = {}

MAX_CONCURRENT = int(os.getenv("ANALYZE_CONCURRENCY", "3"))


class AnalyzeRequest(BaseModel):
    photo_ids: list[int]
    geocode: bool = True
    use_sse: bool = False  # 是否用 SSE 推送进度


class AnalyzeResponse(BaseModel):
    success: bool
    total: int
    analyzed: int
    results: list[dict]
    errors: list[dict]
    generator: str = "mimo"


def _analyze_single(photo: dict, geocode: bool, using_mock: bool) -> dict:
    """分析单张照片（供并发调用）。"""
    photo_id = photo["id"]
    result = {"photo_id": photo_id}

    try:
        # 1. 预处理图片
        original_path = photo.get("file_path")
        if not original_path or not os.path.exists(original_path):
            raise FileNotFoundError(f"图片不存在: {original_path}")

        processed_path = strip_exif_and_compress(original_path)

        # 2. AI 分析（传入位置上下文）
        loc_ctx = f"{photo.get('city','')} {photo.get('district','')} {photo.get('place_name','')} {photo.get('address','')}".strip()
        if using_mock:
            ai_result = analyze_image_mock(processed_path, meta={
                "city": photo.get("city"),
                "place_name": photo.get("place_name"),
                "address": photo.get("address"),
                "taken_time": photo.get("taken_time"),
            })
        else:
            ai_result = analyze_image(processed_path, location_context=loc_ctx)

        ai_error = ai_result.get("error")

        # 3. MiMo 失败 → DeepSeek 兜底
        if ai_error and deepseek_configured():
            try:
                ai_result = generate_photo_fallback({
                    "photo_id": photo_id,
                    "taken_time": photo.get("taken_time"),
                    "city": photo.get("city"),
                    "place_name": photo.get("place_name"),
                    "mimo_error": ai_error,
                })
                ai_error = None
            except Exception as e:
                logger.warning(f"DeepSeek fallback failed for {photo_id}: {e}")

        # 4. 地点解析
        location = {
            "country": photo.get("country"),
            "city": photo.get("city"),
            "district": photo.get("district"),
            "address": photo.get("address"),
            "place_name": (
                photo.get("place_name")
                if photo.get("location_source") == "user"
                or photo.get("location_status") == "found"
                else None
            ),
            "location_status": photo.get("location_status") or "unknown",
            "location_source": photo.get("location_source") or "unknown",
        }

        if geocode and photo.get("has_gps"):
            lat, lon = photo.get("latitude"), photo.get("longitude")
            if lat is not None and lon is not None:
                try:
                    resolved = resolve_location(lat, lon)
                    location["country"] = resolved.get("country") or location["country"]
                    location["city"] = resolved.get("city") or location["city"]
                    location["district"] = resolved.get("district") or location["district"]
                    location["address"] = resolved.get("address") or location["address"]
                    location["location_status"] = resolved.get("location_status", "found")
                    if not location["place_name"] and resolved.get("location_status") == "found":
                        location["place_name"] = resolved.get("place_name")
                    update_photo_location(
                        photo_id=photo_id,
                        country=location.get("country"),
                        city=location.get("city"),
                        district=location.get("district"),
                        address=location.get("address"),
                        place_name=location.get("place_name"),
                        location_status=location["location_status"],
                        location_source=photo.get("location_source") or "exif",
                    )
                except Exception as e:
                    logger.warning(f"Geocode failed for {photo_id}: {e}")

        # 5. 保存 AI 结果
        update_photo_ai_result(
            photo_id=photo_id,
            scene_type=ai_result.get("scene_type"),
            activity=ai_result.get("activity"),
            food=ai_result.get("food", []),
            objects=ai_result.get("objects", []),
            landmark_hint=ai_result.get("landmark_hint"),
            fun_fact=ai_result.get("fun_fact"),
            confidence=ai_result.get("confidence"),
            summary=ai_result.get("diary_sentence"),
            diary_sentence=ai_result.get("diary_sentence"),
            error_message=ai_error,
        )

        result.update({
            "filename": photo["original_filename"],
            "exif": {
                "taken_time": photo.get("taken_time"),
                "has_gps": bool(photo.get("has_gps")),
                "location_status": location.get("location_status"),
                "time_source": photo.get("time_source") or "unknown",
                "location_source": location.get("location_source") or "unknown",
            },
            "location": location,
            "ai_analysis": {
                "scene_type": ai_result.get("scene_type"),
                "scene_subtype": ai_result.get("scene_subtype"),
                "activity": ai_result.get("activity"),
                "food": ai_result.get("food", []),
                "drinks": ai_result.get("drinks", []),
                "objects": ai_result.get("objects", []),
                "readable_text": ai_result.get("readable_text", []),
                "people_description": ai_result.get("people_description"),
                "time_of_day": ai_result.get("time_of_day"),
                "season_hint": ai_result.get("season_hint"),
                "location_clues": ai_result.get("location_clues"),
                "landmark_hint": ai_result.get("landmark_hint"),
                "atmosphere": ai_result.get("atmosphere"),
                "photo_quality": ai_result.get("photo_quality"),
                "fun_fact": ai_result.get("fun_fact"),
                "confidence": ai_result.get("confidence"),
                "diary_sentence": ai_result.get("diary_sentence"),
            },
            "error": ai_error,
        })

    except Exception as e:
        logger.error(f"Analyze error for {photo_id}: {e}")
        result["error"] = str(e)

    return result


@router.post("", response_model=AnalyzeResponse)
async def analyze_photos(request: AnalyzeRequest):
    """并发分析多张照片。"""
    if not request.photo_ids:
        raise HTTPException(status_code=400, detail="photo_ids 不能为空")
    if len(request.photo_ids) > 50:
        raise HTTPException(status_code=400, detail="最多 50 张")

    photos = get_photos_by_ids(request.photo_ids)
    if not photos:
        raise HTTPException(status_code=404, detail="未找到照片")

    using_mock = not mimo_configured()
    if using_mock:
        logger.warning("MiMo 未配置，使用 Mock 模式")

    results = []
    errors = []
    completed = 0
    total = len(photos)

    # 并发分析
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        futures = {
            executor.submit(_analyze_single, p, request.geocode, using_mock): p
            for p in photos
        }
        for future in as_completed(futures):
            completed += 1
            r = future.result()
            if r.get("error") and not r.get("ai_analysis", {}).get("diary_sentence"):
                errors.append({"photo_id": r["photo_id"], "error": r["error"]})
            results.append(r)
            logger.info(f"Analyze progress: {completed}/{total}")

    return AnalyzeResponse(
        success=len(errors) == 0,
        total=total,
        analyzed=len(results),
        results=results,
        errors=errors,
    )


@router.get("/progress")
async def get_progress(session_id: str = Query(...)):
    """SSE 进度推送（前端轮询用）。"""
    import asyncio

    async def event_stream():
        last_completed = -1
        while True:
            progress = _progress_store.get(session_id, {})
            current = progress.get("completed", 0)
            total = progress.get("total", 0)
            if current != last_completed:
                yield f"data: {{\"completed\":{current},\"total\":{total},\"current\":\"{progress.get('current','')}\"}}\n\n"
                last_completed = current
            if current >= total and total > 0:
                yield f"data: {{\"completed\":{total},\"total\":{total},\"done\":true}}\n\n"
                _progress_store.pop(session_id, None)
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---- 智能行程分组 ----
from datetime import datetime, timedelta


class GroupPhotosRequest(BaseModel):
    photo_ids: list[int]
    time_gap_hours: float = 4.0  # 多少小时以上的间隔视为不同行程
    geo_radius_km: float = 50.0   # 多少公里以上的距离变化视为不同行程


@router.post("/group")
async def group_photos_into_trips(request: GroupPhotosRequest):
    """智能分组：按时间+地点将照片分组为不同行程。"""
    if not request.photo_ids:
        raise HTTPException(status_code=400, detail="photo_ids 不能为空")

    photos = get_photos_by_ids(request.photo_ids)
    if not photos:
        raise HTTPException(status_code=404, detail="未找到照片")

    # 按时间排序
    photos_sorted = sorted(photos, key=lambda p: p.get("taken_time") or "9999-99-99 99:99:99")

    groups = []
    current_group = {"photos": [], "start_time": None, "end_time": None, "city": None}

    for p in photos_sorted:
        photo_time = None
        try:
            t = p.get("taken_time")
            if t:
                photo_time = datetime.strptime(str(t)[:19], "%Y-%m-%d %H:%M:%S")
        except: pass

        is_new_group = True
        if current_group["photos"]:
            # 检查时间间隔
            last_time = None
            try:
                lt = current_group["end_time"]
                if lt:
                    last_time = datetime.strptime(str(lt)[:19], "%Y-%m-%d %H:%M:%S")
            except: pass

            if last_time and photo_time:
                gap = (photo_time - last_time).total_seconds() / 3600
                if gap < request.time_gap_hours:
                    is_new_group = False

            # 检查地理位置跳跃
            if not is_new_group and p.get("latitude") and p.get("longitude"):
                last_photo_with_gps = None
                for prev in reversed(current_group["photos"]):
                    if prev.get("latitude") and prev.get("longitude"):
                        last_photo_with_gps = prev
                        break
                if last_photo_with_gps:
                    dist = _haversine(
                        last_photo_with_gps["latitude"], last_photo_with_gps["longitude"],
                        p["latitude"], p["longitude"]
                    )
                    if dist > request.geo_radius_km:
                        is_new_group = True

        if is_new_group and current_group["photos"]:
            groups.append(_format_group(current_group))
            current_group = {"photos": [], "start_time": None, "end_time": None, "city": None}

        current_group["photos"].append(p)
        current_group["city"] = current_group["city"] or p.get("city")
        if photo_time:
            t_str = photo_time.strftime("%Y-%m-%d %H:%M:%S")
            if not current_group["start_time"]:
                current_group["start_time"] = t_str
            current_group["end_time"] = t_str

    if current_group["photos"]:
        groups.append(_format_group(current_group))

    return {"success": True, "total_photos": len(photos_sorted), "groups": groups}


def _format_group(group: dict) -> dict:
    photos = group["photos"]
    cities = list(set(p.get("city") for p in photos if p.get("city")))
    return {
        "photo_ids": [p["id"] for p in photos],
        "photo_count": len(photos),
        "start_time": group["start_time"],
        "end_time": group["end_time"],
        "city": cities[0] if cities else "未知",
        "cities": cities[:5],
        "suggested_name": _suggest_trip_name(photos, cities),
    }


def _suggest_trip_name(photos: list[dict], cities: list[str]) -> str:
    if not photos: return "空行程"
    p0 = photos[0]
    t = (p0.get("taken_time") or "")[:10]
    city = cities[0] if cities else "未知"
    return f"{t} {city}之旅" if t else f"{city}之旅"


import math

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


# ---- AI 滤镜推荐 ----
FILTER_SUGGEST_PROMPT = """分析这张旅行照片，推荐最适合的滤镜风格。

可选滤镜: 原图、暖调、冷调、复古、戏剧、柔焦、黑白、富士、柯达、美食

输出 JSON:
{
  "filter_name": "滤镜名（必须是上面列出的之一）",
  "suggestion": "1-2句推荐理由，如：这张食物的色彩需要更高的饱和度和亮度来突出新鲜感"
}

考虑因素: 场景类型(美食/风景/街拍)、光线条件、色彩构成、氛围。"""


class FilterSuggestRequest(BaseModel):
    photo_id: int


@router.post("/filter-suggest")
async def suggest_filter_for_photo(request: FilterSuggestRequest):
    """AI 分析照片并推荐滤镜风格。"""
    photos = get_photos_by_ids([request.photo_id])
    if not photos:
        raise HTTPException(status_code=404, detail="照片不存在")

    photo = photos[0]
    original_path = photo.get("file_path")
    if not original_path or not os.path.exists(original_path):
        raise HTTPException(status_code=404, detail="照片文件未找到")

    from services.image_preprocess import strip_exif_and_compress
    processed_path = strip_exif_and_compress(original_path)

    using_mock = not mimo_configured()
    if using_mock:
        # Mock: 简单基于场景类型推荐
        scene = photo.get("ai_scene_type", "")
        food = photo.get("ai_food", [])
        if scene == "restaurant" or food:
            return {"success": True, "filter_name": "美食", "filter_css": FILTER_CSS["美食"], "suggestion": "食物场景推荐使用美食滤镜，能突出食材的色泽和新鲜感"}
        if scene in ("beach", "mountain", "landscape", "viewpoint"):
            return {"success": True, "filter_name": "富士", "filter_css": FILTER_CSS["富士"], "suggestion": "风景场景推荐富士滤镜，增添电影般的色调层次"}
        if scene in ("street", "street_market", "night_market"):
            return {"success": True, "filter_name": "复古", "filter_css": FILTER_CSS["复古"], "suggestion": "街拍场景推荐复古滤镜，营造怀旧街头氛围"}
        return {"success": True, "filter_name": "暖调", "filter_css": FILTER_CSS["暖调"], "suggestion": "推荐暖调滤镜，让照片更有温度"}

    # 调用 MiMo 推荐
    try:
        from services.mimo_client import _call_api_with_images, _content_to_text, _extract_json_from_response
        api_response = _call_api_with_images(
            [processed_path], FILTER_SUGGEST_PROMPT,
            system_msg="你是照片后期处理专家。只输出 JSON。",
            temperature=0.3, max_tokens=1024
        )
        choices = api_response.get("choices", [])
        if choices:
            content = _content_to_text(choices[0].get("message", {}).get("content", ""))
            parsed = _extract_json_from_response(content)
            if parsed:
                filter_name = parsed.get("filter_name", "暖调")
                return {
                    "success": True,
                    "filter_name": filter_name,
                    "filter_css": FILTER_CSS.get(filter_name, FILTER_CSS["暖调"]),
                    "suggestion": parsed.get("suggestion", "AI 推荐使用此滤镜"),
                }
        return {"success": False, "detail": "AI 未返回有效建议"}
    except Exception as e:
        logger.warning(f"Filter suggest failed: {e}")
        return {"success": False, "detail": f"AI 请求失败: {e}"}


FILTER_CSS = {
    "原图": "",
    "暖调": "brightness(1.1) saturate(1.3) sepia(0.2) hue-rotate(-10deg)",
    "冷调": "brightness(1.05) saturate(1.1) hue-rotate(10deg)",
    "复古": "sepia(0.5) contrast(0.9) brightness(0.9)",
    "戏剧": "contrast(1.3) saturate(1.2) brightness(0.9)",
    "柔焦": "brightness(1.1) contrast(0.9) saturate(0.8)",
    "黑白": "grayscale(1) contrast(1.1)",
    "富士": "contrast(1.1) saturate(1.1) brightness(1.05) hue-rotate(-5deg)",
    "柯达": "contrast(1.05) saturate(0.9) brightness(1.05) sepia(0.15)",
    "美食": "saturate(1.5) contrast(1.05) brightness(1.1)",
}
