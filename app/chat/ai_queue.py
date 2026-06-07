from __future__ import annotations

"""
AI 聊天请求队列与自动模型路由。

队列只包裹真正的大模型调用阶段，避免外部模型慢响应时压垮后端连接。
当前部署为单 worker；若未来改多 worker，需要迁移到 Redis/MySQL 分布式计数。
"""
import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Deque

from app.ai.model_service import (
    BUILTIN_ARK_DEEPSEEK_V4_FLASH_ID,
    BUILTIN_ARK_DOUBAO_MINI_ID,
    BUILTIN_ARK_GLM_4_7_ID,
)
from app.config import settings


MODEL_LIMITS: tuple[tuple[str, int], ...] = (
    (BUILTIN_ARK_DEEPSEEK_V4_FLASH_ID, settings.CHAT_AI_FLASH_CONCURRENCY),
    (BUILTIN_ARK_DOUBAO_MINI_ID, settings.CHAT_AI_DOUBAO_MINI_CONCURRENCY),
    (BUILTIN_ARK_GLM_4_7_ID, settings.CHAT_AI_GLM_4_7_CONCURRENCY),
)


@dataclass
class ChatQueueSnapshot:
    global_limit: int
    active_total: int
    queued_count: int
    model_active: dict[str, int]
    model_limits: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "globalLimit": self.global_limit,
            "activeTotal": self.active_total,
            "queuedCount": self.queued_count,
            "modelActive": dict(self.model_active),
            "modelLimits": dict(self.model_limits),
        }


class ChatModelQueue:
    def __init__(self, limits: tuple[tuple[str, int], ...], global_limit: int):
        self._limits = {model_id: max(0, int(limit)) for model_id, limit in limits}
        self._priority = [model_id for model_id, _limit in limits]
        capacity_sum = sum(self._limits.values())
        self._global_limit = max(0, min(int(global_limit), capacity_sum))
        self._active = {model_id: 0 for model_id in self._priority}
        self._waiters: Deque[ChatModelWaiter] = deque()
        self._lock = asyncio.Lock()

    def _active_total(self) -> int:
        return sum(self._active.values())

    def _pick_model(self, skip_model_ids: set[str] | None = None) -> str | None:
        skipped = skip_model_ids or set()
        if self._active_total() >= self._global_limit:
            return None
        for model_id in self._priority:
            if model_id in skipped:
                continue
            if self._active[model_id] < self._limits[model_id]:
                return model_id
        return None

    def _assign(self, future: asyncio.Future[str], model_id: str) -> None:
        self._active[model_id] += 1
        if not future.done():
            future.set_result(model_id)

    def _drain_locked(self) -> None:
        while self._waiters:
            waiter = self._waiters[0]
            if waiter.future.cancelled():
                self._waiters.popleft()
                continue
            model_id = self._pick_model(waiter.skip_model_ids)
            if not model_id:
                return
            self._waiters.popleft()
            self._assign(waiter.future, model_id)

    async def acquire(self, skip_model_ids: set[str] | None = None) -> "ChatModelLease":
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        skipped = set(skip_model_ids or set())
        async with self._lock:
            model_id = self._pick_model(skipped)
            if model_id and not self._waiters:
                self._assign(future, model_id)
            else:
                self._waiters.append(ChatModelWaiter(future=future, skip_model_ids=skipped))
                self._drain_locked()

        try:
            assigned_model_id = await future
            return ChatModelLease(self, assigned_model_id)
        except BaseException:
            async with self._lock:
                try:
                    waiter = next(item for item in self._waiters if item.future is future)
                    self._waiters.remove(waiter)
                except ValueError:
                    pass
                except StopIteration:
                    pass
                self._drain_locked()
            raise

    async def release(self, model_id: str) -> None:
        async with self._lock:
            if model_id in self._active and self._active[model_id] > 0:
                self._active[model_id] -= 1
            self._drain_locked()

    async def snapshot(self) -> ChatQueueSnapshot:
        async with self._lock:
            return ChatQueueSnapshot(
                global_limit=self._global_limit,
                active_total=self._active_total(),
                queued_count=sum(1 for item in self._waiters if not item.future.cancelled()),
                model_active=dict(self._active),
                model_limits=dict(self._limits),
            )

    async def reset_for_tests(self) -> None:
        async with self._lock:
            for waiter in self._waiters:
                if not waiter.future.done():
                    waiter.future.cancel()
            self._waiters.clear()
            self._active = {model_id: 0 for model_id in self._priority}


@dataclass
class ChatModelWaiter:
    future: asyncio.Future[str]
    skip_model_ids: set[str]


class ChatModelLease:
    def __init__(self, queue: ChatModelQueue, model_id: str):
        self._queue = queue
        self.model_id = model_id
        self._released = False

    async def __aenter__(self) -> str:
        return self.model_id

    async def __aexit__(self, *_exc_info) -> None:
        await self.release()

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await self._queue.release(self.model_id)


chat_model_queue = ChatModelQueue(
    MODEL_LIMITS,
    global_limit=settings.CHAT_AI_GLOBAL_CONCURRENCY,
)


async def acquire_chat_model_slot(*, skip_model_ids: set[str] | None = None) -> ChatModelLease:
    return await chat_model_queue.acquire(skip_model_ids=skip_model_ids)


async def get_chat_queue_status() -> dict:
    return (await chat_model_queue.snapshot()).to_dict()
