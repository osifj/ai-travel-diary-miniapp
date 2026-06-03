"""
地点解析服务 (可替换模块)。

第一版: Mock 实现 (基于经纬度范围返回预设位置)
后续可接入:
  - 腾讯位置服务:  https://lbs.qq.com/
  - 高德地图 API:    https://lbs.amap.com/
  - 百度地图 API:    https://lbsyun.baidu.com/
  - OpenStreetMap Nominatim: https://nominatim.openstreetmap.org/

模块设计:
  所有 geocoder 实现必须遵循统一接口:
    resolve_location(lat: float, lon: float) -> dict
"""

import logging
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEOCODER_PROVIDER = os.getenv("GEOCODER_PROVIDER", "mock")
GEOCODER_API_KEY = os.getenv("GEOCODER_API_KEY", "")


# ---- 统一接口 ----

def resolve_location(latitude: float, longitude: float) -> dict:
    """
    根据 GPS 坐标解析地点信息。
    
    参数:
      latitude:  纬度 (十进制度数)
      longitude: 经度 (十进制度数)
    
    返回:
      {
        "country":       str | None,  # 国家
        "city":          str | None,  # 城市
        "district":      str | None,  # 区域/区
        "address":       str | None,  # 详细地址
        "place_name":    str | None,  # 地点名称
        "location_status": "found" | "approximate" | "unknown"
      }
    """
    provider = GEOCODER_PROVIDER.lower()

    if provider == "mock":
        return _mock_geocode(latitude, longitude)
    elif provider == "nominatim":
        return _nominatim_geocode(latitude, longitude)
    elif provider == "tencent":
        return _tencent_geocode(latitude, longitude)
    else:
        logger.warning(f"Unknown geocoder provider: {provider}, falling back to mock")
        return _mock_geocode(latitude, longitude)


# ---- Mock 实现 ----

# 预设城市坐标范围 (粗略)
_CITY_RANGES = [
    # (lat_min, lat_max, lon_min, lon_max, country, city, district, place)
    (39.8, 40.0, 116.3, 116.5, "中国", "北京", "东城区", "天安门广场"),
    (31.1, 31.4, 121.3, 121.6, "中国", "上海", "黄浦区", "外滩"),
    (22.2, 22.5, 114.0, 114.3, "中国", "香港", "油尖旺区", "维多利亚港"),
    (22.1, 22.2, 113.5, 113.6, "中国", "澳门", "澳门半岛", "大三巴牌坊"),
    (23.0, 23.2, 113.2, 113.4, "中国", "广州", "越秀区", "广州塔"),
    (22.5, 22.7, 113.9, 114.1, "中国", "深圳", "南山区", "世界之窗"),
    (30.5, 30.7, 103.9, 104.1, "中国", "成都", "锦江区", "宽窄巷子"),
    (29.5, 29.7, 106.4, 106.6, "中国", "重庆", "渝中区", "解放碑"),
    (34.2, 34.3, 108.8, 109.0, "中国", "西安", "雁塔区", "大雁塔"),
    (25.0, 25.1, 121.4, 121.6, "中国", "台北", "信义区", "台北101"),
    (35.6, 35.8, 139.6, 139.8, "日本", "东京", "新宿区", "新宿"),
    (37.5, 37.6, 126.9, 127.0, "韩国", "首尔", "中区", "明洞"),
    (13.7, 13.8, 100.4, 100.6, "泰国", "曼谷", "帕那空县", "大皇宫"),
    (48.8, 48.9, 2.2, 2.4, "法国", "巴黎", "第8区", "埃菲尔铁塔"),
    (40.7, 40.8, -74.1, -73.9, "美国", "纽约", "曼哈顿", "时代广场"),
]


def _mock_geocode(latitude: float, longitude: float) -> dict:
    """Mock 地点解析 — 基于预设城市坐标范围."""

    for lat_min, lat_max, lon_min, lon_max, country, city, district, place in _CITY_RANGES:
        if lat_min <= latitude <= lat_max and lon_min <= longitude <= lon_max:
            return {
                "country": country,
                "city": city,
                "district": district,
                "address": f"{city}{district}附近",
                "place_name": place,
                "location_status": "approximate",
            }

    # 没有匹配的城市，返回未知
    return {
        "country": None,
        "city": None,
        "district": None,
        "address": f"({latitude:.4f}, {longitude:.4f})",
        "place_name": None,
        "location_status": "unknown",
    }


# ---- 真实 API 实现 (骨架) ----

def _nominatim_geocode(latitude: float, longitude: float) -> dict:
    """
    OpenStreetMap Nominatim (免费，需遵守使用条款).
    使用前请阅读: https://operations.osmfoundation.org/policies/nominatim/
    
    限制: 每秒最多 1 次请求，需要 User-Agent。
    """
    try:
        import requests
    except ImportError:
        logger.warning("requests 未安装，回退到 mock geocoder")
        return _mock_geocode(latitude, longitude)

    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": latitude,
        "lon": longitude,
        "format": "json",
        "addressdetails": 1,
        "zoom": 16,
    }
    headers = {
        "User-Agent": "AI-Travel-Diary-MiniApp/0.1.0 (dev)"
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        addr = data.get("address", {})
        return {
            "country": addr.get("country"),
            "city": addr.get("city") or addr.get("town") or addr.get("state"),
            "district": addr.get("suburb") or addr.get("district"),
            "address": data.get("display_name"),
            "place_name": data.get("name"),
            "location_status": "found",
        }
    except Exception as e:
        logger.warning(f"Nominatim geocode failed: {e}")
        return _mock_geocode(latitude, longitude)


def _tencent_geocode(latitude: float, longitude: float) -> dict:
    """
    腾讯位置服务 (需要 API Key).
    文档: https://lbs.qq.com/service/webService/webServiceGuide/webServiceGcoder
    """
    if not GEOCODER_API_KEY:
        logger.warning("GEOCODER_API_KEY 未配置，回退到 mock")
        return _mock_geocode(latitude, longitude)

    try:
        import requests
    except ImportError:
        return _mock_geocode(latitude, longitude)

    url = "https://apis.map.qq.com/ws/geocoder/v1/"
    params = {
        "location": f"{latitude},{longitude}",
        "key": GEOCODER_API_KEY,
        "get_poi": 1,
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("status") == 0:
            result = data.get("result", {})
            addr = result.get("address_component", {})
            poi = (result.get("pois") or [{}])[0]
            return {
                "country": addr.get("nation"),
                "city": addr.get("city"),
                "district": addr.get("district"),
                "address": result.get("address"),
                "place_name": poi.get("title") or result.get("formatted_addresses", {}).get("recommend"),
                "location_status": "found",
            }
        else:
            logger.warning(f"Tencent geocode failed: {data.get('message')}")
            return _mock_geocode(latitude, longitude)
    except Exception as e:
        logger.warning(f"Tencent geocode error: {e}")
        return _mock_geocode(latitude, longitude)
