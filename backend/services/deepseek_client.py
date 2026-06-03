"""
DeepSeek 文本生成客户端。

用途:
  1. MiMo 图片识别失败时，基于时间/地点生成保守兜底描述
  2. 基于照片分析结果、地点、天气生成更自然的游玩日记
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
    """检查 DeepSeek 是否已配置."""
    return bool(
        DEEPSEEK_API_KEY
        and DEEPSEEK_API_KEY != "your_deepseek_api_key_here"
        and DEEPSEEK_BASE_URL
        and DEEPSEEK_MODEL
    )


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None

    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


def _chat_json(messages: list[dict], temperature: Optional[float] = None) -> dict:
    if not is_configured():
        raise ValueError("DEEPSEEK_API_KEY 未配置")

    url = f"{DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": DEEPSEEK_TEMPERATURE if temperature is None else temperature,
        "max_completion_tokens": DEEPSEEK_MAX_COMPLETION_TOKENS,
        "response_format": {"type": "json_object"},
        "stream": False,
        "thinking": {"type": DEEPSEEK_THINKING_TYPE},
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    logger.info(f"Calling DeepSeek API: {url} with model {DEEPSEEK_MODEL}")
    try:
        with httpx.Client(timeout=DEEPSEEK_TIMEOUT_SECONDS) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        raise RuntimeError(f"DeepSeek API 请求超时 ({DEEPSEEK_TIMEOUT_SECONDS:g}s)")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"DeepSeek API 返回错误: {e.response.status_code} {e.response.text[:300]}"
        )
    except Exception as e:
        raise RuntimeError(f"DeepSeek API 请求失败: {e}")

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("DeepSeek API 返回空 choices")

    content = choices[0].get("message", {}).get("content", "")
    parsed = _extract_json(content)
    if not parsed:
        raise RuntimeError(f"DeepSeek JSON 解析失败: {content[:200]}")
    return parsed


def generate_photo_fallback(photo_context: dict) -> dict:
    """MiMo 失败时，基于已知时间/地点生成保守文本兜底，不假装看见图片内容."""
    prompt = f"""你无法看到图片，只能根据已知元数据写保守兜底描述。

已知信息:
{json.dumps(photo_context, ensure_ascii=False, indent=2)}

请只输出 JSON:
{{
  "scene_type": "unknown",
  "activity": "unknown",
  "food": [],
  "objects": [],
  "landmark_or_place_hint": "地点线索或 unknown",
  "mood": "unknown",
  "confidence": "low",
  "diary_sentence": "一句中文说明：这张照片记录于什么时间/地点，但图片内容识别失败"
}}

要求:
1. 不要编造图片里出现的物体、食物、人物、店名。
2. 如果有时间/地点，就自然写入 diary_sentence。
3. 输出合法 JSON object。"""
    return _chat_json([
        {"role": "system", "content": "你是谨慎的旅行日志助手，只基于给定事实写作。"},
        {"role": "user", "content": prompt},
    ], temperature=0.2)


def generate_rich_diary(context: dict) -> dict:
    """生成更丰富、按时间顺序、带地点介绍和天气简介的游玩日记."""
    prompt = f"""请根据以下旅行照片分析数据，写一篇自然、有趣、可读的中文游玩日记。

数据:
{json.dumps(context, ensure_ascii=False, indent=2)}

请只输出 JSON:
{{
  "title": "简洁标题",
  "date": "YYYY-MM-DD 或 unknown",
  "city": "城市名或未知城市",
  "place_intro": "1-2句该地点有意思的介绍。只写你有把握的常识；不确定就写轻量概括。",
  "weather_summary": "1句天气简介；如果 weather.summary 存在，必须原样使用 weather.summary。",
  "content": "一段或多段中文日记。必须按照片 taken_time 顺序描写；先写地点介绍和天气，再写当天经历。语言自然，有画面感，不要流水账。",
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
      "diary_sentence": "该照片的一句自然描述",
      "mood": "氛围"
    }}
  ]
}}

写作要求:
1. 严格按照片时间顺序描写；无时间的照片放在最后。
2. 有 EXIF/用户地点时，优先使用真实地点；AI 推测地点必须写得保守。
3. 食物、物体、活动只使用数据里已有内容，不要新增不存在细节。
4. 天气只允许使用 weather.summary 或 weather 字段里的温度/降雨/天气代码含义；如果 weather.summary 存在，weather_summary 必须原样等于 weather.summary；不要添加湿度、风力、体感、空气湿润、潮闷等未提供数据。
5. 如果 location_status 是 approximate，不要把 place_name 当精确到店/景点；只写城市或区域附近。
6. 不要写“躲雨”“窗外”“窗外下雨”“人不多”“去了某景点”等照片数据没有支持的细节。
7. 日记要像人写的旅行记录，可以有轻微情绪和观察，但所有具体物体、地点、天气体感必须来自数据。
8. 不要输出 Markdown，不要输出额外解释。"""

    return _chat_json([
        {"role": "system", "content": "你是中文旅行日记写作者，重事实、会叙事、不过度编造。"},
        {"role": "user", "content": prompt},
    ], temperature=0.55)
