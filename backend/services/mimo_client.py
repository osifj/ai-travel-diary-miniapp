"""
小米 MiMo 多模态模型 API 客户端。

采用 OpenAI-compatible 接口格式。
配置方式:
  环境变量:
    MIMO_API_KEY   - API Key
    MIMO_BASE_URL  - API Base URL (e.g. https://api.xiaomimimo.com/v1)
    MIMO_MODEL     - 模型名称 (e.g. mimo-v2.5)
"""

import base64
import json
import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)  # 加载 backend/.env

logger = logging.getLogger(__name__)

# ---- 配置 ----
MIMO_API_KEY = os.getenv("MIMO_API_KEY", "")
MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
MIMO_MODEL = os.getenv("MIMO_MODEL", "mimo-v2.5")
MIMO_MAX_COMPLETION_TOKENS = int(os.getenv("MIMO_MAX_COMPLETION_TOKENS", "4096"))
MIMO_TEMPERATURE = float(os.getenv("MIMO_TEMPERATURE", "0.1"))
MIMO_TOP_P = float(os.getenv("MIMO_TOP_P", "0.9"))
MIMO_RESPONSE_FORMAT = os.getenv("MIMO_RESPONSE_FORMAT", "json_object")
MIMO_THINKING_TYPE = os.getenv("MIMO_THINKING_TYPE", "disabled")
MIMO_TIMEOUT_SECONDS = float(os.getenv("MIMO_TIMEOUT_SECONDS", "120"))

# ---- AI Prompt ----
ANALYSIS_PROMPT = """你是一个高精度旅行照片分析助手。请细致分析这张照片的场景、文字、物体、地点线索与旅行叙事价值。

请遵守安全要求：不要做人脸身份识别，不要判断具体人物是谁，不要推断敏感身份。

请只输出 JSON，不要输出额外解释。

字段如下：
{
  "scene_type": "场景类型，例如 restaurant, tourist_attraction, street, hotel, shopping_mall, beach, museum, transport, landscape",
  "activity": "用户可能在做什么，例如 eating, sightseeing, shopping, walking, relaxing, taking_photo",
  "food": ["如果有食物，列出食物名称；如果没有，返回空数组"],
  "objects": ["图中明显物体，尽量具体到可用于日记的名词"],
  "landmark_or_place_hint": "结合招牌、文字、建筑、环境判断地点线索；不确定则写 unknown",
  "mood": "照片氛围，例如 happy, relaxed, crowded, peaceful, romantic",
  "confidence": "high / medium / low",
  "diary_sentence": "用中文写一句自然的旅行日记描述"
}

注意：
1. 不要做人脸身份识别
2. 不要猜测具体人物是谁
3. 如果不确定，用 unknown 或 confidence: low
4. 如果图中有可读文字，请把它融合进 objects 或 landmark_or_place_hint
5. 输出必须是合法 JSON object"""


def _image_to_base64(image_path: str) -> str:
    """将图片文件编码为 base64 字符串."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _guess_image_mime(image_path: str) -> str:
    """按文件扩展名推断 MIME；失败时按预处理后的 JPEG 处理."""
    mime_type, _ = mimetypes.guess_type(image_path)
    if mime_type in {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/bmp",
        "image/heic",
        "image/heif",
    }:
        return mime_type
    return "image/jpeg"


def _build_openai_request(image_path: str) -> dict:
    """构建 OpenAI-compatible 请求体."""
    image_b64 = _image_to_base64(image_path)
    image_mime = _guess_image_mime(image_path)

    payload = {
        "model": MIMO_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是小米 MiMo 视觉理解助手。只输出用户要求的 JSON。",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": ANALYSIS_PROMPT,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_mime};base64,{image_b64}",
                        },
                    },
                ],
            }
        ],
        "max_completion_tokens": MIMO_MAX_COMPLETION_TOKENS,
        "temperature": MIMO_TEMPERATURE,
        "top_p": MIMO_TOP_P,
        "stream": False,
        "thinking": {
            "type": MIMO_THINKING_TYPE,
        },
    }

    if MIMO_RESPONSE_FORMAT:
        payload["response_format"] = {"type": MIMO_RESPONSE_FORMAT}

    return payload


def _message_content_to_text(content) -> str:
    """兼容 OpenAI-compatible 返回的 string 或 content part list."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return "" if content is None else str(content)


def _extract_json_from_response(text: str) -> Optional[dict]:
    """
    从 AI 返回的文本中提取 JSON。
    
    AI 可能返回:
      - 纯 JSON: {"scene_type": ...}
      - Markdown 代码块: ```json\n{...}\n```
      - 前后有说明文字
    """
    if not text:
        return None

    text = text.strip()

    # 尝试 1: 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试 2: 提取 Markdown JSON 代码块
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试 3: 查找第一个 { 到最后一个 } 之间的内容
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    logger.warning(f"Failed to extract JSON from response: {text[:200]}...")
    return None


