"""实时语音 REST 与 WebSocket 路由。"""
import contextlib

from fastapi import APIRouter, Depends, Query, WebSocket
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.realtime_voice import config as realtime_config
from app.realtime_voice.protocol import error_event
from app.realtime_voice.registry import session_registry
from app.realtime_voice.observability import voice_metrics
from app.realtime_voice.schemas import (
    AudioFormatOut,
    CreateVoiceTicketRequest,
    VoiceHealthOut,
    VoiceTicketOut,
)
from app.realtime_voice.session import RealtimeVoiceSessionRunner
from app.realtime_voice.tickets import (
    VoiceTicketError,
    consume_ticket,
    issue_ticket,
    normalize_voice,
)
from app.response import AI_SERVICE_ERROR, PARAM_INVALID, ApiException, success


api_router = APIRouter(prefix="/realtime-voice", tags=["实时语音分身"])
ws_router = APIRouter()


def _configured() -> bool:
    return bool(str(settings.VOLC_REALTIME_VOICE_API_KEY or "").strip())


@api_router.get("/health", summary="实时语音配置与容量状态")
def realtime_voice_health():
    out = VoiceHealthOut(
        enabled=bool(settings.VOLC_REALTIME_VOICE_ENABLED),
        configured=_configured(),
        provider=settings.REALTIME_VOICE_PROVIDER,
        active_sessions=session_registry.active_count,
        max_sessions=max(1, int(settings.REALTIME_VOICE_MAX_GLOBAL_SESSIONS)),
        metrics=voice_metrics.snapshot(),
    )
    return success(out.model_dump(by_alias=True))


@api_router.post("/tickets", summary="签发一次性实时语音 WebSocket Ticket")
def create_realtime_voice_ticket(
    body: CreateVoiceTicketRequest,
    current_user: User = Depends(get_current_user),
):
    if not settings.VOLC_REALTIME_VOICE_ENABLED:
        raise ApiException(
            code=AI_SERVICE_ERROR,
            message="实时语音暂未开放",
            status_code=503,
        )
    if not _configured():
        raise ApiException(
            code=AI_SERVICE_ERROR,
            message="实时语音服务尚未配置",
            status_code=503,
        )
    try:
        voice = normalize_voice(body.voice)
    except VoiceTicketError as exc:
        raise ApiException(
            code=PARAM_INVALID,
            message=str(exc),
            status_code=400,
        ) from exc

    ticket, expires_at = issue_ticket(
        user_id=current_user.id,
        client_platform=body.client_platform,
        voice=voice,
        output_format=body.output_format,
    )
    out = VoiceTicketOut(
        ticket=ticket,
        expires_at=expires_at,
        websocket_path="/ws/realtime-avatar",
        input=AudioFormatOut(
            type="pcm",
            sample_rate=16000,
            channels=1,
            bits_per_sample=16,
            recommended_frame_ms=20,
        ),
        output=AudioFormatOut(
            type="pcm_s16le",
            sample_rate=24000,
            channels=1,
            bits_per_sample=16,
        ),
    )
    return success(out.model_dump(by_alias=True))


@ws_router.websocket("/ws/realtime-avatar")
async def realtime_avatar_socket(
    websocket: WebSocket,
    ticket: str = Query(...),
    db: Session = Depends(get_db),
):
    await websocket.accept()
    try:
        payload = consume_ticket(ticket)
    except VoiceTicketError as exc:
        await websocket.send_json(
            error_event(
                session_id="unbound",
                code="invalid_ticket",
                message=str(exc),
                recoverable=False,
            )
        )
        await websocket.close(code=4001)
        return

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user:
        await websocket.send_json(
            error_event(
                session_id="unbound",
                code="user_not_found",
                message="用户不存在或已注销",
                recoverable=False,
            )
        )
        await websocket.close(code=4001)
        return

    provider = realtime_config.create_provider()
    runner = RealtimeVoiceSessionRunner(
        websocket=websocket,
        user=user,
        ticket_payload=payload,
        provider=provider,
        db_factory=sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=db.get_bind(),
        ),
    )
    if not session_registry.claim(
        user.id,
        runner.session_id,
        max_sessions=int(settings.REALTIME_VOICE_MAX_GLOBAL_SESSIONS),
    ):
        await websocket.send_json(
            error_event(
                session_id=runner.session_id,
                code="session_limit",
                message="当前已有实时语音会话，或服务繁忙",
                recoverable=False,
            )
        )
        await websocket.close(code=4008)
        return

    try:
        await runner.run()
    finally:
        session_registry.release(user.id, runner.session_id)
        with contextlib.suppress(Exception):
            await websocket.close()
