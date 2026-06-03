"""
图片上传接口 — POST /upload

接收微信小程序上传的图片，保存到本地，返回 photo_id。
"""

import os
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from models.database import insert_photo
from services.exif_reader import read_exif

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])

# 上传文件存储目录
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "uploads")

# 允许的图片格式
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".bmp", ".tiff", ".tif"}

MAX_FILE_SIZE = 30 * 1024 * 1024  # 30 MB


def _to_float(value: Optional[str]) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _merge_effective_exif(exif_data: Optional[dict], client_data: dict) -> dict:
    effective = dict(exif_data or {})
    client_time = client_data.get("taken_time")
    client_latitude = client_data.get("latitude")
    client_longitude = client_data.get("longitude")
    has_client_gps = client_latitude is not None and client_longitude is not None

    if not effective.get("taken_time") and client_time:
        effective["taken_time"] = client_time
        effective["time_source"] = "user"
    else:
        effective["time_source"] = "exif" if effective.get("taken_time") else "unknown"

    if not effective.get("has_gps") and has_client_gps:
        effective["latitude"] = client_latitude
        effective["longitude"] = client_longitude
        effective["has_gps"] = True
        effective["location_status"] = "found"
        effective["location_source"] = "user"
    else:
        effective["location_source"] = "exif" if effective.get("has_gps") else "unknown"

    effective["client_city"] = client_data.get("city")
    effective["client_address"] = client_data.get("address")
    effective["client_place_name"] = client_data.get("place_name")
    return effective


@router.post("")
async def upload_photo(
    file: UploadFile = File(...),
    client_taken_time: Optional[str] = Form(None),
    client_latitude: Optional[str] = Form(None),
    client_longitude: Optional[str] = Form(None),
    client_city: Optional[str] = Form(None),
    client_address: Optional[str] = Form(None),
    client_place_name: Optional[str] = Form(None),
):
    """
    上传单张图片。
    
    - 校验文件类型和大小
    - 保存到 data/uploads/
    - 读取 EXIF 信息
    - 存入数据库
    - 返回 photo_id 和 EXIF 摘要
    """
    # ---- 1. 校验文件扩展名 ----
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式: {ext}。支持的格式: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # ---- 2. 读取文件内容 ----
    content = await file.read()
    file_size = len(content)

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大: {file_size / 1024 / 1024:.1f} MB。最大允许 {MAX_FILE_SIZE / 1024 / 1024:.0f} MB"
        )

    if file_size == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    # ---- 3. 保存文件 ----
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)

    with open(file_path, "wb") as f:
        f.write(content)

    logger.info(f"Saved upload: {file_path} ({file_size} bytes)")

    # ---- 4. 存入数据库 ----
    photo_id = insert_photo(
        file_path=file_path,
        original_filename=file.filename,
        file_size=file_size,
    )

    # ---- 5. 读取 EXIF + 合并小程序端补充元数据 ----
    exif_data = None
    exif_error = None
    client_data = {
        "taken_time": _clean_text(client_taken_time),
        "latitude": _to_float(client_latitude),
        "longitude": _to_float(client_longitude),
        "city": _clean_text(client_city),
        "address": _clean_text(client_address),
        "place_name": _clean_text(client_place_name),
    }
    try:
        exif_data = read_exif(file_path)
        from models.database import update_photo_exif, update_photo_client_metadata
        update_photo_exif(
            photo_id=photo_id,
            taken_time=exif_data.get("taken_time"),
            latitude=exif_data.get("latitude"),
            longitude=exif_data.get("longitude"),
            has_gps=exif_data.get("has_gps", False),
            device_make=exif_data.get("device_make"),
            device_model=exif_data.get("device_model"),
            image_format=exif_data.get("image_format"),
        )
        update_photo_client_metadata(photo_id=photo_id, **client_data)
    except Exception as e:
        exif_error = str(e)
        logger.warning(f"EXIF read failed for photo {photo_id}: {e}")
        from models.database import update_photo_client_metadata
        update_photo_client_metadata(photo_id=photo_id, **client_data)

    effective_exif = _merge_effective_exif(exif_data, client_data)

    return {
        "success": True,
        "photo_id": photo_id,
        "filename": file.filename,
        "file_size": file_size,
        "exif": effective_exif,
        "exif_error": exif_error,
    }


@router.post("/batch")
async def upload_photos(files: list[UploadFile] = File(...)):
    """
    批量上传多张图片 (最多 20 张)。
    返回每个文件的 photo_id。
    """
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="单次最多上传 20 张图片")

    results = []
    errors = []

    for file in files:
        try:
            # 复用单张上传逻辑 (简化版)
            if not file.filename:
                errors.append({"filename": "unknown", "error": "文件名为空"})
                continue

            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                errors.append({"filename": file.filename, "error": f"不支持的格式: {ext}"})
                continue

            content = await file.read()
            file_size = len(content)

            if file_size == 0 or file_size > MAX_FILE_SIZE:
                errors.append({"filename": file.filename, "error": "文件为空或过大"})
                continue

            unique_name = f"{uuid.uuid4().hex}{ext}"
            file_path = os.path.join(UPLOAD_DIR, unique_name)

            with open(file_path, "wb") as f:
                f.write(content)

            photo_id = insert_photo(
                file_path=file_path,
                original_filename=file.filename,
                file_size=file_size,
            )

            # 读取 EXIF
            try:
                exif_data = read_exif(file_path)
                from models.database import update_photo_exif
                update_photo_exif(
                    photo_id=photo_id,
                    taken_time=exif_data.get("taken_time"),
                    latitude=exif_data.get("latitude"),
                    longitude=exif_data.get("longitude"),
                    has_gps=exif_data.get("has_gps", False),
                    device_make=exif_data.get("device_make"),
                    device_model=exif_data.get("device_model"),
                    image_format=exif_data.get("image_format"),
                )
            except Exception:
                exif_data = None

            results.append({
                "photo_id": photo_id,
                "filename": file.filename,
                "exif": exif_data,
            })

        except Exception as e:
            errors.append({"filename": file.filename or "unknown", "error": str(e)})

    return {
        "success": len(errors) == 0,
        "uploaded": len(results),
        "results": results,
        "errors": errors,
    }
