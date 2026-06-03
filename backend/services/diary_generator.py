"""
游玩日志生成服务。

输入: 一组照片分析结果 (含时间、地点、AI 分析)
输出: 结构化的中文游玩日志

第一版: 基于模板 + 规则生成 (不依赖 LLM)
后续可接入 MiMo 文本模型或其他 LLM 生成更自然的日记。
"""

import logging
from datetime import datetime
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)


def generate_diary(photos: list[dict]) -> dict:
    """
    根据一组照片分析结果生成游玩日志。

    参数 photos: 每个元素应包含:
      - taken_time:        "2025-06-08 10:20:00" | None
      - city:              "香港" | None
      - address:           "尖沙咀附近" | None
      - scene_type:        "restaurant" | None
      - activity:          "eating" | None
      - food:              ["noodles"] | []
      - objects:           ["plate", "cup"] | []
      - landmark_or_place_hint: "harbour" | None
      - mood:              "relaxed" | None
      - confidence:        "high" | "medium" | "low"
      - diary_sentence:    "这张照片看起来是..." | None

    返回:
      {
        "title":   "香港一日城市游玩记录",
        "date":    "2025-06-08",
        "city":    "香港",
        "content": "今天的照片主要记录了...",
        "keywords": ["香港", "城市漫步", ...],
        "photo_count": 5,
        "photo_summaries": [...],
      }
    """
    if not photos:
        raise ValueError("照片列表不能为空")

    # ---- 1. 按日期分组 ----
    date_groups = _group_by_date(photos)
    # 使用照片最多的一组日期
    main_date = max(date_groups.keys(), key=lambda d: len(date_groups[d]))
    main_photos = date_groups[main_date]

    # ---- 2. 提取城市 ----
    city = _extract_dominant_city(main_photos)

    # ---- 3. 按时间段排序 ----
    sorted_photos = sorted(main_photos, key=lambda p: p.get("taken_time") or "")

    # ---- 4. 聚合分析 ----
    scene_counts = _count_field(sorted_photos, "scene_type")
    activity_counts = _count_field(sorted_photos, "activity")
    all_food = _collect_food(sorted_photos)
    moods = _count_field(sorted_photos, "mood")
    dominant_mood = max(moods, key=moods.get) if moods else "relaxed"

    # ---- 5. 生成标题 ----
    title = _generate_title(city, main_date, sorted_photos)

    # ---- 6. 生成正文 ----
    content = _generate_content(city, main_date, sorted_photos, scene_counts, activity_counts, all_food, dominant_mood)

    # ---- 7. 生成关键词 ----
    keywords = _generate_keywords(city, scene_counts, activity_counts, all_food, dominant_mood)

    # ---- 8. 照片摘要 ----
    photo_summaries = _generate_photo_summaries(sorted_photos)

    return {
        "title": title,
        "date": main_date,
        "city": city or "未知城市",
        "content": content,
        "keywords": keywords,
        "photo_count": len(sorted_photos),
        "photo_summaries": photo_summaries,
    }


# ---- 内部辅助函数 ----

def _group_by_date(photos: list[dict]) -> dict[str, list[dict]]:
    """按日期分组照片."""
    groups = defaultdict(list)
    for p in photos:
        taken = p.get("taken_time")
        if taken:
            date = taken[:10]  # "2025-06-08 10:20:00" -> "2025-06-08"
        else:
            date = "unknown"
        groups[date].append(p)
    return dict(groups)


def _extract_dominant_city(photos: list[dict]) -> Optional[str]:
    """提取出现最多的城市."""
    cities = [p.get("city") for p in photos if p.get("city")]
    if not cities:
        return None
    return max(set(cities), key=cities.count)


def _count_field(photos: list[dict], field: str) -> dict[str, int]:
    """统计某个字段的频次."""
    counts = defaultdict(int)
    for p in photos:
        val = p.get(field)
        if val:
            counts[val] += 1
    return dict(counts)


