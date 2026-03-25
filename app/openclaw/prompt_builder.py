"""
个性化 System Prompt 构建器

build_chat_system_prompt(user, db) -> str
根据用户的写作风格偏好、今日素材、最近日记趋势，
生成带有个性化上下文的 system prompt，传给 OpenClaw Gateway。
"""
import json
import time
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.diary import Diary
from app.models.material import RawMaterial
from app.models.user import User


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _load_json(text: str, default):
    try:
        return json.loads(text or "")
    except Exception:
        return default


def build_chat_system_prompt(user: User, db: Session) -> str:
    """
    构建个性化 AI 对话 system prompt

    包含：
    - 用户昵称 / 签名
    - 写作风格标签 + 自定义 prompt
    - 今日素材摘要（最近 5 条）
    - 最近日记标题 + 情绪趋势（最近 3 篇）
    """
    lines = []

    # ── 基本角色设定 ──────────────────────────────────
    lines.append("你是日迹 App 的 AI 伙伴，陪伴用户记录大学生活的点滴。")
    lines.append("请用温暖、亲切的语气与用户对话，像一个有共鸣的朋友。")
    lines.append("")

    # ── 用户基本信息 ──────────────────────────────────
    if user.name:
        lines.append(f"【用户信息】")
        lines.append(f"昵称：{user.name}")
        if user.school:
            lines.append(f"学校：{user.school}")
        if user.major:
            lines.append(f"专业：{user.major}")
        if user.signature:
            lines.append(f"个性签名：{user.signature}")
        lines.append("")

    # ── 写作风格偏好 ──────────────────────────────────
    style_tags = _load_json(user.style_tags, [])
    custom_style = (user.custom_style_prompt or "").strip()
    if style_tags or custom_style:
        lines.append("【写作风格偏好】")
        if style_tags:
            lines.append(f"风格标签：{', '.join(style_tags)}")
        if custom_style:
            lines.append(f"自定义描述：{custom_style}")
        lines.append("")

    # ── 今日素材摘要 ──────────────────────────────────
    today = _today_str()
    today_materials = (
        db.query(RawMaterial)
        .filter(RawMaterial.user_id == user.id, RawMaterial.date == today)
        .order_by(RawMaterial.created_at.desc())
        .limit(5)
        .all()
    )
    if today_materials:
        lines.append("【今日素材摘要】")
        for mat in reversed(today_materials):
            emotion = _load_json(mat.emotion, {})
            emotion_str = ""
            if emotion.get("label"):
                emoji = emotion.get("emoji", "")
                emotion_str = f"（{emotion['label']}{emoji}）"
            if mat.type == "text" and mat.content:
                snippet = mat.content[:60]
                if len(mat.content) > 60:
                    snippet += "..."
                lines.append(f"- 文字{emotion_str}：{snippet}")
            elif mat.type == "image":
                lines.append(f"- 图片{emotion_str}")
            elif mat.type == "voice" and mat.content:
                snippet = mat.content[:60]
                lines.append(f"- 语音转文字{emotion_str}：{snippet}")
        lines.append("")

    # ── 最近日记趋势 ──────────────────────────────────
    recent_diaries = (
        db.query(Diary)
        .filter(Diary.user_id == user.id)
        .order_by(Diary.created_at.desc())
        .limit(3)
        .all()
    )
    if recent_diaries:
        lines.append("【最近日记趋势】")
        for diary in reversed(recent_diaries):
            title = diary.title or "无标题"
            emotion_summary = _load_json(diary.emotion_summary, {})
            dominant = emotion_summary.get("dominant", "")
            emotion_str = f"（主要情绪：{dominant}）" if dominant else ""
            date_str = diary.date or ""
            lines.append(f"- {date_str} 《{title}》{emotion_str}")
        lines.append("")

    lines.append("请根据以上背景信息，给予个性化、有温度的回应。")

    return "\n".join(lines)
