"""
AI 功能路由
实现 fortune/comic/share-card/bgm/tts/novel-chapter 六个接口
"""
import json
import os
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.diary import Diary
from app.ai.minimax_client import get_minimax_client
from app.ai.schemas import (
    ComicRequest,
    ShareCardRequest, BgmRequest, TtsRequest, NovelChapterRequest,
)
from app.response import ok, ApiException, NOT_FOUND

router = APIRouter(prefix="/ai", tags=["AI 功能"])


@router.get("/fortune", summary="AI 今日运势")
async def get_fortune(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    根据用户最近 3 篇日记的情绪趋势生成今日运势
    返回 {fortune, score, advice, lucky_color, lucky_number}
    """
    # 查最近 3 篇日记的 emotion_summary
    recent_diaries = (
        db.query(Diary)
        .filter(Diary.user_id == current_user.id)
        .order_by(Diary.created_at.desc())
        .limit(3)
        .all()
    )

    emotion_texts = []
    for d in recent_diaries:
        try:
            summary = json.loads(d.emotion_summary or "{}")
            if summary.get("dominant"):
                emotion_texts.append(
                    f"日期{d.date}：主要情绪={summary['dominant']}"
                )
        except (json.JSONDecodeError, AttributeError):
            pass

    emotion_context = "、".join(emotion_texts) if emotion_texts else "无近期情绪记录"

    client = get_minimax_client()
    system_prompt = (
        "你是一个温暖的运势预测助手，根据用户的情绪趋势生成今日运势。"
        "严格返回如下 JSON（无其他文字）：\n"
        '{"fortune": "运势描述（100字以内）", "score": 85, '
        '"advice": "今日建议（50字以内）", "lucky_color": "幸运色", "lucky_number": 7}'
    )
    messages = [
        {
            "role": "user",
            "content": f"用户最近情绪：{emotion_context}。请生成今日运势。",
        }
    ]
    raw = await client.chat_completion(messages, system_prompt=system_prompt, temperature=0.8)

    try:
        result = json.loads(raw.strip())
    except (json.JSONDecodeError, AttributeError):
        # 解析失败时返回默认运势
        result = {
            "fortune": raw.strip() if raw else "今日运势良好，保持积极心态！",
            "score": 80,
            "advice": "多喝水，保持好心情。",
            "lucky_color": "蓝色",
            "lucky_number": 7,
        }

    return ok(result)


@router.post("/comic", summary="AI 漫画生成")
async def generate_comic(
    req: ComicRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    根据日记内容和风格生成漫画图片
    返回 {image_url, prompt_used}
    """
    client = get_minimax_client()

    # 先用 AI 从日记内容提取关键场景，生成图片 prompt
    scene_messages = [
        {
            "role": "user",
            "content": (
                f"从以下日记提取一个最有画面感的场景，用英文描述画面（50词以内），"
                f"风格：{req.style}。\n\n日记内容：{req.diary_content}"
            ),
        }
    ]
    scene_prompt = await client.chat_completion(
        scene_messages,
        system_prompt=f"你是漫画分镜师，擅长将日记文字转化为{req.style}风格的画面描述。只输出英文场景描述，无其他内容。",
        temperature=0.7,
    )
    scene_prompt = scene_prompt.strip()

    image_url = await client.generate_image(scene_prompt, aspect_ratio="3:4")

    return ok({"image_url": image_url, "prompt_used": scene_prompt})


@router.post("/share-card", summary="生成分享卡片")
async def generate_share_card(
    req: ShareCardRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    查日记内容 → 生成金句 + 卡片背景图
    返回 {image_url, quote, diary_title}
    """
    diary = (
        db.query(Diary)
        .filter(Diary.id == req.diary_id, Diary.user_id == current_user.id)
        .first()
    )
    if not diary:
        raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)

    client = get_minimax_client()

    # 并行：提取金句 + 生成卡片背景
    quote_messages = [
        {
            "role": "user",
            "content": f"从以下日记中提炼一句最有共鸣的金句（20字以内）：\n\n{diary.content}",
        }
    ]
    quote_task = client.chat_completion(
        quote_messages,
        system_prompt="你是文案大师，从日记中提炼最有感染力的金句。只输出金句本身，无引号无解释。",
        temperature=0.8,
    )

    card_prompt = (
        f"Minimalist share card background for a diary app, "
        f"soft watercolor texture, aesthetic, warm colors, no text"
    )
    image_task = client.generate_image(card_prompt, aspect_ratio="3:4")

    import asyncio
    quote, image_url = await asyncio.gather(quote_task, image_task)

    return ok({
        "image_url": image_url,
        "quote": quote.strip(),
        "diary_title": diary.title or diary.content[:20],
    })


@router.post("/bgm", summary="AI 生成 BGM")
async def generate_bgm(
    req: BgmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    根据情绪关键词生成背景音乐
    返回 {audio_url, mood, duration_hint}
    """
    # 情绪 → 音乐风格映射
    mood_map = {
        "开心": "upbeat, cheerful, pop, bright piano",
        "悲伤": "melancholic, slow, gentle piano, sad",
        "平静": "calm, ambient, soft, relaxing, meditation",
        "感动": "emotional, orchestral, touching, warm strings",
        "焦虑": "tense, fast-paced, ambient, electronic",
        "期待": "hopeful, bright, ascending melody, optimistic",
        "愤怒": "intense, rock, powerful, energetic",
        "无聊": "lo-fi, chill, relaxed, background music",
    }
    music_style = mood_map.get(req.mood, "gentle, ambient, background music")
    prompt = f"{music_style}, background music for diary app, instrumental"

    client = get_minimax_client()
    audio_url = await client.generate_music(prompt=prompt, is_instrumental=True)

    return ok({
        "audio_url": audio_url,
        "mood": req.mood,
        "duration_hint": "30-60秒",
    })


@router.post("/tts", summary="文字转语音")
async def text_to_speech(
    req: TtsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    将文字转为语音，保存到 uploads/tts/ 目录
    返回 {audio_url, duration_hint}
    """
    client = get_minimax_client()
    audio_bytes = await client.text_to_speech(req.text, voice_id=req.voice)

    # 保存音频文件
    tts_dir = os.path.join(settings.UPLOAD_DIR, "tts")
    os.makedirs(tts_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.mp3"
    file_path = os.path.join(tts_dir, filename)
    with open(file_path, "wb") as f:
        f.write(audio_bytes)

    audio_url = f"/uploads/tts/{filename}"

    return ok({
        "audio_url": audio_url,
        "duration_hint": f"约 {max(1, len(req.text) // 5)} 秒",
    })


@router.post("/novel-chapter", summary="AI 小说章节")
async def generate_novel_chapter(
    req: NovelChapterRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    将日记内容改编为指定风格小说章节
    返回 {chapter_title, content, genre}
    """
    client = get_minimax_client()

    context = ""
    if req.previous_chapter:
        context = f"\n\n上一章结尾：\n{req.previous_chapter[-200:]}"

    system_prompt = (
        f"你是一位擅长{req.genre}小说的作家，将用户的日记内容改编为{req.genre}风格的小说章节。"
        "要求：有吸引人的章节标题、生动的场景描写、情感细腻。"
        "严格返回如下 JSON（无其他文字）：\n"
        '{"chapter_title": "第X章 标题", "content": "章节正文（400字以上）"}'
    )
    messages = [
        {
            "role": "user",
            "content": (
                f"请将以下日记改编为{req.genre}风格小说章节：\n\n"
                f"{req.diary_content}{context}"
            ),
        }
    ]
    raw = await client.chat_completion(messages, system_prompt=system_prompt, temperature=0.9)

    try:
        result = json.loads(raw.strip())
        chapter_title = result.get("chapter_title", "无题")
        content = result.get("content", raw)
    except (json.JSONDecodeError, AttributeError):
        chapter_title = f"{req.genre}·日记改编"
        content = raw.strip()

    return ok({
        "chapter_title": chapter_title,
        "content": content,
        "genre": req.genre,
    })
