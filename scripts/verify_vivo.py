"""
蓝心（vivo）全链路冒烟验证脚本

逐项打通 vivo 开放平台能力，确认 App 端上线前后端 AI 链路可用。
只读调用真实接口，不写数据库。

用法：
    python scripts/verify_vivo.py                 # 跑全部用例
    python scripts/verify_vivo.py --only chat,tts # 只跑指定用例
    python scripts/verify_vivo.py --list          # 列出用例名
    python scripts/verify_vivo.py --image-url https://example.com/a.jpg

用例名：config / chat / stream / vision / tts / asr / embedding / image / realtime
"""
import argparse
import array
import asyncio
import io
import os
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

# 视觉理解的图片来源：留空则先用文生图现场生成一张，避免依赖外部图床可用性
DEFAULT_IMAGE_URL = ""

PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []
SKIPPED: list[tuple[str, str]] = []


def _title(name: str, desc: str) -> None:
    print(f"\n{'=' * 64}\n[{name}] {desc}\n{'-' * 64}")


def _ok(name: str, detail: str = "") -> None:
    PASSED.append(name)
    print(f"[OK] {name} {detail}".rstrip())


def _fail(name: str, reason: str) -> None:
    FAILED.append((name, reason))
    print(f"[FAIL] {name} -> {reason}")


def _skip(name: str, reason: str) -> None:
    SKIPPED.append((name, reason))
    print(f"[SKIP] {name} -> {reason}")


def _preview(text: str, limit: int = 80) -> str:
    flat = " ".join(str(text or "").split())
    return flat[:limit] + ("..." if len(flat) > limit else "")


def _resample_pcm16(samples: array.array, src_rate: int, dst_rate: int) -> array.array:
    """线性插值重采样。Python 3.13 移除了 audioop，这里手写以免引入额外依赖。"""
    if src_rate == dst_rate or not samples:
        return samples

    ratio = src_rate / dst_rate
    out_len = int(len(samples) / ratio)
    out = array.array("h", [0]) * out_len

    for i in range(out_len):
        pos = i * ratio
        left = int(pos)
        right = min(left + 1, len(samples) - 1)
        weight = pos - left
        out[i] = int(samples[left] * (1 - weight) + samples[right] * weight)

    return out


def _to_asr_wav(audio: bytes) -> tuple[bytes | None, str]:
    """把 TTS 产物转换成 ASR 要求的 16kHz / 16bit / 单声道 wav。

    返回 (音频, 说明)。无法转换时音频为 None。
    """
    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        return None, "TTS 返回的不是 wav（可能是 mp3），本脚本不内置解码器"

    try:
        with wave.open(io.BytesIO(audio), "rb") as reader:
            channels = reader.getnchannels()
            width = reader.getsampwidth()
            rate = reader.getframerate()
            raw = reader.readframes(reader.getnframes())
    except Exception as exc:
        return None, f"wav 解析失败: {exc}"

    if width != 2:
        return None, f"位深 {width * 8}bit 非 16bit，无法直接转换"

    samples = array.array("h")
    samples.frombytes(raw)

    if channels > 1:
        samples = array.array("h", samples[::channels])

    note = f"源 {rate}Hz/{channels}ch"
    if rate != 16000:
        samples = _resample_pcm16(samples, rate, 16000)
        note += " -> 重采样 16000Hz/1ch"

    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(samples.tobytes())

    return out.getvalue(), note


# ── 用例 ────────────────────────────────────────────────────────

