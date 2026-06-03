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
ANALYSIS_PROMPT = """你是旅行场景分析专家。请仔细观察这张照片的所有细节——场景、人物、文字、物体、光线、氛围、时间线索、地点线索——输出精准的结构化分析。

如果提供了已知的地理位置信息，请结合你对这个地点的了解，交叉验证图片中的线索。
{location_hint}

输出 JSON:
{
  "scene_type": "restaurant | hotel_lobby | hotel_room | street_market | museum | temple | beach | mountain | airport | train_station | shopping_mall | cafe | bar | garden | landmark | viewpoint | night_market | convenience_store | subway | ferry | street | scenic_spot | park | other",
  "scene_subtype": "更细粒度分类，如 restaurant→dim_sum / hotpot / ramen / seafood / fine_dining / street_food / cafe",
  "activity": "eating | sightseeing | taking_photo | shopping | hiking | waiting | commuting | checking_in | swimming | relaxing | walking | posing",
  "food": ["具体菜名，包含菜系和做法，如 鲜虾云吞面、麻辣火锅、提拉米苏"],
  "drinks": ["具体饮品，如 冻柠茶、手冲咖啡、清酒"],
  "objects": ["具体可写进日记的物体，含品牌如果可见"],
  "readable_text": ["图中可读文字：店名、路牌、菜单、标语、价格等"],
  "people_description": "图中人物的数量、大致年龄范围、行为、着装特点。可以描述外貌和动作",
  "time_of_day": "根据光线、阴影角度、天空颜色推断具体时间。如：清晨六点薄雾、上午九点阳光斜照、正午十二点烈日、下午四点金色阳光、傍晚七点晚霞、夜晚十点霓虹灯。写出具体的光线特征和时间感",
  "season_hint": "根据植被、服装、天气推断季节",
  "location_clues": "逐条列出所有地点线索：建筑风格（骑楼/唐楼/玻璃幕墙）、招牌文字语言、植被类型、路面材质、交通工具型号颜色、路牌样式。每条都要具体",
  "geo_verification": "如果提供了地理位置，结合你对这个地点的了解，验证图片内容是否吻合。如：已知在'旺角弥敦道'，图片中确实可见弥敦道特征的大厦和招牌",
  "landmark_hint": "综合所有线索+地理位置判断具体地点名",
  "atmosphere": "光线+空间+时间+地点的融合描述。如：下午四点的阳光从弥敦道西侧大厦间隙穿过，在骑楼下投出明暗交替的光带",
  "photo_quality": "构图/光线描述",
  "fun_fact": "基于图中内容+你对这个地点的了解，写1-2句冷知识。地名来历、建筑历史、街区特色",
  "confidence": "high | medium | low",
  "diary_sentence": "一句包含具体时间+具体地点的旅行日记。如：下午四点站在弥敦道和旺角道的十字路口，绿灯亮起的瞬间人潮从四面涌来"
}

要求:
1. scene_type 用细分类别
2. food/drinks 分开列，具体到菜名
3. readable_text 捕获所有文字
4. people_description 可描述外貌、行为、着装
5. time_of_day 必须根据光线/阴影推断，越具体越好
6. location_clues 必须逐条列出，像侦探一样分析每个细节
7. geo_verification 交叉验证地理位置和图片内容
8. atmosphere 融合时间+空间+地点
9. diary_sentence 必须有时间词+地名
10. fun_fact 结合地点知识，不写维基百科
11. 输出必须是合法 JSON object"""

