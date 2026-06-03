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

    # ---- diaries 表 ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS diaries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         TEXT    DEFAULT 'default',
            title           TEXT    NOT NULL,
            date            TEXT    NOT NULL,
            city            TEXT,
            content         TEXT    NOT NULL,
            keywords        TEXT,   -- JSON array
            photo_ids       TEXT,   -- JSON array of photo IDs
            created_at      TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    conn.commit()
    conn.close()


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
):
    """更新照片的 EXIF 元数据."""
    conn = get_connection()
    conn.execute(
        """UPDATE photos SET
            taken_time = ?, latitude = ?, longitude = ?, has_gps = ?,
            device_make = ?, device_model = ?, image_format = ?,
            status = 'exif_parsed'
           WHERE id = ?""",
        (taken_time, latitude, longitude, 1 if has_gps else 0,
         device_make, device_model, image_format,
         photo_id)
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
):
    """更新照片的地点解析结果."""
    conn = get_connection()
    conn.execute(
        """UPDATE photos SET
            country = ?, city = ?, district = ?, address = ?,
            place_name = ?, location_status = ?
           WHERE id = ?""",
        (country, city, district, address, place_name, location_status, photo_id)
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
    user_id: str = "default",
) -> int:
    """插入一篇游玩日志，返回 diary_id."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO diaries (user_id, title, date, city, content, keywords, photo_ids)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, title, date, city, content,
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
