"""
游玩日志接口 — POST /generate_diary, GET /diary/{id}

功能:
  - 根据照片分析结果生成游玩日志
  - 获取已生成的日志
"""

import json
import logging
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from models.database import (
    get_photos_by_ids, insert_diary, get_diary, get_diaries_by_user,
    update_diary_refined, delete_diary, search_diaries,
)
from services.diary_generator import generate_diary
from services.weather_service import get_weather_summary
from services.deepseek_client import generate_rich_diary, is_configured as deepseek_is_configured

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diary", tags=["diary"])


class GenerateDiaryRequest(BaseModel):
    photo_ids: list[int]
    user_id: str = "default"
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
    weather_summary: Optional[str] = None
    place_intro: Optional[str] = None
    generator: str = "template"
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

    # ---- 2. 转换为 diary_generator/DeepSeek 需要的格式 ----
    photo_data = []
    for p in photos:
        precise_place_name = (
            p.get("place_name")
            if p.get("location_source") == "user"
            or p.get("location_status") == "found"
            else None
        )
        photo_data.append({
            "photo_id": p["id"],
            "taken_time": p.get("taken_time"),
            "latitude": p.get("latitude"),
            "longitude": p.get("longitude"),
            "city": p.get("city"),
            "address": p.get("address"),
            "place_name": precise_place_name,
            "place_type": p.get("place_type"),
            "time_source": p.get("time_source"),
            "location_source": p.get("location_source"),
            "location_status": p.get("location_status"),
            "scene_type": p.get("ai_scene_type"),
            "activity": p.get("ai_activity"),
            "food": p.get("ai_food", []),
            "objects": p.get("ai_objects", []),
            "landmark_or_place_hint": p.get("ai_landmark_hint"),
            "fun_fact": p.get("ai_fun_fact"),
            "confidence": p.get("ai_confidence"),
            "diary_sentence": p.get("diary_sentence"),
            "error_message": p.get("error_message"),
        })
    photo_data = sorted(photo_data, key=lambda p: p.get("taken_time") or "9999-99-99 99:99:99")

    weather_data = _build_weather_data(photo_data)

    # ---- 3. 生成日志：DeepSeek 优先，模板兜底 ----
    try:
        template_diary = generate_diary(photo_data, weather=weather_data)
        diary_data = template_diary
        if deepseek_is_configured():
            try:
                rich_context = {
                    "photos": photo_data,
                    "weather": weather_data,
                    "template": template_diary,
                    "requirements": {
                        "sort_by_time": True,
                        "include_place_intro": True,
                        "include_weather": True,
                        "language": "zh-CN",
                    },
                }
                rich_diary = generate_rich_diary(rich_context)
                diary_data = _normalize_rich_diary(rich_diary, template_diary, photo_data, weather_data)
            except Exception as e:
                logger.warning(f"DeepSeek diary generation failed, using template: {e}")
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
            user_id=request.user_id or "default",
            weather_summary=diary_data.get("weather_summary"),
            place_intro=diary_data.get("place_intro"),
            generator=diary_data.get("generator", "template"),
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
        weather_summary=diary_data.get("weather_summary"),
        place_intro=diary_data.get("place_intro"),
        generator=diary_data.get("generator", "template"),
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

    # 解析 chat_history JSON
    chat_history = []
    raw_chat = diary.get("chat_history")
    if raw_chat:
        try: chat_history = json.loads(raw_chat)
        except: pass

    return {
        "success": True,
        "diary": diary,
        "chat_history": chat_history,
        "photos": [
            {
                "photo_id": p["id"],
                "filename": p["original_filename"],
                "taken_time": p.get("taken_time"),
                "city": p.get("city"),
                "place_name": (
                    p.get("place_name")
                    if p.get("location_source") == "user"
                    or p.get("location_status") == "found"
                    else None
                ),
                "address": p.get("address"),
                "latitude": p.get("latitude"),
                "longitude": p.get("longitude"),
                "file_basename": os.path.basename(p.get("file_path", "")),
                "has_gps": bool(p.get("has_gps")),
                "time_source": p.get("time_source"),
                "location_source": p.get("location_source"),
                "scene_type": p.get("ai_scene_type"),
                "diary_sentence": p.get("diary_sentence"),
            }
            for p in photos
        ],
    }


