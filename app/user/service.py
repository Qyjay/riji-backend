"""
用户模块服务层
"""
import json
import time
from collections import Counter
from collections import defaultdict
from datetime import datetime, timedelta
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


def _date_from_ms(ts: int) -> str:
    try:
        return datetime.fromtimestamp(int(ts or 0) / 1000).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _short_date(date: str) -> str:
    try:
        d = datetime.strptime(date, "%Y-%m-%d")
        return f"{d.month}月{d.day}日"
    except Exception:
        return date or ""


def _level_threshold(level: int) -> int:
    if level <= 1:
        return 0
    return int(100 * (level - 1) ** 1.45)


def _level_from_xp(total_xp: int) -> dict:
    level = 1
    while _level_threshold(level + 1) <= total_xp:
        level += 1
    current = _level_threshold(level)
    next_level = _level_threshold(level + 1)
    span = max(1, next_level - current)
    in_level = max(0, total_xp - current)
    return {
        "level": level,
        "title": _growth_title(level),
        "total_xp": total_xp,
        "current_level_xp": current,
        "next_level_xp": next_level,
        "xp_in_current_level": in_level,
        "xp_to_next_level": max(0, next_level - total_xp),
        "progress_percent": min(100, max(0, round(in_level / span * 100))),
    }


def _growth_title(level: int) -> str:
    if level >= 20:
        return "生活策展人"
    if level >= 15:
        return "成长记录家"
    if level >= 10:
        return "日记创作者"
    if level >= 5:
        return "稳定探索者"
    return "探索者"


def _calc_streaks(dates: set[str]) -> tuple[int, int]:
    if not dates:
        return 0, 0
    parsed = sorted(datetime.strptime(d, "%Y-%m-%d").date() for d in dates if d)
    longest = 1
    current_run = 1
    for prev, cur in zip(parsed, parsed[1:]):
        if (cur - prev).days == 1:
            current_run += 1
        elif cur != prev:
            longest = max(longest, current_run)
            current_run = 1
    longest = max(longest, current_run)

    today = datetime.now().date()
    current = 0
    day = today
    while day.strftime("%Y-%m-%d") in dates:
        current += 1
        day -= timedelta(days=1)
    return current, longest


def _add_daily_xp(daily: dict, date: str, amount: int) -> None:
    if date and amount:
        daily[date] += amount


