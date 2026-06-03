"""
EXIF 读取服务。

优先使用系统安装的 exiftool (对 iPhone HEIC 更稳定)，
如果不可用则回退到 Pillow。

支持格式: JPG, JPEG, PNG, HEIC (需 exiftool 或 pillow-heif)

exiftool 安装方式:
  macOS:  brew install exiftool
  Ubuntu: sudo apt install exiftool
  Windows: 下载 https://exiftool.org/
"""

import json
import logging
import os
import subprocess
from datetime import datetime
from typing import Any, Optional

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

logger = logging.getLogger(__name__)


# ---- GPS 坐标转换 ----

def _dm_to_decimal(degrees: float, minutes: float, seconds: float, ref: str) -> float:
    """将 度/分/秒 (DMS) 转换为十进制度数."""
    decimal = degrees + minutes / 60.0 + seconds / 3600.0
    if ref in ('S', 'W'):
        decimal = -decimal
    return round(decimal, 6)


def _parse_gps_from_exiftool(raw: dict) -> Optional[dict]:
    """
    从 exiftool JSON 输出中提取 GPS 坐标。
    返回 {"latitude": float, "longitude": float} 或 None。
    """
    lat = raw.get("GPSLatitude")
    lon = raw.get("GPSLongitude")
    lat_ref = raw.get("GPSLatitudeRef", "N")
    lon_ref = raw.get("GPSLongitudeRef", "E")

    if lat is None or lon is None:
        # 尝试可选的复合字段
        lat = raw.get("GPSPosition")
        if lat is not None and isinstance(lat, str):
            parts = lat.replace("deg", "").replace("'", "").replace('"', "").split(",")
            if len(parts) >= 2:
                try:
                    lat_d = float(parts[0].strip().split()[0])
                    lon_d = float(parts[1].strip().split()[0])
                    return {"latitude": round(lat_d, 6), "longitude": round(lon_d, 6)}
                except (ValueError, IndexError):
                    pass
        return None

    try:
        # exiftool 返回的 GPS 可能是字符串 "22 deg 19' 9.48\" N"
        # 也可能已经是数字
        if isinstance(lat, str) and isinstance(lon, str):
            return {"latitude": float(lat.split()[0]), "longitude": float(lon.split()[0])}
        elif isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return {"latitude": round(float(lat), 6), "longitude": round(float(lon), 6)}
    except (ValueError, IndexError, TypeError):
        pass

    return None


def _parse_gps_from_pillow(img: Image.Image) -> Optional[dict]:
    """从 Pillow Exif 中提取 GPS 坐标."""
    exif_data = img._getexif()
    if not exif_data:
        return None

    gps_info = {}
    for tag_id, value in exif_data.items():
        tag = TAGS.get(tag_id, tag_id)
        if tag == "GPSInfo" and isinstance(value, dict):
            for gps_tag_id, gps_value in value.items():
                gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                gps_info[gps_tag] = gps_value

    if not gps_info:
        return None

    try:
        lat = gps_info.get("GPSLatitude")
        lat_ref = gps_info.get("GPSLatitudeRef", "N")
        lon = gps_info.get("GPSLongitude")
        lon_ref = gps_info.get("GPSLongitudeRef", "E")

        if lat and lon:
            lat_decimal = _dm_to_decimal(
                float(lat[0]), float(lat[1]), float(lat[2]), lat_ref
            )
            lon_decimal = _dm_to_decimal(
                float(lon[0]), float(lon[1]), float(lon[2]), lon_ref
            )
            return {"latitude": lat_decimal, "longitude": lon_decimal}
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.warning(f"Pillow GPS parse error: {e}")

    return None


# ---- EXIF 读取主入口 ----

