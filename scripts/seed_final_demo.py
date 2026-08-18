# -*- coding: utf-8 -*-
"""Create an idempotent, recent seven-day demo account for the final.

Usage:
    .venv/bin/python scripts/seed_final_demo.py

Main account:
    username: avalin_demo
    password: 123456
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import or_


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.auth.service import hash_password  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.memory.ingestion import (  # noqa: E402
    ingest_chat_session,
    ingest_diary,
    ingest_material,
    ingest_plaza_comment,
    ingest_plaza_post,
    ingest_social_message,
)
from app.models.anniversary import Anniversary  # noqa: E402
from app.models.avatar import (  # noqa: E402
    AvatarAtoaInteraction,
    AvatarAtoaSession,
    AvatarMatch,
    AvatarMemory,
    AvatarProfile,
    AvatarStatus,
    AvatarSurfJob,
    AvatarSurfLog,
    AvatarUsageStat,
)
from app.models.biography import BiographyChapter  # noqa: E402
from app.models.chat import ChatMessage, ChatSession  # noqa: E402
from app.models.derivative import DiaryDerivative  # noqa: E402
from app.models.diary import Diary  # noqa: E402
from app.models.material import RawMaterial  # noqa: E402
from app.models.memory import (  # noqa: E402
    AgentAction,
    AvatarCard,
    MemoryChunk,
    MemoryDocument,
    MemoryFact,
    MemoryProfile,
)
from app.models.plaza import PlazaComment, PlazaPost, PostLike  # noqa: E402
from app.models.social import Match, SocialMessage  # noqa: E402
from app.models.study import Pomodoro, Todo  # noqa: E402
from app.models.user import User, UserAchievement, UserSettings  # noqa: E402
from app.models.user_profile import UserProfile  # noqa: E402


TZ = ZoneInfo("Asia/Shanghai")
PASSWORD = "123456"
MAIN_USERNAME = "avalin_demo"
MANAGED_USERNAMES = [
    MAIN_USERNAME,
    "li_youran_demo",
    "wang_xinyi_demo",
    "zhao_mingyuan_demo",
]


def _id() -> str:
    return str(uuid4())


def _json(value, default: str = "[]") -> str:
    if value is None:
        return default
    return json.dumps(value, ensure_ascii=False)


def _ms(day: str, hhmm: str = "12:00") -> int:
    dt = datetime.strptime(f"{day} {hhmm}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    return int(dt.timestamp() * 1000)


def _now_ms() -> int:
    return int(datetime.now(TZ).timestamp() * 1000)


def _avatar_url(name: str, scene: str) -> str:
    prompt = (
        f"realistic friendly Chinese university student profile portrait, {name}, {scene}, "
        "natural daylight, clean warm neutral background, smartphone app avatar, no text, no watermark"
    )
    return (
        "https://copilot-cn.bytedance.net/api/ide/v1/text_to_image"
        f"?prompt={quote(prompt)}&image_size=square"
    )


def _media_pool(folder: str, suffixes: tuple[str, ...]) -> list[str]:
    result: list[str] = []
    upload_dir = ROOT_DIR / "uploads"
    if not upload_dir.exists():
        return result
    for path in sorted(upload_dir.rglob("*")):
        if path.is_file() and folder in path.parts and path.suffix.lower() in suffixes:
            result.append("/" + path.relative_to(ROOT_DIR).as_posix())
    return result


def _seven_days() -> list[str]:
    today = datetime.now(TZ).date()
    return [(today - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)]


DAY_STORIES = [
    {
        "title": "把一周慢下来",
        "note": "周五课程结束后，我在校园里慢慢走了一圈，决定认真记录接下来这一周。",
        "photo": "傍晚的校园步道被树影切成明暗两段，路边有骑车经过的学生。",
        "voice": "最近节奏有点快，我想找一个也喜欢散步和拍照的人，不需要一直说话也不会尴尬。",
        "location": "南开大学津南校区",
        "weather": "晴 29℃",
        "emotion": ("期待", 82, "🌤"),
        "tags": ["校园散步", "摄影", "慢生活"],
    },
    {
        "title": "图书馆里的专注下午",
        "note": "下午在图书馆改完了比赛原型，番茄钟把一个很大的任务拆成了四小段。",
        "photo": "木色书桌上放着笔记本电脑、橙色便签和一杯冰美式，屏幕是产品流程图。",
        "voice": "一个人推进项目效率很高，但也希望有人能听懂我为什么对产品细节这么较真。",
        "location": "南开大学图书馆",
        "weather": "多云 28℃",
        "emotion": ("专注", 88, "🎯"),
        "tags": ["产品设计", "AIGC", "图书馆"],
    },
    {
        "title": "一次不赶时间的夜跑",
        "note": "今晚第一次没有追配速，只沿着操场跑了三公里，结束后整个人安静了很多。",
        "photo": "夜色中的塑胶跑道和远处亮灯的教学楼，近处有一双白色跑鞋。",
        "voice": "我更喜欢轻松跑，不想把运动也变成竞争。如果有人同频，偶尔一起跑就很好。",
        "location": "南开大学体育场",
        "weather": "晴 26℃",
        "emotion": ("舒展", 86, "🏃"),
        "tags": ["夜跑", "低压力运动", "校园"],
    },
    {
        "title": "被一场雨留在咖啡店",
        "note": "突如其来的雨把我留在校门口的咖啡店，我索性整理了最近拍的照片。",
        "photo": "玻璃窗上挂着雨滴，窗边桌面有相机和摊开的照片，室内是暖黄色灯光。",
        "voice": "翻照片时发现我总在拍那些很普通的瞬间，树影、空椅子、下雨后的路面。",
        "location": "海河教育园区",
        "weather": "阵雨 25℃",
        "emotion": ("平静", 78, "🌧"),
        "tags": ["雨天", "街头摄影", "咖啡店"],
    },
    {
        "title": "把方案讲给真正的人听",
        "note": "今天找同学完整讲了一遍 Avalin，最有价值的反馈是：不要替用户决定关系。",
        "photo": "会议桌上铺着手绘流程图，两部手机展示着记忆页和分身对话页。",
        "voice": "我越来越确定，人机边界不是限制，而是这个产品值得信任的原因。",
        "location": "软件学院创新实验室",
        "weather": "晴 30℃",
        "emotion": ("笃定", 91, "💡"),
        "tags": ["Avalin", "人机边界", "用户测试"],
    },
    {
        "title": "同一片晚霞",
        "note": "傍晚在湖边拍到一片很低的橙色晚霞，回去后发现广场上也有人发了相似视角。",
        "photo": "湖边晚霞呈暖橙色，水面有细碎反光，画面边缘是一棵被风吹动的柳树。",
        "voice": "原来同一所校园里真的有人和我看见了同一个瞬间，只是我们以前没有入口。",
        "location": "南开大学大通湖",
        "weather": "晴 27℃",
        "emotion": ("惊喜", 93, "🌇"),
        "tags": ["晚霞", "大通湖", "同频"],
    },
    {
        "title": "让分身先替我开口",
        "note": "今天把公开名片重新确认了一遍，只授权摄影、散步和轻松夜跑相关的信息。",
        "photo": "手机屏幕上是分身名片授权页，旁边放着相机和一张校园湖边的照片。",
        "voice": "我愿意让分身先聊两轮，但是否认识对方、要不要交换联系方式，必须由我自己决定。",
        "location": "南开大学宿舍",
        "weather": "多云 28℃",
        "emotion": ("安心", 90, "🧡"),
        "tags": ["分身名片", "隐私授权", "AtoA"],
    },
]


SUPPORT_USERS = [
    {
        "username": "li_youran_demo",
        "name": "李悠冉",
        "school": "南开大学",
        "major": "新闻与传播",
        "grade": "大三",
        "interests": ["校园摄影", "晚霞", "散步", "轻松夜跑"],
        "summary": "喜欢记录校园里的普通瞬间，社交慢热，习惯先从共同作品和具体活动开始认识人。",
    },
    {
        "username": "wang_xinyi_demo",
        "name": "王心怡",
        "school": "天津大学",
        "major": "工业设计",
        "grade": "大二",
        "interests": ["产品设计", "展览", "咖啡", "摄影"],
        "summary": "关注产品体验与视觉叙事，希望找到能一起看展、讨论设计又尊重独处时间的朋友。",
    },
    {
        "username": "zhao_mingyuan_demo",
        "name": "赵明远",
        "school": "南开大学",
        "major": "计算机科学",
        "grade": "大三",
        "interests": ["AIGC", "夜跑", "产品开发", "开源"],
        "summary": "正在做 AIGC 项目，表达直接但友善，偏好围绕具体问题展开交流。",
    },
]


def purge_managed_data(db) -> None:
    users = db.query(User).filter(User.username.in_(MANAGED_USERNAMES)).all()
    if not users:
        return
    user_ids = [item.id for item in users]
    diary_ids = [r[0] for r in db.query(Diary.id).filter(Diary.user_id.in_(user_ids)).all()]
    session_ids = [r[0] for r in db.query(ChatSession.id).filter(ChatSession.user_id.in_(user_ids)).all()]
    post_ids = [r[0] for r in db.query(PlazaPost.id).filter(PlazaPost.user_id.in_(user_ids)).all()]
    match_ids = [
        r[0]
        for r in db.query(Match.id)
        .filter(or_(Match.user_id.in_(user_ids), Match.target_id.in_(user_ids)))
        .all()
    ]
    document_ids = [
        r[0] for r in db.query(MemoryDocument.id).filter(MemoryDocument.user_id.in_(user_ids)).all()
    ]

    db.query(AvatarAtoaInteraction).filter(
        or_(
            AvatarAtoaInteraction.initiator_id.in_(user_ids),
            AvatarAtoaInteraction.user_a_id.in_(user_ids),
            AvatarAtoaInteraction.user_b_id.in_(user_ids),
        )
    ).delete(synchronize_session=False)
    db.query(AvatarAtoaSession).filter(AvatarAtoaSession.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(AvatarSurfJob).filter(AvatarSurfJob.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(AvatarSurfLog).filter(AvatarSurfLog.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(AvatarMatch).filter(
        or_(AvatarMatch.user_id.in_(user_ids), AvatarMatch.target_user_id.in_(user_ids))
    ).delete(synchronize_session=False)

    db.query(MemoryFact).filter(MemoryFact.user_id.in_(user_ids)).delete(synchronize_session=False)
    if document_ids:
        db.query(MemoryChunk).filter(
            or_(MemoryChunk.user_id.in_(user_ids), MemoryChunk.document_id.in_(document_ids))
        ).delete(synchronize_session=False)
    db.query(MemoryDocument).filter(MemoryDocument.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(MemoryProfile).filter(MemoryProfile.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(AvatarCard).filter(AvatarCard.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(AgentAction).filter(AgentAction.user_id.in_(user_ids)).delete(synchronize_session=False)

    if match_ids:
        db.query(SocialMessage).filter(SocialMessage.match_id.in_(match_ids)).delete(
            synchronize_session=False
        )
    db.query(SocialMessage).filter(SocialMessage.from_uid.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(Match).filter(
        or_(Match.user_id.in_(user_ids), Match.target_id.in_(user_ids))
    ).delete(synchronize_session=False)

    if post_ids:
        db.query(PostLike).filter(PostLike.post_id.in_(post_ids)).delete(synchronize_session=False)
        db.query(PlazaComment).filter(PlazaComment.post_id.in_(post_ids)).delete(
            synchronize_session=False
        )
    db.query(PostLike).filter(PostLike.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(PlazaComment).filter(PlazaComment.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(PlazaPost).filter(PlazaPost.user_id.in_(user_ids)).delete(synchronize_session=False)

    db.query(ChatMessage).filter(
        or_(ChatMessage.user_id.in_(user_ids), ChatMessage.session_id.in_(session_ids))
    ).delete(synchronize_session=False)
    db.query(ChatSession).filter(ChatSession.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    if diary_ids:
        db.query(Anniversary).filter(Anniversary.diary_id.in_(diary_ids)).delete(
            synchronize_session=False
        )
        db.query(DiaryDerivative).filter(DiaryDerivative.diary_id.in_(diary_ids)).delete(
            synchronize_session=False
        )
    db.query(Anniversary).filter(Anniversary.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(Diary).filter(Diary.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(RawMaterial).filter(RawMaterial.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(BiographyChapter).filter(BiographyChapter.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(Pomodoro).filter(Pomodoro.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(Todo).filter(Todo.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(AvatarMemory).filter(AvatarMemory.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(AvatarProfile).filter(AvatarProfile.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(AvatarUsageStat).filter(AvatarUsageStat.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(AvatarStatus).filter(AvatarStatus.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(UserProfile).filter(UserProfile.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(UserAchievement).filter(UserAchievement.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(UserSettings).filter(UserSettings.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    db.commit()


def create_user(
    db,
    *,
    username: str,
    name: str,
    school: str,
    major: str,
    grade: str,
    interests: list[str],
    summary: str,
    avatar_scene: str,
    comprehensive: bool = False,
) -> User:
    now = _now_ms()
    user = User(
        id=_id(),
        username=username,
        password=hash_password(PASSWORD),
        name=name,
        school=school,
        major=major,
        grade=grade,
        avatar=_avatar_url(name, avatar_scene),
        signature=summary,
        level=8 if comprehensive else 4,
        xp=1680 if comprehensive else 680,
        diary_count=7 if comprehensive else 1,
        streak_days=7 if comprehensive else 3,
        pomodoro_count=12 if comprehensive else 2,
        style_tags=_json(["真实细节", "克制表达", "生活观察"], "[]"),
        custom_style_prompt="保留具体场景和真实感受，不过度抒情。",
        created_at=now - 7 * 24 * 3600 * 1000,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    db.add(
        UserSettings(
            id=_id(),
            user_id=user.id,
            theme="light",
            notifications=True,
            auto_bgm=False,
            diary_privacy="private",
            language="zh-CN",
            chat_material_enabled=True,
            chat_silence_threshold=30,
            chat_material_toast=True,
            chat_min_rounds=3,
        )
    )
    db.add(
        UserProfile(
            id=_id(),
            user_id=user.id,
            preferences=_json(
                {
                    "recording": ["照片", "语音", "短文字"],
                    "activities": interests[:3],
                    "socialPace": "先低压力试聊，再由真人确认",
                },
                "{}",
            ),
            personality="细腻、独立、慢热，愿意围绕具体兴趣建立关系。",
            writing_style="用具体场景承载感受，语言自然克制。",
            relations=_json({"室友周然": "亲近朋友", "产品组同学": "项目伙伴"}, "{}"),
            interests=_json(interests, "[]"),
            updated_at=now,
        )
    )
    db.add(
        AvatarCard(
            id=_id(),
            user_id=user.id,
            display_name=f"{name}的分身",
            public_summary=summary,
            interest_tags=_json(interests, "[]"),
            social_intent=_json(["buddy", "share", "activity"], "[]"),
            conversation_style=_json(
                {"tone": "自然、友善、低压力", "pace": "先聊共同经历，再提出具体活动"},
                "{}",
            ),
            boundaries=_json(
                ["不公开私密日记原文", "不交换联系方式", "不替本人承诺见面"],
                "[]",
            ),
            visibility="public",
            updated_at=now,
        )
    )
    db.add(
        AvatarStatus(
            id=_id(),
            user_id=user.id,
            is_active=True,
            browsed_count=48 if comprehensive else 12,
            matched_count=6 if comprehensive else 2,
            chatting_count=2 if comprehensive else 0,
            last_active_at=now,
            enabled_channels=_json(["buddy", "help", "share"], "[]"),
            enabled_actions=_json(["browse", "match", "comment"], "[]"),
            match_range=_json({"school": school, "distanceKm": 12}, "{}"),
            surf_frequency="adaptive",
            surf_window=_json({"start": "08:00", "end": "23:00", "timezone": "Asia/Shanghai"}, "{}"),
            personalized_surf_plan=_json(
                {
                    "mode": "personalized",
                    "preferredHours": [9, 13, 18, 21],
                    "dailyLimit": 5,
                    "minIntervalMinutes": 120,
                },
                "{}",
            ),
            next_surf_at=now + 2 * 3600 * 1000,
            last_surf_at=now - 30 * 60 * 1000,
            daily_surf_count=2,
            daily_action_count=1,
            quiet_mode=False,
            auto_match_enabled=True,
            auto_comment_enabled=True,
            auto_publish_enabled=False,
        )
    )
    db.add(
        AvatarProfile(
            id=_id(),
            user_id=user.id,
            summary=summary,
            diary_count=7 if comprehensive else 1,
            chat_count=7 if comprehensive else 0,
            generated_at=now,
        )
    )
    return user


def create_daily_history(db, user: User, days: list[str]) -> tuple[list[Diary], list[RawMaterial], list[ChatSession]]:
    images = _media_pool("diary-image", (".jpg", ".jpeg", ".png", ".webp"))
    voices = _media_pool("voice", (".m4a", ".wav", ".mp3"))
    diaries: list[Diary] = []
    materials: list[RawMaterial] = []
    sessions: list[ChatSession] = []

    for index, (day, story) in enumerate(zip(days, DAY_STORIES)):
        image_url = images[index % len(images)] if images else ""
        voice_url = voices[index % len(voices)] if voices else ""
        emotion = {"label": story["emotion"][0], "score": story["emotion"][1], "emoji": story["emotion"][2]}
        common = {
            "user_id": user.id,
            "location": _json({"address": story["location"], "lat": None, "lng": None}, "{}"),
            "emotion": _json(emotion, "{}"),
        }
        text_material = RawMaterial(
            id=_id(),
            type="text",
            content=story["note"],
            media_url="[]",
            thumbnail_url="[]",
            tags=_json(story["tags"], "[]"),
            date=f"{day} 10:20:00",
            created_at=_ms(day, "10:20"),
            **common,
        )
        image_material = RawMaterial(
            id=_id(),
            type="image",
            content=story["photo"],
            media_url=_json([image_url] if image_url else [], "[]"),
            thumbnail_url=_json([image_url] if image_url else [], "[]"),
            tags=_json(story["tags"] + ["视觉理解"], "[]"),
            date=f"{day} 18:10:00",
            created_at=_ms(day, "18:10"),
            **common,
        )
        voice_material = RawMaterial(
            id=_id(),
            type="voice",
            content=story["voice"],
            media_url=_json([voice_url] if voice_url else [], "[]"),
            thumbnail_url="[]",
            tags=_json(story["tags"] + ["语音"], "[]"),
            date=f"{day} 21:15:00",
            created_at=_ms(day, "21:15"),
            **common,
        )
        db.add_all([text_material, image_material, voice_material])
        db.flush()

        session = ChatSession(
            id=_id(),
            user_id=user.id,
            status="closed",
            start_time=_ms(day, "21:30"),
            end_time=_ms(day, "21:48"),
            message_count=6,
            title=f"聊聊：{story['title']}",
            summary=f"从今天的记录中确认了“{story['tags'][0]}”是值得保留的近期线索。",
            mood=story["emotion"][0],
            mood_emoji=story["emotion"][2],
            topic_tags=_json(story["tags"], "[]"),
            material_id=None,
            date=day,
            created_at=_ms(day, "21:30"),
        )
        db.add(session)
        db.flush()
        messages = [
            ("user", story["voice"]),
            ("assistant", f"我听见你在意的不是热闹，而是围绕“{story['tags'][0]}”自然发生的陪伴。"),
            ("user", "对，我不希望为了社交而社交，也不想让 AI 替我做决定。"),
            ("assistant", "可以只把这条作为画像证据，公开名片只保留兴趣和社交节奏。"),
            ("user", "那就这样，先让分身帮我找到可能同频的人。"),
            ("assistant", "已记录。分身可以试聊，但申请认识和建立关系仍由你确认。"),
        ]
        for msg_index, (role, content) in enumerate(messages):
            db.add(
                ChatMessage(
                    id=_id(),
                    user_id=user.id,
                    role=role,
                    content=content,
                    timestamp=_ms(day, f"21:{30 + msg_index * 3:02d}"),
                    session_id=session.id,
                    client_message_id=f"demo-{day}-{msg_index}",
                    attachments="[]",
                )
            )
        chat_material = RawMaterial(
            id=_id(),
            user_id=user.id,
            type="chat",
            content=f"与 AI 围绕“{story['title']}”完成了一次梳理，确认了兴趣、边界和下一步。",
            media_url="[]",
            thumbnail_url="[]",
            location=common["location"],
            emotion=common["emotion"],
            tags=_json(story["tags"] + ["AI对话"], "[]"),
            date=f"{day} 21:50:00",
            created_at=_ms(day, "21:50"),
            chat_session_id=session.id,
            start_time=session.start_time,
            end_time=session.end_time,
        )
        db.add(chat_material)
        db.flush()
        session.material_id = chat_material.id

        day_materials = [text_material, image_material, voice_material, chat_material]
        diary = Diary(
            id=_id(),
            user_id=user.id,
            title=story["title"],
            content=(
                f"{story['note']}\n\n{story['photo']}\n\n"
                f"晚上重新听语音时，我发现这一周反复出现的不是“想认识更多人”，"
                f"而是想找到能共享具体时刻、又尊重彼此节奏的人。"
                f"我愿意把{story['tags'][0]}写进公开名片，但不会公开日记原文。"
            ),
            images=_json([image_url] if image_url else [], "[]"),
            emotion=_json(emotion, "{}"),
            tags=_json(story["tags"], "[]"),
            location=story["location"],
            weather=story["weather"],
            style="日记式",
            has_comic=index == 5,
            has_bgm=False,
            comic_url=image_url if index == 5 else "",
            bgm_url="",
            image_understandings=_json([story["photo"]], "[]"),
            created_at=_ms(day, "22:15"),
            updated_at=_ms(day, "22:20"),
            special_date="第一次让分身试聊" if index == 6 else "",
            ai_comment=f"你今天把“{story['tags'][0]}”从一个模糊偏好变成了可验证的生活线索。",
            emotion_summary=_json(
                {
                    "dominant": story["emotion"][0],
                    "distribution": {story["emotion"][0]: story["emotion"][1]},
                    "trend": [{"hour": 22, "label": story["emotion"][0], "score": story["emotion"][1]}],
                },
                "{}",
            ),
            material_ids=_json([item.id for item in day_materials], "[]"),
            edit_count=1 if index == 4 else 0,
            max_edits=3,
            status="published",
            date=day,
        )
        db.add(diary)
        diaries.append(diary)
        materials.extend(day_materials)
        sessions.append(session)

    db.flush()
    return diaries, materials, sessions


def create_personal_features(db, user: User, diaries: list[Diary], days: list[str]) -> None:
    now = _now_ms()
    for index, content in enumerate(
        [
            "偏好傍晚在校园散步，并拍摄树影、湖面和晚霞。",
            "喜欢低压力夜跑，不追求配速和竞技。",
            "对产品细节和人机边界有持续兴趣。",
            "社交慢热，更适合先围绕具体共同经历交流。",
            "希望寻找摄影、散步或 AIGC 项目搭子。",
            "不授权分身公开私密日记、联系方式和住址。",
            "所有结交申请必须由本人确认。",
            "近期正在准备 Avalin 项目的决赛演示。",
        ]
    ):
        category = ["interest", "habit", "interest", "personality", "need", "fact", "fact", "need"][index]
        db.add(
            AvatarMemory(
                id=_id(),
                user_id=user.id,
                category=category,
                content=content,
                source="diary" if index < 5 else "manual",
                source_ref=diaries[min(index, len(diaries) - 1)].id,
                confidence=0.96,
                is_active=True,
                is_pinned=index in (0, 4, 6),
                need_type="buddy" if category == "need" else None,
                urgency="active" if category == "need" else None,
                match_status="searching" if category == "need" else None,
                tags=_json(["摄影", "散步", "AtoA"], "[]"),
                created_at=now - (8 - index) * 3600 * 1000,
                updated_at=now,
            )
        )

    db.add(
        MemoryProfile(
            id=_id(),
            user_id=user.id,
            profile_type="avatar",
            summary="细腻、慢热但有明确行动力的产品设计者，偏好从共同作品和低压力活动开始认识人。",
            traits=_json({"细腻": 0.92, "独立": 0.87, "行动力": 0.84, "边界感": 0.95}, "{}"),
            interests=_json(["校园摄影", "轻松夜跑", "AIGC 产品", "散步"], "[]"),
            preferences=_json({"socialPace": "slow", "bestTime": "18:00-22:00"}, "{}"),
            relations=_json({"室友周然": "亲近朋友", "产品组同学": "项目伙伴"}, "{}"),
            social_style=_json({"opening": "从共同照片或具体活动开始", "frequency": "低频高质量"}, "{}"),
            boundaries=_json(["不暴露私密原文", "不自动承诺见面", "不交换联系方式"], "[]"),
            recent_state="正在准备决赛，同时希望找到能一起拍校园晚霞的同频搭子。",
            version=3,
            generated_at=now,
            source_range=_json({"start": days[0], "end": days[-1], "diaryCount": 7}, "{}"),
        )
    )
    for weekday in range(7):
        hour = [9, 13, 18, 21][weekday % 4]
        db.add(
            AvatarUsageStat(
                id=_id(),
                user_id=user.id,
                weekday=weekday,
                hour=hour,
                open_count=3 + weekday % 3,
                active_ms=(12 + weekday * 2) * 60 * 1000,
                page_weights=_json({"memory": 5, "avatar": 4, "plaza": 3, "chat": 2}, "{}"),
                last_seen_at=now - (6 - weekday) * 24 * 3600 * 1000,
                updated_at=now,
            )
        )

    for index, content in enumerate(
        ["完成决赛演示主流程", "和分身确认公开名片边界", "周末去大通湖拍一组晚霞", "整理 AtoA 用户测试反馈"]
    ):
        db.add(
            Todo(
                id=_id(),
                user_id=user.id,
                content=content,
                completed=index in (1, 3),
                priority="high" if index == 0 else "medium",
                created_at=_ms(days[max(0, index + 2)], "09:00"),
            )
        )
    for index in range(12):
        day = days[index % 7]
        db.add(
            Pomodoro(
                id=_id(),
                user_id=user.id,
                task=["打磨交互原型", "整理答辩材料", "修复 AtoA 流程"][index % 3],
                subject="Avalin 决赛",
                duration=25,
                completed_at=_ms(day, f"{14 + index % 5:02d}:25"),
                created_at=_ms(day, f"{14 + index % 5:02d}:00"),
            )
        )
    for achievement in ["diary_7", "streak_7", "pomodoro_10", "social_match"]:
        db.add(
            UserAchievement(
                id=_id(),
                user_id=user.id,
                achievement_id=achievement,
                unlocked_at=now - 2 * 3600 * 1000,
            )
        )
    db.add(
        Anniversary(
            id=_id(),
            user_id=user.id,
            title="第一次让分身替我试聊",
            date=days[-1][5:],
            year=int(days[-1][:4]),
            source="ai_extracted",
            related_person="李悠冉",
            diary_id=diaries[-1].id,
            created_at=now,
        )
    )
    db.add_all(
        [
            DiaryDerivative(
                id=_id(),
                diary_id=diaries[-2].id,
                type="share_card",
                content="你以为只有自己这样。其实，同频的人也在等一个入口。",
                media_url="",
                share_scope="private",
                created_at=now - 24 * 3600 * 1000,
            ),
            DiaryDerivative(
                id=_id(),
                diary_id=diaries[-2].id,
                type="comic",
                content="傍晚，两个人在同一片晚霞下按下快门。",
                media_url=json.loads(diaries[-2].images or "[]")[0] if json.loads(diaries[-2].images or "[]") else "",
                share_scope="private",
                created_at=now - 23 * 3600 * 1000,
            ),
        ]
    )
    db.add(
        BiographyChapter(
            id=_id(),
            user_id=user.id,
            chapter_index=1,
            title="同频的人，也在等一个入口",
            content="这一周，陈婷婷用照片、语音和日记重新认识了自己的节奏。她没有让 AI 替她交朋友，而是先把记忆变成证据，把边界写进名片，再让两个分身完成一次低风险试聊。",
            preview="从七天生活记录，到一次由本人决定的连接。",
            word_count=620,
            summary="记录逐渐形成画像，画像驱动分身完成 AtoA 预社交。",
            cover_image_url=json.loads(diaries[-2].images or "[]")[0] if json.loads(diaries[-2].images or "[]") else "",
            illustrations=_json([{"diary_id": diaries[-2].id, "image_url": diaries[-2].comic_url, "anchor_para": 1}], "[]"),
            date_range_start=days[0],
            date_range_end=days[-1],
            source_diary_ids=_json([item.id for item in diaries], "[]"),
            source_material_count=28,
            source_post_count=3,
            status="done",
            created_at=now,
            updated_at=now,
        )
    )


def create_plaza_and_social(db, main: User, supports: list[User], days: list[str]) -> tuple[list[PlazaPost], list[SocialMessage]]:
    images = _media_pool("diary-image", (".jpg", ".jpeg", ".png", ".webp"))
    post_specs = [
        (main, "share", "今天在大通湖拍到一片很低的晚霞。不是滤镜，是下过雨之后真实的橙色。", ["晚霞", "校园摄影"], days[-2]),
        (main, "buddy", "想找一位不赶配速的夜跑搭子，三公里左右，跑完可以各自回去。", ["夜跑", "低压力运动"], days[-4]),
        (main, "help", "正在测试一个“AI 先试聊、真人再决定”的社交产品，想听听大家对边界感的真实看法。", ["AIGC", "产品测试"], days[-3]),
        (supports[0], "share", "原来你也拍了。同一个傍晚，我在湖的另一边按下快门。", ["晚霞", "校园摄影"], days[-1]),
        (supports[1], "buddy", "周末想去看设计展，节奏慢一点，边看边聊即可。", ["设计", "看展"], days[-2]),
        (supports[2], "help", "AIGC 项目进入联调阶段，想找人互测一次完整产品流程。", ["AIGC", "产品开发"], days[-1]),
    ]
    posts: list[PlazaPost] = []
    for index, (author, kind, content, tags, day) in enumerate(post_specs):
        image = images[index % len(images)] if images and kind == "share" else ""
        post = PlazaPost(
            id=_id(),
            user_id=author.id,
            type=kind,
            content=content,
            images=_json([image] if image else [], "[]"),
            location="南开大学津南校区" if author.school == "南开大学" else author.school,
            tags=_json(tags, "[]"),
            likes=3 + index,
            comments=1,
            agent_responses=2 if index < 4 else 1,
            is_from_agent=False,
            allow_agent_reply=True,
            school_only=False,
            created_at=_ms(day, f"{18 + index % 4:02d}:20"),
        )
        db.add(post)
        posts.append(post)
    db.flush()
    for index, post in enumerate(posts):
        commenter = supports[index % len(supports)] if post.user_id == main.id else main
        db.add(
            PlazaComment(
                id=_id(),
                post_id=post.id,
                user_id=commenter.id,
                parent_comment_id=None,
                content=["这个视角我也拍过，湖面反光特别好看。", "这个边界我赞同，AI 只能建议，不能替人承诺。", "时间合适的话我愿意参加一次互测。"][index % 3],
                is_agent=index % 2 == 1,
                created_at=post.created_at + 20 * 60 * 1000,
            )
        )
        db.add(
            PostLike(
                id=_id(),
                post_id=post.id,
                user_id=commenter.id,
                created_at=post.created_at + 10 * 60 * 1000,
            )
        )

    accepted = Match(
        id=_id(),
        user_id=main.id,
        target_id=supports[2].id,
        common_tags=_json(["AIGC", "产品开发", "用户测试"], "[]"),
        status="accepted",
        match_type="buddy",
        match_report=_json(
            {
                "compatibility": 88,
                "analysis": "双方都有真实项目和明确协作目标，适合先进行一次产品互测。",
                "common_points": ["AIGC 产品", "重视真实反馈", "沟通直接"],
                "differences": ["一个更关注产品边界，一个更关注工程实现"],
            },
            "{}",
        ),
        user_portrait_snapshot="{}",
        created_at=_ms(days[-3], "20:00"),
    )
    incoming = Match(
        id=_id(),
        user_id=supports[1].id,
        target_id=main.id,
        common_tags=_json(["摄影", "设计"], "[]"),
        status="pending",
        match_type="buddy",
        match_report="想邀请你周末一起看设计展，先从公共场合的短活动开始。",
        user_portrait_snapshot="{}",
        created_at=_ms(days[-1], "11:30"),
    )
    db.add_all([accepted, incoming])
    db.flush()
    social_messages: list[SocialMessage] = []
    for index, (sender, content) in enumerate(
        [
            (main, "你好，我看到你也在做 AIGC 项目。要不要互测一次完整流程？"),
            (supports[2], "可以。我更想从异常流程和隐私边界开始测。"),
            (main, "正好，这是我最希望被认真挑战的部分。"),
            (supports[2], "那明天下午四点，创新实验室见。"),
        ]
    ):
        message = SocialMessage(
            id=_id(),
            match_id=accepted.id,
            from_uid=sender.id,
            content=content,
            timestamp=_ms(days[-2], f"20:{10 + index * 4:02d}"),
        )
        db.add(message)
        social_messages.append(message)
    db.flush()
    return posts, social_messages


def create_atoa_demo(db, main: User, supports: list[User], posts: list[PlazaPost], days: list[str]) -> None:
    now = _now_ms()
    surf_log = AvatarSurfLog(
        id=_id(),
        user_id=main.id,
        trigger="manual",
        status="success",
        scanned_posts=18,
        scanned_users=12,
        generated_matches=3,
        generated_actions=1,
        started_at=now - 35 * 60 * 1000,
        finished_at=now - 32 * 60 * 1000,
        scanned_atoa_pairs=8,
        upgraded_to_mutual=3,
        surf_report="浏览了 12 位候选，找到 3 位值得先聊的人；优先依据是共同经历、社交节奏和公开边界。",
    )
    db.add(surf_log)
    db.flush()
    session = AvatarAtoaSession(
        id=_id(),
        user_id=main.id,
        candidate_ids=_json([item.id for item in supports], "[]"),
        excluded_ids="[]",
        score_snapshot=_json({supports[0].id: 94, supports[1].id: 86, supports[2].id: 88}, "{}"),
        status="active",
        surf_log_id=surf_log.id,
        created_at=now - 32 * 60 * 1000,
        updated_at=now - 5 * 60 * 1000,
    )
    db.add(session)
    db.flush()
    surf_log.top10_session_id = session.id
    db.add(
        AvatarSurfJob(
            id=_id(),
            user_id=main.id,
            trigger="manual",
            status="succeeded",
            attempts=1,
            available_at=now - 36 * 60 * 1000,
            result_json=_json({"sessionId": session.id, "generated": 3}, "{}"),
            error_message="",
            created_at=now - 36 * 60 * 1000,
            started_at=now - 35 * 60 * 1000,
            finished_at=now - 32 * 60 * 1000,
            updated_at=now - 32 * 60 * 1000,
        )
    )

    conversations = [
        [
            {"role": "avatar_a", "content": "婷婷最近总在拍校园里普通但会让人停一下的瞬间。你也喜欢这种记录吗？"},
            {"role": "avatar_b", "content": "很像悠冉。她昨天也拍了大通湖的晚霞，而且不太喜欢为了社交而刻意找话题。"},
            {"role": "avatar_a", "content": "婷婷更喜欢边散步边拍，不赶行程，也接受安静一会儿。"},
            {"role": "avatar_b", "content": "这个节奏很合适。悠冉通常会先分享一张照片，再决定要不要一起去拍下一次。"},
            {"role": "avatar_a", "content": "那可以先从“同一个校园视角”继续聊，不涉及联系方式或见面承诺。"},
            {"role": "avatar_b", "content": "同意。她们都把边界说得很清楚，也确实有可验证的共同经历。"},
        ],
        [
            {"role": "avatar_a", "content": "婷婷在做重视人机边界的 AIGC 产品，也常用照片整理思路。"},
            {"role": "avatar_b", "content": "心怡关注产品体验和视觉叙事，她会更想聊设计判断，而不是泛泛交换兴趣。"},
            {"role": "avatar_a", "content": "那先聊一次产品展示如何让证据可见，这个主题足够具体。"},
            {"role": "avatar_b", "content": "可以，保持低压力，不自动提出线下邀约。"},
        ],
        [
            {"role": "avatar_a", "content": "婷婷希望有人能从研发视角挑战 AtoA 的异常流程和隐私边界。"},
            {"role": "avatar_b", "content": "明远正好在做 AIGC 工程，也明确表示只围绕具体问题协作。"},
            {"role": "avatar_a", "content": "两人已经完成一次真人互测，可以保留为已建立的项目搭子关系。"},
            {"role": "avatar_b", "content": "确认，这段关系由真人建立，不需要分身继续推进。"},
        ],
    ]
    for index, target in enumerate(supports):
        interaction = AvatarAtoaInteraction(
            id=_id(),
            initiator_id=main.id,
            session_id=session.id,
            user_a_id=main.id,
            user_b_id=target.id,
            interaction_type="card_exchange",
            outcome="pending_user_decision" if index < 2 else "connect_confirmed",
            score_a=[94, 86, 88][index],
            score_b=[92, 84, 90][index],
            shared_topics=_json(
                [["校园摄影", "晚霞", "散步"], ["产品设计", "摄影"], ["AIGC", "产品开发"]][index],
                "[]",
            ),
            reasons_a=_json(
                [
                    ["拍摄过同一片校园晚霞", "都偏好低压力的共同活动", "双方边界清晰"],
                    ["都关注产品如何被理解", "可以从具体作品开始交流"],
                    ["已有真实互测经历", "关注点在产品与工程上互补"],
                ][index],
                "[]",
            ),
            reasons_b=_json(["对方也认可这种交流节奏", "公开名片没有隐私冲突"], "[]"),
            risk_flags="[]",
            conversation=_json(conversations[index], "[]"),
            triggered_match_id=None,
            is_visible_to_a=True,
            is_visible_to_b=index == 2,
            interaction_phase=2 if index == 0 else 1,
            user_decision="continue" if index == 0 else None,
            created_at=now - (25 - index * 5) * 60 * 1000,
            updated_at=now - (10 - index * 2) * 60 * 1000,
        )
        db.add(interaction)
        db.add(
            AvatarMatch(
                id=_id(),
                user_id=main.id,
                post_id=posts[min(index + 3, len(posts) - 1)].id,
                match_score=[94, 86, 88][index],
                match_reasons=interaction.reasons_a,
                agent_conversation=interaction.conversation,
                status="viewed" if index < 2 else "chatting",
                target_user_id=target.id,
                match_type="atoa",
                intent_type="buddy",
                risk_flags="[]",
                suggested_opening=["原来你也拍了这片晚霞。", "想听听你如何展示一个抽象产品概念。", "继续从隐私边界开始互测吧。"][index],
                ai_refined=True,
                ai_refined_at=now,
                their_score=[92, 84, 90][index],
                their_reasons=_json(["共同经历真实", "沟通节奏兼容"], "[]"),
                is_mutual=True,
                peer_match_id=None,
                target_avatar_card_id=None,
                created_at=now - (25 - index * 5) * 60 * 1000,
            )
        )
    db.add_all(
        [
            AgentAction(
                id=_id(),
                user_id=main.id,
                agent_id="avalin-avatar",
                action_type="plaza_comment",
                target_type="plaza_post",
                target_id=posts[3].id,
                input_context=_json({"reason": "共同校园摄影视角"}, "{}"),
                output_text="原来你也拍了。我在湖的另一边，刚好也是这个时间。",
                status="draft",
                created_at=now - 18 * 60 * 1000,
                updated_at=now - 18 * 60 * 1000,
            ),
            AgentAction(
                id=_id(),
                user_id=main.id,
                agent_id="avalin-avatar",
                action_type="memory_card_update",
                target_type="avatar_card",
                target_id=main.id,
                input_context=_json({"source": "seven_day_profile"}, "{}"),
                output_text="新增公开兴趣：校园摄影、轻松夜跑；保留原隐私边界。",
                status="published",
                created_at=now - 2 * 3600 * 1000,
                updated_at=now - 2 * 3600 * 1000,
            ),
        ]
    )


def ingest_unified_memory(
    db,
    main: User,
    materials: list[RawMaterial],
    sessions: list[ChatSession],
    diaries: list[Diary],
    posts: list[PlazaPost],
    social_messages: list[SocialMessage],
) -> None:
    settings.MEMORY_ENABLED = True
    settings.MEMORY_VECTOR_ENABLED = False
    settings.MEMORY_EMBEDDING_PROVIDER = "hash"
    for item in materials:
        ingest_material(db, item)
    for item in sessions:
        ingest_chat_session(db, item)
    for item in diaries:
        ingest_diary(db, item)
    for item in posts:
        if item.user_id == main.id:
            ingest_plaza_post(db, item)
    comments = db.query(PlazaComment).filter(PlazaComment.user_id == main.id).all()
    for item in comments:
        ingest_plaza_comment(db, item)
    for item in social_messages:
        if item.from_uid == main.id:
            ingest_social_message(db, item)

    now = _now_ms()
    facts = [
        ("interest", "陈婷婷喜欢拍摄校园晚霞和普通生活瞬间", "校园摄影", True),
        ("habit", "陈婷婷通常在傍晚散步或进行三公里轻松夜跑", "傍晚活动", False),
        ("preference", "陈婷婷偏好低频、高质量、围绕具体活动的社交", "社交节奏", True),
        ("boundary", "分身不得公开私密日记原文和联系方式", "隐私边界", True),
        ("goal", "陈婷婷近期正在准备 Avalin 决赛演示", "近期目标", False),
        ("need", "陈婷婷希望找到校园摄影或 AIGC 产品搭子", "社交需求", True),
    ]
    evidence_docs = (
        db.query(MemoryDocument)
        .filter(MemoryDocument.user_id == main.id, MemoryDocument.source_type == "diary")
        .order_by(MemoryDocument.occurred_at.asc())
        .all()
    )
    for index, (category, content, subject, pinned) in enumerate(facts):
        doc = evidence_docs[min(index, len(evidence_docs) - 1)] if evidence_docs else None
        chunk = (
            db.query(MemoryChunk)
            .filter(MemoryChunk.document_id == doc.id)
            .order_by(MemoryChunk.chunk_index.asc())
            .first()
            if doc
            else None
        )
        db.add(
            MemoryFact(
                id=_id(),
                user_id=main.id,
                category=category,
                content=content,
                subject=subject,
                predicate="体现",
                object=content,
                confidence=0.96,
                stability="stable" if category in ("interest", "preference", "boundary") else "recent",
                evidence_document_id=doc.id if doc else None,
                evidence_chunk_id=chunk.id if chunk else None,
                source_type="diary",
                valid_from=doc.occurred_at if doc else now,
                valid_to=None,
                is_active=True,
                is_pinned=pinned,
                created_at=now,
                updated_at=now,
            )
        )
    db.commit()


def print_summary(db, main: User, days: list[str]) -> None:
    print("=" * 72)
    print("Avalin 决赛演示账号已生成")
    print("=" * 72)
    print(f"账号: {MAIN_USERNAME}")
    print(f"密码: {PASSWORD}")
    print(f"角色: {main.name} / {main.school} / {main.major}")
    print(f"模拟周期: {days[0]} ~ {days[-1]}")
    print("")
    rows = [
        ("日记", db.query(Diary).filter(Diary.user_id == main.id).count()),
        ("多模态素材", db.query(RawMaterial).filter(RawMaterial.user_id == main.id).count()),
        ("AI 对话", db.query(ChatSession).filter(ChatSession.user_id == main.id).count()),
        ("统一记忆文档", db.query(MemoryDocument).filter(MemoryDocument.user_id == main.id).count()),
        ("结构化记忆事实", db.query(MemoryFact).filter(MemoryFact.user_id == main.id).count()),
        ("分身记忆", db.query(AvatarMemory).filter(AvatarMemory.user_id == main.id).count()),
        ("广场帖子", db.query(PlazaPost).filter(PlazaPost.user_id == main.id).count()),
        ("AtoA 探针对话", db.query(AvatarAtoaInteraction).filter(AvatarAtoaInteraction.user_a_id == main.id).count()),
        ("关系记录", db.query(Match).filter(or_(Match.user_id == main.id, Match.target_id == main.id)).count()),
        ("待办", db.query(Todo).filter(Todo.user_id == main.id).count()),
        ("番茄钟", db.query(Pomodoro).filter(Pomodoro.user_id == main.id).count()),
    ]
    for label, count in rows:
        print(f"- {label}: {count}")
    print("=" * 72)


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        purge_managed_data(db)
        main_user = create_user(
            db,
            username=MAIN_USERNAME,
            name="陈婷婷",
            school="南开大学",
            major="软件工程",
            grade="大三",
            interests=["校园摄影", "轻松夜跑", "AIGC 产品", "散步", "用户研究"],
            summary="南开软件工程学生，正在做 AIGC 产品；喜欢拍校园晚霞和轻松夜跑，社交慢热且重视边界。",
            avatar_scene="female student, short black hair, software engineering student, calm confident expression",
            comprehensive=True,
        )
        support_users = [
            create_user(
                db,
                username=item["username"],
                name=item["name"],
                school=item["school"],
                major=item["major"],
                grade=item["grade"],
                interests=item["interests"],
                summary=item["summary"],
                avatar_scene=f"student majoring in {item['major']}, approachable natural expression",
            )
            for item in SUPPORT_USERS
        ]
        days = _seven_days()
        diaries, materials, sessions = create_daily_history(db, main_user, days)
        create_personal_features(db, main_user, diaries, days)
        posts, social_messages = create_plaza_and_social(db, main_user, support_users, days)
        create_atoa_demo(db, main_user, support_users, posts, days)
        db.commit()
        ingest_unified_memory(
            db,
            main_user,
            materials,
            sessions,
            diaries,
            posts,
            social_messages,
        )
        db.commit()
        print_summary(db, main_user, days)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
