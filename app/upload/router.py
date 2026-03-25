"""
文件上传路由
- POST /upload/avatar       头像上传（最大 5MB）
- POST /upload/diary-image  日记图片上传（最大 10MB）
"""
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import success
from app.upload.service import save_file

router = APIRouter(prefix="/upload", tags=["文件上传"])

# 5MB
AVATAR_MAX_SIZE = 5 * 1024 * 1024
# 10MB
DIARY_IMAGE_MAX_SIZE = 10 * 1024 * 1024


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
    db: Session = Depends(get_db),
):
    """
    上传日记配图
    - 支持格式：jpeg/png/gif/webp
    - 最大大小：10MB
    """
    url = await save_file(file, current_user.id, "diary-image", max_size=DIARY_IMAGE_MAX_SIZE)
    return success(data={"url": url}, message="图片上传成功")
