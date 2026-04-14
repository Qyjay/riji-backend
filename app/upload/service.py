"""
文件上传服务
- 按用户和类别分目录存储
- 校验文件类型和大小
- 返回可访问的 URL
"""
import io
import os
import time
from typing import Dict, Optional
from uuid import uuid4

from fastapi import UploadFile

from app.config import settings
from app.response import ApiException, PARAM_INVALID

try:
    from PIL import Image, ImageOps, ExifTags
except ImportError:  # pragma: no cover
    Image = None
    ImageOps = None
    ExifTags = None

# 允许的图片 MIME 类型
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_AUDIO_TYPES = {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/m4a", "audio/ogg"}
ALLOWED_CHAT_FILE_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "text/csv",
}

IMAGE_EXT_MAP = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}

AUDIO_EXT_MAP = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/m4a": "m4a",
    "audio/ogg": "ogg",
}

CHAT_FILE_EXT_MAP = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/plain": "txt",
    "text/csv": "csv",
}

_UPLOADED_IMAGE_META_CACHE: Dict[str, Dict] = {}
_UPLOAD_META_TTL_MS = 10 * 60 * 1000


def _now_ms() -> int:
    return int(time.time() * 1000)


def _cleanup_uploaded_meta_cache(now_ms: int) -> None:
    expired = [
        url
        for url, meta in _UPLOADED_IMAGE_META_CACHE.items()
        if now_ms - int(meta.get("cached_at", 0)) > _UPLOAD_META_TTL_MS
    ]
    for url in expired:
        _UPLOADED_IMAGE_META_CACHE.pop(url, None)


def _cache_uploaded_image_meta(url: str, thumbnail_url: str, location: dict) -> None:
    now_ms = _now_ms()
    _cleanup_uploaded_meta_cache(now_ms)
    _UPLOADED_IMAGE_META_CACHE[url] = {
        "thumbnail_url": thumbnail_url,
        "location": location or {},
        "cached_at": now_ms,
    }


def get_uploaded_image_meta(url: str) -> Optional[dict]:
    """按上传 URL 读取图片元数据（缩略图与位置信息）。"""
    now_ms = _now_ms()
    _cleanup_uploaded_meta_cache(now_ms)
    meta = _UPLOADED_IMAGE_META_CACHE.get(url)
    if not meta:
        return None
    return {
        "thumbnail_url": meta.get("thumbnail_url", ""),
        "location": meta.get("location", {}),
    }


def _resolve_upload_rule(category: str):
    if category == "voice":
        return ALLOWED_AUDIO_TYPES, AUDIO_EXT_MAP, "mp3/wav/m4a/ogg"
    if category == "chat-file":
        return ALLOWED_CHAT_FILE_TYPES, CHAT_FILE_EXT_MAP, "pdf/doc/docx/ppt/pptx/xls/xlsx/txt/csv"
    return ALLOWED_IMAGE_TYPES, IMAGE_EXT_MAP, "jpeg/png/gif/webp"


def _build_storage_paths(user_id: str, category: str, filename: str) -> tuple[str, str, str]:
    dir_path = os.path.join(settings.UPLOAD_DIR, user_id, category)
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, filename)
    url = f"/uploads/{user_id}/{category}/{filename}"
    return dir_path, file_path, url


async def _read_and_validate_upload(
    file: UploadFile,
    category: str,
    max_size: int,
) -> tuple[bytes, str, str]:
    allowed_types, ext_map, allowed_desc = _resolve_upload_rule(category)
    content_type = file.content_type or ""
    if content_type not in allowed_types:
        raise ApiException(
            code=PARAM_INVALID,
            message=f"不支持的文件类型 {content_type}，仅支持 {allowed_desc}",
            status_code=400,
        )

    content = await file.read()
    if len(content) > max_size:
        size_mb = max_size / 1024 / 1024
        raise ApiException(
            code=PARAM_INVALID,
            message=f"文件大小超出限制（最大 {size_mb:.0f}MB）",
            status_code=400,
        )

    ext = ext_map.get(content_type, next(iter(ext_map.values())))
    return content, ext, content_type


def _to_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _gps_dms_to_degree(values, ref: Optional[str]) -> Optional[float]:
    if not values or len(values) < 3:
        return None
    d = _to_float(values[0])
    m = _to_float(values[1])
    s = _to_float(values[2])
    if d is None or m is None or s is None:
        return None
    degree = d + (m / 60.0) + (s / 3600.0)
    if ref in {"S", "W"}:
        degree = -degree
    return round(degree, 6)