def case_config() -> None:
    """检查凭证与供应商开关是否指向蓝心。"""
    _title("config", "配置自检")

    app_id = str(settings.VIVO_APP_ID or "").strip()
    app_key = str(settings.VIVO_APP_KEY or "").strip()

    if not app_id or not app_key:
        _fail("config", "VIVO_APP_ID / VIVO_APP_KEY 未配置")
        return

    print(f"  VIVO_APP_ID       = {app_id}")
    print(f"  VIVO_APP_KEY      = {app_key[:12]}...{app_key[-6:]}")
    print(f"  VIVO_API_BASE     = {settings.VIVO_API_BASE}")
    print(f"  VIVO_MODEL        = {settings.VIVO_MODEL}")
    print(f"  VIVO_VISION_MODEL = {settings.VIVO_VISION_MODEL}")
    print(f"  LLM_PROVIDER      = {settings.LLM_PROVIDER}")

    problems = []
    if settings.LLM_PROVIDER != "vivo":
        problems.append(f"LLM_PROVIDER={settings.LLM_PROVIDER}，应为 vivo")
    if not settings.VIVO_VISION_ENABLED:
        problems.append("VIVO_VISION_ENABLED=false，视觉理解会被跳过")
    if settings.ARK_VISION_ENABLED and str(settings.ARK_API_KEY or "").strip():
        problems.append("ARK 视觉仍处于启用状态，可能抢占蓝心视觉链路")
    if str(settings.MINIMAX_API_KEY or "").strip():
        problems.append("MINIMAX_API_KEY 非空，内置模型列表会把 MiniMax 标记为可用")
    if settings.MEMORY_EMBEDDING_PROVIDER != "vivo":
        problems.append(f"MEMORY_EMBEDDING_PROVIDER={settings.MEMORY_EMBEDDING_PROVIDER}，向量未走蓝心")

    if problems:
        _fail("config", "; ".join(problems))
    else:
        _ok("config", "凭证与供应商开关均指向蓝心")


async def case_chat() -> None:
    """非流式对话。"""
    _title("chat", "蓝心大模型 - 非流式对话")
    from app.ai.minimax_client import get_minimax_client

    client = get_minimax_client()
    started = time.time()
    reply = await client.chat_completion(
        messages=[{"role": "user", "content": "用一句话介绍你自己，不超过20个字。"}],
        system_prompt="你是日记应用 Avalin 的 AI 伙伴。",
        max_tokens=128,
    )
    cost = time.time() - started

    if not str(reply or "").strip():
        _fail("chat", "返回内容为空")
        return
    print(f"  回复: {_preview(reply)}")
    _ok("chat", f"{cost:.2f}s")


async def case_stream() -> None:
    """流式对话，统计首 token 延迟。"""
    _title("stream", "蓝心大模型 - 流式对话")
    from app.ai.minimax_client import get_minimax_client

    client = get_minimax_client()
    started = time.time()
    first_at = None
    chunks = 0
    buffer = ""

    async for chunk in client.stream_chat(
        messages=[{"role": "user", "content": "数一下 1 到 5。"}],
        max_tokens=128,
    ):
        if first_at is None:
            first_at = time.time() - started
        chunks += 1
        buffer += chunk

    if chunks == 0:
        _fail("stream", "未收到任何 chunk")
        return
    print(f"  首字延迟: {first_at:.2f}s / 共 {chunks} 个 chunk")
    print(f"  完整回复: {_preview(buffer)}")
    _ok("stream", f"总耗时 {time.time() - started:.2f}s")


async def case_vision(image_url: str) -> None:
    """视觉理解。"""
    _title("vision", "蓝心视觉理解 - 图片描述")
    from app.ai.service import understand_image_text

    if not settings.VIVO_VISION_ENABLED:
        _skip("vision", "VIVO_VISION_ENABLED=false")
        return

    if not image_url:
        # 用蓝心自己生成的图做输入，图床和模型同属 vivo，可访问性最可靠
        from app.ai.minimax_client import get_minimax_client
        print("  未指定图片，先用文生图生成一张…")
        image_url = await get_minimax_client().generate_image(
            prompt="一只橘猫趴在窗台上晒太阳，窗外有绿植",
            aspect_ratio="1:1",
        )
        if not str(image_url or "").strip():
            _skip("vision", "文生图未返回图片，无法构造视觉输入")
            return

    print(f"  图片: {image_url}")
    started = time.time()
    text = await understand_image_text(image_url)
    cost = time.time() - started

    # understand_image_text 失败时返回空串而不抛异常
    if not str(text or "").strip():
        _fail("vision", "返回空描述（图片不可访问、模型无权限或超时，详见服务端日志）")
        return
    print(f"  描述: {_preview(text, 120)}")
    _ok("vision", f"{cost:.2f}s")


