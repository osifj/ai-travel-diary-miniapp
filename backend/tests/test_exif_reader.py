"""
EXIF 读取模块测试。
"""

import os
import pytest
from services.exif_reader import read_exif, _normalize_time, _dm_to_decimal


class TestNormalizeTime:
    def test_standard_format(self):
        assert _normalize_time("2025:06:08 10:20:00") == "2025-06-08 10:20:00"

    def test_dash_format(self):
        assert _normalize_time("2025-06-08 10:20:00") == "2025-06-08 10:20:00"

    def test_iso_format(self):
        assert _normalize_time("2025-06-08T10:20:00") == "2025-06-08 10:20:00"

    def test_none(self):
        assert _normalize_time(None) is None

    def test_empty(self):
        assert _normalize_time("") is None


class TestDMToDecimal:
    def test_north_east(self):
        # 22°19'9.48" N
        result = _dm_to_decimal(22, 19, 9.48, "N")
        assert abs(result - 22.3193) < 0.001

    def test_south_west(self):
        # 33°51'0" S, 151°12'0" E
        lat = _dm_to_decimal(33, 51, 0, "S")
        lon = _dm_to_decimal(151, 12, 0, "E")
        assert lat < 0
        assert abs(lat - (-33.85)) < 0.01
        assert lon > 0


class TestReadExif:
    def test_jpeg_no_exif(self):
        """测试无 EXIF 的 JPEG 图片."""
        # 使用项目中已有的测试图片
        test_img = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "uploads",
        )
        # 查找任意一张已上传的图片
        if os.path.exists(test_img):
            for f in os.listdir(test_img):
                if f.endswith('.jpg'):
                    result = read_exif(os.path.join(test_img, f))
                    assert "has_gps" in result
                    assert "taken_time" in result
                    assert "location_status" in result
                    break

    def test_nonexistent_file(self):
        """测试不存在的文件."""
        with pytest.raises(FileNotFoundError):
            read_exif("/nonexistent/path/photo.jpg")
