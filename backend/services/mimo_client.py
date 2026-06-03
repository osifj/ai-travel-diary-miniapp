"""
小米 MiMo 多模态模型 API 客户端。

采用 OpenAI-compatible 接口格式。
功能:
  1. 单张图片分析 (analyze_image)
  2. 批量图片生成全流程日记 (generate_diary_from_photos)
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

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

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

# ---- 图片分析 Prompt (已移除人脸限制) ----
ANALYSIS_PROMPT = """你是旅行场景分析专家。请仔细观察这张照片的所有细节——场景、人物、文字、物体、光线、氛围——输出精准的结构化分析。

输出 JSON:
{
  "scene_type": "restaurant | hotel_lobby | hotel_room | street_market | museum | temple | beach | mountain | airport | train_station | shopping_mall | cafe | bar | garden | landmark | viewpoint | night_market | convenience_store | subway | ferry | street | scenic_spot | park | other",
  "scene_subtype": "更细粒度分类，如 restaurant→dim_sum / hotpot / ramen / seafood / fine_dining / street_food / cafe",
  "activity": "eating | sightseeing | taking_photo | shopping | hiking | waiting | commuting | checking_in | swimming | relaxing | walking | posing",
  "food": ["具体菜名，包含菜系和做法，如 鲜虾云吞面、麻辣火锅、提拉米苏"],
  "drinks": ["具体饮品，如 冻柠茶、手冲咖啡、清酒"],
  "objects": ["具体可写进日记的物体，含品牌如果可见"],
  "readable_text": ["图中可读文字：店名、路牌、菜单、标语、价格等"],
  "people_description": "图中人物的数量、大致年龄范围、行为、着装特点。可以描述外貌和动作，但不要尝试识别具体身份。例如：两位年轻女性在自拍，穿着夏装，面带笑容",
  "landmark_hint": "结合招牌/建筑/环境判断具体地点。有把握写具体名，不确定写区域+类型",
  "atmosphere": "光线特征+空间特征，如 午后自然光从落地窗洒入、暖黄灯光居酒屋吧台、开阔山顶俯瞰城市",
  "photo_quality": "构图/光线描述，如 逆光剪影、微距特写、广角全景、俯拍",
  "fun_fact": "基于图中内容，写1-2句有趣的科普。比如菜系来历、建筑风格、器物文化。要有'人味'——像朋友聊天时的有趣冷知识",
  "confidence": "high | medium | low",
  "diary_sentence": "一句有画面感的中文旅行日记。不是'在餐厅吃饭'，而是'坐在窗边吃一碗冒着热气的鲜虾云吞面，窗外是旺角的霓虹灯'"
}

要求:
1. scene_type 用细分类别，不要全归为 restaurant/tourist_attraction
2. food/drinks 分开列，具体到菜名和做法
3. readable_text 捕获所有可见中文/英文文字
4. people_description 可以描述外貌、人数、行为、着装，不要回避人物
5. atmosphere 用客观光线+空间描述
6. fun_fact 像朋友聊天时的冷知识，不写维基百科
7. diary_sentence 有具体细节和画面感
8. 输出必须是合法 JSON object"""

# ---- 全流程日记生成 Prompt ----
DIARY_FROM_ANALYSIS_PROMPT = """你是旅行文学作家。请根据以下照片的结构化分析数据，写一篇自然、有信息量、有叙事感的中文游记。

写作风格：
- 像朋友写的旅行日记，有具体感官细节
- 有恰到好处的科普（在描述中自然带出）
- 按时间线叙事，有节奏感
- 具体 > 抽象，观察 > 感受
- 可以描述同行的人和有趣互动

照片分析数据:
{analysis_data}

地点和时间上下文:
{context}

请只输出 JSON:
{{
  "title": "有吸引力的标题，如'九龙城的午后：从云吞面到启德机场旧址'",
  "date": "YYYY-MM-DD",
  "city": "城市",
  "place_intro": "1-2句开篇引子，像杂志文章第一段",
  "weather_summary": "天气简述（使用提供的天气数据）",
  "content": "正文。按时间顺序叙事，每段围绕1-2张照片展开。具体感官描写优先。科普自然融入叙述。可以有对话感和人物描写。全文300-800字。",
  "keywords": ["5-8个具体关键词"],
  "photo_summaries": [
    {{
      "taken_time": "照片时间",
      "city": "城市",
      "place_name": "地点名",
      "scene_type": "场景",
      "activity": "活动",
      "diary_sentence": "该照片的日记描述"
    }}
  ]
}}