def _collect_food(photos: list[dict]) -> list[str]:
    """收集所有食物名称 (去重)."""
    food_set = set()
    for p in photos:
        food_list = p.get("food", [])
        if isinstance(food_list, list):
            for f in food_list:
                if f and f != "unknown":
                    food_set.add(f)
    return list(food_set)


def _generate_title(city: Optional[str], date: str, photos: list[dict]) -> str:
    """生成日志标题."""
    city_part = city or "未知地点"

    # 判断游玩类型
    scene_types = _count_field(photos, "scene_type")
    if scene_types.get("restaurant", 0) >= len(photos) * 0.5:
        type_part = "美食探索记录"
    elif scene_types.get("tourist_attraction", 0) >= len(photos) * 0.4:
        type_part = "景点游玩记录"
    elif scene_types.get("beach", 0) >= len(photos) * 0.3:
        type_part = "海边休闲记录"
    else:
        type_part = "城市游玩记录"

    return f"{city_part}{type_part}"


def _generate_content(
    city: Optional[str],
    date: str,
    photos: list[dict],
    scene_counts: dict,
    activity_counts: dict,
    all_food: list[str],
    dominant_mood: str,
) -> str:
    """生成游玩日志正文."""

    city_name = city or "未知地点"
    date_display = date.replace("-", "年", 1).replace("-", "月") + "日"
    photo_count = len(photos)

    # 开头
    lines = []
    lines.append(f"{date_display}，你在{city_name}记录了{photo_count}张照片。")

    # 按场景描述
    scene_desc_map = {
        "restaurant": "用餐",
        "tourist_attraction": "观光游览",
        "street": "城市漫步",
        "beach": "海边休闲",
        "museum": "参观展览",
        "shopping_mall": "购物",
        "hotel": "休息",
        "landscape": "欣赏风景",
        "transport": "出行途中",
    }

    activity_desc_map = {
        "eating": "用餐",
        "sightseeing": "观光",
        "shopping": "购物",
        "walking": "散步",
        "relaxing": "放松",
        "taking_photo": "拍照",
    }

    mood_desc_map = {
        "happy": "愉快",
        "relaxed": "轻松",
        "crowded": "热闹",
        "peaceful": "宁静",
        "romantic": "浪漫",
    }

    # 时间段分析
    morning_photos = [p for p in photos if p.get("taken_time") and "06:00" <= p["taken_time"][11:16] < "12:00"]
    afternoon_photos = [p for p in photos if p.get("taken_time") and "12:00" <= p["taken_time"][11:16] < "18:00"]
    evening_photos = [p for p in photos if p.get("taken_time") and "18:00" <= p["taken_time"][11:16] < "24:00"]

    # 上午
    if morning_photos:
        scenes = _count_field(morning_photos, "scene_type")
        acts = _count_field(morning_photos, "activity")
        top_scene = max(scenes, key=scenes.get) if scenes else None
        top_act = max(acts, key=acts.get) if acts else None

        scene_text = scene_desc_map.get(top_scene, "活动") if top_scene else "活动"
        act_text = activity_desc_map.get(top_act, "") if top_act else ""
        sentence = f"上午的照片显示你可能在{scene_text}"
        if act_text:
            sentence += f"，主要是在{act_text}"
        sentence += "。"
        lines.append(sentence)

    # 中午/下午
    if afternoon_photos:
        scenes = _count_field(afternoon_photos, "scene_type")
        acts = _count_field(afternoon_photos, "activity")
        top_scene = max(scenes, key=scenes.get) if scenes else None
        top_act = max(acts, key=acts.get) if acts else None

        scene_text = scene_desc_map.get(top_scene, "活动") if top_scene else "活动"
        act_text = activity_desc_map.get(top_act, "") if top_act else ""

        sentence = f"下午"
        if top_scene and top_scene != morning_photos and top_scene in scene_desc_map:
            sentence += f"你似乎去了{scene_text}"
        else:
            sentence += f"你继续在{scene_text}"
        if act_text:
            sentence += f"，主要是{act_text}"
        sentence += "。"
        lines.append(sentence)

    # 晚上
    if evening_photos:
        scenes = _count_field(evening_photos, "scene_type")
        acts = _count_field(evening_photos, "activity")
        top_scene = max(scenes, key=scenes.get) if scenes else None
        top_act = max(acts, key=acts.get) if acts else None

        scene_text = scene_desc_map.get(top_scene, "活动") if top_scene else "活动"
        sentences = [f"晚上的照片记录了{scene_text}"]
        if top_scene == "restaurant":
            sentences[0] = "晚上你似乎去了餐厅用餐"
        if all_food:
            sentences.append(f"，照片中出现了{'、'.join(all_food[:3])}")
        sentences.append("。")
        lines.append("".join(sentences))

    # 食物总结
    if all_food:
        lines.append(f"这一天你在美食方面有不错的体验，照片中出现了{'、'.join(all_food[:5])}。")

    # 整体氛围
    mood_text = mood_desc_map.get(dominant_mood, "轻松")
    lines.append(f"整体来看，这一天以{scene_desc_map.get(max(scene_counts, key=scene_counts.get), '城市探索')}为主，氛围{mood_text}。")

    # 如果置信度整体偏低，加一句
    low_conf_count = sum(1 for p in photos if p.get("confidence") == "low")
    if low_conf_count > len(photos) * 0.5:
        lines.append('（注：部分照片的 AI 识别置信度较低，以上描述基于"看起来像"的推断。）')

    return "\n\n".join(lines)


