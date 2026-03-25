"""
用户模块路由（含 v2 画像接口）
"""
import json
import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import ok
from app.user.schemas import UpdateProfileRequest, UpdateSettingsRequest

router = APIRouter(prefix="/user", tags=["用户"])


# ==================== v2 新增：用户画像 ====================

@router.get("/portrait", summary="获取 AI 画像（v2）")
def get_portrait(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取用户 AI 画像（从 user_profiles 取）"""
    from app.models.user_profile import UserProfile
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        return ok(None)

    def _decode(s, default):
        try:
            return json.loads(s) if s else default
        except Exception:
            return default

    return ok({
        "personality": profile.personality or "",
        "writing_style": profile.writing_style or "",
        "interests": _decode(profile.interests, []),
        "preferences": _decode(profile.preferences, {}),
        "relations": _decode(profile.relations, {}),
        "updated_at": profile.updated_at,
    })


@router.post("/portrait/refresh", summary="刷新 AI 画像")
async def refresh_portrait(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """调用 AI 分析日记+聊天数据，刷新用户画像"""
    from app.models.diary import Diary
    from app.models.chat import ChatMessage
    from app.models.user_profile import UserProfile
    from app.ai.minimax_client import get_minimax_client

    # 获取最近 10 篇日记摘要
    diaries = (
        db.query(Diary)
        .filter(Diary.user_id == current_user.id)
        .order_by(Diary.created_at.desc())
        .limit(10)
        .all()
    )
    diary_summaries = "\n".join([
        f"[{d.date}] {d.title or ''}: {(d.content or '')[:100]}"
        for d in diaries
    ])

    # 获取最近 20 条聊天摘要
    chats = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == current_user.id, ChatMessage.role == "user")
        .order_by(ChatMessage.timestamp.desc())
        .limit(20)
        .all()
    )
    chat_summaries = "\n".join([c.content[:80] for c in chats])

    client = get_minimax_client()
    result = await client.generate_portrait(diary_summaries, chat_summaries)

    now = int(time.time() * 1000)
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        profile = UserProfile(user_id=current_user.id, updated_at=now)
        db.add(profile)

    profile.personality = result.get("personality", "")
    profile.writing_style = result.get("writing_style", "")
    profile.interests = json.dumps(result.get("interests", []), ensure_ascii=False)
    profile.preferences = json.dumps(result.get("preferences", {}), ensure_ascii=False)
    profile.relations = json.dumps(result.get("relations", {}), ensure_ascii=False)
    profile.updated_at = now

    db.commit()
    db.refresh(profile)

    return ok(result)



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