@router.delete("/{diary_id}")
async def remove_diary(diary_id: int):
    """删除一篇日记."""
    ok = delete_diary(diary_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"日志 {diary_id} 不存在")
    return {"success": True, "message": "已删除"}


@router.get("/")
async def list_diaries(user_id: str = "default", limit: int = 20, q: str = ""):
    """获取用户的所有日志列表，支持搜索."""
    q = (q or "").strip()
    if q:
        diaries = search_diaries(user_id=user_id, query=q, limit=min(limit, 50))
    else:
        diaries = get_diaries_by_user(user_id=user_id, limit=min(limit, 50))
    return {
        "success": True,
        "count": len(diaries),
        "diaries": diaries,
    }


def _build_weather_data(photo_data: list[dict]) -> dict:
    """选择最早一张有时间和 GPS 的照片查询天气."""
    for photo in photo_data:
        if photo.get("taken_time") and photo.get("latitude") is not None and photo.get("longitude") is not None:
            return get_weather_summary(
                latitude=photo.get("latitude"),
                longitude=photo.get("longitude"),
                day_value=photo.get("taken_time"),
                city=photo.get("city"),
            )
    return get_weather_summary(None, None, None)


@router.post("/{diary_id}/refine")
async def refine_diary(diary_id: int, body: dict):
    """
    用户补充内容后重新整合日记。

    请求体: {"user_notes": "用户的补充内容文本"}
    """
    user_notes = (body or {}).get("user_notes", "")
    if not user_notes or not user_notes.strip():
        raise HTTPException(status_code=400, detail="user_notes 不能为空")

    diary = get_diary(diary_id)
    if not diary:
        raise HTTPException(status_code=404, detail=f"日志 {diary_id} 不存在")

    if not deepseek_is_configured():
        raise HTTPException(status_code=503, detail="DeepSeek 未配置，无法进行日记整合")

    from services.deepseek_client import refine_diary_with_user_notes

    try:
        refined = refine_diary_with_user_notes(diary, user_notes.strip())
    except Exception as e:
        logger.error(f"Refine diary failed: {e}")
        raise HTTPException(status_code=500, detail=f"日记整合失败: {e}")

    # 保留原日记中的客观字段
    content = refined.get("content") or diary.get("content")
    title = refined.get("title") or diary.get("title")
    keywords = refined.get("keywords") or diary.get("keywords")
    if isinstance(keywords, str):
        try: keywords = json.loads(keywords)
        except Exception: keywords = []

    # 保存精修结果
    from models.database import update_diary_refined
    try:
        update_diary_refined(
            diary_id=diary_id,
            user_notes=user_notes.strip(),
            refined_content=content,
        )
    except Exception as e:
        logger.warning(f"Failed to save refined diary: {e}")

    return {
        "success": True,
        "diary_id": diary_id,
        "title": title,
        "content": content,
        "keywords": keywords,
        "weather_summary": refined.get("weather_summary") or diary.get("weather_summary"),
        "place_intro": refined.get("place_intro") or diary.get("place_intro"),
        "generator": "deepseek-refined",
    }


@router.post("/{diary_id}/restyle")
async def restyle_diary(diary_id: int, body: dict):
    """
    换风格重新生成日记。

    请求体: {"style": "轻松" | "正式" | "简短" | "科普"}
    """
    style = (body or {}).get("style", "轻松")
    diary = get_diary(diary_id)
    if not diary:
        raise HTTPException(status_code=404, detail=f"日志 {diary_id} 不存在")
    if not deepseek_is_configured():
        raise HTTPException(status_code=503, detail="DeepSeek 未配置")

    from services.deepseek_client import restyle_diary

    try:
        result = restyle_diary(diary, style)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重新生成失败: {e}")

    return {
        "success": True,
        "diary_id": diary_id,
        "title": result.get("title") or diary.get("title"),
        "content": result.get("content"),
        "keywords": result.get("keywords") or diary.get("keywords"),
        "style": style,
        "generator": "deepseek-restyled",
    }


