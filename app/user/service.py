"""
用户模块服务层
"""
import json
import time
from collections import Counter
from typing import List

from sqlalchemy.orm import Session

from app.models.user import User, UserSettings, UserAchievement
from app.response import ApiException, NOT_FOUND


def _now_ms() -> int:
    return int(time.time() * 1000)


def _decode(s, default=None):
    if default is None:
        default = {}
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


# 成就定义（硬编码）
ACHIEVEMENTS = [
    {"id": "first_diary", "title": "第一篇日记", "description": "写下你的第一篇日记", "icon": "📖"},
    {"id": "diary_7", "title": "坚持一周", "description": "连续写日记 7 天", "icon": "🔥"},
    {"id": "diary_30", "title": "月记达人", "description": "累计写日记 30 篇", "icon": "🌙"},
    {"id": "diary_100", "title": "百日日记", "description": "累计写日记 100 篇", "icon": "💯"},
    {"id": "first_material", "title": "素材收集者", "description": "添加第一条素材", "icon": "📸"},
    {"id": "material_50", "title": "素材大师", "description": "累计添加 50 条素材", "icon": "🎨"},
    {"id": "first_pomodoro", "title": "专注开始", "description": "完成第一个番茄钟", "icon": "🍅"},
    {"id": "pomodoro_10", "title": "专注达人", "description": "累计完成 10 个番茄钟", "icon": "⏰"},
    {"id": "pomodoro_50", "title": "专注大师", "description": "累计完成 50 个番茄钟", "icon": "🏆"},
    {"id": "first_anniversary", "title": "纪念日管理员", "description": "添加第一个纪念日", "icon": "🎂"},
    {"id": "ai_chat_10", "title": "AI 知己", "description": "与 AI 对话 10 次", "icon": "🤖"},
    {"id": "first_comic", "title": "漫画初体验", "description": "生成第一幅漫画", "icon": "🖼️"},
    {"id": "first_novel", "title": "小说家", "description": "生成第一篇小说", "icon": "📝"},
    {"id": "first_share", "title": "分享达人", "description": "分享第一条内容", "icon": "🔗"},
    {"id": "emotion_happy", "title": "快乐使者", "description": "记录 10 条开心情绪", "icon": "😊"},
    {"id": "style_variety", "title": "风格多样", "description": "尝试所有日记风格", "icon": "🎭"},
    {"id": "night_owl", "title": "夜猫子", "description": "在深夜写日记 5 次", "icon": "🦉"},
    {"id": "early_bird", "title": "早起鸟", "description": "在早晨写日记 5 次", "icon": "🐦"},
    {"id": "social_match", "title": "社交达人", "description": "完成第一次匹配", "icon": "🤝"},
    {"id": "portrait_complete", "title": "画像完整", "description": "完成 AI 画像生成", "icon": "🎨"},
    {"id": "streak_14", "title": "两周连续", "description": "连续写日记 14 天", "icon": "🌟"},
    {"id": "streak_30", "title": "月度坚持", "description": "连续写日记 30 天", "icon": "🏅"},
    {"id": "first_extract", "title": "信息挖掘者", "description": "第一次 AI 信息提取", "icon": "🔍"},
    {"id": "semester_report", "title": "学期总结", "description": "查看第一份学期报告", "icon": "📊"},
]


def get_user_profile(db: Session, user_id: str) -> dict:
    """获取用户资料"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ApiException(code=NOT_FOUND, message="用户不存在", status_code=404)

    style_tags = _decode(user.style_tags, None) if user.style_tags else None

    return {
        "name": user.name or "",
        "school": user.school or "",
        "major": user.major or "",
        "level": user.level or 1,
        "diary_count": user.diary_count or 0,
        "streak_days": user.streak_days or 0,
        "pomodoro_count": user.pomodoro_count or 0,
        "avatar": user.avatar or "",
        "style_tags": style_tags,
        "custom_style_prompt": user.custom_style_prompt or None,
    }


def update_user_profile(db: Session, user_id: str, data: dict) -> dict:
    """更新用户资料"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ApiException(code=NOT_FOUND, message="用户不存在", status_code=404)

    if "name" in data and data["name"] is not None:
        user.name = data["name"]
    if "school" in data and data["school"] is not None:
        user.school = data["school"]
    if "major" in data and data["major"] is not None:
        user.major = data["major"]
    if "avatar" in data and data["avatar"] is not None:
        user.avatar = data["avatar"]
    if "style_tags" in data and data["style_tags"] is not None:
        user.style_tags = json.dumps(data["style_tags"], ensure_ascii=False)
    if "custom_style_prompt" in data and data["custom_style_prompt"] is not None:
        user.custom_style_prompt = data["custom_style_prompt"]

    user.updated_at = _now_ms()
    db.commit()
    db.refresh(user)
    return get_user_profile(db, user_id)


