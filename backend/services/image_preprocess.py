"""
图片预处理服务。

功能:
  1. 压缩图片到适合 AI 分析的尺寸 (减小传输体积)
  2. 去除 EXIF 元数据 (隐私保护 — 不把 GPS 发给 AI)
  3. 可选: HEIC -> JPEG 转换 (需 pillow-heif)
"""

import io
import logging
import os
import subprocess
from PIL import Image
from typing import Optional

logger = logging.getLogger(__name__)

# 预处理后图片保存目录
PROCESSED_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "processed")

# 默认压缩参数
MAX_DIMENSION = 1024       # 最大边长 (px)
JPEG_QUALITY = 80          # JPEG 压缩质量


def strip_exif_and_compress(
    input_path: str,
    max_dimension: int = MAX_DIMENSION,
    jpeg_quality: int = JPEG_QUALITY,
) -> str:
    """
    去除 EXIF + 压缩图片。
    
    输入: 原始图片路径
    输出: 处理后的 JPEG 图片路径 (在 data/processed/ 下)
    
    处理流程:
      1. 用 Pillow 打开图片 (Pillow 不保留 EXIF 除非显式保存)
      2. 缩放到 max_dimension 以内
      3. 转为 RGB (避免 RGBA/CMYK 等问题)
      4. 保存为 JPEG (自动去除所有元数据)
    """
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_path = os.path.join(PROCESSED_DIR, f"{base_name}_processed.jpg")

    try:
        img = Image.open(input_path)

        # 转为 RGB (JPEG 不支持 alpha 通道)
        if img.mode in ("RGBA", "LA", "P", "CMYK"):
            # 对于有透明通道的图片，用白色背景
            if img.mode == "RGBA":
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])  # alpha channel as mask
                img = background
            elif img.mode == "CMYK":
                img = img.convert("RGB")
            else:
                img = img.convert("RGB")

        # 计算缩放比例
        width, height = img.size
        if width > max_dimension or height > max_dimension:
            ratio = min(max_dimension / width, max_dimension / height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            logger.info(
                f"Resized: {width}x{height} -> {new_width}x{new_height}"
            )

        # 保存为 JPEG — exif=None 确保不写入 EXIF
        # Pillow 默认不会保留 EXIF，显式设置 exif=b"" 更安全
        img.save(output_path, "JPEG", quality=jpeg_quality, exif=b"")
        logger.info(f"Processed image saved: {output_path}")

        return output_path

    except Exception as e:
        if os.path.splitext(input_path)[1].lower() in (".heic", ".heif"):
            converted = _convert_heic_with_sips(input_path, output_path, max_dimension)
            if converted:
                return converted

        logger.error(f"Image processing failed: {e}")
        # 如果处理失败，返回原图 (由调用方决定是否使用)
        logger.warning(f"Falling back to original: {input_path}")
        return input_path


def _convert_heic_with_sips(
    input_path: str,
    output_path: str,
    max_dimension: int,
) -> Optional[str]:
    """macOS 下用 sips 转 HEIC/HEIF 为 JPEG，供 AI 分析使用."""
    try:
        result = subprocess.run(
            [
                "sips",
                "-s", "format", "jpeg",
                "--resampleHeightWidthMax", str(max_dimension),
                input_path,
                "--out", output_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning(f"sips HEIC convert failed: {result.stderr}")
            return None
        logger.info(f"Converted HEIC with sips: {output_path}")
        return output_path
    except Exception as e:
        logger.warning(f"sips HEIC convert error: {e}")
        return None


def create_thumbnail(
    input_path: str,
    size: tuple[int, int] = (300, 300),
) -> Optional[str]:
    """
    创建缩略图 (用于小程序端预览，可选功能).
    """
    try:
        thumb_dir = os.path.join(PROCESSED_DIR, "thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(thumb_dir, f"{base_name}_thumb.jpg")

        img = Image.open(input_path)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        img.thumbnail(size, Image.LANCZOS)
        img.save(output_path, "JPEG", quality=70, exif=b"")
        return output_path
    except Exception as e:
        logger.warning(f"Thumbnail creation failed: {e}")
        return None
