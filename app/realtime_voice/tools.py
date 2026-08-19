"""实时语音 Function Calling 注册、执行、审计与记忆工具。"""
from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Type
from uuid import uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.memory.retriever import retrieve_memories
from app.models.memory import MemoryDocument
from app.models.realtime_voice import RealtimeToolCall
from app.models.user import User
from app.realtime_voice.confirmations import (
    ConfirmationError,
    ConfirmationManager,
)
from app.realtime_voice.observability import (
    hash_user_id,
    log_voice_event,
    voice_metrics,
)
from app.realtime_voice.policy import (
    ToolPolicyError,
    ToolRisk,
    ensure_tool_can_be_exposed,
)
from app.realtime_voice.protocol import server_event
from app.realtime_voice.provider import (
    ProviderToolCall,
    ProviderToolResult,
    ToolDefinition,
)
from app.realtime_voice.tool_schemas import (
    CreateSocialMissionDraftArgs,
    DraftSocialMissionArgs,
    GetMemoryDocumentArgs,
    GetSocialMissionProgressArgs,
    ListSocialMissionsArgs,
    OpenAppPageArgs,
    SearchPersonalMemoryArgs,
    StartSocialMissionArgs,
)
from app.response import ApiException
from app.social.mission_service import (
    create_mission,
    get_mission,
    list_candidates,
    list_missions,
    parse_mission_text,
    start_mission,
)


MEMORY_SOURCE_TYPES = {
    "diary",
    "material",
    "plaza_post",
    "plaza_comment",
    "social_message",
    "chat_session",
}


class ToolExecutionError(ValueError):
    pass


@dataclass
class ToolHandlerOutput:
    data: Any
    display: dict[str, Any] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    confirmation_id: str | None = None


@dataclass
class ToolExecutionContext:
    voice_session_id: str
    client_session_id: str
    user_id: str
    allowed_document_ids: set[str] = field(default_factory=set)
    mission_drafts: dict[str, dict[str, Any]] = field(default_factory=dict)
    confirmations: ConfirmationManager | None = None
    current_user_turn: int = 0
    _document_lock: threading.Lock = field(default_factory=threading.Lock)
    _mission_lock: threading.Lock = field(default_factory=threading.Lock)

    def allow_documents(self, document_ids: list[str]) -> None:
        with self._document_lock:
            self.allowed_document_ids.update(document_ids)
            if len(self.allowed_document_ids) > 100:
                self.allowed_document_ids = set(list(self.allowed_document_ids)[-100:])

    def document_is_allowed(self, document_id: str) -> bool:
        with self._document_lock:
            return document_id in self.allowed_document_ids

    def note_user_turn(self) -> int:
        with self._mission_lock:
            self.current_user_turn += 1
            return self.current_user_turn

    def save_mission_draft(self, draft_id: str, payload: dict[str, Any]) -> None:
        with self._mission_lock:
            self.mission_drafts[draft_id] = payload
            if len(self.mission_drafts) > 10:
                oldest = next(iter(self.mission_drafts))
                self.mission_drafts.pop(oldest, None)

    def get_mission_draft(self, draft_id: str) -> dict[str, Any] | None:
        with self._mission_lock:
            return self.mission_drafts.get(draft_id)


ToolHandler = Callable[[Session, ToolExecutionContext, BaseModel], ToolHandlerOutput]