# ---- 全流程日记生成 Prompt ----
DIARY_FROM_ANALYSIS_PROMPT = """你是旅行文学作家，对香港及世界各地的地理、街道、建筑、历史有深入了解。请根据照片分析数据和地理位置，写一篇自然、有信息量、有叙事感的中文游记。

核心要求——利用你的地理知识丰富游记：
- 🌏 如果已知照片拍于具体街道/区域（如'中环德辅道中'），你必须激活你对这个地点的了解：这条街的历史、沿街有什么建筑/店铺、周边有什么地标、为什么叫这个名字
- ⏰ 每一段开头必须先交代具体时间（如'早上八点从中环地铁站A口出来'）
- 📍 每一段必须锚定具体地点，不仅仅是区名，要到街道级别（如'德辅道中和毕打街的十字路口'而非'中环'）
- 🚶 地点之间的过渡要有空间感和距离感（如'沿着德辅道中往西走五分钟就到了...'）
- 📖 在描述地点时自然融入你对这个地方的知识——建筑的历史、街名的由来、附近出名的店铺

写作风格：
- 像朋友写的旅行日记，有具体感官细节
- 地理知识自然融入叙述，不突兀
- 按时间线+空间线双重叙事
- 具体 > 抽象，观察 > 感受

照片分析数据:
{analysis_data}

地点和时间上下文:
{context}

请只输出 JSON:
{{
  "title": "有吸引力的标题，必须包含时间+具体地点，如'上午十点的中环德辅道中：从叮叮车到陆羽茶室'",
  "date": "YYYY-MM-DD",
  "city": "城市",
  "place_intro": "1-2句开篇引子，交代地点+时间+天气+你对这个地点的了解。如：德辅道中是中环的主动脉，沿着这条街走，左手是汇丰银行总部，右手是渣打银行大厦，抬头能看见中银大厦的三角切面在阳光下闪着银光",
  "weather_summary": "天气简述",
  "content": "正文。严格按时序+空间线叙事。每段必须有时间+具体街道/地点。要写出街道的特征（宽度、建筑风格、人流密度、声音气味）。结合你对这个地点的知识——这条街为什么叫这个名字、旁边有什么出名的店或建筑。全文300-800字。",
  "keywords": ["5-8个关键词，必须包含具体地名和街道名"],
  "photo_summaries": [
    {{
      "taken_time": "照片时间",
      "city": "城市",
      "place_name": "具体地点名，要到街道级别",
      "scene_type": "场景",
      "activity": "活动",
      "diary_sentence": "一句话描述，必须有时间+具体地点+你对该地的一个有趣知识"
    }}
  ]
}}

原则:
- 地点是灵魂：用你的地理知识让每段都像一篇微型城市导览
- 时间线是骨架：'几点几分'或'上午/下午/傍晚'
- 空间线是血肉：'从A街走到B街'、'坐叮叮车从西环到中环'
- 地名要具体到街道级别，不像'中环'、'尖沙咀'这种大区域
- 每张照片充分利用 geo_verification 和 location_clues 来定位
- 不编造数据中没有的内容，但可以补充你对这个地点已有的常识
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

def analyze_image(image_path: str, location_context: str = "") -> dict:
    """分析单张图片（细粒度，已去人脸限制）。location_context 可选，如 '香港中环德辅道中'。"""
    result = {
        "scene_type": None, "scene_subtype": None, "activity": None,
        "food": [], "drinks": [], "objects": [], "readable_text": [],
        "landmark_hint": None, "atmosphere": None, "photo_quality": None,
        "people_description": None, "fun_fact": None,
        "time_of_day": None, "season_hint": None, "location_clues": None,
        "confidence": None, "diary_sentence": None,
        "raw_response": None, "error": None,
    }

    if not os.path.exists(image_path):
        result["error"] = f"图片不存在: {image_path}"
        return result

    try:
        # 构建带位置上下文的 prompt
        loc_hint = f"已知地理位置: {location_context}" if location_context else "无已知地理位置，请仅根据图片内容分析"
        prompt = ANALYSIS_PROMPT.replace('{location_hint}', loc_hint)
        api_response = _call_api_with_images(
            [image_path], prompt,
            system_msg="你是旅行照片分析专家。仔细观察每个细节，结合地理知识分析。只输出要求的 JSON。",
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
        {"scene_type":"restaurant","scene_subtype":"dim_sum","activity":"eating","food":["鲜虾云吞面","丝袜奶茶"],"drinks":["冻柠茶"],"objects":["餐桌","碗碟","筷子","菜单"],"readable_text":["兰芳园","云吞面 $42"],"people_description":"两位年轻人在靠窗位置用餐，穿着休闲夏装","time_of_day":"下午三点，阳光从窗外斜射进来，在木桌上投下光斑","season_hint":"夏季，短袖着装","location_clues":"繁体中文招牌、典型的港式茶餐厅卡座布局、马赛克地砖、窗外可见密集的霓虹招牌和双层巴士","landmark_hint":"旺角兰芳园茶餐厅","atmosphere":"下午暖黄阳光洒在木桌上，窗外是旺角人来人往的街景","photo_quality":"俯拍餐桌特写","fun_fact":"云吞面是香港经典平民美食，竹升面用竹竿反复压打，面条筋道弹牙","confidence":"medium","diary_sentence":"下午三点，坐在旺角兰芳园的窗边，一碗冒着热气的鲜虾云吞面配上冻柠茶，午后的阳光把木桌晒得发暖"},
        {"scene_type":"landmark","scene_subtype":"viewpoint","activity":"sightseeing","food":[],"drinks":[],"objects":["城市天际线","观景台","望远镜"],"people_description":"几名游客在观景台拍照","time_of_day":"黄昏时分，太阳正在西沉，天空呈现金色到粉色的渐变","season_hint":"夏季，日落较晚，天色仍亮","location_clues":"俯瞰维港两岸的高楼群，远处可见青马大桥轮廓，观景台护栏是凌霄阁标志性设计","landmark_hint":"太平山顶凌霄阁","atmosphere":"黄昏金色阳光洒在城市建筑上，海面泛着金光","photo_quality":"广角全景","fun_fact":"太平山顶海拔552米，是香港岛最高点，山顶缆车自1888年运营至今","confidence":"high","diary_sentence":"傍晚六点站在太平山顶，维多利亚港两岸的摩天大楼在夕阳中渐次亮起灯光"},
        {"scene_type":"street_market","scene_subtype":"wet_market","activity":"shopping","food":["新鲜水果","烧腊"],"drinks":[],"objects":["水果摊","烧腊档","霓虹招牌","手推车"],"people_description":"摊主在切烧鹅，几位顾客在挑选水果","time_of_day":"上午十点左右，阳光从骑楼缝隙照进来","season_hint":"深秋，长袖薄外套","location_clues":"密集的霓虹招牌竖排繁体字、骑楼建筑、街市地面潮湿、烧腊档挂着一排烧鹅叉烧","landmark_hint":"旺角街市","atmosphere":"热闹的市井气息，红灯笼和霓虹招牌交织，上午的阳光从头顶的帆布棚缝隙漏下来","photo_quality":"街头抓拍","fun_fact":"香港街市的烧腊档一般凌晨三四点就开炉，烧鹅要经过上皮、风干、烤制三道工序","confidence":"medium","diary_sentence":"上午十点穿过旺角街市，烧腊档飘来的蜜汁香气混合着水果摊的热带果香，阳光从招牌缝隙洒在湿漉漉的地面上"},
        {"scene_type":"beach","scene_subtype":"sandy_beach","activity":"relaxing","food":[],"drinks":["椰子"],"objects":["沙滩","遮阳伞","沙滩巾","椰青"],"people_description":"几组游客在沙滩上晒太阳、游泳","time_of_day":"正午十二点，烈日当头","season_hint":"盛夏，沙滩上都是遮阳伞","location_clues":"新月形沙滩、背后是低矮山丘和豪宅区、海水呈蓝绿色、沙滩坡度平缓","landmark_hint":"浅水湾","atmosphere":"正午烈日把沙滩晒得发烫，海面在阳光下闪着碎银般的光","photo_quality":"广角海岸线","fun_fact":"浅水湾沙滩的沙是人工运来的，原本这里是岩石海岸，英殖时期为打造度假胜地从海南运来细沙","confidence":"high","diary_sentence":"正午的浅水湾，烈日把沙滩晒得发烫，抱着椰青躲进遮阳伞下看海浪一层层推上来"},
        {"scene_type":"museum","scene_subtype":"art_museum","activity":"sightseeing","food":[],"drinks":[],"objects":["画作","雕塑","展厅","解说牌"],"people_description":"几位参观者在画作前驻足讨论","time_of_day":"下午两点，室内恒温","season_hint":"无季节特征","location_clues":"极简主义建筑风格、挑高混凝土天花板、工业风管道外露、展品是当代艺术装置、英文和繁体中文双语解说","landmark_hint":"M+博物馆","atmosphere":"冷白展厅灯光，挑高空间，下午的阳光从天窗滤进来","photo_quality":"展厅内部拍摄","fun_fact":"M+博物馆是亚洲首个全球性当代视觉文化博物馆，建筑由赫尔佐格和德梅隆设计","confidence":"high","diary_sentence":"下午两点走进M+的挑高展厅，冷白灯光下每个人都放慢了脚步，只有偶尔的快门声打破安静"},
    ]
    return scenarios[idx]
