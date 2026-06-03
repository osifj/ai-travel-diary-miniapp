"""
日记生成模块测试。
"""

import pytest
from services.diary_generator import generate_diary, _group_by_date, _extract_dominant_city


class TestGroupByDate:
    def test_single_date(self):
        photos = [
            {"taken_time": "2025-06-08 10:00:00"},
            {"taken_time": "2025-06-08 14:00:00"},
        ]
        groups = _group_by_date(photos)
        assert "2025-06-08" in groups
        assert len(groups["2025-06-08"]) == 2

    def test_multi_date(self):
        photos = [
            {"taken_time": "2025-06-08 10:00:00"},
            {"taken_time": "2025-06-09 10:00:00"},
        ]
        groups = _group_by_date(photos)
        assert len(groups) == 2

    def test_unknown_date(self):
        photos = [
            {"taken_time": None},
            {"taken_time": "2025-06-08 10:00:00"},
        ]
        groups = _group_by_date(photos)
        assert "unknown" in groups
        assert "2025-06-08" in groups


class TestExtractDominantCity:
    def test_majority(self):
        photos = [
            {"city": "香港"}, {"city": "香港"}, {"city": "北京"}
        ]
        assert _extract_dominant_city(photos) == "香港"

    def test_none(self):
        photos = [{"city": None}, {"city": None}]
        assert _extract_dominant_city(photos) is None


class TestGenerateDiary:
    def test_basic(self):
        """基本日记生成测试."""
        photos = [
            {
                "taken_time": "2025-06-08 10:20:00",
                "city": "香港",
                "address": "尖沙咀附近",
                "scene_type": "tourist_attraction",
                "activity": "sightseeing",
                "food": [],
                "landmark_or_place_hint": "harbour",
                "diary_sentence": "这张照片看起来是在海港附近观光。",
                "mood": "happy",
                "confidence": "medium",
            },
            {
                "taken_time": "2025-06-08 13:10:00",
                "city": "香港",
                "address": "旺角附近",
                "scene_type": "restaurant",
                "activity": "eating",
                "food": ["noodles", "drink"],
                "landmark_or_place_hint": "unknown",
                "diary_sentence": "这张照片看起来是在餐厅吃饭。",
                "mood": "relaxed",
                "confidence": "medium",
            },
        ]

        result = generate_diary(photos)

        assert "title" in result
        assert "date" in result
        assert "city" in result
        assert "content" in result
        assert "keywords" in result
        assert "photo_count" in result
        assert "photo_summaries" in result

        assert result["photo_count"] == 2
        assert result["date"] == "2025-06-08"
        assert "香港" in result["city"]
        assert len(result["keywords"]) >= 3
        assert len(result["content"]) > 0
        assert len(result["photo_summaries"]) == 2

    def test_empty_photos(self):
        """空照片列表应抛出异常."""
        with pytest.raises(ValueError):
            generate_diary([])

    def test_no_exif_date(self):
        """无拍摄时间的照片."""
        photos = [
            {
                "taken_time": None,
                "city": None,
                "scene_type": "landscape",
                "activity": "walking",
                "food": [],
                "mood": "peaceful",
                "confidence": "low",
            }
        ]
        result = generate_diary(photos)
        assert result["date"] == "unknown"