def get_settings(db: Session, user_id: str) -> dict:
    """获取用户设置"""
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        # 默认设置
        return {
            "theme": "light",
            "notifications": True,
            "auto_bgm": False,
            "diary_privacy": "private",
            "language": "zh-CN",
            "chat_material_enabled": True,
            "chat_silence_threshold": 30,
            "chat_material_toast": True,
            "chat_min_rounds": 3,
            "chat_model_id": "",
        }
    return {
        "theme": settings.theme or "light",
        "notifications": settings.notifications if settings.notifications is not None else True,
        "auto_bgm": settings.auto_bgm if settings.auto_bgm is not None else False,
        "diary_privacy": settings.diary_privacy or "private",
        "language": settings.language or "zh-CN",
        "chat_material_enabled": settings.chat_material_enabled if settings.chat_material_enabled is not None else True,
        "chat_silence_threshold": settings.chat_silence_threshold if settings.chat_silence_threshold is not None else 30,
        "chat_material_toast": settings.chat_material_toast if settings.chat_material_toast is not None else True,
        "chat_min_rounds": settings.chat_min_rounds if settings.chat_min_rounds is not None else 3,
        "chat_model_id": settings.chat_model_id or "",
    }


def update_settings(db: Session, user_id: str, data: dict) -> dict:
    """更新用户设置"""
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        from uuid import uuid4
        settings = UserSettings(
            id=str(uuid4()),
            user_id=user_id,
        )
        db.add(settings)

    if "theme" in data and data["theme"] is not None:
        settings.theme = data["theme"]
    if "notifications" in data and data["notifications"] is not None:
        settings.notifications = data["notifications"]
    if "auto_bgm" in data and data["auto_bgm"] is not None:
        settings.auto_bgm = data["auto_bgm"]
    if "diary_privacy" in data and data["diary_privacy"] is not None:
        settings.diary_privacy = data["diary_privacy"]
    if "language" in data and data["language"] is not None:
        settings.language = data["language"]
    if "chat_material_enabled" in data and data["chat_material_enabled"] is not None:
        settings.chat_material_enabled = data["chat_material_enabled"]
    if "chat_silence_threshold" in data and data["chat_silence_threshold"] is not None:
        settings.chat_silence_threshold = data["chat_silence_threshold"]
    if "chat_material_toast" in data and data["chat_material_toast"] is not None:
        settings.chat_material_toast = data["chat_material_toast"]
    if "chat_min_rounds" in data and data["chat_min_rounds"] is not None:
        settings.chat_min_rounds = data["chat_min_rounds"]
    if "chat_model_id" in data and data["chat_model_id"] is not None:
        model_id = str(data["chat_model_id"] or "").strip()
        if model_id:
            from app.ai.model_service import (
                BUILTIN_ARK_DEEPSEEK_V4_FLASH_ID,
                BUILTIN_ARK_DEEPSEEK_V4_PRO_ID,
                BUILTIN_ARK_DOUBAO_MINI_ID,
                BUILTIN_ARK_GLM_4_7_ID,
                BUILTIN_MINIMAX_ID,
                BUILTIN_VIVO_ID,
            )
            from app.models.user import UserLlmModel

            builtin_ids = {
                BUILTIN_VIVO_ID,
                BUILTIN_MINIMAX_ID,
                BUILTIN_ARK_DEEPSEEK_V4_FLASH_ID,
                BUILTIN_ARK_DEEPSEEK_V4_PRO_ID,
                BUILTIN_ARK_DOUBAO_MINI_ID,
                BUILTIN_ARK_GLM_4_7_ID,
            }
            if model_id not in builtin_ids:
                exists = (
                    db.query(UserLlmModel)
                    .filter(UserLlmModel.id == model_id, UserLlmModel.user_id == user_id, UserLlmModel.is_enabled.is_(True))
                    .first()
                )
                if not exists:
                    from app.response import PARAM_ERROR

                    raise ApiException(code=PARAM_ERROR, message="聊天默认模型不存在", status_code=400)
        settings.chat_model_id = model_id

    db.commit()
    db.refresh(settings)
    return get_settings(db, user_id)


