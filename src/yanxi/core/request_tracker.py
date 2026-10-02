"""线程安全的最新请求标识，不依赖 GUI 或网络实现。"""

from threading import Lock


class RequestTracker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._next_id = 0
        self._active_id: int | None = None

    def begin(self) -> int:
        with self._lock:
            self._next_id += 1
            self._active_id = self._next_id
            return self._active_id

    def invalidate(self) -> None:
        with self._lock:
            self._active_id = None

    def is_current(self, request_id: int) -> bool:
        with self._lock:
            return request_id == self._active_id
