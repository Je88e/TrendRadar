# coding=utf-8
"""ConfigStore 单元测试 — 线程安全的 AppContext 持有者。

垂直切片顺序见 docs/online-config-design.md §6 与本会话 TDD plan。
store 通过 build_ctx 工厂解耦真实 AppContext 构造（避免单元测试
触发 litellm 等重依赖），故用 object() 作 ctx 替身验证换引用语义。
"""

import threading

from trendradar.admin.store import ConfigStore


def test_get_returns_initial_context():
    """get() 返回构造时传入的初始 ctx（reload 前身份不变）。"""
    # Arrange
    initial = object()
    store = ConfigStore(initial_ctx=initial, build_ctx=lambda: object())

    # Act
    got = store.get()

    # Assert
    assert got is initial


def test_reload_swaps_to_new_context():
    """reload() 后 get() 返回 build_ctx 产出的新实例；旧实例引用不变（drain）。"""
    # Arrange
    initial = object()
    fresh = object()
    store = ConfigStore(initial_ctx=initial, build_ctx=lambda: fresh)

    # Act
    store.reload()
    got = store.get()

    # Assert
    assert got is fresh
    assert got is not initial


def test_concurrent_get_and_reload_are_thread_safe():
    """并发 get()/reload() 不抛错；每次 reload 恰好构造一次新 ctx（无撕裂）。

    线程安全契约的守卫测试：GIL 下单属性赋值本身原子，故无法可靠 RED，
    此测试固化「reload→build 一一对应、终态为已知产物」不变量，防后续
    重构（如引入多步复合换引用）破坏。
    """
    # Arrange
    initial = object()
    builds: list = []
    build_lock = threading.Lock()
    reload_count = 0
    rc_lock = threading.Lock()

    def build_ctx():
        ctx = object()
        with build_lock:
            builds.append(ctx)
        return ctx

    store = ConfigStore(initial_ctx=initial, build_ctx=build_ctx)
    errors: list = []
    stop = threading.Event()

    def getter():
        while not stop.is_set():
            try:
                store.get()
            except Exception as e:  # noqa: BLE001 - 收集任意异常断言无撕裂
                errors.append(e)

    def reloader():
        nonlocal reload_count
        while not stop.is_set():
            try:
                store.reload()
                with rc_lock:
                    reload_count += 1
            except Exception as e:  # noqa: BLE001
                errors.append(e)

    # Act
    threads = [threading.Thread(target=getter) for _ in range(4)]
    threads += [threading.Thread(target=reloader) for _ in range(2)]
    for t in threads:
        t.start()
    stop.wait(0.2)
    stop.set()
    for t in threads:
        t.join(timeout=2)

    # Assert
    assert errors == [], f"并发出现异常: {errors}"
    assert len(builds) == reload_count  # 每次 reload 恰好一次 build
    final = store.get()
    assert final is initial or final in builds  # 终态为已知产物