@router.post("/{diary_id}/chat")
async def chat_about_diary(diary_id: int, body: dict):
    """
    多轮对话 — 流式 SSE 返回 AI 回复。
    """
    from fastapi.responses import StreamingResponse

    messages = (body or {}).get("messages", [])
    diary_context = (body or {}).get("diary_context", {})

    diary = get_diary(diary_id)
    if not diary:
        raise HTTPException(status_code=404, detail="日记不存在")
    if not deepseek_is_configured():
        raise HTTPException(status_code=503, detail="DeepSeek 未配置")

    from services.deepseek_client import chat_about_diary as do_chat
    from services.deepseek_client import _chat_text_stream as stream_chat

    # 构建完整的 system prompt + messages
    import json as _json
    ctx = _json.dumps(diary_context, ensure_ascii=False, indent=2)
    system_prompt = f"""你要帮助用户完善这篇旅行日记。你可以确认修改、追问细节、给建议、补科普。用户说的为准。当用户满意时说「✅ 我已准备好整合日记」。

日记上下文: {ctx}"""

    msgs = [{"role": "system", "content": system_prompt}] + messages[-20:]

    full_reply = ""

    async def generate():
        nonlocal full_reply
        try:
            for chunk in stream_chat(msgs, temperature=0.7):
                full_reply += chunk
                yield f"data: {_json.dumps({'c': chunk})}\n\n"
            # 保存对话到数据库
            messages.append({"role": "assistant", "content": full_reply})
            try:
                from models.database import save_chat_history
                save_chat_history(diary_id, messages)
            except Exception:
                pass
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'e': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/{diary_id}/integrate")
async def integrate_chat(diary_id: int, body: dict):
    """
    把多轮对话内容整合进日记，替换原日记。

    请求体: {"messages": [...]}
    """
    messages = (body or {}).get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages 不能为空")

    diary = get_diary(diary_id)
    if not diary:
        raise HTTPException(status_code=404, detail="日记不存在")
    if not deepseek_is_configured():
        raise HTTPException(status_code=503, detail="DeepSeek 未配置")

    from services.deepseek_client import integrate_chat_history as do_integrate

    try:
        result = do_integrate(diary, messages)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"整合失败: {e}")

    content = result.get("content") or diary.get("content")
    try:
        update_diary_refined(diary_id, "通过对话整合", content)
    except Exception as e:
        logger.warning(f"Failed to save: {e}")

    return {
        "success": True,
        "diary_id": diary_id,
        "title": result.get("title") or diary.get("title"),
        "content": content,
        "keywords": result.get("keywords") or diary.get("keywords"),
        "generator": "deepseek-chat-integrated",
    }


def _normalize_rich_diary(
    rich_diary: dict,
    template_diary: dict,
    photo_data: list[dict],
    weather_data: dict,
) -> dict:
    """合并 DeepSeek 输出和模板保底字段."""
    photo_count = len(photo_data)
    summaries = rich_diary.get("photo_summaries")
    if not isinstance(summaries, list) or len(summaries) == 0:
        summaries = template_diary["photo_summaries"]

    keywords = rich_diary.get("keywords")
    if not isinstance(keywords, list) or len(keywords) == 0:
        keywords = template_diary["keywords"]

    content = rich_diary.get("content") or template_diary["content"]
    place_intro = rich_diary.get("place_intro")
    weather_summary = weather_data.get("summary") or rich_diary.get("weather_summary")

    return {
        "title": rich_diary.get("title") or template_diary["title"],
        "date": rich_diary.get("date") or template_diary["date"],
        "city": rich_diary.get("city") or template_diary["city"],
        "content": content,
        "keywords": keywords[:8],
        "photo_count": photo_count,
        "photo_summaries": summaries,
        "weather_summary": weather_summary,
        "place_intro": place_intro,
        "generator": "deepseek",
    }