def _check_exiftool() -> bool:
    """检查系统是否安装了 exiftool."""
    try:
        result = subprocess.run(
            ["exiftool", "-ver"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _read_with_exiftool(file_path: str) -> dict[str, Any]:
    """使用 exiftool 读取 EXIF (JSON 输出)."""
    result = subprocess.run(
        ["exiftool", "-json", "-g", file_path],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"exiftool failed: {result.stderr}")

    data = json.loads(result.stdout)
    if not data or not isinstance(data, list):
        raise ValueError("exiftool returned empty/invalid JSON")

    raw = data[0]
    gps_data = _parse_gps_from_exiftool(raw)

    # 提取时间: 优先 DateTimeOriginal > CreateDate > FileModifyDate
    taken_time = (
        raw.get("DateTimeOriginal")
        or raw.get("CreateDate")
        or raw.get("FileModifyDate")
    )

    return {
        "taken_time": _normalize_time(taken_time),
        "latitude": gps_data["latitude"] if gps_data else None,
        "longitude": gps_data["longitude"] if gps_data else None,
        "has_gps": gps_data is not None,
        "device_make": raw.get("Make"),
        "device_model": raw.get("Model"),
        "image_format": raw.get("FileType") or raw.get("MIMEType"),
        "location_status": "found" if gps_data else "missing",
    }


def _read_with_pillow(file_path: str) -> dict[str, Any]:
    """使用 Pillow 读取 EXIF (回退方案)."""
    img = Image.open(file_path)
    gps_data = _parse_gps_from_pillow(img)

    exif_data = img._getexif() or {}
    taken_time = None
    for tag_id, value in exif_data.items():
        tag = TAGS.get(tag_id, tag_id)
        if tag in ("DateTimeOriginal", "DateTime"):
            taken_time = value
            break
    if not taken_time:
        taken_time = exif_data.get(306)  # 306 = DateTime

    return {
        "taken_time": _normalize_time(taken_time),
        "latitude": gps_data["latitude"] if gps_data else None,
        "longitude": gps_data["longitude"] if gps_data else None,
        "has_gps": gps_data is not None,
        "device_make": exif_data.get(271) or getattr(img, "info", {}).get("make"),
        "device_model": exif_data.get(272) or getattr(img, "info", {}).get("model"),
        "image_format": (img.format or os.path.splitext(file_path)[1].lstrip(".")).upper(),
        "location_status": "found" if gps_data else "missing",
    }


def _normalize_time(raw_time: Optional[str]) -> Optional[str]:
    """标准化时间字符串为 'YYYY-MM-DD HH:MM:SS'."""
    if not raw_time:
        return None
    # exiftool 可能返回类似 "2025:06:08 10:20:00" 的格式
    raw_time = str(raw_time).strip()
    # 常见格式
    formats = [
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y:%m:%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y:%m:%d %H:%M",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw_time.replace("+00:00", "").rstrip("Z"), fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    # 最后的 fallback: 取前 19 个字符
    if len(raw_time) >= 19:
        return raw_time[:19].replace(":", "-", 2)  # 2025:06:08 -> 2025-06-08
    return raw_time


# ---- 统一入口 ----

_EXIFTOOL_AVAILABLE = None  # 缓存检查结果


def read_exif(file_path: str) -> dict[str, Any]:
    """
    读取图片的 EXIF 信息。

    返回格式:
    {
        "taken_time": "2025-06-08 10:20:00" | null,
        "latitude": 22.3193 | null,
        "longitude": 114.1694 | null,
        "has_gps": true | false,
        "device_make": "Apple" | null,
        "device_model": "iPhone 15 Pro" | null,
        "image_format": "HEIC" | "JPEG" | ...,
        "location_status": "found" | "missing"
    }
    """
    global _EXIFTOOL_AVAILABLE

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # 惰性检查 exiftool
    if _EXIFTOOL_AVAILABLE is None:
        _EXIFTOOL_AVAILABLE = _check_exiftool()
        logger.info(f"exiftool available: {_EXIFTOOL_AVAILABLE}")

    if _EXIFTOOL_AVAILABLE:
        try:
            return _read_with_exiftool(file_path)
        except Exception as e:
            logger.warning(f"exiftool read failed, falling back to Pillow: {e}")

    try:
        return _read_with_pillow(file_path)
    except Exception as e:
        # 完全无法读取 EXIF，返回基本信息
        logger.error(f"EXIF read error for {file_path}: {e}")
        ext = os.path.splitext(file_path)[1].lstrip(".").upper()
        return {
            "taken_time": None,
            "latitude": None,
            "longitude": None,
            "has_gps": False,
            "device_make": None,
            "device_model": None,
            "image_format": ext,
            "location_status": "missing",
            "error": str(e),
        }