async def case_tts() -> bytes:
    """语音合成，返回音频字节供 ASR 用例复用。"""
    _title("tts", "蓝心音频生成 - TTS")
    from app.ai.minimax_client import get_minimax_client

    client = get_minimax_client()
    started = time.time()
    audio = await client.text_to_speech(
        text="今天天气不错，适合去图书馆看书。",
        user_id="verify-vivo-script",
    )
    cost = time.time() - started

    if not audio:
        _fail("tts", "返回空音频")
        return b""
    print(f"  音频大小: {len(audio)} bytes")
    _ok("tts", f"{cost:.2f}s")
    return audio


async def case_asr(audio: bytes) -> None:
    """短语音识别，用 TTS 产物回灌形成闭环。"""
    _title("asr", "蓝心实时短语音识别 - ASR")
    from app.ai.minimax_client import get_minimax_client

    if not audio:
        _skip("asr", "没有可用音频（TTS 用例未通过或未运行）")
        return

    # ASR 只接受 16kHz/16bit/单声道，TTS 输出采样率通常更高，需要先转换
    converted, note = _to_asr_wav(audio)
    if not converted:
        _skip("asr", note)
        return
    print(f"  音频预处理: {note}")

    client = get_minimax_client()
    started = time.time()
    result = await client.speech_to_text_short(
        audio_bytes=converted,
        audio_format="wav",
        user_id="verify-vivo-script",
    )
    cost = time.time() - started

    text = str((result or {}).get("text") or "").strip()
    if not text:
        _fail("asr", f"未识别出文本，原始返回: {_preview(str(result))}")
        return
    print(f"  识别结果: {text}")
    _ok("asr", f"{cost:.2f}s")


def case_embedding() -> None:
    """文本向量。"""
    _title("embedding", "蓝心文本向量 - Embedding")
    from app.memory.indexer import _embed_texts

    started = time.time()
    vectors = _embed_texts(["今天心情很好", "图书馆抢到了位子"], mode="document")
    cost = time.time() - started

    if not vectors or not vectors[0]:
        _fail("embedding", "返回空向量")
        return

    provider = settings.MEMORY_EMBEDDING_PROVIDER
    dimensions = len(vectors[0])
    print(f"  provider: {provider} / 条数: {len(vectors)} / 维度: {dimensions}")

    # MEMORY_EMBEDDING_DIMENSIONS 只作为 dashscope 的请求参数，
    # vivo 的维度由模型（m3e-base = 768）决定，ChromaDB 按首次写入的维度建集合。
    if provider == "dashscope":
        expected = settings.MEMORY_EMBEDDING_DIMENSIONS
        if dimensions != expected:
            _fail("embedding", f"维度 {dimensions} 与 MEMORY_EMBEDDING_DIMENSIONS={expected} 不一致")
            return
    elif dimensions != settings.MEMORY_EMBEDDING_DIMENSIONS:
        print(f"  提示: MEMORY_EMBEDDING_DIMENSIONS={settings.MEMORY_EMBEDDING_DIMENSIONS} "
              f"对 {provider} 不生效，实际维度以模型为准")

    _ok("embedding", f"{cost:.2f}s")