def get_achievements(db: Session, user_id: str) -> List[dict]:
    """获取成就列表"""
    unlocked = {
        ua.achievement_id: ua.unlocked_at
        for ua in db.query(UserAchievement).filter(UserAchievement.user_id == user_id).all()
    }
    result = []
    for ach in ACHIEVEMENTS:
        unlocked_at = unlocked.get(ach["id"])
        result.append({
            "id": ach["id"],
            "title": ach["title"],
            "description": ach["description"],
            "icon": ach["icon"],
            "unlocked": ach["id"] in unlocked,
            "unlocked_at": unlocked_at,
        })
    return result


def get_growth_data(db: Session, user_id: str) -> dict:
    """获取成长数据"""
    from app.models.diary import Diary
    from app.models.study import Pomodoro
    from collections import defaultdict

    # 日记按日期统计
    diaries = db.query(Diary).filter(Diary.user_id == user_id).all()
    diary_by_date = defaultdict(int)
    emotion_counts = Counter()
    tag_counts = Counter()
    for d in diaries:
        if d.date:
            diary_by_date[d.date] += 1
        # 情绪统计
        em = _decode(d.emotion_summary, {})
        dominant = em.get("dominant", "")
        if dominant:
            emotion_counts[dominant] += 1
        # 标签统计
        tags = _decode(d.tags, [])
        for tag in tags:
            tag_counts[tag] += 1

    # 番茄钟按日期统计
    pomodoros = db.query(Pomodoro).filter(
        Pomodoro.user_id == user_id, Pomodoro.completed_at.isnot(None)
    ).all()
    pomo_by_date = defaultdict(int)
    for p in pomodoros:
        import datetime
        day = datetime.datetime.fromtimestamp(p.completed_at / 1000).strftime("%Y-%m-%d")
        pomo_by_date[day] += 1

    # 计算连续天数数组
    streak_list = list(range(1, (db.query(User).filter(User.id == user_id).first().streak_days or 0) + 1))

    return {
        "diaries": [{"date": k, "count": v} for k, v in sorted(diary_by_date.items())],
        "emotions": [{"label": k, "count": v} for k, v in emotion_counts.most_common(10)],
        "tags": [{"label": k, "count": v} for k, v in tag_counts.most_common(20)],
        "pomodoros": [{"date": k, "count": v} for k, v in sorted(pomo_by_date.items())],
        "streak": streak_list,
    }


def get_semester_report(db: Session, user_id: str) -> dict:
    """获取学期报告"""
    from app.models.diary import Diary
    from app.models.study import Pomodoro

    diaries = db.query(Diary).filter(Diary.user_id == user_id).all()
    pomodoros = db.query(Pomodoro).filter(
        Pomodoro.user_id == user_id, Pomodoro.completed_at.isnot(None)
    ).all()
    unlocked_count = db.query(UserAchievement).filter(UserAchievement.user_id == user_id).count()

    emotion_counts = Counter()
    tag_counts = Counter()
    for d in diaries:
        em = _decode(d.emotion_summary, {})
        dominant = em.get("dominant", "")
        if dominant:
            emotion_counts[dominant] += 1
        tags = _decode(d.tags, [])
        for tag in tags:
            tag_counts[tag] += 1

    user = db.query(User).filter(User.id == user_id).first()

    highlights = []
    if len(diaries) >= 10:
        highlights.append(f"本学期共写了 {len(diaries)} 篇日记，记录了许多美好时光")
    if len(pomodoros) >= 5:
        highlights.append(f"完成了 {len(pomodoros)} 个番茄钟，专注力很棒")
    if emotion_counts.most_common(1):
        top_em = emotion_counts.most_common(1)[0][0]
        highlights.append(f"主要情绪是「{top_em}」，生活充实愉快")
    if unlocked_count > 0:
        highlights.append(f"解锁了 {unlocked_count} 个成就，持续成长中")

    return {
        "total_diaries": len(diaries),
        "total_pomodoros": len(pomodoros),
        "top_emotions": [{"label": k, "count": v} for k, v in emotion_counts.most_common(5)],
        "top_tags": [{"label": k, "count": v} for k, v in tag_counts.most_common(10)],
        "writing_time": len(diaries) * 15,  # 估算每篇 15 分钟
        "avg_emotion": 75,  # 默认平均情绪分
        "streak": user.streak_days or 0 if user else 0,
        "achievements": unlocked_count,
        "highlights": highlights,
    }
