"""数据库驱动的 AtoA 冲浪 worker。

生产环境保持单实例运行，串行消费任务，避免 vivo 模型接口瞬时并发过高。
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.avatar.service import claim_next_surf_job, process_surf_job  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("avatar-worker")
stop_event: asyncio.Event | None = None


def _request_stop(*_args) -> None:
    if stop_event is not None:
        stop_event.set()


async def run_worker() -> None:
    global stop_event
    # Event 必须在 asyncio.run 创建的当前事件循环内初始化。
    # Python 3.9 会拒绝等待在模块加载阶段绑定到其他循环的 Event。
    stop_event = asyncio.Event()
    init_db()
    poll_seconds = max(0.5, float(getattr(settings, "ATOA_WORKER_POLL_SEC", 2.0)))
    logger.info("avatar worker started, poll interval %.1fs", poll_seconds)

    while not stop_event.is_set():
        db = SessionLocal()
        try:
            job = claim_next_surf_job(db)
            if not job:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
                except asyncio.TimeoutError:
                    pass
                continue
            logger.info("processing surf job %s for user %s", job.id, job.user_id)
            try:
                await process_surf_job(db, job)
                logger.info("surf job %s succeeded", job.id)
            except Exception:
                logger.exception("surf job %s failed", job.id)
        finally:
            db.close()

    logger.info("avatar worker stopped")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    asyncio.run(run_worker())