async def case_image() -> None:
    """文生图。"""
    _title("image", "蓝心图片生成 - 文生图")
    from app.ai.minimax_client import get_minimax_client

    client = get_minimax_client()
    started = time.time()
    url = await client.generate_image(
        prompt="手绘水彩风格，一本摊开的日记本放在窗边，阳光洒进来",
        aspect_ratio="1:1",
    )
    cost = time.time() - started

    if not str(url or "").strip():
        _fail("image", "返回空 URL")
        return
    print(f"  图片 URL: {_preview(url, 120)}")
    _ok("image", f"{cost:.2f}s")


def case_realtime() -> None:
    """实时语音配置检查（保留火山全双工，不实际建连）。"""
    _title("realtime", "实时语音配置检查（火山全双工）")

    provider = settings.REALTIME_VOICE_PROVIDER
    enabled = settings.VOLC_REALTIME_VOICE_ENABLED
    key = str(settings.VOLC_REALTIME_VOICE_API_KEY or "").strip()

    print(f"  REALTIME_VOICE_PROVIDER      = {provider}")
    print(f"  VOLC_REALTIME_VOICE_ENABLED  = {enabled}")
    print(f"  VOLC_REALTIME_VOICE_URL      = {settings.VOLC_REALTIME_VOICE_URL}")
    print(f"  API_KEY                      = {'已配置' if key else '未配置'}")

    problems = []
    if provider == "volcengine_duplex":
        if not enabled:
            problems.append("VOLC_REALTIME_VOICE_ENABLED=false，语音通话不可用")
        if not key:
            problems.append("VOLC_REALTIME_VOICE_API_KEY 为空")
    elif provider == "fake":
        problems.append("provider=fake，仅供测试，不能用于真机")

    if problems:
        _fail("realtime", "; ".join(problems))
    else:
        _ok("realtime", "配置完整（未建连，真实连通性请在真机验证）")


# ── 调度 ────────────────────────────────────────────────────────

ALL_CASES = ["config", "chat", "stream", "vision", "tts", "asr", "embedding", "image", "realtime"]


async def run(selected: list[str], image_url: str) -> None:
    audio = b""

    for name in ALL_CASES:
        if name not in selected:
            continue
        try:
            if name == "config":
                case_config()
            elif name == "chat":
                await case_chat()
            elif name == "stream":
                await case_stream()
            elif name == "vision":
                await case_vision(image_url)
            elif name == "tts":
                audio = await case_tts()
            elif name == "asr":
                await case_asr(audio)
            elif name == "embedding":
                case_embedding()
            elif name == "image":
                await case_image()
            elif name == "realtime":
                case_realtime()
        except Exception as exc:
            _fail(name, f"{type(exc).__name__}: {exc}")

    print(f"\n{'=' * 64}\n汇总\n{'-' * 64}")
    print(f"  通过 {len(PASSED)} / 失败 {len(FAILED)} / 跳过 {len(SKIPPED)}")
    if PASSED:
        print(f"  [OK]   {', '.join(PASSED)}")
    for name, reason in SKIPPED:
        print(f"  [SKIP] {name}: {reason}")
    for name, reason in FAILED:
        print(f"  [FAIL] {name}: {reason}")
    print("=" * 64)


def main() -> int:
    parser = argparse.ArgumentParser(description="蓝心（vivo）全链路冒烟验证")
    parser.add_argument("--only", default="", help=f"逗号分隔的用例名，可选：{','.join(ALL_CASES)}")
    parser.add_argument("--image-url", default=DEFAULT_IMAGE_URL, help="视觉理解用例使用的图片地址")
    parser.add_argument("--list", action="store_true", help="列出全部用例名后退出")
    args = parser.parse_args()

    if args.list:
        for name in ALL_CASES:
            print(name)
        return 0

    if args.only.strip():
        selected = [x.strip() for x in args.only.split(",") if x.strip()]
        unknown = [x for x in selected if x not in ALL_CASES]
        if unknown:
            print(f"未知用例: {', '.join(unknown)}；可选：{', '.join(ALL_CASES)}")
            return 2
    else:
        selected = list(ALL_CASES)

    asyncio.run(run(selected, args.image_url))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
