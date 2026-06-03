"""
天气查询服务。

默认使用 Open-Meteo 公开 API，无需 API Key。
输入经纬度 + 日期，返回当天温度、降雨和天气简介。
"""

import logging
from datetime import date, datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

WEATHER_CODE_TEXT = {
    0: "晴朗",
    1: "大致晴朗",
    2: "局部多云",
    3: "多云",
    45: "有雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "较强毛毛雨",
    56: "冻毛毛雨",
    57: "较强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "较强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "阵雨",
    81: "较强阵雨",
    82: "强阵雨",
    85: "阵雪",
    86: "强阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴冰雹",
}


def _parse_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip()
    if len(text) >= 10:
        return text[:10]
    return None


def _weather_url_for(day: str) -> str:
    try:
        target = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        return FORECAST_URL

    today = date.today()
    if target < today:
        return ARCHIVE_URL
    return FORECAST_URL


def _summarize(data: dict, city: Optional[str], day: str) -> dict:
    daily = data.get("daily") or {}
    codes = daily.get("weather_code") or []
    max_temps = daily.get("temperature_2m_max") or []
    min_temps = daily.get("temperature_2m_min") or []
    rain = daily.get("precipitation_sum") or []

    if not codes:
        raise ValueError("weather response missing daily weather_code")

    code = codes[0]
    weather_text = WEATHER_CODE_TEXT.get(code, f"天气代码 {code}")
    temp_min = min_temps[0] if min_temps else None
    temp_max = max_temps[0] if max_temps else None
    precipitation = rain[0] if rain else None

    place = city or "当地"
    parts = [f"{day} {place}天气{weather_text}"]
    if temp_min is not None and temp_max is not None:
        parts.append(f"气温约 {temp_min:.0f}-{temp_max:.0f}°C")
    if precipitation is not None:
        parts.append(f"降雨量约 {precipitation:.1f} mm")

    return {
        "date": day,
        "city": city,
        "weather_code": code,
        "weather_text": weather_text,
        "temperature_min_c": temp_min,
        "temperature_max_c": temp_max,
        "precipitation_mm": precipitation,
        "source": "open-meteo",
        "summary": "，".join(parts) + "。",
    }


def get_weather_summary(
    latitude: Optional[float],
    longitude: Optional[float],
    day_value: Optional[str],
    city: Optional[str] = None,
) -> dict:
    """查询天气；参数不足或失败时返回可识别的降级结果."""
    day = _parse_date(day_value)
    if latitude is None or longitude is None or not day:
        return {
            "source": "missing",
            "summary": "未获得足够的日期和经纬度，暂未查询到真实天气。",
        }

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": day,
        "end_date": day,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
        "timezone": "auto",
    }
    url = _weather_url_for(day)

    try:
        with httpx.Client(timeout=15) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return _summarize(response.json(), city, day)
    except Exception as e:
        logger.warning(f"Weather lookup failed via {url}: {e}")
        fallback_url = ARCHIVE_URL if url == FORECAST_URL else FORECAST_URL
        try:
            with httpx.Client(timeout=15) as client:
                response = client.get(fallback_url, params=params)
                response.raise_for_status()
                return _summarize(response.json(), city, day)
        except Exception as fallback_error:
            logger.warning(f"Weather fallback failed via {fallback_url}: {fallback_error}")

    return {
        "source": "error",
        "summary": "天气查询暂时失败，日记中不使用精确天气数据。",
    }