def _decode_gps_area_info(value) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="ignore").strip("\x00").strip()
        return text
    if isinstance(value, str):
        return value.strip()
    return ""


def extract_image_location(content: bytes) -> dict:
    """从图片 EXIF 读取 GPS 经纬度和位置描述。"""
    if Image is None or ExifTags is None:
        return {}

    try:
        with Image.open(io.BytesIO(content)) as img:
            exif = img.getexif()
            if not exif:
                return {}

            gps_raw = exif.get(34853)  # GPSInfo
            if not gps_raw:
                return {}

            if not isinstance(gps_raw, dict):
                try:
                    gps_raw = dict(gps_raw)
                except (TypeError, ValueError):
                    return {}

            gps_tags = ExifTags.GPSTAGS
            gps = {gps_tags.get(k, k): v for k, v in gps_raw.items()}

            lat = _gps_dms_to_degree(gps.get("GPSLatitude"), gps.get("GPSLatitudeRef"))
            lng = _gps_dms_to_degree(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef"))

            if lat is None or lng is None:
                return {}

            location = {"lat": lat, "lng": lng}
            area = _decode_gps_area_info(gps.get("GPSAreaInformation"))
            if area:
                location["address"] = area
            else:
                location["address"] = f"{lat:.6f},{lng:.6f}"
            return location
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def _generate_thumbnail(content: bytes, user_id: str, category: str, ext: str) -> str:
    if Image is None:
        return ""

    try:
        with Image.open(io.BytesIO(content)) as img:
            if ImageOps is not None:
                thumb = ImageOps.exif_transpose(img)
            else:
                thumb = img.copy()

            thumb.thumbnail((512, 512))
            thumb_ext = "jpg" if ext == "gif" else ext
            thumb_name = f"thumb_{uuid4()}.{thumb_ext}"
            _, thumb_path, thumb_url = _build_storage_paths(user_id, category, thumb_name)

            fmt = {
                "jpg": "JPEG",
                "png": "PNG",
                "webp": "WEBP",
                "gif": "GIF",
            }.get(thumb_ext, "JPEG")

            if thumb_ext == "jpg" and thumb.mode not in {"RGB", "L"}:
                thumb = thumb.convert("RGB")

            save_kwargs = {"format": fmt}
            if fmt == "JPEG":
                save_kwargs["quality"] = 85

            thumb.save(thumb_path, **save_kwargs)
            return thumb_url
    except (OSError, ValueError, TypeError, AttributeError):
        return ""


async def save_file(file: UploadFile, user_id: str, category: str, max_size: int = None) -> str:
    """
    保存上传文件到本地

    Args:
        file: FastAPI UploadFile 对象
        user_id: 用户 ID
        category: 文件类别，如 'avatar' / 'diary-image'
        max_size: 最大文件大小（字节），None 则用全局配置

    Returns:
        可访问的 URL 路径，如 /uploads/xxx/avatar/uuid.jpg
    """
    if max_size is None:
        max_size = settings.MAX_FILE_SIZE
    content, ext, _ = await _read_and_validate_upload(file, category, max_size)
    filename = f"{uuid4()}.{ext}"
    _, file_path, url = _build_storage_paths(user_id, category, filename)

    # 写入文件
    with open(file_path, "wb") as f:
        f.write(content)

    return url


async def save_diary_image_with_metadata(
    file: UploadFile,
    user_id: str,
    max_size: int = None,
) -> dict:
    """保存日记图片并返回 url、缩略图和位置信息。"""
    if max_size is None:
        max_size = settings.MAX_FILE_SIZE

    category = "diary-image"
    content, ext, _ = await _read_and_validate_upload(file, category, max_size)

    filename = f"{uuid4()}.{ext}"
    _, file_path, url = _build_storage_paths(user_id, category, filename)
    with open(file_path, "wb") as f:
        f.write(content)

    thumbnail_url = _generate_thumbnail(content, user_id, category, ext) or url
    location = extract_image_location(content)

    _cache_uploaded_image_meta(url, thumbnail_url, location)

    return {
        "url": url,
        "thumbnail_url": thumbnail_url,
        "location": location,
    }
