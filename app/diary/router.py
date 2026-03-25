"""
日记模块路由骨架
组员 B+C 负责实现
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.diary.schemas import CreateDiaryRequest, UpdateDiaryRequest

router = APIRouter(prefix="/diaries", tags=["日记"])


@router.get("", summary="获取日记列表")
def list_diaries(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=50, description="每页条数"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 B 实现 - 接口 C1
    获取当前用户的日记列表（分页）
    1. 查询 diaries 表，按 created_at DESC 排序
    2. 支持分页（page / page_size）
    3. 返回 {total, page, page_size, items: [...]}
    提示：images/emotion/tags 是 JSON 字符串，需要 json.loads()
    """
    pass


@router.get("/{diary_id}", summary="获取日记详情")
def get_diary(
    diary_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 B 实现 - 接口 C2
    获取单篇日记详情
    1. 查询指定 id 的日记
    2. 验证归属（diary.user_id == current_user.id）
    3. 不存在 → raise ApiException(NOT_FOUND, "日记不存在", 404)
    """
    pass


@router.post("", summary="创建日记")
def create_diary(
    req: CreateDiaryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 C 实现 - 接口 C3
    创建新日记
    1. 生成 UUID 作为 id
    2. images/emotion/tags 用 json.dumps() 转为字符串存储
    3. 创建 Diary 记录
    4. 更新 User.diary_count += 1
    5. 返回创建的日记
    """
    pass


@router.put("/{diary_id}", summary="更新日记")
def update_diary(
    diary_id: str,
    req: UpdateDiaryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 C 实现 - 编辑日记
    1. 查询并验证归属
    2. 更新非 None 的字段
    3. 更新 updated_at 时间戳
    4. 返回更新后的日记
    """
    pass


@router.delete("/{diary_id}", summary="删除日记")
def delete_diary(
    diary_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 C 实现 - 删除日记
    1. 查询并验证归属
    2. 删除日记记录
    3. 更新 User.diary_count -= 1（注意不要小于 0）
    4. 返回 success()
    """
    pass
