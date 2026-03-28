"""
文件上传服务
- 按用户和类别分目录存储
- 校验文件类型和大小
- 返回可访问的 URL
"""
import os
from uuid import uuid4

from fastapi import UploadFile

from app.config import settings
from app.response import ApiException, PARAM_INVALID

# 允许的图片 MIME 类型
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


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

    # 校验文件类型
    content_type = file.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise ApiException(
            code=PARAM_INVALID,
            message=f"不支持的文件类型 {content_type}，仅支持 jpeg/png/gif/webp",
            status_code=400,
        )

    # 读取文件内容
    content = await file.read()

    # 校验文件大小
    if len(content) > max_size:
        size_mb = max_size / 1024 / 1024
        raise ApiException(
            code=PARAM_INVALID,
            message=f"文件大小超出限制（最大 {size_mb:.0f}MB）",
            status_code=400,
        )

    # 确定文件扩展名
    ext_map = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/webp": "webp",
    }
    ext = ext_map.get(content_type, "jpg")

    # 创建目录：uploads/{user_id}/{category}/
    dir_path = os.path.join(settings.UPLOAD_DIR, user_id, category)
    os.makedirs(dir_path, exist_ok=True)

    # 使用 UUID 作为文件名，避免冲突
    filename = f"{uuid4()}.{ext}"
    file_path = os.path.join(dir_path, filename)

    # 写入文件
    with open(file_path, "wb") as f:
        f.write(content)

    # 返回可访问的 URL（通过 /uploads 静态文件挂载）
    url = f"/uploads/{user_id}/{category}/{filename}"
    return url