原则:
- 可以描述人物（外貌、行为、互动），增加人性化叙事
- 具体 > 抽象：'竹升面在沸水里翻滚了30秒' > '面条很美味'
- 观察 > 感受：'午后阳光透过梧桐叶洒在石板路上' > '感觉很惬意'
- fun_fact 自然融入对应事物的描写中
- 不编造数据中没有的内容
- 输出必须是合法 JSON object"""


def _image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _guess_image_mime(image_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(image_path)
    if mime_type in {"image/jpeg","image/png","image/gif","image/webp","image/bmp","image/heic","image/heif"}:
        return mime_type
    return "image/jpeg"


def _extract_json_from_response(text: str) -> Optional[dict]:
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
    logger.warning(f"Failed to extract JSON: {text[:200]}...")
    return None


def _content_to_text(content) -> str:
    if isinstance(content, str): return content
    if isinstance(content, list):
        return "\n".join(
            item.get("text","") if isinstance(item,dict) else str(item)
            for item in content
        )
    return "" if content is None else str(content)


def _call_api_with_images(image_paths: list[str], prompt: str, system_msg: str = "你是小米 MiMo。只输出 JSON。", temperature: float = None, max_tokens: int = None) -> dict:
    """通用 MiMo 调用，支持单图或多图。"""
    if not MIMO_API_KEY or MIMO_API_KEY == "your_api_key_here":
        raise ValueError("MIMO_API_KEY 未配置")
    if not MIMO_BASE_URL or MIMO_BASE_URL == "your_mimo_base_url_here":
        raise ValueError("MIMO_BASE_URL 未配置")

    user_content = [{"type": "text", "text": prompt}]
    for img_path in image_paths:
        b64 = _image_to_base64(img_path)
        mime = _guess_image_mime(img_path)
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"}
        })

    payload = {
        "model": MIMO_MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_content},
        ],
        "max_completion_tokens": max_tokens or MIMO_MAX_COMPLETION_TOKENS,
        "temperature": temperature if temperature is not None else MIMO_TEMPERATURE,
        "top_p": MIMO_TOP_P,
        "stream": False,
        "thinking": {"type": MIMO_THINKING_TYPE},
    }
    if MIMO_RESPONSE_FORMAT:
        payload["response_format"] = {"type": MIMO_RESPONSE_FORMAT}

    url = f"{MIMO_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {MIMO_API_KEY}",
        "api-key": MIMO_API_KEY,
        "Content-Type": "application/json",
    }

    logger.info(f"Calling MiMo: {url} model={MIMO_MODEL} images={len(image_paths)}")

    try:
        with httpx.Client(timeout=MIMO_TIMEOUT_SECONDS) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        raise RuntimeError(f"MiMo API 超时 ({MIMO_TIMEOUT_SECONDS:g}s)")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"MiMo API 错误: {e.response.status_code}")
    except Exception as e:
        raise RuntimeError(f"MiMo API 请求失败: {e}")


# ---- 公开接口 ----

def analyze_image(image_path: str) -> dict:
    """分析单张图片（细粒度，已去人脸限制）。"""
    result = {
        "scene_type": None, "scene_subtype": None, "activity": None,
        "food": [], "drinks": [], "objects": [], "readable_text": [],
        "landmark_hint": None, "atmosphere": None, "photo_quality": None,
        "people_description": None, "fun_fact": None,
        "confidence": None, "diary_sentence": None,
        "raw_response": None, "error": None,
    }

    if not os.path.exists(image_path):
        result["error"] = f"图片不存在: {image_path}"
        return result

    try:
        api_response = _call_api_with_images(
            [image_path], ANALYSIS_PROMPT,
            system_msg="你是旅行照片分析专家。仔细观察每个细节，只输出要求的 JSON。",
            temperature=0.1, max_tokens=4096
        )
        choices = api_response.get("choices", [])
        if not choices:
            result["error"] = "MiMo 返回空 choices"
            return result
        content = _content_to_text(choices[0].get("message", {}).get("content", ""))
        result["raw_response"] = content
        parsed = _extract_json_from_response(content)
        if parsed:
            for k in result:
                if k in parsed and k not in ("raw_response", "error"):
                    result[k] = parsed[k]
        else:
            result["diary_sentence"] = content[:200] if content else None
            result["confidence"] = "low"
            result["error"] = "JSON 解析失败"
        return result
    except Exception as e:
        logger.error(f"analyze_image failed: {e}")
        result["error"] = str(e)
        return result


def generate_diary_from_analysis(photo_analyses: list[dict], context: dict) -> dict:
    """MiMo 基于分析结果生成全流程日记。每张照片的分析包含 scene_type/activity/food/objects/people/fun_fact/diary_sentence 等。"""
    prompt = DIARY_FROM_ANALYSIS_PROMPT.format(
        analysis_data=json.dumps(photo_analyses, ensure_ascii=False, indent=2),
        context=json.dumps(context, ensure_ascii=False, indent=2),
    )

    result = {
        "title": None, "date": None, "city": None,
        "place_intro": None, "weather_summary": None,
        "content": None, "keywords": [], "photo_summaries": [],
        "error": None,
    }

    try:
        api_response = _call_api_with_images(
            [], prompt,
            system_msg="你是旅行文学作家。重事实、会叙事、有品味。只输出 JSON。",
            temperature=0.55, max_tokens=8192
        )
        choices = api_response.get("choices", [])
        if not choices:
            result["error"] = "MiMo diary 返回空 choices"
            return result
        content = _content_to_text(choices[0].get("message", {}).get("content", ""))
        parsed = _extract_json_from_response(content)
        if parsed:
            for k in result:
                if k in parsed and k not in ("error",):
                    result[k] = parsed[k]
        else:
            result["error"] = "MiMo diary JSON 解析失败"
        return result
    except Exception as e:
        logger.error(f"generate_diary_from_analysis failed: {e}")
        result["error"] = str(e)
        return result


def is_configured() -> bool:
    return bool(MIMO_API_KEY and MIMO_API_KEY != "your_api_key_here" and MIMO_BASE_URL and MIMO_BASE_URL != "your_mimo_base_url_here")


def analyze_image_mock(image_path: str) -> dict:
    """Mock 分析。"""
    import hashlib
    logger.info(f"MOCK analysis: {image_path}")
    h = hashlib.md5(image_path.encode()).hexdigest()
    idx = int(h[:8], 16) % 5
    scenarios = [
        {"scene_type":"restaurant","scene_subtype":"dim_sum","activity":"eating","food":["鲜虾云吞面","丝袜奶茶"],"drinks":["冻柠茶"],"objects":["餐桌","碗碟","筷子","菜单"],"readable_text":["兰芳园","云吞面 $42"],"people_description":"两位年轻人在靠窗位置用餐，穿着休闲夏装","landmark_hint":"旺角兰芳园茶餐厅","atmosphere":"暖黄灯光，窗外是旺角街景","photo_quality":"俯拍餐桌特写","fun_fact":"云吞面是香港经典平民美食，竹升面用竹竿反复压打，面条筋道弹牙","confidence":"medium","diary_sentence":"午后坐在旺角兰芳园的窗边，一碗冒着热气的鲜虾云吞面配上冻柠茶，窗外人来人往"},
        {"scene_type":"landmark","scene_subtype":"viewpoint","activity":"sightseeing","food":[],"drinks":[],"objects":["城市天际线","观景台","望远镜"],"people_description":"几名游客在观景台拍照","landmark_hint":"太平山顶凌霄阁","atmosphere":"黄昏金色阳光洒在城市建筑上","photo_quality":"广角全景","fun_fact":"太平山顶海拔552米，是香港岛最高点，山顶缆车自1888年运营至今","confidence":"high","diary_sentence":"黄昏时分站在太平山顶，维多利亚港两岸的摩天大楼在金色阳光中渐次亮起灯光"},
        {"scene_type":"street_market","scene_subtype":"wet_market","activity":"shopping","food":["新鲜水果","烧腊"],"drinks":[],"objects":["水果摊","烧腊档","霓虹招牌","手推车"],"people_description":"摊主在切烧鹅，几位顾客在挑选水果","landmark_hint":"旺角街市","atmosphere":"热闹的市井气息，红灯笼和霓虹招牌交织","photo_quality":"街头抓拍","fun_fact":"香港街市的烧腊档一般凌晨三四点就开炉，烧鹅要经过上皮、风干、烤制三道工序","confidence":"medium","diary_sentence":"穿过旺角街市，烧腊档飘来的蜜汁香气混合着水果摊的热带果香，是香港最真实的人间烟火"},
        {"scene_type":"beach","scene_subtype":"sandy_beach","activity":"relaxing","food":[],"drinks":["椰子"],"objects":["沙滩","遮阳伞","沙滩巾","椰青"],"people_description":"几组游客在沙滩上晒太阳、游泳","landmark_hint":"浅水湾","atmosphere":"正午烈日，海水湛蓝","photo_quality":"广角海岸线","fun_fact":"浅水湾沙滩的沙是人工运来的，原本这里是岩石海岸，英殖时期为打造度假胜地从海南运来细沙","confidence":"high","diary_sentence":"浅水湾的午后，烈日把沙滩晒得发烫，抱着椰青躲进遮阳伞下看海浪一层层推上来"},
        {"scene_type":"museum","scene_subtype":"art_museum","activity":"sightseeing","food":[],"drinks":[],"objects":["画作","雕塑","展厅","解说牌"],"people_description":"几位参观者在画作前驻足讨论","landmark_hint":"M+博物馆","atmosphere":"冷白展厅灯光，挑高空间","photo_quality":"展厅内部拍摄","fun_fact":"M+博物馆是亚洲首个全球性当代视觉文化博物馆，建筑由赫尔佐格和德梅隆设计","confidence":"high","diary_sentence":"在 M+ 的挑高展厅里，冷白灯光下每个人都放慢了脚步，连说话声都变得轻柔"},
    ]
    return scenarios[idx]
