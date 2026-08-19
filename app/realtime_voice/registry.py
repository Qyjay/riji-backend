"""进程内实时会话注册表。

当前生产仅运行单个 Uvicorn worker。扩展到多 worker 前需要迁移至 Redis。
"""
from threading import Lock


class RealtimeSessionRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._by_user: dict[str, str] = {}

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._by_user)

    def claim(self, user_id: str, session_id: str, *, max_sessions: int) -> bool:
        with self._lock:
            current = self._by_user.get(user_id)
            if current and current != session_id:
                return False
            if not current and len(self._by_user) >= max(1, max_sessions):
                return False
            self._by_user[user_id] = session_id
            return True

    def release(self, user_id: str, session_id: str) -> None:
        with self._lock:
            if self._by_user.get(user_id) == session_id:
                self._by_user.pop(user_id, None)

    def reset(self) -> None:
        """仅用于测试清理。"""
        with self._lock:
            self._by_user.clear()


session_registry = RealtimeSessionRegistry()