def _call_api(image_path: str) -> dict:
    """
    调用 MiMo API 分析图片。
    
    返回原始响应字典 (可能包含 choices[0].message.content)。
    """
    if not MIMO_API_KEY or MIMO_API_KEY == "your_api_key_here":
        raise ValueError(
            "MIMO_API_KEY 未配置。请在 backend/.env 中设置真实的 API Key。"
        )

    # 检查 base_url 是否有效
    if not MIMO_BASE_URL or MIMO_BASE_URL == "your_mimo_base_url_here":
        raise ValueError(
            "MIMO_BASE_URL 未配置。请在 backend/.env 中设置 API Base URL。"
        )

    url = f"{MIMO_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {MIMO_API_KEY}",
        "api-key": MIMO_API_KEY,
        "Content-Type": "application/json",
    }
    payload = _build_openai_request(image_path)

    logger.info(f"Calling MiMo API: {url} with model {MIMO_MODEL}")
    logger.debug(f"Image: {image_path}")

    try:
        with httpx.Client(timeout=MIMO_TIMEOUT_SECONDS) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise RuntimeError(f"MiMo API 请求超时 ({MIMO_TIMEOUT_SECONDS:g}s)")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"MiMo API 返回错误: {e.response.status_code} {e.response.text[:300]}"
        )
    except Exception as e:
        raise RuntimeError(f"MiMo API 请求失败: {e}")


# ---- 公开接口 ----

def analyze_image(image_path: str) -> dict:
    """
    分析单张图片。
    
    参数:
      image_path: 已去除 EXIF 的压缩图片路径
    
    返回:
      {
        "scene_type": str | None,
        "activity": str | None,
        "food": list[str],
        "objects": list[str],
        "landmark_or_place_hint": str | None,
        "mood": str | None,
        "confidence": str | None,
        "diary_sentence": str | None,
        "raw_response": str | None,  # AI 原始返回 (调试用)
        "error": str | None,
      }
    """
    result = {
        "scene_type": None,
        "activity": None,
        "food": [],
        "objects": [],
        "landmark_or_place_hint": None,
        "mood": None,
        "confidence": None,
        "diary_sentence": None,
        "raw_response": None,
        "error": None,
    }

    # 检查图片是否存在
    if not os.path.exists(image_path):
        result["error"] = f"图片不存在: {image_path}"
        return result

    try:
        # 调用 MiMo API
        api_response = _call_api(image_path)

        # 提取文本
        choices = api_response.get("choices", [])
        if not choices:
            result["error"] = "MiMo API 返回空 choices"
            return result

        content = _message_content_to_text(
            choices[0].get("message", {}).get("content", "")
        )
        result["raw_response"] = content

        # 解析 JSON
        parsed = _extract_json_from_response(content)
        if parsed:
            result.update({
                "scene_type": parsed.get("scene_type"),
                "activity": parsed.get("activity"),
                "food": parsed.get("food", []),
                "objects": parsed.get("objects", []),
                "landmark_or_place_hint": parsed.get("landmark_or_place_hint"),
                "mood": parsed.get("mood"),
                "confidence": parsed.get("confidence"),
                "diary_sentence": parsed.get("diary_sentence"),
            })
        else:
            # JSON 解析失败 — 使用原始文本作为 summary
            result["diary_sentence"] = content[:200] if content else None
            result["confidence"] = "low"
            result["error"] = "JSON 解析失败，已使用原始返回作为摘要"

        return result

    except Exception as e:
        logger.error(f"analyze_image failed: {e}")
        result["error"] = str(e)
        return result


def is_configured() -> bool:
    """检查 MiMo API 是否已配置."""
    return (
        MIMO_API_KEY
        and MIMO_API_KEY != "your_api_key_here"
        and MIMO_BASE_URL
        and MIMO_BASE_URL != "your_mimo_base_url_here"
        and MIMO_MODEL
    )


def analyze_image_mock(image_path: str) -> dict:
    """
    Mock 分析 (当 MiMo API 未配置时使用).
    返回模拟的分析结果，用于开发测试。
    """
    logger.info(f"Using MOCK analysis for: {image_path}")

    # 基于文件名/path 做简单变化以展示不同结果
    import hashlib
    h = hashlib.md5(image_path.encode()).hexdigest()
    scenarios = [
        {
            "scene_type": "restaurant",
            "activity": "eating",
            "food": ["noodles", "drink"],
            "objects": ["table", "plate", "cup", "food"],
            "landmark_or_place_hint": "unknown",
            "mood": "relaxed",
            "confidence": "medium",
            "diary_sentence": "这张照片看起来是在一家餐厅用餐，桌上有面食和饮品。",
        },
        {
            "scene_type": "tourist_attraction",
            "activity": "sightseeing",
            "food": [],
            "objects": ["building", "sky", "tourists", "landmark"],
            "landmark_or_place_hint": "city landmark",
            "mood": "happy",
            "confidence": "medium",
            "diary_sentence": "这张照片看起来是在一个景点参观，画面中有城市地标。",
        },
        {
            "scene_type": "street",
            "activity": "walking",
            "food": [],
            "objects": ["street", "shops", "people", "buildings"],
            "landmark_or_place_hint": "shopping street",
            "mood": "crowded",
            "confidence": "medium",
            "diary_sentence": "这张照片看起来是在城市街道上漫步，周围很热闹。",
        },
        {
            "scene_type": "beach",
            "activity": "relaxing",
            "food": [],
            "objects": ["sea", "sand", "umbrella", "sky"],
            "landmark_or_place_hint": "coastline",
            "mood": "peaceful",
            "confidence": "medium",
            "diary_sentence": "这张照片看起来是在海边放松，景色很宁静。",
        },
        {
            "scene_type": "museum",
            "activity": "sightseeing",
            "food": [],
            "objects": ["exhibit", "artwork", "display", "interior"],
            "landmark_or_place_hint": "museum interior",
            "mood": "relaxed",
            "confidence": "medium",
            "diary_sentence": "这张照片看起来是在博物馆里参观展览。",
        },
    ]

    idx = int(h[:8], 16) % len(scenarios)
    return scenarios[idx]