@dataclass
class ToolSpec:
    name: str
    description: str
    args_model: Type[BaseModel]
    risk: ToolRisk
    handler: ToolHandler
    read_only: bool = True

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.args_model.model_json_schema(by_alias=True),
        )


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        ensure_tool_can_be_exposed(spec.risk)
        if spec.name in self._tools:
            raise ToolPolicyError(f"工具重复注册：{spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def definitions(self) -> list[ToolDefinition]:
        return [spec.definition() for spec in self._tools.values()]


def _deep_link(source_type: str, source_id: str) -> str:
    if source_type == "diary":
        return f"/pages/diary/detail?id={source_id}"
    if source_type in {"plaza_post", "plaza_post_index"}:
        return f"/pages/plaza/detail?id={source_id}"
    if source_type == "chat_session":
        return "/pages/chat/index"
    return "/pages/index/index"


def _search_personal_memory(
    db: Session,
    context: ToolExecutionContext,
    raw_args: BaseModel,
) -> ToolHandlerOutput:
    args = SearchPersonalMemoryArgs.model_validate(raw_args.model_dump(by_alias=True))
    source_types = args.source_types or sorted(MEMORY_SOURCE_TYPES)
    invalid = [item for item in source_types if item not in MEMORY_SOURCE_TYPES]
    if invalid:
        raise ToolExecutionError("包含不允许检索的记忆来源")
    items = retrieve_memories(
        db,
        user_id=context.user_id,
        query=args.query,
        scenario="chat",
        top_k=min(args.top_k, 6),
        source_types=source_types,
    )
    result_items = []
    for item in items[:6]:
        document_id = str(item.get("document_id") or "")
        source_type = str(item.get("source_type") or "")
        source_id = str(item.get("source_id") or "")
        result_items.append(
            {
                "documentId": document_id,
                "sourceType": source_type,
                "sourceId": source_id,
                "title": str(item.get("title") or ""),
                "snippet": str(item.get("content") or "")[:240],
                "occurredAt": int(item.get("occurred_at") or 0),
                "score": round(float(item.get("score") or 0), 4),
                "deepLink": _deep_link(source_type, source_id),
            }
        )
    context.allow_documents(
        [item["documentId"] for item in result_items if item["documentId"]]
    )
    return ToolHandlerOutput(
        data={"items": result_items},
        display={"kind": "memory_evidence", "items": result_items[:3]},
    )


def _get_memory_document(
    db: Session,
    context: ToolExecutionContext,
    raw_args: BaseModel,
) -> ToolHandlerOutput:
    args = GetMemoryDocumentArgs.model_validate(raw_args.model_dump(by_alias=True))
    if not context.document_is_allowed(args.document_id):
        raise ToolExecutionError("记忆不存在或当前会话未授权")
    document = (
        db.query(MemoryDocument)
        .filter(
            MemoryDocument.id == args.document_id,
            MemoryDocument.user_id == context.user_id,
            MemoryDocument.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if not document:
        raise ToolExecutionError("记忆不存在或当前会话未授权")
    data = {
        "documentId": document.id,
        "sourceType": document.source_type,
        "sourceId": document.source_id,
        "title": document.title or "",
        "content": (document.content or "")[:800],
        "occurredAt": document.occurred_at,
        "deepLink": _deep_link(document.source_type, document.source_id),
    }
    return ToolHandlerOutput(
        data=data,
        display={"kind": "memory_document", "item": data},
    )


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _mission_summary(draft: dict[str, Any]) -> dict[str, Any]:
    time_window = draft.get("timeWindow") or draft.get("time_window") or {}
    location = draft.get("location") or {}
    headcount = draft.get("headcount") or {}
    radius = location.get("radiusKm")
    location_label = str(location.get("label") or "位置待确认")
    if radius:
        location_label = f"{location_label}附近 {radius} km"
    return {
        "activity": str(draft.get("title") or "找朋友"),
        "time": str(time_window.get("label") or "时间待确认"),
        "location": location_label,
        "headcount": f"再找 {max(1, int(headcount.get('wanted') or 1))} 人",
        "scope": "公开帖子与授权名片",
        "notice": "不会自动发帖或申请认识",
    }


def _summary_lines(summary: dict[str, Any]) -> list[str]:
    return [
        f"活动：{summary['activity']}",
        f"时间：{summary['time']}",
        f"地点：{summary['location']}",
        f"人数：{summary['headcount']}",
        f"范围：{summary['scope']}",
    ]


def _mission_create_payload(draft: dict[str, Any]) -> dict[str, Any]:
    permissions = dict(draft.get("permissions") or {})
    permissions["autoPublish"] = False
    permissions["autoConnect"] = False
    return {
        "mode": draft.get("mode"),
        "purpose_type": draft.get("purposeType"),
        "title": draft.get("title"),
        "description": draft.get("description"),
        "source": "realtime_voice",
        "time_window": draft.get("timeWindow") or {},
        "location": draft.get("location") or {},
        "headcount": draft.get("headcount") or {},
        "budget": draft.get("budget") or {},
        "must_haves": draft.get("mustHaves") or [],
        "preferences": draft.get("preferences") or [],
        "boundaries": draft.get("boundaries") or [],
        "public_memory_ids": draft.get("publicMemoryIds") or [],
        "permissions": permissions,
        "search_strategy": draft.get("searchStrategy") or "search_then_draft",
        "expires_at": draft.get("expiresAt"),
    }


def _mission_fingerprint(mission: dict[str, Any]) -> str:
    return _canonical_hash(
        {
            "id": mission.get("id"),
            "mode": mission.get("mode"),
            "purpose_type": mission.get("purpose_type"),
            "title": mission.get("title"),
            "description": mission.get("description"),
            "time_window": mission.get("time_window") or {},
            "location": mission.get("location") or {},
            "headcount": mission.get("headcount") or {},
            "permissions": mission.get("permissions") or {},
            "search_strategy": mission.get("search_strategy"),
            "expires_at": mission.get("expires_at"),
        }
    )


def _current_user(db: Session, context: ToolExecutionContext) -> User:
    user = db.query(User).filter(User.id == context.user_id).first()
    if not user:
        raise ToolExecutionError("当前用户不存在或已注销")
    return user


def _draft_social_mission(
    db: Session,
    context: ToolExecutionContext,
    raw_args: BaseModel,
) -> ToolHandlerOutput:
    args = DraftSocialMissionArgs.model_validate(raw_args.model_dump(by_alias=True))
    try:
        parsed = parse_mission_text(args.text, _current_user(db, context))
    except ApiException as exc:
        raise ToolExecutionError(exc.message) from exc
    draft = dict(parsed.get("draft") or {})
    questions = [str(item) for item in (parsed.get("questions") or []) if str(item).strip()]
    if any(keyword in args.text for keyword in ("每天", "天天", "经常")):
        recurring_question = "你是想今天去一次、固定周期约，还是最近有空时再找？"
        questions = [recurring_question, *questions]
    questions = list(dict.fromkeys(questions))[:3]
    summary = _mission_summary(draft)
    draft_hash = _canonical_hash(draft)
    draft_id = str(uuid4())
    context.save_mission_draft(
        draft_id,
        {
            "draft": draft,
            "draftHash": draft_hash,
            "questions": questions,
            "summary": summary,
            "createdTurn": context.current_user_turn,
        },
    )
    data = {
        "draftId": draft_id,
        "draftHash": draft_hash,
        "draft": draft,
        "inferredFields": parsed.get("inferred_fields") or [],
        "questions": questions,
        "summary": summary,
    }
    return ToolHandlerOutput(
        data=data,
        display={
            "kind": "mission_draft",
            "draftId": draft_id,
            "summary": summary,
            "questions": questions,
            "readyForConfirmation": not questions,
        },
    )


def _create_social_mission_draft(
    db: Session,
    context: ToolExecutionContext,
    raw_args: BaseModel,
) -> ToolHandlerOutput:
    args = CreateSocialMissionDraftArgs.model_validate(
        raw_args.model_dump(by_alias=True)
    )
    cached = context.get_mission_draft(args.draft_id)
    if not cached or cached.get("draftHash") != args.draft_hash:
        raise ToolExecutionError("草稿不存在、已变化或不属于当前会话")
    questions = cached.get("questions") or []
    if questions:
        raise ToolExecutionError("草稿仍有待确认问题，不能创建任务")
    try:
        mission = create_mission(
            db,
            _current_user(db, context),
            _mission_create_payload(cached["draft"]),
        )
    except ApiException as exc:
        raise ToolExecutionError(exc.message) from exc
    if mission.get("status") != "draft":
        raise ToolExecutionError("任务未能以草稿状态创建")
    summary = _mission_summary(
        {
            "title": mission.get("title"),
            "time_window": mission.get("time_window"),
            "location": mission.get("location"),
            "headcount": mission.get("headcount"),
        }
    )
    if not context.confirmations:
        raise ToolExecutionError("确认服务尚未启用")
    confirmation = context.confirmations.create(
        action="start_social_mission",
        resource_id=mission["id"],
        resource_hash=_mission_fingerprint(mission),
        title=f"开始寻找{mission.get('title') or '合适的人'}？",
        summary=_summary_lines(summary),
        created_turn=context.current_user_turn,
        metadata={"missionId": mission["id"]},
    )
    public_confirmation = confirmation.public_payload()
    return ToolHandlerOutput(
        data={
            "mission": {
                "id": mission["id"],
                "title": mission["title"],
                "status": mission["status"],
                "deepLink": f"/pages/social/mission-detail?id={mission['id']}",
            },
            "summary": summary,
            "confirmation": public_confirmation,
            "confirmationToken": confirmation.token,
        },
        display={
            "kind": "mission_created",
            "missionId": mission["id"],
            "status": "draft",
            "summary": summary,
        },
        events=[
            server_event(
                "confirmation.required",
                session_id=context.client_session_id,
                confirmation=public_confirmation,
            )
        ],
        confirmation_id=confirmation.id,
    )


def _safe_mission_result(result: dict[str, Any]) -> dict[str, Any]:
    mission = result["mission"]
    candidates = []
    for item in (result.get("candidates") or [])[:3]:
        user = item.get("target_user") or {}
        post = item.get("target_post") or {}
        reasons = [
            str(reason.get("text") or "")
            for reason in (item.get("fit_reasons") or [])[:3]
            if isinstance(reason, dict) and reason.get("text")
        ]
        candidates.append(
            {
                "id": item.get("id"),
                "name": user.get("name") or post.get("authorName") or "待查看候选",
                "school": user.get("school") or post.get("authorSchool") or "",
                "fitReasons": reasons,
                "questions": (item.get("questions") or [])[:3],
            }
        )
    return {
        "mission": {
            "id": mission["id"],
            "title": mission["title"],
            "status": mission["status"],
            "candidateCount": int(mission.get("candidate_count") or 0),
            "pendingCount": int(mission.get("pending_count") or 0),
            "deepLink": f"/pages/social/mission-detail?id={mission['id']}",
        },
        "scannedCount": int(result.get("scanned_count") or 0),
        "matchedCount": int(result.get("matched_count") or 0),
        "candidates": candidates,
        "suggestion": str(result.get("suggestion") or ""),
    }


def _start_social_mission(
    db: Session,
    context: ToolExecutionContext,
    raw_args: BaseModel,
) -> ToolHandlerOutput:
    args = StartSocialMissionArgs.model_validate(raw_args.model_dump(by_alias=True))
    if not context.confirmations:
        raise ToolExecutionError("确认服务尚未启用")
    try:
        mission = get_mission(db, context.user_id, args.mission_id)
        confirmation, should_execute = context.confirmations.resolve_voice(
            token=args.confirmation_token,
            action="start_social_mission",
            resource_id=args.mission_id,
            resource_hash=_mission_fingerprint(mission),
            current_turn=context.current_user_turn,
        )
        if should_execute:
            result = start_mission(
                db,
                _current_user(db, context),
                args.mission_id,
            )
            confirmation.result = _safe_mission_result(result)
        elif confirmation.result is None:
            raise ToolExecutionError("确认已经处理，任务没有重复执行")
    except (ApiException, ConfirmationError) as exc:
        if "confirmation" in locals() and confirmation.result is None:
            confirmation.status = "pending"
            confirmation.decision = ""
            confirmation.channel = ""
        message = exc.message if isinstance(exc, ApiException) else str(exc)
        raise ToolExecutionError(message) from exc
    safe_result = confirmation.result or {}
    deep_link = safe_result.get("mission", {}).get("deepLink", "")
    return ToolHandlerOutput(
        data=safe_result,
        display={"kind": "mission_progress", **safe_result},
        events=[
            server_event(
                "navigation.suggested",
                session_id=context.client_session_id,
                path=deep_link,
                label="查看任务进度",
            )
        ] if deep_link else [],
        confirmation_id=confirmation.id,
    )


def _list_social_missions(
    db: Session,
    context: ToolExecutionContext,
    raw_args: BaseModel,
) -> ToolHandlerOutput:
    args = ListSocialMissionsArgs.model_validate(raw_args.model_dump(by_alias=True))
    rows = list_missions(db, context.user_id, status=args.status)[: args.limit]
    items = [
        {
            "id": row["id"],
            "title": row["title"],
            "mode": row["mode"],
            "status": row["status"],
            "candidateCount": int(row.get("candidate_count") or 0),
            "pendingCount": int(row.get("pending_count") or 0),
            "updatedAt": int(row.get("updated_at") or 0),
            "deepLink": f"/pages/social/mission-detail?id={row['id']}",
        }
        for row in rows
    ]
    return ToolHandlerOutput(data={"items": items})


def _get_social_mission_progress(
    db: Session,
    context: ToolExecutionContext,
    raw_args: BaseModel,
) -> ToolHandlerOutput:
    args = GetSocialMissionProgressArgs.model_validate(
        raw_args.model_dump(by_alias=True)
    )
    try:
        mission = get_mission(db, context.user_id, args.mission_id)
        candidates = list_candidates(db, context.user_id, args.mission_id)
    except ApiException as exc:
        raise ToolExecutionError(exc.message) from exc
    safe = _safe_mission_result(
        {
            "mission": mission,
            "candidates": candidates,
            "scanned_count": 0,
            "matched_count": len(candidates),
            "suggestion": "",
        }
    )
    return ToolHandlerOutput(
        data=safe,
        display={"kind": "mission_progress", **safe},
    )


def _open_app_page(
    db: Session,
    context: ToolExecutionContext,
    raw_args: BaseModel,
) -> ToolHandlerOutput:
    args = OpenAppPageArgs.model_validate(raw_args.model_dump(by_alias=True))
    routes = {
        "home": ("/pages/index/index", "返回首页"),
        "chat": ("/pages/chat/index", "返回文字对话"),
        "social": ("/pages/social/index", "查看找朋友"),
        "social_find": ("/pages/social/find", "发起找人"),
        "avatar_memory": ("/pages/profile/avatar-memory", "查看分身记忆"),
    }
    if args.page == "mission":
        if not args.resource_id:
            raise ToolExecutionError("打开任务页面需要任务 ID")
        try:
            get_mission(db, context.user_id, args.resource_id)
        except ApiException as exc:
            raise ToolExecutionError(exc.message) from exc
        path, label = (
            f"/pages/social/mission-detail?id={args.resource_id}",
            "查看任务进度",
        )
    elif args.page == "diary":
        if not args.resource_id or not context.document_is_allowed(args.resource_id):
            raise ToolExecutionError("日记不存在或当前会话未授权")
        document = (
            db.query(MemoryDocument)
            .filter(
                MemoryDocument.id == args.resource_id,
                MemoryDocument.user_id == context.user_id,
                MemoryDocument.source_type == "diary",
                MemoryDocument.is_deleted == False,  # noqa: E712
            )
            .first()
        )
        if not document:
            raise ToolExecutionError("日记不存在或当前会话未授权")
        path, label = (
            f"/pages/diary/detail?id={document.source_id}",
            "查看这篇日记",
        )
    else:
        path, label = routes[args.page]
    event = server_event(
        "navigation.suggested",
        session_id=context.client_session_id,
        path=path,
        label=label,
    )
    return ToolHandlerOutput(data={"path": path, "label": label}, events=[event])


def default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="search_personal_memory",
            description=(
                "检索当前用户自己的日记、素材、聊天或社交记忆。"
                "当回答涉及用户过去的具体经历时必须先调用。"
            ),
            args_model=SearchPersonalMemoryArgs,
            risk=ToolRisk.R0,
            handler=_search_personal_memory,
            read_only=True,
        )
    )
    registry.register(
        ToolSpec(
            name="get_memory_document",
            description=(
                "读取本次会话刚刚检索到的一条记忆详情。"
                "documentId 必须来自 search_personal_memory 的返回。"
            ),
            args_model=GetMemoryDocumentArgs,
            risk=ToolRisk.R0,
            handler=_get_memory_document,
            read_only=True,
        )
    )
    registry.register(
        ToolSpec(
            name="draft_social_mission",
            description=(
                "把用户口头表达的找人需求整理成任务草稿，不写数据库。"
                "如果返回 questions，必须先追问，不能创建任务。"
            ),
            args_model=DraftSocialMissionArgs,
            risk=ToolRisk.R0,
            handler=_draft_social_mission,
            read_only=True,
        )
    )
    registry.register(
        ToolSpec(
            name="create_social_mission_draft",
            description=(
                "将当前会话刚整理且没有待确认问题的找人草稿保存为私有草稿。"
                "只接受 draft_social_mission 返回的 draftId 和 draftHash。"
            ),
            args_model=CreateSocialMissionDraftArgs,
            risk=ToolRisk.R1,
            handler=_create_social_mission_draft,
            read_only=False,
        )
    )
    registry.register(
        ToolSpec(
            name="start_social_mission",
            description=(
                "在用户明确确认后启动私有找人任务。"
                "必须提供当前会话签发的 confirmationToken，不能自动发帖、试聊或建立关系。"
            ),
            args_model=StartSocialMissionArgs,
            risk=ToolRisk.R2,
            handler=_start_social_mission,
            read_only=False,
        )
    )
    registry.register(
        ToolSpec(
            name="list_social_missions",
            description="查看当前用户自己的找人任务列表和公开进度摘要。",
            args_model=ListSocialMissionsArgs,
            risk=ToolRisk.R0,
            handler=_list_social_missions,
            read_only=True,
        )
    )
    registry.register(
        ToolSpec(
            name="get_social_mission_progress",
            description=(
                "查看当前用户某个找人任务的状态、候选数量和最多三个安全摘要。"
            ),
            args_model=GetSocialMissionProgressArgs,
            risk=ToolRisk.R0,
            handler=_get_social_mission_progress,
            read_only=True,
        )
    )
    registry.register(
        ToolSpec(
            name="open_app_page",
            description=(
                "建议用户打开 Avalin 白名单页面。只返回导航建议，不直接控制客户端。"
            ),
            args_model=OpenAppPageArgs,
            risk=ToolRisk.R0,
            handler=_open_app_page,
            read_only=True,
        )
    )
    return registry


class ToolRouter:
    def __init__(
        self,
        *,
        voice_session_id: str,
        client_session_id: str,
        user_id: str,
        db_factory: Callable[[], Session],
        registry: ToolRegistry | None = None,
    ) -> None:
        self.registry = registry or default_tool_registry()
        self.context = ToolExecutionContext(
            voice_session_id=voice_session_id,
            client_session_id=client_session_id,
            user_id=user_id,
            confirmations=ConfirmationManager(
                user_id=user_id,
                voice_session_id=voice_session_id,
            ),
        )
        self.db_factory = db_factory

    def tool_definitions(self) -> list[ToolDefinition]:
        return self.registry.definitions()

    def note_user_turn(self) -> int:
        return self.context.note_user_turn()

    @staticmethod
    def _decode(raw: str, default):
        try:
            return json.loads(raw) if raw else default
        except (TypeError, ValueError, json.JSONDecodeError):
            return default

    @staticmethod
    def _idempotency_key(voice_session_id: str, call: ProviderToolCall) -> str:
        raw = f"{voice_session_id}:{call.call_id}:{call.name}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _provider_envelope(*, ok: bool, data=None, error: str | None = None) -> dict:
        return {"ok": ok, "data": data if ok else None, "error": error}

    @staticmethod
    def _serialized_provider_output(envelope: dict) -> str:
        raw = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
        limit = max(500, int(settings.REALTIME_VOICE_MAX_TOOL_RESULT_CHARS))
        if len(raw) <= limit:
            return raw
        preview = raw[: max(100, limit - 180)]
        return json.dumps(
            {
                "ok": True,
                "data": {"truncated": True, "preview": preview},
                "error": None,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _stored_result(
        self,
        call: ProviderToolCall,
        row: RealtimeToolCall,
    ) -> tuple[ProviderToolResult, list[dict]]:
        stored = self._decode(row.result_json, {})
        provider_envelope = stored.get("provider")
        if not isinstance(provider_envelope, dict):
            provider_envelope = self._provider_envelope(
                ok=False,
                error="工具调用仍在处理中",
            )
        displays = stored.get("display")
        if not isinstance(displays, list):
            displays = []
        return (
            ProviderToolResult(
                call_id=call.call_id,
                output=self._serialized_provider_output(provider_envelope),
            ),
            displays,
        )

    def _create_audit_row(
        self,
        db: Session,
        *,
        call: ProviderToolCall,
        spec: ToolSpec | None,
        arguments: dict,
    ) -> tuple[RealtimeToolCall, bool]:
        existing = (
            db.query(RealtimeToolCall)
            .filter(
                RealtimeToolCall.voice_session_id == self.context.voice_session_id,
                RealtimeToolCall.provider_call_id == call.call_id,
            )
            .first()
        )
        if existing:
            return existing, False
        now = int(time.time() * 1000)
        row = RealtimeToolCall(
            id=str(uuid4()),
            voice_session_id=self.context.voice_session_id,
            user_id=self.context.user_id,
            provider_call_id=call.call_id,
            tool_name=call.name[:120],
            arguments_json=json.dumps(arguments, ensure_ascii=False),
            risk_level=(spec.risk.value if spec else ToolRisk.R3.value),
            status="received" if spec else "rejected",
            idempotency_key=self._idempotency_key(
                self.context.voice_session_id,
                call,
            ),
            error_message="" if spec else "工具未注册",
            created_at=now,
            updated_at=now,
            finished_at=None if spec else now,
        )
        db.add(row)
        try:
            db.commit()
            db.refresh(row)
            return row, True
        except IntegrityError:
            db.rollback()
            existing = (
                db.query(RealtimeToolCall)
                .filter(
                    RealtimeToolCall.voice_session_id == self.context.voice_session_id,
                    RealtimeToolCall.provider_call_id == call.call_id,
                )
                .one()
            )
            return existing, False

    def _execute_one_sync(
        self,
        call: ProviderToolCall,
    ) -> tuple[ProviderToolResult, list[dict]]:
        spec = self.registry.get(call.name)
        try:
            raw_arguments = json.loads(call.arguments or "{}")
            if not isinstance(raw_arguments, dict):
                raise ValueError
        except (TypeError, ValueError, json.JSONDecodeError):
            raw_arguments = {}
            argument_error = "工具参数不是合法 JSON 对象"
        else:
            argument_error = ""

        db = self.db_factory()
        try:
            row, created = self._create_audit_row(
                db,
                call=call,
                spec=spec,
                arguments=raw_arguments,
            )
            if not created and row.status in {
                "succeeded",
                "failed",
                "rejected",
                "running",
                "awaiting_confirmation",
            }:
                return self._stored_result(call, row)

            if not spec:
                envelope = self._provider_envelope(
                    ok=False,
                    error="该工具未开放",
                )
                stored = {"provider": envelope, "display": []}
                row.result_json = json.dumps(stored, ensure_ascii=False)
                db.commit()
                return self._stored_result(call, row)

            row.status = "running"
            row.updated_at = int(time.time() * 1000)
            db.commit()
            try:
                if argument_error:
                    raise ToolExecutionError(argument_error)
                args = spec.args_model.model_validate(raw_arguments)
                output = spec.handler(db, self.context, args)
                envelope = self._provider_envelope(ok=True, data=output.data)
                display_events = []
                if output.display:
                    display_events.append(
                        server_event(
                            "tool.result",
                            session_id=self.context.client_session_id,
                            name=spec.name,
                            display=output.display,
                        )
                    )
                display_events.extend(output.events)
                row.status = (
                    "awaiting_confirmation"
                    if output.confirmation_id
                    and spec.name == "create_social_mission_draft"
                    else "succeeded"
                )
                row.confirmation_id = output.confirmation_id
                row.error_message = ""
            except (ValidationError, ToolExecutionError) as exc:
                envelope = self._provider_envelope(
                    ok=False,
                    error=str(exc)[:300],
                )
                display_events = []
                row.status = "failed"
                row.error_message = str(exc)[:500]
            except Exception:
                envelope = self._provider_envelope(
                    ok=False,
                    error="工具执行失败",
                )
                display_events = []
                row.status = "failed"
                row.error_message = "internal_tool_error"

            now = int(time.time() * 1000)
            row.result_json = json.dumps(
                {"provider": envelope, "display": display_events},
                ensure_ascii=False,
            )
            row.updated_at = now
            row.finished_at = now
            db.commit()
            return (
                ProviderToolResult(
                    call_id=call.call_id,
                    output=self._serialized_provider_output(envelope),
                ),
                display_events,
            )
        finally:
            db.close()

    def _mark_timeout(self, call: ProviderToolCall) -> None:
        db = self.db_factory()
        try:
            row = (
                db.query(RealtimeToolCall)
                .filter(
                    RealtimeToolCall.voice_session_id == self.context.voice_session_id,
                    RealtimeToolCall.provider_call_id == call.call_id,
                )
                .first()
            )
            if row:
                now = int(time.time() * 1000)
                envelope = self._provider_envelope(ok=False, error="工具执行超时")
                row.status = "failed"
                row.error_message = "tool_timeout"
                row.result_json = json.dumps(
                    {"provider": envelope, "display": []},
                    ensure_ascii=False,
                )
                row.updated_at = now
                row.finished_at = now
                db.commit()
        finally:
            db.close()

    async def _execute_one(
        self,
        call: ProviderToolCall,
        read_semaphore: asyncio.Semaphore,
        write_lock: asyncio.Lock,
    ) -> tuple[ProviderToolResult, list[dict]]:
        spec = self.registry.get(call.name)
        lock = read_semaphore if (spec is None or spec.read_only) else write_lock
        async with lock:
            # 当前 P0 工具都是本地短查询。同步 SQLAlchemy Session 不跨线程，
            # 避免 SQLite/StaticPool 和生产连接池出现线程事务竞态。
            started = time.monotonic()
            result = self._execute_one_sync(call)
            elapsed = time.monotonic() - started
            timeout = max(1, int(settings.REALTIME_VOICE_TOOL_TIMEOUT_SEC))
            if elapsed > timeout:
                self._mark_timeout(call)
                voice_metrics.increment("tool_timeout")
                log_voice_event(
                    "tool_timeout",
                    voice_session_id=self.context.voice_session_id,
                    user_id_hash=hash_user_id(self.context.user_id),
                    provider_call_id=call.call_id,
                    tool_name=call.name,
                    latency_ms=int(elapsed * 1000),
                )
                envelope = self._provider_envelope(
                    ok=False,
                    error="这次查询没有完成，请稍后重试",
                )
                return (
                    ProviderToolResult(
                        call_id=call.call_id,
                        output=self._serialized_provider_output(envelope),
                    ),
                    [],
                )
            voice_metrics.increment("tool_completed")
            return result

    async def execute_calls(
        self,
        calls: list[ProviderToolCall],
    ) -> tuple[list[ProviderToolResult], list[dict]]:
        if not calls:
            return [], []
        read_semaphore = asyncio.Semaphore(3)
        write_lock = asyncio.Lock()
        completed = await asyncio.gather(
            *(
                self._execute_one(call, read_semaphore, write_lock)
                for call in calls
            )
        )
        results = [item[0] for item in completed]
        display_events = [event for item in completed for event in item[1]]
        return results, display_events

    def _record_screen_confirmation(
        self,
        *,
        confirmation_id: str,
        decision: str,
        result: dict[str, Any],
        status: str,
    ) -> None:
        db = self.db_factory()
        try:
            now = int(time.time() * 1000)
            provider_call_id = f"screen:{confirmation_id}"
            row = (
                db.query(RealtimeToolCall)
                .filter(
                    RealtimeToolCall.voice_session_id
                    == self.context.voice_session_id,
                    RealtimeToolCall.provider_call_id == provider_call_id,
                )
                .first()
            )
            if not row:
                row = RealtimeToolCall(
                    id=str(uuid4()),
                    voice_session_id=self.context.voice_session_id,
                    user_id=self.context.user_id,
                    provider_call_id=provider_call_id,
                    tool_name="start_social_mission",
                    arguments_json=json.dumps(
                        {
                            "confirmationId": confirmation_id,
                            "decision": decision,
                            "channel": "screen",
                        },
                        ensure_ascii=False,
                    ),
                    risk_level=ToolRisk.R2.value,
                    confirmation_id=confirmation_id,
                    idempotency_key=hashlib.sha256(
                        f"{self.context.voice_session_id}:{provider_call_id}".encode(
                            "utf-8"
                        )
                    ).hexdigest(),
                    created_at=now,
                )
                db.add(row)
            row.status = status
            row.result_json = json.dumps(
                {
                    "provider": self._provider_envelope(ok=True, data=result),
                    "display": [],
                    "confirmation": {
                        "decision": decision,
                        "channel": "screen",
                    },
                },
                ensure_ascii=False,
            )
            row.error_message = ""
            row.updated_at = now
            row.finished_at = now
            db.commit()

            linked = (
                db.query(RealtimeToolCall)
                .filter(
                    RealtimeToolCall.voice_session_id
                    == self.context.voice_session_id,
                    RealtimeToolCall.confirmation_id == confirmation_id,
                    RealtimeToolCall.status == "awaiting_confirmation",
                )
                .all()
            )
            for item in linked:
                item.status = "succeeded" if decision == "approve" else "rejected"
                item.updated_at = now
                item.finished_at = now
            db.commit()
        finally:
            db.close()

    async def resolve_confirmation(
        self,
        *,
        confirmation_id: str,
        decision: str,
    ) -> tuple[ProviderToolResult | None, list[dict]]:
        manager = self.context.confirmations
        if not manager:
            raise ToolExecutionError("当前没有待确认操作")
        try:
            record, should_execute = manager.resolve_screen(
                confirmation_id=confirmation_id,
                decision=decision,
            )
        except ConfirmationError as exc:
            raise ToolExecutionError(str(exc)) from exc

        events = [
            server_event(
                "confirmation.resolved",
                session_id=self.context.client_session_id,
                confirmationId=record.id,
                decision=record.decision,
                channel=record.channel,
            )
        ]
        provider_result: ProviderToolResult | None = None
        if decision == "reject":
            result = {
                "confirmationId": record.id,
                "decision": "reject",
                "missionId": record.resource_id,
                "status": "draft",
            }
            self._record_screen_confirmation(
                confirmation_id=record.id,
                decision=decision,
                result=result,
                status="rejected",
            )
            return provider_result, events

        if should_execute:
            db = self.db_factory()
            try:
                mission = get_mission(db, self.context.user_id, record.resource_id)
                if _mission_fingerprint(mission) != record.resource_hash:
                    record.status = "expired"
                    raise ToolExecutionError("任务摘要已变化，请重新确认")
                try:
                    started = start_mission(
                        db,
                        _current_user(db, self.context),
                        record.resource_id,
                    )
                except ApiException as exc:
                    record.status = "pending"
                    record.decision = ""
                    record.channel = ""
                    raise ToolExecutionError(exc.message) from exc
                record.result = _safe_mission_result(started)
            finally:
                db.close()
        if record.result is None:
            raise ToolExecutionError("确认已经处理，任务没有重复执行")

        result = record.result
        self._record_screen_confirmation(
            confirmation_id=record.id,
            decision=decision,
            result=result,
            status="succeeded",
        )
        events.append(
            server_event(
                "tool.result",
                session_id=self.context.client_session_id,
                name="start_social_mission",
                display={"kind": "mission_progress", **result},
            )
        )
        deep_link = result.get("mission", {}).get("deepLink", "")
        if deep_link:
            events.append(
                server_event(
                    "navigation.suggested",
                    session_id=self.context.client_session_id,
                    path=deep_link,
                    label="查看任务进度",
                )
            )
        provider_result = ProviderToolResult(
            call_id=f"confirmation:{record.id}",
            output=self._serialized_provider_output(
                self._provider_envelope(
                    ok=True,
                    data={
                        **result,
                        "confirmation": {
                            "decision": "approve",
                            "channel": "screen",
                        },
                    },
                )
            ),
        )
        return provider_result, events