def _generate_keywords(
    city: Optional[str],
    scene_counts: dict,
    activity_counts: dict,
    all_food: list[str],
    dominant_mood: str,
) -> list[str]:
    """生成关键词 (3-8 个)."""
    keywords = []

    if city:
        keywords.append(city)

    # 场景相关关键词
    scene_kw_map = {
        "restaurant": "美食",
        "tourist_attraction": "景点打卡",
        "street": "城市漫步",
        "beach": "海边",
        "museum": "博物馆",
        "shopping_mall": "购物",
        "landscape": "自然风光",
        "transport": "出行",
    }
    for scene, count in sorted(scene_counts.items(), key=lambda x: -x[1])[:3]:
        kw = scene_kw_map.get(scene)
        if kw and kw not in keywords:
            keywords.append(kw)

    # 活动相关
    act_kw_map = {
        "eating": "美食体验",
        "sightseeing": "观光游览",
        "shopping": "购物",
        "walking": "散步",
        "relaxing": "休闲",
    }
    for act, count in sorted(activity_counts.items(), key=lambda x: -x[1])[:2]:
        kw = act_kw_map.get(act)
        if kw and kw not in keywords:
            keywords.append(kw)

    # 食物
    for food in all_food[:2]:
        if food not in keywords:
            keywords.append(food)

    # 氛围
    mood_kw_map = {
        "happy": "愉快",
        "relaxed": "轻松",
        "crowded": "热闹",
        "peaceful": "宁静",
        "romantic": "浪漫",
    }
    mood_kw = mood_kw_map.get(dominant_mood)
    if mood_kw and mood_kw not in keywords:
        keywords.append(mood_kw)

    # 限制 3-8 个
    return keywords[:8] if len(keywords) >= 3 else keywords + ["旅行", "日常记录"][:8 - len(keywords)]


def _generate_photo_summaries(photos: list[dict]) -> list[dict]:
    """为每张照片生成简要摘要."""
    summaries = []
    for p in photos:
        summaries.append({
            "taken_time": p.get("taken_time"),
            "city": p.get("city"),
            "address": p.get("address"),
            "scene_type": p.get("scene_type"),
            "activity": p.get("activity"),
            "diary_sentence": p.get("diary_sentence"),
            "mood": p.get("mood"),
        })
    return summaries
