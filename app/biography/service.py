"""
我的小传模块服务层
- 聚合用户日记/帖子/素材/记忆，按章节自动生成自传体小说
- 解锁机制：每累计 N 篇新日记可生成下一章
- 复用已生成漫画作为章节插图，并为每章生成封面图
"""
import asyncio
import json
import logging
import os
import re
import time
from typing import List, Optional
from urllib.parse import unquote_plus, urlparse
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.biography import BiographyChapter
from app.models.diary import Diary
from app.models.material import RawMaterial
from app.models.plaza import PlazaPost
from app.models.memory import MemoryFact, MemoryProfile
from app.models.derivative import DiaryDerivative
from app.response import ApiException, NOT_FOUND, PARAM_ERROR


logger = logging.getLogger(__name__)


# 每累计这么多篇新日记可解锁/生成一章
def _resolve_chapter_threshold() -> int:
    raw = os.getenv("BIOGRAPHY_CHAPTER_THRESHOLD", "7")
    try:
        value = int(raw)
        return value if value > 0 else 7
    except Exception:
        return 7


def _resolve_ai_timeout_sec() -> int:
    raw = os.getenv("BIOGRAPHY_AI_TIMEOUT_SEC", "90")
    try:
        value = int(raw)
        return value if value > 0 else 90
    except Exception:
        return 90


CHAPTER_THRESHOLD = _resolve_chapter_threshold()
AI_TIMEOUT_SEC = _resolve_ai_timeout_sec()
TASK_TTL_MS = 60 * 60 * 1000
_TASKS: dict[str, dict] = {}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


