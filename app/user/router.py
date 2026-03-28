"""
用户模块路由
"""
import json
import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import success
from app.user.schemas import (
    UpdateProfileRequest, UpdateSettingsRequest,
    UserProfileOut, AchievementOut, GrowthDataOut, SettingsOut, SemesterReportOut,
)
from app.user import service

router = APIRouter(prefix="/user", tags=["用户"])


@router.get("/profile", summary="获取用户资料")
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = service.get_user_profile(db, current_user.id)
    out = UserProfileOut(**data)
    return success(out.model_dump(by_alias=True))


@router.post("/profile", summary="更新用户资料")
def update_profile(
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = req.model_dump(exclude_unset=True)
    result = service.update_user_profile(db, current_user.id, data)
    out = UserProfileOut(**result)
    return success(out.model_dump(by_alias=True))


@router.get("/agent-portrait", summary="获取 AI 画像图")
async def get_agent_portrait(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """生成/获取 AI 用户画像图片 URL"""
    from app.models.user_profile import UserProfile
    from app.ai.minimax_client import get_minimax_client

    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if profile and profile.personality:
        prompt = f"为一个性格{profile.personality}的大学生绘制一幅温暖的 AI 肖像画，风格：水彩插画"
    else:
        prompt = "为一个阳光开朗的大学生绘制一幅温暖的 AI 肖像画，风格：水彩插画"

    client = get_minimax_client()
    url = await client.generate_image(prompt, aspect_ratio="1:1")
    return success(url)


@router.get("/growth", summary="获取成长数据")
def get_growth(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = service.get_growth_data(db, current_user.id)
    out = GrowthDataOut(**data)
    return success(out.model_dump(by_alias=True))


@router.get("/achievements", summary="获取成就列表（裸数组）")
def get_achievements(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = service.get_achievements(db, current_user.id)
    return success([AchievementOut(**item).model_dump(by_alias=True) for item in items])


@router.get("/settings", summary="获取用户设置")
def get_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = service.get_settings(db, current_user.id)
    # SettingsOut 的 auto_bgm 有 alias="autoBGM"
    out = SettingsOut(
        theme=data["theme"],
        notifications=data["notifications"],
        auto_bgm=data["auto_bgm"],
        diary_privacy=data["diary_privacy"],
        language=data["language"],
    )
    return success(out.model_dump(by_alias=True))


@router.post("/settings", summary="更新用户设置")
def update_settings(
    req: UpdateSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = req.model_dump(exclude_unset=True)
    result = service.update_settings(db, current_user.id, data)
    out = SettingsOut(
        theme=result["theme"],
        notifications=result["notifications"],
        auto_bgm=result["auto_bgm"],
        diary_privacy=result["diary_privacy"],
        language=result["language"],
    )
    return success(out.model_dump(by_alias=True))


@router.get("/semester-report", summary="获取学期报告")
def get_semester_report(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = service.get_semester_report(db, current_user.id)
    out = SemesterReportOut(**data)
    return success(out.model_dump(by_alias=True))


@router.get("/portrait", summary="获取用户画像")
def get_portrait(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取用户 AI 画像（从 user_profiles 取）"""
    from app.models.user_profile import UserProfile

    def _decode(s, default):
        try:
            return json.loads(s) if s else default
        except Exception:
            return default

    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        return success({
            "preferences": [],
            "personality": [],
            "relations": [],
            "interests": [],
        })

    # 转换 preferences: dict -> list of {category, items}
    raw_prefs = _decode(profile.preferences, {})
    if isinstance(raw_prefs, dict):
        prefs_list = [{"category": k, "items": v if isinstance(v, list) else [v]} for k, v in raw_prefs.items()]
    elif isinstance(raw_prefs, list):
        prefs_list = raw_prefs
    else:
        prefs_list = []

    # 转换 personality: str -> list
    personality = profile.personality or ""
    if isinstance(personality, str):
        personality_list = [p.strip() for p in personality.split("、") if p.strip()] if personality else []
    else:
        personality_list = personality

    # 转换 relations: dict -> list of {name, relation}
    raw_relations = _decode(profile.relations, {})
    if isinstance(raw_relations, dict):
        relations_list = [{"name": k, "relation": v} for k, v in raw_relations.items()]
    elif isinstance(raw_relations, list):
        relations_list = raw_relations
    else:
        relations_list = []

    interests = _decode(profile.interests, [])
    if not isinstance(interests, list):
        interests = []

    return success({
        "preferences": prefs_list,
        "personality": personality_list,
        "relations": relations_list,
        "interests": interests,
    })


@router.post("/portrait/refresh", summary="刷新用户画像")
async def refresh_portrait(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """调用 AI 分析日记+聊天数据，刷新用户画像"""
    from app.models.diary import Diary
    from app.models.chat import ChatMessage
    from app.models.user_profile import UserProfile
    from app.ai.minimax_client import get_minimax_client
    from uuid import uuid4

    def _decode(s, default):
        try:
            return json.loads(s) if s else default
        except Exception:
            return default

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
        profile = UserProfile(id=str(uuid4()), user_id=current_user.id, updated_at=now)
        db.add(profile)

    profile.personality = result.get("personality", "")
    profile.writing_style = result.get("writing_style", "")
    profile.interests = json.dumps(result.get("interests", []), ensure_ascii=False)
    profile.preferences = json.dumps(result.get("preferences", {}), ensure_ascii=False)
    profile.relations = json.dumps(result.get("relations", {}), ensure_ascii=False)
    profile.updated_at = now

    db.commit()
    db.refresh(profile)

    # 转换响应格式与 get_portrait 一致
    personality = profile.personality or ""
    personality_list = [p.strip() for p in personality.split("、") if p.strip()] if personality else []

    raw_prefs = _decode(profile.preferences, {})
    if isinstance(raw_prefs, dict):
        prefs_list = [{"category": k, "items": v if isinstance(v, list) else [v]} for k, v in raw_prefs.items()]
    else:
        prefs_list = raw_prefs if isinstance(raw_prefs, list) else []

    raw_relations = _decode(profile.relations, {})
    if isinstance(raw_relations, dict):
        relations_list = [{"name": k, "relation": v} for k, v in raw_relations.items()]
    else:
        relations_list = raw_relations if isinstance(raw_relations, list) else []

    interests = _decode(profile.interests, [])

    return success({
        "preferences": prefs_list,
        "personality": personality_list,
        "relations": relations_list,
        "interests": interests if isinstance(interests, list) else [],
    })
