"""
数据库模型 — 使用 SQLite。

表结构:
  - photos:   存储每张照片的原始信息、EXIF 元数据、AI 分析结果
  - diaries:  存储生成的游玩日志
"""

import sqlite3
import os
import json
from datetime import datetime
from typing import Optional

# 数据库文件路径 (放在 backend/data/ 下)
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "travel_diary.db")


def get_connection() -> sqlite3.Connection:
    """获取数据库连接 (SQLite 线程安全)."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # 支持按列名访问
    conn.execute("PRAGMA journal_mode=WAL")  # 更好的并发
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表结构."""
    conn = get_connection()
    cursor = conn.cursor()

    # ---- photos 表 ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS photos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         TEXT    DEFAULT 'default',
            file_path       TEXT    NOT NULL,
            original_filename TEXT  NOT NULL,
            file_size       INTEGER DEFAULT 0,

            -- EXIF 信息
            taken_time      TEXT,
            latitude        REAL,
            longitude       REAL,
            has_gps         INTEGER DEFAULT 0,
            device_make     TEXT,
            device_model    TEXT,
            image_format    TEXT,
            client_taken_time TEXT,
            client_latitude REAL,
            client_longitude REAL,
            client_city    TEXT,
            client_address TEXT,
            client_place_name TEXT,
            time_source    TEXT    DEFAULT 'unknown',
            location_source TEXT   DEFAULT 'unknown',

            -- 地点解析结果
            country         TEXT,
            city            TEXT,
            district        TEXT,
            address         TEXT,
            place_name      TEXT,
            location_status TEXT    DEFAULT 'unknown',

            -- AI 分析结果
            ai_scene_type   TEXT,
            ai_activity     TEXT,
            ai_food         TEXT,   -- JSON array
            ai_objects      TEXT,   -- JSON array
            ai_landmark_hint TEXT,
            ai_mood         TEXT,
            ai_confidence   TEXT,
            ai_summary      TEXT,
            diary_sentence  TEXT,

            -- 状态
            status          TEXT    DEFAULT 'uploaded',  
            -- uploaded | exif_parsed | analyzed | error

            error_message   TEXT,

            created_at      TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    _ensure_photo_columns(cursor)

    # ---- diaries 表 ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS diaries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         TEXT    DEFAULT 'default',
            title           TEXT    NOT NULL,
            date            TEXT    NOT NULL,
            city            TEXT,
            content         TEXT    NOT NULL,
            weather_summary TEXT,
            place_intro     TEXT,
            generator       TEXT    DEFAULT 'template',
            keywords        TEXT,   -- JSON array
            photo_ids       TEXT,   -- JSON array of photo IDs
            created_at      TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    _ensure_diary_columns(cursor)

    conn.commit()
    conn.close()


def _ensure_photo_columns(cursor: sqlite3.Cursor):
    """为已有 SQLite 表补齐新增列."""
    rows = cursor.execute("PRAGMA table_info(photos)").fetchall()
    existing = {row[1] for row in rows}
    columns = {
        "client_taken_time": "TEXT",
        "client_latitude": "REAL",
        "client_longitude": "REAL",
        "client_city": "TEXT",
        "client_address": "TEXT",
        "client_place_name": "TEXT",
        "time_source": "TEXT DEFAULT 'unknown'",
        "location_source": "TEXT DEFAULT 'unknown'",
    }
    for name, definition in columns.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE photos ADD COLUMN {name} {definition}")


def _ensure_diary_columns(cursor: sqlite3.Cursor):
    """为已有 SQLite 日志表补齐新增列."""
    rows = cursor.execute("PRAGMA table_info(diaries)").fetchall()
    existing = {row[1] for row in rows}
    columns = {
        "weather_summary": "TEXT",
        "place_intro": "TEXT",
        "generator": "TEXT DEFAULT 'template'",
    }
    for name, definition in columns.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE diaries ADD COLUMN {name} {definition}")


# ---- 辅助函数 ----

def insert_photo(
    file_path: str,
    original_filename: str,
    file_size: int = 0,
    user_id: str = "default"
) -> int:
    """插入一条照片记录，返回 photo_id."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO photos (user_id, file_path, original_filename, file_size, status)
           VALUES (?, ?, ?, ?, 'uploaded')""",
        (user_id, file_path, original_filename, file_size)
    )
    conn.commit()
    photo_id = cursor.lastrowid
    conn.close()
    return photo_id


def update_photo_exif(
    photo_id: int,
    taken_time: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    has_gps: bool = False,
    device_make: Optional[str] = None,
    device_model: Optional[str] = None,
    image_format: Optional[str] = None,
    time_source: Optional[str] = None,
    location_source: Optional[str] = None,
):
    """更新照片的 EXIF 元数据."""
    effective_time_source = time_source or ("exif" if taken_time else "unknown")
    effective_location_source = location_source or ("exif" if has_gps else "unknown")
    conn = get_connection()
    conn.execute(
        """UPDATE photos SET
            taken_time = ?, latitude = ?, longitude = ?, has_gps = ?,
            device_make = ?, device_model = ?, image_format = ?,
            time_source = ?, location_source = ?,
            status = 'exif_parsed'
           WHERE id = ?""",
        (taken_time, latitude, longitude, 1 if has_gps else 0,
         device_make, device_model, image_format,
         effective_time_source, effective_location_source,
         photo_id)
    )
    conn.commit()
    conn.close()