def _encode(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _decode(s: str, default=None):
    if default is None:
        default = {}
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


def is_known_placeholder_media_url(url: str) -> bool:
    """识别历史上曾被当成成功结果保存的远程文字占位图。"""
    raw = str(url or "").strip()
    if not raw:
        return False
    normalized = raw
    for _ in range(2):
        try:
            normalized = unquote_plus(normalized)
        except Exception:
            break
    normalized = re.sub(r"[\s_+-]+", " ", normalized).lower()
    return (
        "placehold.co" in normalized
        or "placeholder.com" in normalized
        or "my story" in normalized
        or "diary comic" in normalized
    )


def _valid_generated_image_url(url: str) -> str:
    """仅接受可展示的 http(s) 图片地址，拒绝空值、相对路径和占位图。"""
    value = str(url or "").strip()
    if not value or is_known_placeholder_media_url(value):
        return ""
    try:
        parsed = urlparse(value)
    except Exception:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return value


def _filter_illustrations(raw) -> List[dict]:
    decoded = _decode(raw, []) if isinstance(raw, str) else raw
    if not isinstance(decoded, list):
        return []
    result = []
    for item in decoded:
        if not isinstance(item, dict):
            continue
        image_url = str(item.get("image_url") or item.get("imageUrl") or "").strip()
        if not image_url or is_known_placeholder_media_url(image_url):
            continue
        result.append(item)
    return result


# ==================== 任务管理 ====================

def _prune_tasks(now: Optional[int] = None) -> None:
    current = now or _now_ms()
    expired = [
        task_id
        for task_id, task in _TASKS.items()
        if current - int(task.get("updated_at") or task.get("created_at") or 0) > TASK_TTL_MS
    ]
    for task_id in expired:
        _TASKS.pop(task_id, None)


def _task_to_dict(task: dict) -> dict:
    return {
        "task_id": task.get("task_id", ""),
        "status": task.get("status", "running"),
        "chapter_id": task.get("chapter_id") or None,
        "chapter_index": int(task.get("chapter_index") or 0),
        "error": task.get("error", ""),
        "created_at": int(task.get("created_at") or 0),
        "updated_at": int(task.get("updated_at") or task.get("created_at") or 0),
    }


# ==================== 数据聚合 ====================

def _published_diaries(db: Session, user_id: str) -> List[Diary]:
    """按日期升序返回用户全部日记（草稿也纳入，保证素材充足）。"""
    return (
        db.query(Diary)
        .filter(Diary.user_id == user_id)
        .order_by(Diary.created_at.asc())
        .all()
    )


def _consumed_diary_ids(db: Session, user_id: str) -> set:
    """已被既有章节消耗的日记 id 集合。"""
    chapters = (
        db.query(BiographyChapter)
        .filter(BiographyChapter.user_id == user_id)
        .all()
    )
    consumed: set = set()
    for ch in chapters:
        for did in _decode(ch.source_diary_ids, []):
            consumed.add(did)
    return consumed


def _latest_comic_url(db: Session, diary_id: str) -> str:
    """取某篇日记最新生成的漫画图片 URL，用作插图。"""
    comic = (
        db.query(DiaryDerivative)
        .filter(DiaryDerivative.diary_id == diary_id, DiaryDerivative.type == "comic")
        .order_by(DiaryDerivative.created_at.desc())
        .first()
    )
    if comic and (comic.media_url or "").strip():
        return comic.media_url.strip()
    # 兼容旧字段：Diary.comic_url
    d = db.query(Diary).filter(Diary.id == diary_id).first()
    if d and (d.comic_url or "").strip():
        return d.comic_url.strip()
    return ""


def get_progress(db: Session, user_id: str) -> dict:
    """计算解锁进度：可生成的下一章是否就绪。"""
    consumed = _consumed_diary_ids(db, user_id)
    all_diaries = _published_diaries(db, user_id)
    pending = [d for d in all_diaries if d.id not in consumed]

    chapter_count = (
        db.query(BiographyChapter)
        .filter(BiographyChapter.user_id == user_id)
        .count()
    )

    pending_count = len(pending)
    can_generate = pending_count >= CHAPTER_THRESHOLD
    return {
        "threshold": CHAPTER_THRESHOLD,
        "chapter_count": chapter_count,
        "pending_diary_count": pending_count,
        "needed_for_next": max(0, CHAPTER_THRESHOLD - pending_count),
        "can_generate": can_generate,
        "next_chapter_index": chapter_count + 1,
    }


def _chapter_to_dict(ch: BiographyChapter) -> dict:
    cover_url = str(ch.cover_image_url or "").strip()
    if is_known_placeholder_media_url(cover_url):
        cover_url = ""
    return {
        "id": ch.id,
        "chapter_index": ch.chapter_index,
        "title": ch.title or "",
        "content": ch.content or "",
        "preview": ch.preview or "",
        "word_count": ch.word_count or 0,
        "summary": ch.summary or "",
        "cover_image_url": cover_url,
        "illustrations": _filter_illustrations(ch.illustrations),
        "date_range_start": ch.date_range_start or "",
        "date_range_end": ch.date_range_end or "",
        "source_material_count": ch.source_material_count or 0,
        "source_post_count": ch.source_post_count or 0,
        "status": ch.status or "done",
        "created_at": int(ch.created_at or 0),
        "updated_at": int(ch.updated_at or 0),
    }


def get_biography(db: Session, user_id: str) -> dict:
    """返回小传目录 + 进度。"""
    chapters = (
        db.query(BiographyChapter)
        .filter(BiographyChapter.user_id == user_id)
        .order_by(BiographyChapter.chapter_index.asc())
        .all()
    )
    return {
        "chapters": [_chapter_to_dict(ch) for ch in chapters],
        "progress": get_progress(db, user_id),
    }


def get_chapter(db: Session, user_id: str, chapter_id: str) -> dict:
    ch = (
        db.query(BiographyChapter)
        .filter(BiographyChapter.id == chapter_id, BiographyChapter.user_id == user_id)
        .first()
    )
    if not ch:
        raise ApiException(code=NOT_FOUND, message="章节不存在", status_code=404)
    return _chapter_to_dict(ch)


# ==================== 生成逻辑 ====================

def _build_diary_block(db: Session, diaries: List[Diary]) -> tuple[str, List[dict]]:
    """拼接日记原文块，并收集每篇日记的插图（最新漫画）。"""
    lines = []
    illustrations = []
    for idx, d in enumerate(diaries):
        date = d.date or ""
        emotion = _decode(d.emotion_summary, {}).get("dominant", "") or ""
        weather = d.weather or ""
        content = (d.content or "").strip()
        lines.append(
            f"【第{idx + 1}天 {date}｜天气:{weather}｜情绪:{emotion}】\n{content}"
        )
        comic_url = _latest_comic_url(db, d.id)
        if comic_url:
            illustrations.append({
                "diary_id": d.id,
                "image_url": comic_url,
                "anchor_para": idx,  # 锚定到对应段落
            })
    return "\n\n".join(lines), illustrations


def _build_context_block(db: Session, user_id: str, diaries: List[Diary]) -> str:
    """补充帖子 / 素材 / 记忆画像，丰富叙事。"""
    if not diaries:
        return ""
    start_ts = min(int(d.created_at or 0) for d in diaries)
    end_ts = max(int(d.created_at or 0) for d in diaries)

    parts = []

    posts = (
        db.query(PlazaPost)
        .filter(
            PlazaPost.user_id == user_id,
            PlazaPost.created_at >= start_ts,
            PlazaPost.created_at <= end_ts,
        )
        .order_by(PlazaPost.created_at.asc())
        .limit(20)
        .all()
    )
    if posts:
        post_text = "\n".join(f"- {(p.content or '').strip()[:120]}" for p in posts)
        parts.append(f"【这段时间发布的动态】\n{post_text}")

    materials = (
        db.query(RawMaterial)
        .filter(
            RawMaterial.user_id == user_id,
            RawMaterial.created_at >= start_ts,
            RawMaterial.created_at <= end_ts,
        )
        .order_by(RawMaterial.created_at.asc())
        .limit(30)
        .all()
    )
    if materials:
        mat_text = "\n".join(f"- {(m.content or '').strip()[:80]}" for m in materials if (m.content or '').strip())
        if mat_text:
            parts.append(f"【随手记录的素材】\n{mat_text}")

    facts = (
        db.query(MemoryFact)
        .filter(MemoryFact.user_id == user_id, MemoryFact.is_active == True)  # noqa: E712
        .order_by(MemoryFact.confidence.desc())
        .limit(20)
        .all()
    )
    if facts:
        fact_text = "\n".join(f"- {(f.content or '').strip()[:80]}" for f in facts if (f.content or '').strip())
        if fact_text:
            parts.append(f"【关于主人公的已知事实】\n{fact_text}")

    profile = (
        db.query(MemoryProfile)
        .filter(MemoryProfile.user_id == user_id)
        .order_by(MemoryProfile.version.desc())
        .first()
    )
    if profile and (profile.summary or "").strip():
        parts.append(f"【主人公画像】\n{profile.summary.strip()[:400]}")

    return "\n\n".join(parts)


def _build_cover_retry_prompt(mood: str) -> str:
    return (
        "生成一张健康、全年龄的自传小说章节封面插画。"
        "暖色手绘风景，安静日常氛围，不出现人物特写，不含文字、标志、水印或边框。"
        f"整体情绪：{mood or '平静'}。"
    )


async def _generate_cover_image(client, prompt: str, mood: str) -> str:
    """封面失败后用安全简化 prompt 重试；最终失败返回空串而非伪图。"""
    prompts = [prompt, _build_cover_retry_prompt(mood)]
    for index, current_prompt in enumerate(prompts):
        started = time.monotonic()
        try:
            generated = await asyncio.wait_for(
                client.generate_image(current_prompt, aspect_ratio="16:9"),
                timeout=AI_TIMEOUT_SEC,
            )
            cover_url = _valid_generated_image_url(generated)
            if cover_url:
                return cover_url
            logger.warning(
                "biography cover returned unusable url (attempt %s, %.2fs)",
                index + 1,
                time.monotonic() - started,
            )
        except Exception as exc:
            logger.warning(
                "biography cover generation failed (attempt %s, %.2fs): %s",
                index + 1,
                time.monotonic() - started,
                exc,
            )
    logger.error("biography cover generation exhausted retries; chapter will use no cover")
    return ""


async def generate_chapter(db: Session, user_id: str) -> dict:
    """生成下一章自传：聚合数据 -> LLM 写正文 -> 封面图 -> 复用漫画插图 -> 落库。"""
    consumed = _consumed_diary_ids(db, user_id)
    all_diaries = _published_diaries(db, user_id)
    pending = [d for d in all_diaries if d.id not in consumed]

    if len(pending) < CHAPTER_THRESHOLD:
        raise ApiException(
            code=PARAM_ERROR,
            message=f"素材不足，还需 {CHAPTER_THRESHOLD - len(pending)} 篇日记才能解锁下一章",
            status_code=400,
        )

    # 本章消耗一个完整门槛批次
    batch = pending[:CHAPTER_THRESHOLD]
    chapter_count = (
        db.query(BiographyChapter)
        .filter(BiographyChapter.user_id == user_id)
        .count()
    )
    chapter_index = chapter_count + 1

    # 续写连贯性：取上一章梗概
    prev_summary = ""
    prev = (
        db.query(BiographyChapter)
        .filter(BiographyChapter.user_id == user_id)
        .order_by(BiographyChapter.chapter_index.desc())
        .first()
    )
    if prev and (prev.summary or "").strip():
        prev_summary = prev.summary.strip()

    diary_block, illustrations = _build_diary_block(db, batch)
    context_block = _build_context_block(db, user_id, batch)

    date_start = batch[0].date or ""
    date_end = batch[-1].date or ""

    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()
    logger.info(
        "biography chapter generate via provider=%s model=%s",
        getattr(client, "provider", ""),
        getattr(client, "vivo_model", "") or getattr(client, "model", ""),
    )

    system_prompt = (
        "你是一位擅长写自传体长篇小说的作家。"
        "请基于主人公真实的日记与生活记录，把这一段时间改写成自传小说的「一个章节」。\n"
        "写作要求：\n"
        "1. 第一人称中文叙述，文学性强、有画面感与情感起伏；\n"
        "2. 忠于事实，不虚构关键事件，但可润色细节与心理活动；\n"
        "3. 自然串联多天经历，形成有主题、有起承转合的完整章节；\n"
        "4. 篇幅 1200-2000 字，分多个自然段；\n"
        "5. 与上一章的情节保持连贯。\n"
        "输出严格为 JSON（不要 markdown 代码块），格式：\n"
        '{"title":"章节标题","content":"正文（用\\n\\n分段）","summary":"100字内本章梗概，供下一章续写"}'
    )

    user_parts = []
    if prev_summary:
        user_parts.append(f"【上一章梗概】\n{prev_summary}")
    user_parts.append(f"【本章日记原文】\n{diary_block}")
    if context_block:
        user_parts.append(context_block)
    user_parts.append("请输出本章 JSON。")
    user_prompt = "\n\n".join(user_parts)

    title = f"第{chapter_index}章"
    content = ""
    summary = ""
    messages = [{"role": "user", "content": user_prompt}]
    call_kwargs = {
        "system_prompt": system_prompt,
        "temperature": 0.8,
        "max_tokens": 4096,
        "timeout_sec": float(AI_TIMEOUT_SEC),
    }
    try:
        try:
            raw = await asyncio.wait_for(
                client.chat_completion(
                    messages,
                    response_format={"type": "json_object"},
                    **call_kwargs,
                ),
                timeout=AI_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            raise
        except Exception as json_mode_error:
            logger.warning(
                "biography JSON mode unavailable, fallback plain completion: %s",
                str(json_mode_error)[:200],
            )
            raw = await asyncio.wait_for(
                client.chat_completion(messages, **call_kwargs),
                timeout=AI_TIMEOUT_SEC,
            )
        parsed = _parse_chapter_json(raw)
        title = parsed.get("title") or title
        content = parsed.get("content") or ""
        summary = parsed.get("summary") or ""
    except Exception as exc:
        logger.warning("biography chapter llm failed, falling back to diary text: %s", exc)
        content = ""

    if not content.strip():
        # 兜底：直接拼接日记原文，保证可读
        content = "\n\n".join((d.content or "").strip() for d in batch if (d.content or "").strip())
        summary = summary or content.strip()[:100]

    word_count = len(content.replace("\n", "").replace(" ", ""))
    preview = content.strip().replace("\n", "")[:80]

    # 章节封面图
    cover_emotions = [
        _decode(d.emotion_summary, {}).get("dominant", "") for d in batch
    ]
    cover_emotions = [e for e in cover_emotions if e]
    mood = cover_emotions[0] if cover_emotions else "平静"
    cover_prompt = (
        "为一本自传体小说生成一张章节封面插画，治愈系青春文艺风、柔和暖色、手绘质感、"
        "有故事感与意境，画面干净、无文字无水印无边框。"
        f"主题情绪：{mood}。章节标题意境：{title}。"
    )
    cover_url = await _generate_cover_image(client, cover_prompt, mood)

    now = _now_ms()
    material_count = (
        db.query(RawMaterial)
        .filter(
            RawMaterial.user_id == user_id,
            RawMaterial.created_at >= min(int(d.created_at or 0) for d in batch),
            RawMaterial.created_at <= max(int(d.created_at or 0) for d in batch),
        )
        .count()
    )
    post_count = (
        db.query(PlazaPost)
        .filter(
            PlazaPost.user_id == user_id,
            PlazaPost.created_at >= min(int(d.created_at or 0) for d in batch),
            PlazaPost.created_at <= max(int(d.created_at or 0) for d in batch),
        )
        .count()
    )

    ch = BiographyChapter(
        id=_uuid(),
        user_id=user_id,
        chapter_index=chapter_index,
        title=title,
        content=content,
        preview=preview,
        word_count=word_count,
        summary=summary,
        cover_image_url=cover_url,
        illustrations=_encode(illustrations),
        date_range_start=date_start,
        date_range_end=date_end,
        source_diary_ids=_encode([d.id for d in batch]),
        source_material_count=material_count,
        source_post_count=post_count,
        status="done",
        created_at=now,
        updated_at=now,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return _chapter_to_dict(ch)


def _parse_chapter_json(raw: str) -> dict:
    """从模型输出里稳健解析 JSON（兼容 ```json 包裹）。"""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # 尝试截取第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return {}


def start_generate_task(db: Session, user_id: str) -> dict:
    """创建异步生成任务。"""
    progress = get_progress(db, user_id)
    if not progress["can_generate"]:
        raise ApiException(
            code=PARAM_ERROR,
            message=f"素材不足，还需 {progress['needed_for_next']} 篇日记才能解锁下一章",
            status_code=400,
        )

    _prune_tasks()
    for task in _TASKS.values():
        if task.get("user_id") == user_id and task.get("status") == "running":
            return _task_to_dict(task)

    now = _now_ms()
    task = {
        "task_id": _uuid(),
        "user_id": user_id,
        "status": "running",
        "chapter_id": None,
        "chapter_index": progress["next_chapter_index"],
        "error": "",
        "created_at": now,
        "updated_at": now,
    }
    _TASKS[task["task_id"]] = task
    return _task_to_dict(task)


def get_task(user_id: str, task_id: str) -> dict:
    _prune_tasks()
    task = _TASKS.get(task_id)
    if not task or task.get("user_id") != user_id:
        raise ApiException(code=NOT_FOUND, message="生成任务不存在", status_code=404)
    return _task_to_dict(task)


async def run_generate_task(task_id: str) -> None:
    """后台执行小传章节生成。"""
    from app.database import SessionLocal

    task = _TASKS.get(task_id)
    if not task:
        return

    db = SessionLocal()
    try:
        result = await generate_chapter(db, str(task.get("user_id") or ""))
        task["status"] = "done"
        task["chapter_id"] = result.get("id")
        task["chapter_index"] = result.get("chapter_index")
        task["error"] = ""
    except ApiException as exc:
        task["status"] = "failed"
        task["error"] = exc.message[:200]
    except Exception as exc:
        task["status"] = "failed"
        task["error"] = str(exc)[:200] or "生成失败"
    finally:
        task["updated_at"] = _now_ms()
        db.close()