def _percent(value: int, target: int) -> int:
    return min(100, max(0, round((value / max(1, target)) * 100)))


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
    """获取成就列表：基于用户真实数据动态判定解锁状态。"""
    from app.models.diary import Diary
    from app.models.material import RawMaterial
    from app.models.study import Pomodoro
    from app.models.chat import ChatMessage
    from app.models.derivative import DiaryDerivative
    from app.models.anniversary import Anniversary
    from app.models.avatar import AvatarProfile
    from app.models.social import Match

    diaries = db.query(Diary).filter(Diary.user_id == user_id).all()
    materials = db.query(RawMaterial).filter(RawMaterial.user_id == user_id).all()
    pomodoros = db.query(Pomodoro).filter(
        Pomodoro.user_id == user_id, Pomodoro.completed_at.isnot(None)
    ).all()
    user_chat_count = db.query(ChatMessage).filter(
        ChatMessage.user_id == user_id, ChatMessage.role == "user"
    ).count()
    derivatives = (
        db.query(DiaryDerivative)
        .join(Diary, DiaryDerivative.diary_id == Diary.id)
        .filter(Diary.user_id == user_id)
        .all()
    )
    anniversary_count = db.query(Anniversary).filter(Anniversary.user_id == user_id).count()
    avatar_profile = db.query(AvatarProfile).filter(AvatarProfile.user_id == user_id).first()
    accepted_match_count = db.query(Match).filter(
        ((Match.user_id == user_id) | (Match.target_id == user_id)),
        Match.status == "accepted",
    ).count()

    diary_count = len(diaries)
    diary_dates = {d.date for d in diaries if d.date}
    _, longest_streak = _calc_streaks(diary_dates)
    material_count = len(materials)
    pomodoro_count = len(pomodoros)
    comic_count = sum(1 for x in derivatives if x.type == "comic")
    novel_count = sum(1 for x in derivatives if x.type == "novel")
    shared_count = sum(1 for x in derivatives if (x.share_scope or "private") != "private")
    styles_used = {(d.style or "").strip() for d in diaries if (d.style or "").strip()}

    happy_emotion_count = 0
    night_owl_count = 0
    early_bird_count = 0
    for d in diaries:
        em = _decode(d.emotion_summary, {})
        dominant = em.get("dominant", "")
        if dominant in ("开心", "快乐", "高兴", "愉快", "满足"):
            happy_emotion_count += 1
        hour = datetime.fromtimestamp(d.created_at / 1000).hour if d.created_at else -1
        if hour >= 23 or hour < 4:
            night_owl_count += 1
        if 5 <= hour < 9:
            early_bird_count += 1

    # 已查看学期报告 / 信息提取无独立持久化记录，沿用旧表（如果存在解锁记录则尊重之）
    legacy_unlocked = {
        ua.achievement_id: ua.unlocked_at
        for ua in db.query(UserAchievement).filter(UserAchievement.user_id == user_id).all()
    }

    conditions = {
        "first_diary": diary_count >= 1,
        "diary_7": longest_streak >= 7,
        "diary_30": diary_count >= 30,
        "diary_100": diary_count >= 100,
        "first_material": material_count >= 1,
        "material_50": material_count >= 50,
        "first_pomodoro": pomodoro_count >= 1,
        "pomodoro_10": pomodoro_count >= 10,
        "pomodoro_50": pomodoro_count >= 50,
        "first_anniversary": anniversary_count >= 1,
        "ai_chat_10": user_chat_count >= 10,
        "first_comic": comic_count >= 1,
        "first_novel": novel_count >= 1,
        "first_share": shared_count >= 1,
        "emotion_happy": happy_emotion_count >= 10,
        "style_variety": len(styles_used) >= 3,
        "night_owl": night_owl_count >= 5,
        "early_bird": early_bird_count >= 5,
        "social_match": accepted_match_count >= 1,
        "portrait_complete": avatar_profile is not None and bool((avatar_profile.summary or "").strip()),
        "streak_14": longest_streak >= 14,
        "streak_30": longest_streak >= 30,
        "first_extract": False,
        "semester_report": "semester_report" in legacy_unlocked,
    }

    # first_extract 没有专用统计字段，沿用历史解锁记录
    conditions["first_extract"] = "first_extract" in legacy_unlocked

    result = []
    for ach in ACHIEVEMENTS:
        unlocked = bool(conditions.get(ach["id"], False))
        result.append({
            "id": ach["id"],
            "title": ach["title"],
            "description": ach["description"],
            "icon": ach["icon"],
            "unlocked": unlocked,
            "unlocked_at": legacy_unlocked.get(ach["id"]),
        })
    return result