def update_photo_client_metadata(
    photo_id: int,
    taken_time: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    city: Optional[str] = None,
    address: Optional[str] = None,
    place_name: Optional[str] = None,
):
    """保存小程序端补充的时间/地点，并只在 EXIF 缺失时作为有效值."""
    has_client_gps = latitude is not None and longitude is not None
    conn = get_connection()
    conn.execute(
        """UPDATE photos SET
            client_taken_time = ?,
            client_latitude = ?,
            client_longitude = ?,
            client_city = ?,
            client_address = ?,
            client_place_name = ?,
            time_source = CASE
                WHEN taken_time IS NULL AND ? IS NOT NULL THEN 'user'
                ELSE COALESCE(time_source, 'unknown')
            END,
            taken_time = COALESCE(taken_time, ?),
            location_source = CASE
                WHEN (latitude IS NULL OR longitude IS NULL) AND ? THEN 'user'
                ELSE COALESCE(location_source, 'unknown')
            END,
            latitude = COALESCE(latitude, ?),
            longitude = COALESCE(longitude, ?),
            has_gps = CASE
                WHEN has_gps = 1 OR ? THEN 1
                ELSE 0
            END,
            city = COALESCE(city, ?),
            address = COALESCE(address, ?),
            place_name = COALESCE(place_name, ?),
            location_status = CASE
                WHEN location_status IN ('found', 'approximate') THEN location_status
                WHEN ? THEN 'found'
                ELSE COALESCE(location_status, 'unknown')
            END
           WHERE id = ?""",
        (
            taken_time, latitude, longitude, city, address, place_name,
            taken_time, taken_time,
            1 if has_client_gps else 0,
            latitude, longitude, 1 if has_client_gps else 0,
            city, address, place_name,
            1 if (has_client_gps or city or address or place_name) else 0,
            photo_id,
        )
    )
    conn.commit()
    conn.close()


def update_photo_location(
    photo_id: int,
    country: Optional[str] = None,
    city: Optional[str] = None,
    district: Optional[str] = None,
    address: Optional[str] = None,
    place_name: Optional[str] = None,
    location_status: str = "unknown",
    location_source: Optional[str] = None,
):
    """更新照片的地点解析结果."""
    conn = get_connection()
    conn.execute(
        """UPDATE photos SET
            country = ?, city = ?, district = ?, address = ?,
            place_name = ?, location_status = ?,
            location_source = COALESCE(?, location_source)
           WHERE id = ?""",
        (country, city, district, address, place_name, location_status,
         location_source, photo_id)
    )
    conn.commit()
    conn.close()


def update_photo_ai_result(
    photo_id: int,
    scene_type: Optional[str] = None,
    activity: Optional[str] = None,
    food: Optional[list] = None,
    objects: Optional[list] = None,
    landmark_hint: Optional[str] = None,
    mood: Optional[str] = None,
    confidence: Optional[str] = None,
    summary: Optional[str] = None,
    diary_sentence: Optional[str] = None,
    error_message: Optional[str] = None,
):
    """更新照片的 AI 分析结果."""
    conn = get_connection()
    status = 'error' if error_message else 'analyzed'
    conn.execute(
        """UPDATE photos SET
            ai_scene_type = ?, ai_activity = ?,
            ai_food = ?, ai_objects = ?,
            ai_landmark_hint = ?, ai_mood = ?, ai_confidence = ?,
            ai_summary = ?, diary_sentence = ?,
            status = ?, error_message = ?
           WHERE id = ?""",
        (scene_type, activity,
         json.dumps(food or [], ensure_ascii=False),
         json.dumps(objects or [], ensure_ascii=False),
         landmark_hint, mood, confidence,
         summary, diary_sentence,
         status, error_message,
         photo_id)
    )
    conn.commit()
    conn.close()


def get_photo(photo_id: int) -> Optional[dict]:
    """获取单张照片记录."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    d = dict(row)
    # 解析 JSON 字段
    for field in ('ai_food', 'ai_objects'):
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except json.JSONDecodeError:
                pass
    return d


def get_photos_by_ids(photo_ids: list[int]) -> list[dict]:
    """批量获取照片记录."""
    if not photo_ids:
        return []
    conn = get_connection()
    placeholders = ','.join('?' * len(photo_ids))
    rows = conn.execute(
        f"SELECT * FROM photos WHERE id IN ({placeholders})",
        photo_ids
    ).fetchall()
    conn.close()
    results = []
    for row in rows:
        d = dict(row)
        for field in ('ai_food', 'ai_objects'):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except json.JSONDecodeError:
                    pass
        results.append(d)
    return results


def insert_diary(
    title: str,
    date: str,
    city: str,
    content: str,
    keywords: list[str],
    photo_ids: list[int],
    weather_summary: Optional[str] = None,
    place_intro: Optional[str] = None,
    generator: str = "template",
    user_id: str = "default",
) -> int:
    """插入一篇游玩日志，返回 diary_id."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO diaries (
            user_id, title, date, city, content,
            weather_summary, place_intro, generator,
            keywords, photo_ids
        )
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, title, date, city, content,
         weather_summary, place_intro, generator,
         json.dumps(keywords, ensure_ascii=False),
         json.dumps(photo_ids))
    )
    conn.commit()
    diary_id = cursor.lastrowid
    conn.close()
    return diary_id


def get_diary(diary_id: int) -> Optional[dict]:
    """获取单篇日志."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM diaries WHERE id = ?", (diary_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    d = dict(row)
    for field in ('keywords', 'photo_ids'):
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except json.JSONDecodeError:
                pass
    return d


def get_diaries_by_user(user_id: str = "default", limit: int = 20) -> list[dict]:
    """获取用户的所有日志."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM diaries WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()
    conn.close()
    results = []
    for row in rows:
        d = dict(row)
        for field in ('keywords', 'photo_ids'):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except json.JSONDecodeError:
                    pass
        results.append(d)
    return results
