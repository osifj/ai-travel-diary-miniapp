"""
DeepSeek 文本生成客户端。

用途:
  1. MiMo 图片识别失败时，基于时间/地点生成保守兜底描述
  2. 基于照片分析结果、地点、天气生成更自然的游玩日记
  3. 接收用户补充内容，重新整合生成更完整的日记
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_MAX_COMPLETION_TOKENS = int(os.getenv("DEEPSEEK_MAX_COMPLETION_TOKENS", "4096"))
DEEPSEEK_TEMPERATURE = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.8"))
DEEPSEEK_TIMEOUT_SECONDS = float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "90"))
DEEPSEEK_THINKING_TYPE = os.getenv("DEEPSEEK_THINKING_TYPE", "disabled")


def is_configured() -> bool:
    return bool(DEEPSEEK_API_KEY and DEEPSEEK_API_KEY != "your_deepseek_api_key_here")


def _extract_json(text: str) -> Optional[dict]:
    if not text: return None
    text = text.strip()
    try: return json.loads(text)
    except json.JSONDecodeError: pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        try: return json.loads(m.group(1))
        except json.JSONDecodeError: pass
    s = text.find("{"); e = text.rfind("}")
    if s != -1 and e != -1 and e > s:
        try: return json.loads(text[s:e+1])
        except json.JSONDecodeError: pass
    return None


def _chat_json(messages: list[dict], temperature: Optional[float] = None) -> dict:
    if not is_configured(): raise ValueError("DEEPSEEK_API_KEY 未配置")
    url = f"{DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": DEEPSEEK_MODEL, "messages": messages,
        "temperature": DEEPSEEK_TEMPERATURE if temperature is None else temperature,
        "max_completion_tokens": DEEPSEEK_MAX_COMPLETION_TOKENS,
        "response_format": {"type": "json_object"}, "stream": False,
        "thinking": {"type": DEEPSEEK_THINKING_TYPE},
    }
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    logger.info(f"Calling DeepSeek API: {url} with model {DEEPSEEK_MODEL}")
    try:
        with httpx.Client(timeout=DEEPSEEK_TIMEOUT_SECONDS) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise RuntimeError(f"DeepSeek API timeout ({DEEPSEEK_TIMEOUT_SECONDS:g}s)")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"DeepSeek API error: {e.response.status_code}")
    choices = data.get("choices", [])
    if not choices: raise RuntimeError("DeepSeek returned empty choices")
    content = choices[0].get("message", {}).get("content", "")
    parsed = _extract_json(content)
    if not parsed: raise RuntimeError(f"DeepSeek JSON parse failed: {content[:200]}")
    return parsed


def generate_photo_fallback(photo_context: dict) -> dict:
    prompt = f"""你无法看到图片，只能根据已知元数据写保守兜底描述。
已知: {json.dumps(photo_context, ensure_ascii=False)}
输出 JSON: {{"scene_type":"unknown","activity":"unknown","food":[],"objects":[],"landmark_or_place_hint":"unknown","fun_fact":"","confidence":"low","diary_sentence":"..."}}"""
    return _chat_json([{"role":"system","content":"你是谨慎的旅行日志助手。"},{"role":"user","content":prompt}], temperature=0.2)


def generate_rich_diary(context: dict) -> dict:
    """生成更丰富、按时间顺序、带科普描述的游玩日记."""
    prompt = f"""请根据以下旅行照片分析数据，写一篇自然、有知识性的中文游玩日记。

数据:
{json.dumps(context, ensure_ascii=False, indent=2)}

请只输出 JSON:
{{
  "title": "简洁标题",
  "date": "YYYY-MM-DD 或 unknown",
  "city": "城市名或未知城市",
  "place_intro": "1-2句该地点有意思的介绍。只写你有把握的常识；不确定就写轻量概括。",
  "weather_summary": "1句天气简介；如果 weather.summary 存在，必须原样使用 weather.summary。",
  "content": "一段或多段中文日记。必须按照片 taken_time 顺序描写。对每张照片中识别到的食物、场景、物体，可以自然融入简短的科普描述（如食材来历、建筑风格、地方文化等）。科普必须基于数据中已有的 fun_fact 或 food/objects 字段，不可凭空编造。语言自然流畅，有画面感和知识性。",
  "keywords": ["3到8个关键词"],
  "photo_summaries": [
    {{
      "taken_time": "照片时间或 null",
      "city": "城市或 null",
      "address": "地址或 null",
      "place_name": "地点名或 null",
      "time_source": "exif/user/unknown",
      "location_source": "exif/user/ai/unknown",
      "location_status": "found/approximate/unknown",
      "scene_type": "场景",
      "activity": "活动",
      "diary_sentence": "该照片的一句自然描述"
    }}
  ]
}}

写作要求:
1. 严格按照片时间顺序描写；无时间的照片放在最后。
2. 有 EXIF/用户地点时优先使用真实地点；AI 推测地点必须写得保守。
3. 食物、物体、活动、科普只使用数据里已有的内容（fun_fact、food、objects 等字段），不新增不存在细节。
4. 天气只允许使用 weather.summary 或 weather 字段里的温度/降雨；weather_summary 必须原样等于 weather.summary。
5. location_status 为 approximate 时不要把 place_name 当精确地点，只写城市或区域附近。
6. 不要写心情/氛围标签（如 happy、轻松、愉快），用事实和观察叙事。
7. 不要编造窗外、躲雨、人不多、去了某景点等数据未支持的细节。
8. 每张照片如果 fun_fact 非空，在正文中自然融入该科普信息。
9. 不要输出 Markdown，不要输出额外解释。"""

    return _chat_json([
        {"role": "system", "content": "你是中文旅行日记写作者。重事实、会叙事、善用科普知识丰富内容，不编造，不写心情。"},
        {"role": "user", "content": prompt},
    ], temperature=0.55)


def refine_diary_with_user_notes(original_diary: dict, user_notes: str) -> dict:
    """接收用户补充内容，重新整合生成更完整的日记."""
    prompt = f"""请将用户补充的信息整合进原有旅行日记，重新输出一篇更完整的日记。

原有日记:
{json.dumps(original_diary, ensure_ascii=False, indent=2)}

用户补充内容:
{user_notes}

请只输出 JSON:
{{
  "title": "可更新的标题",
  "date": "YYYY-MM-DD",
  "city": "城市名",
  "place_intro": "1-2句地点介绍",
  "weather_summary": "天气简介（保留原日记中的天气信息）",
  "content": "整合后的完整日记。保留原日记中基于照片识别的客观内容（场景、食物、物体、科普、天气），将用户补充的信息自然融入相应的段落。用户提到的地点可加入简短的常识性科普。不要编造用户未提及的内容。",
  "keywords": ["更新后的关键词"],
  "photo_summaries": "保留原日记中 photo_summaries 不变"
}}

整合原则:
1. 原日记中基于照片数据的内容（场景、物体、食物、fun_fact）全部保留
2. 用户补充的内容自然融入对应位置（如用户说中午在某餐厅，就插入到对应时间段）
3. 用户提到的地点可以加入简短常识科普（如尖沙咀是香港九龙半岛南端的商业和旅游中心）
4. 用户提到的食物可以加入食材文化介绍
5. 不要写心情/氛围标签
6. 不要编造用户未提到的细节
7. 保留原始天气和地点介绍"""

    return _chat_json([
        {"role": "system", "content": "你是中文旅行日记写作者。善于整合用户回忆与AI识别内容，加入适当科普，不编造，不写心情。"},
        {"role": "user", "content": prompt},
    ], temperature=0.6)