def get_growth_data(db: Session, user_id: str) -> dict:
    """获取成长数据"""
    from app.models.diary import Diary
    from app.models.material import RawMaterial
    from app.models.study import Pomodoro, Todo
    from app.models.chat import ChatMessage
    from app.models.derivative import DiaryDerivative
    from app.models.plaza import PlazaPost, PlazaComment
    from app.models.social import Match, SocialMessage

    diaries = db.query(Diary).filter(Diary.user_id == user_id).all()
    materials = db.query(RawMaterial).filter(RawMaterial.user_id == user_id).all()
    pomodoros = db.query(Pomodoro).filter(
        Pomodoro.user_id == user_id, Pomodoro.completed_at.isnot(None)
    ).all()
    todos = db.query(Todo).filter(Todo.user_id == user_id).all()
    chat_messages = db.query(ChatMessage).filter(ChatMessage.user_id == user_id).all()
    derivatives = (
        db.query(DiaryDerivative)
        .join(Diary, DiaryDerivative.diary_id == Diary.id)
        .filter(Diary.user_id == user_id)
        .all()
    )
    plaza_posts = db.query(PlazaPost).filter(PlazaPost.user_id == user_id).all()
    plaza_comments = db.query(PlazaComment).filter(PlazaComment.user_id == user_id).all()
    matches = db.query(Match).filter(
        (Match.user_id == user_id) | (Match.target_id == user_id)
    ).all()
    social_messages = db.query(SocialMessage).filter(SocialMessage.from_uid == user_id).all()
    unlocked_achievements = db.query(UserAchievement).filter(UserAchievement.user_id == user_id).all()

    diary_by_date = defaultdict(int)
    material_by_date = defaultdict(int)
    pomo_by_date = defaultdict(int)
    xp_by_date = defaultdict(int)
    emotion_counts = Counter()
    tag_counts = Counter()
    timeline = []

    for d in diaries:
        if d.date:
            diary_by_date[d.date] += 1
        em = _decode(d.emotion_summary, {})
        dominant = em.get("dominant", "")
        if dominant:
            emotion_counts[dominant] += 1
        tags = _decode(d.tags, [])
        for tag in tags:
            tag_counts[tag] += 1
        word_bonus = min(20, (len(d.content or "") // 100) * 2)
        xp = 30 + word_bonus
        _add_daily_xp(xp_by_date, d.date, xp)
        timeline.append({
            "date": d.date or _date_from_ms(d.created_at),
            "type": "diary",
            "title": "生成日记",
            "description": f"{d.title or '无标题'} · {len(d.content or '')} 字",
            "xp": xp,
            "source_id": d.id,
        })

    for m in materials:
        day = m.date or _date_from_ms(m.created_at)
        material_by_date[day] += 1
        xp = 5
        if m.emotion:
            xp += 3
        _add_daily_xp(xp_by_date, day, xp)

    for p in pomodoros:
        day = _date_from_ms(p.completed_at)
        pomo_by_date[day] += 1
        _add_daily_xp(xp_by_date, day, 15)

    for todo in todos:
        day = _date_from_ms(todo.created_at)
        _add_daily_xp(xp_by_date, day, 10 if todo.completed else 3)

    user_chat_messages = [msg for msg in chat_messages if msg.role == "user"]
    chat_by_date = defaultdict(int)
    for msg in user_chat_messages:
        day = _date_from_ms(msg.timestamp)
        chat_by_date[day] += 1
    for day, count in chat_by_date.items():
        _add_daily_xp(xp_by_date, day, min(40, count * 2))

    for derivative in derivatives:
        day = _date_from_ms(derivative.created_at)
        _add_daily_xp(xp_by_date, day, 20)
        if derivative.type == "comic":
            title = "生成漫画"
        elif derivative.type == "novel":
            title = "生成小说"
        else:
            title = "生成分享卡片"
        timeline.append({
            "date": day,
            "type": f"derivative_{derivative.type}",
            "title": title,
            "description": "完成一次日记二次创作",
            "xp": 20,
            "source_id": derivative.id,
        })

    for post in plaza_posts:
        _add_daily_xp(xp_by_date, _date_from_ms(post.created_at), 15)

    comment_by_date = defaultdict(int)
    for comment in plaza_comments:
        comment_by_date[_date_from_ms(comment.created_at)] += 1
    for day, count in comment_by_date.items():
        _add_daily_xp(xp_by_date, day, min(50, count * 5))

    for match in matches:
        if match.status == "accepted":
            _add_daily_xp(xp_by_date, _date_from_ms(match.created_at), 20)

    social_by_date = defaultdict(int)
    for msg in social_messages:
        social_by_date[_date_from_ms(msg.timestamp)] += 1
    for day, count in social_by_date.items():
        _add_daily_xp(xp_by_date, day, min(40, count * 2))

    for ach in unlocked_achievements:
        _add_daily_xp(xp_by_date, _date_from_ms(ach.unlocked_at), 20)

    diary_dates = {d.date for d in diaries if d.date}
    streak_days, longest_streak = _calc_streaks(diary_dates)
    for threshold, xp in [(7, 50), (14, 100), (30, 250)]:
        if longest_streak >= threshold:
            last_date = max(diary_dates) if diary_dates else ""
            _add_daily_xp(xp_by_date, last_date, xp)

    total_xp = sum(xp_by_date.values())
    level_payload = _level_from_xp(total_xp)
    today = datetime.now().strftime("%Y-%m-%d")
    start_day = datetime.now().date() - timedelta(days=29)
    chart = []
    for i in range(30):
        day = (start_day + timedelta(days=i)).strftime("%Y-%m-%d")
        chart.append({
            "date": day,
            "label": f"{(start_day + timedelta(days=i)).month}/{(start_day + timedelta(days=i)).day}",
            "xp": xp_by_date.get(day, 0),
            "diaries": diary_by_date.get(day, 0),
            "materials": material_by_date.get(day, 0),
            "pomodoros": pomo_by_date.get(day, 0),
        })

    total_words = sum(len(d.content or "") for d in diaries)
    completed_todos = sum(1 for todo in todos if todo.completed)
    comic_count = sum(1 for derivative in derivatives if derivative.type == "comic")
    novel_count = sum(1 for derivative in derivatives if derivative.type == "novel")
    share_count = sum(1 for derivative in derivatives if derivative.type == "share_card")
    accepted_matches = sum(1 for match in matches if match.status == "accepted")
    emotion_material_count = sum(1 for m in materials if m.emotion)

    stats = {
        "diaryCount": len(diaries),
        "materialCount": len(materials),
        "wordCount": total_words,
        "streakDays": streak_days,
        "longestStreak": longest_streak,
        "pomodoroCount": len(pomodoros),
        "todoCount": len(todos),
        "completedTodoCount": completed_todos,
        "chatRounds": len(user_chat_messages),
        "derivativeCount": len(derivatives),
        "comicCount": comic_count,
        "achievementCount": len(unlocked_achievements),
        "plazaPostCount": len(plaza_posts),
        "plazaCommentCount": len(plaza_comments),
        "acceptedMatchCount": accepted_matches,
    }

    skills = [
        {"key": "writing", "name": "写作", "value": _percent(len(diaries) * 6 + total_words // 250, 100), "basis": "日记篇数与字数"},
        {"key": "recording", "name": "记录", "value": _percent(len(materials) * 2 + longest_streak * 5, 100), "basis": "素材数量与连续记录"},
        {"key": "focus", "name": "专注", "value": _percent(len(pomodoros) * 8 + completed_todos * 4, 100), "basis": "番茄钟与待办完成"},
        {"key": "creation", "name": "创作", "value": _percent(len(derivatives) * 15, 100), "basis": "漫画、小说、分享卡片"},
        {"key": "social", "name": "社交", "value": _percent(len(plaza_posts) * 12 + len(plaza_comments) * 3 + accepted_matches * 20, 100), "basis": "广场互动与搭子匹配"},
        {"key": "selfInsight", "name": "自我理解", "value": _percent(emotion_material_count * 3 + len(emotion_counts) * 10, 100), "basis": "情绪识别与情绪多样性"},
    ]

    milestone_defs = [
        ("first_diary", "第 1 篇日记", len(diaries) >= 1, min((d.date for d in diaries if d.date), default="")),
        ("diary_7", "累计 7 篇日记", len(diaries) >= 7, ""),
        ("streak_7", "连续记录 7 天", longest_streak >= 7, ""),
        ("material_50", "收集 50 条素材", len(materials) >= 50, ""),
        ("first_comic", "生成第一幅漫画", comic_count >= 1, ""),
        ("pomodoro_10", "完成 10 个番茄钟", len(pomodoros) >= 10, ""),
        ("chat_50", "与 AI 对话 50 轮", len(user_chat_messages) >= 50, ""),
        ("level_10", "达到 Lv.10", level_payload["level"] >= 10, ""),
    ]
    milestones = [
        {
            "id": key,
            "name": name,
            "done": done,
            "date": _short_date(date) if date else ("已完成" if done else ""),
        }
        for key, name, done, date in milestone_defs
    ]

    if len(diaries) >= 1:
        first = min(diaries, key=lambda d: d.created_at or 0)
        timeline.append({
            "date": first.date or _date_from_ms(first.created_at),
            "type": "milestone",
            "title": "写下第一篇日记",
            "description": first.title or "开始记录生活",
            "xp": 30,
            "source_id": first.id,
        })
    if len(materials) >= 1:
        first_material = min(materials, key=lambda m: m.created_at or 0)
        timeline.append({
            "date": first_material.date or _date_from_ms(first_material.created_at),
            "type": "material",
            "title": "收集第一条素材",
            "description": "开始把生活片段放进 Avalin",
            "xp": 5,
            "source_id": first_material.id,
        })

    timeline = sorted(timeline, key=lambda item: item.get("date") or "", reverse=True)[:30]

    xp_breakdown = [
        {"label": "日记", "xp": sum(30 + min(20, (len(d.content or "") // 100) * 2) for d in diaries)},
        {"label": "素材", "xp": len(materials) * 5 + emotion_material_count * 3},
        {"label": "学习", "xp": len(pomodoros) * 15 + completed_todos * 10 + (len(todos) - completed_todos) * 3},
        {"label": "AI 对话", "xp": sum(min(40, count * 2) for count in chat_by_date.values())},
        {"label": "创作", "xp": len(derivatives) * 20},
        {"label": "社交", "xp": len(plaza_posts) * 15 + sum(min(50, count * 5) for count in comment_by_date.values()) + accepted_matches * 20},
        {"label": "成就", "xp": len(unlocked_achievements) * 20},
    ]

    return {
        **level_payload,
        "stats": stats,
        "skills": skills,
        "chart": chart,
        "milestones": milestones,
        "timeline": timeline,
        "today_xp": xp_by_date.get(today, 0),
        "xp_breakdown": xp_breakdown,
        "diaries": [{"date": k, "count": v} for k, v in sorted(diary_by_date.items())],
        "emotions": [{"label": k, "count": v} for k, v in emotion_counts.most_common(10)],
        "tags": [{"label": k, "count": v} for k, v in tag_counts.most_common(20)],
        "pomodoros": [{"date": k, "count": v} for k, v in sorted(pomo_by_date.items())],
        "streak": list(range(1, streak_days + 1)),
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
