"""
文件上传路由
- POST /upload/avatar       头像上传（最大 5MB）
- POST /upload/diary-image  日记图片上传（最大 10MB）
- POST /upload/diary-images 日记图片批量上传（单次最多 9 张）
"""
from typing import List

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import ApiException, PARAM_INVALID, success
from app.upload.service import save_file, save_diary_image_with_metadata

router = APIRouter(prefix="/upload", tags=["文件上传"])

# 5MB
AVATAR_MAX_SIZE = 5 * 1024 * 1024
# 10MB
DIARY_IMAGE_MAX_SIZE = 10 * 1024 * 1024
DIARY_IMAGE_BATCH_MAX_COUNT = 9


@router.post("/avatar", summary="上传头像")
async def upload_avatar(
    file: UploadFile = File(..., description="头像图片（jpeg/png，最大 5MB）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    上传用户头像
    - 支持格式：jpeg/png/gif/webp
    - 最大大小：5MB
    - 自动更新用户 avatar 字段
    """
    import time

    url = await save_file(file, current_user.id, "avatar", max_size=AVATAR_MAX_SIZE)

    # 更新用户头像
    current_user.avatar = url
    current_user.updated_at = int(time.time() * 1000)
    db.commit()

    return success(data={"avatar": url}, message="头像上传成功")


@router.post("/diary-image", summary="上传日记图片")
async def upload_diary_image(
    file: UploadFile = File(..., description="日记图片（jpeg/png，最大 10MB）"),
    current_user: User = Depends(get_current_user),
):
    """
    上传日记配图
    - 支持格式：jpeg/png/gif/webp
    - 最大大小：10MB
    """
    uploaded = await save_diary_image_with_metadata(
        file,
        current_user.id,
        max_size=DIARY_IMAGE_MAX_SIZE,
    )
    return success(
        data={
            "url": uploaded["url"],
            "thumbnailUrl": uploaded["thumbnail_url"],
            "location": uploaded["location"],
        },
        message="图片上传成功",
    )


@router.post("/diary-images", summary="批量上传日记图片")
async def upload_diary_images(
    files: List[UploadFile] = File(..., description="日记图片列表（jpeg/png，单张最大 10MB）"),
    current_user: User = Depends(get_current_user),
):
    """
    批量上传日记配图
    - 支持格式：jpeg/png/gif/webp
    - 单张最大：10MB
    - 单次最多：9 张
    """
    if not files:
        raise ApiException(
            code=PARAM_INVALID,
            message="请至少上传一张图片",
            status_code=400,
        )

    if len(files) > DIARY_IMAGE_BATCH_MAX_COUNT:
        raise ApiException(
            code=PARAM_INVALID,
            message=f"单次最多上传 {DIARY_IMAGE_BATCH_MAX_COUNT} 张图片",
            status_code=400,
        )

    items = []
    for file in files:
        uploaded = await save_diary_image_with_metadata(
            file,
            current_user.id,
            max_size=DIARY_IMAGE_MAX_SIZE,
        )
        items.append(
            {
                "url": uploaded["url"],
                "thumbnailUrl": uploaded["thumbnail_url"],
                "location": uploaded["location"],
            }
        )

    return success(data={"items": items}, message="图片上传成功")


# v2 新增：语音上传
VOICE_MAX_SIZE = 20 * 1024 * 1024  # 20MB
CHAT_FILE_MAX_SIZE = 20 * 1024 * 1024  # 20MB


@router.post("/voice", summary="上传语音素材")
async def upload_voice(
    file: UploadFile = File(..., description="语音文件（mp3/wav/m4a，最大 20MB）"),
    current_user: User = Depends(get_current_user),
):
    """
    上传语音素材文件
    - 支持格式：mp3/wav/m4a/ogg
    - 最大大小：20MB
    """
    url = await save_file(file, current_user.id, "voice", max_size=VOICE_MAX_SIZE)
    return success(data={"url": url}, message="语音上传成功")


@router.post("/chat-file", summary="上传聊天文件附件")
async def upload_chat_file(
    file: UploadFile = File(..., description="聊天文件（pdf/doc/ppt/xls/txt/csv，最大 20MB）"),
    current_user: User = Depends(get_current_user),
):
    url = await save_file(file, current_user.id, "chat-file", max_size=CHAT_FILE_MAX_SIZE)
    return success(
        data={
            "url": url,
            "name": file.filename or "未命名文件",
            "size": file.size or 0,
            "mimeType": file.content_type or "",
        },
        message="文件上传成功",
    )

