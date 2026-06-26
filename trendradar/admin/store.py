# coding=utf-8
"""
ConfigStore — 线程安全的 AppContext 持有者。

get() 返回当前快照（调用方生命周期内稳定）；reload() 通过 build_ctx 工厂
在锁外构造新 ctx、锁内换引用，旧实例 drain（在飞周期跑完后 GC）。

store 不直接依赖 AppContext / load_config（避免触发 litellm 等重依赖），
ctx 的构造由调用方经 build_ctx 工厂注入。生产侧 =
``lambda: AppContext(load_config(config_path))``。
详见 docs/online-config-design.md §3。
"""

from __future__ import annotations

import threading
from typing import Callable, Generic, TypeVar

_T = TypeVar("_T")


class ConfigStore(Generic[_T]):
    """线程安全的 ctx 持有者。"""

    def __init__(self, initial_ctx: _T, build_ctx: Callable[[], _T]):
        self._ctx = initial_ctx
        self._build_ctx = build_ctx
        self._lock = threading.RLock()

    def get(self) -> _T:
        """返回当前 ctx 快照。"""
        with self._lock:
            return self._ctx

    def reload(self) -> None:
        """构造新 ctx 并原子换引用。旧实例 drain（不主动关闭，在飞周期跑完 GC）。

        构造在锁外进行（build_ctx 可能慢或失败），仅换引用入锁，避免阻塞 get()。
        """
        new_ctx = self._build_ctx()
        with self._lock:
            self._ctx = new_ctx
