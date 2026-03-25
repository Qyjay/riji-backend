"""
用户模块路由（含 v2 画像接口）
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import ok
from app.user.schemas import UpdateProfileRequest, UpdateSettingsRequest
from app.user import service

router = APIRouter(prefix="/user", tags=["用户"])


# ==================== v2 新增：用户画像 ====================

@router.get("/portrait", summary="获取 AI 画像（v2）")
def get_portrait(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取用户 AI 画像（从 user_profiles 取）"""
    return ok(service.get_portrait(db, current_user.id))


@router.post("/portrait/refresh", summary="刷新 AI 画像")
async def refresh_portrait(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """调用 AI 分析日记+聊天数据，刷新用户画像"""
    return ok(await service.refresh_portrait(db, current_user.id))



@router.get("/profile", summary="获取用户资料")
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 A 实现 - 接口 B1
    获取当前用户的完整资料
    返回：id, username, name, school, major, grade, avatar, signature,
          level, xp, diary_count, streak_days, pomodoro_count
    """
    pass


@router.post("/profile", summary="更新用户资料")
def update_profile(
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 A 实现 - 接口 B2
    更新用户资料（name/school/major/grade/signature）
    只更新请求中非 None 的字段
    更新 updated_at 时间戳
    """
    pass


@router.get("/growth", summary="获取成长数据")
def get_growth(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 A 实现 - 接口 B4
    获取用户成长数据
    返回：level, xp, streak_days, diary_count, pomodoro_count
    可加入升级所需 xp 等计算逻辑
    """
    pass


@router.get("/achievements", summary="获取成就列表")
def get_achievements(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 A 实现 - 接口 B5
    获取用户已解锁的成就列表
    查询 user_achievements 表，关联成就定义（可以硬编码或从配置读）
    """
    pass


@router.get("/settings", summary="获取用户设置")
def get_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 A 实现 - 接口 B6（GET）
    获取当前用户的设置
    查询 user_settings 表
    """
    pass


@router.post("/settings", summary="更新用户设置")
def update_settings(
    req: UpdateSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 A 实现 - 接口 B6（POST）
    更新用户设置（theme/notifications/auto_bgm/diary_privacy/language）
    查询 user_settings，更新非 None 的字段
    """
    pass


@router.get("/semester-report", summary="获取学期报告")
def get_semester_report(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 A 实现 - 接口 B7
    生成学期总结报告
    统计：本学期日记数量、情绪分布、番茄钟完成数、最常用标签等
    可结合 AI 生成文字总结
    """
    pass


@router.get("/agent-portrait", summary="获取 AI 画像")
def get_agent_portrait(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 A 实现 - 接口 B8
    基于用户数据生成 AI 性格画像
    分析日记情绪、标签、写作风格等，调用 AI 生成个性化描述
    """
    pass
