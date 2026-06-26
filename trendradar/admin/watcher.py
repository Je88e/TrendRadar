# coding=utf-8
"""
ConfigWatcher — mtime 轮询 + debounce 触发 reload。

纯 mtime 轮询（不依赖 inotify/watchdog），WSL2 / Docker bind-mount 跨平台一致。
check() 为单次轮询决策，注入 time_func 可使 debounce 确定性测试。
设计见 docs/online-config-design.md §3（daemon 线程 2）。
"""

from __future__ import annotations

import os
import threading
import time
from typing import Callable, Dict, List, Optional


class ConfigWatcher:
    """轮询文件 mtime，变化稳定 debounce 秒后触发 reload_callback。"""

    def __init__(
        self,
        paths: List[str],
        reload_callback: Callable[[], None],
        *,
        poll_interval: float = 2.0,
        debounce: float = 1.0,
        time_func: Callable[[], float] = time.monotonic,
    ):
        self._paths = list(paths)
        self._reload = reload_callback
        self._poll_interval = poll_interval
        self._debounce = debounce
        self._time = time_func
        self._last_mtimes: Dict[str, Optional[int]] = self._snapshot()
        self._pending_change_at: Optional[float] = None
        self._stop_event: threading.Event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _mtime(self, path: str) -> Optional[int]:
        try:
            return os.stat(path).st_mtime_ns
        except OSError:
            return None

    def _snapshot(self) -> Dict[str, Optional[int]]:
        return {p: self._mtime(p) for p in self._paths}

    def check(self) -> bool:
        """单次轮询决策。返回 True 表示本次触发了 reload。

        检测到变化即（重新）arm 待触发时间戳；持续变化不断推迟触发，
        仅当稳定超过 debounce 秒才真正 reload（合并多次快速写入）。
        """
        now = self._time()
        current = self._snapshot()
        if current != self._last_mtimes:
            self._last_mtimes = current
            self._pending_change_at = now  # 检测到变化即（重新）arm
        if (
            self._pending_change_at is not None
            and (now - self._pending_change_at) >= self._debounce
        ):
            self._pending_change_at = None
            try:
                self._reload()
                return True
            except Exception as e:
                # reload 失败（如配置坏文件 build ctx 抛错）不应拖垮 watcher；
                # pending 已清、last_mtimes 已更新，待下次文件变化再触发
                print(f"[ConfigWatcher] reload 失败（忽略，待下次文件变化重试）: {e}")
                return False
        return False

    def _run(self) -> None:
        """线程主循环：每隔 poll_interval 做一次 check()，直到 stop() 置位。"""
        while not self._stop_event.wait(self._poll_interval):
            self.check()

    def start(self) -> None:
        """启动 daemon 轮询线程（幂等：已启动则 no-op）。"""
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="trendradar-config-watcher",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """停止轮询线程并 join（幂等：未启动则 no-op）。"""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=self._poll_interval * 4 + 1.0)
        self._thread = None
