# coding=utf-8
"""ConfigWatcher 单元测试 — mtime 轮询 + debounce 触发 store.reload()。

设计见 docs/online-config-design.md §3（daemon 线程 2）。
check() 为单次轮询决策，注入 time_func 使 debounce 可确定性测试，
无需真实线程睡眠。线程循环仅包裹 check()。
"""

import os

from trendradar.admin.watcher import ConfigWatcher


def test_mtime_change_triggers_reload_after_debounce(tmp_path):
    """mtime 变化 → debounce 到期后触发一次 reload；未到期不触发。"""
    # Arrange
    f = tmp_path / "config.yaml"
    f.write_text("a: 1", encoding="utf-8")
    now = [0.0]
    reloads = []
    watcher = ConfigWatcher(
        paths=[str(f)],
        reload_callback=lambda: reloads.append(1),
        debounce=1.0,
        time_func=lambda: now[0],
    )

    # Act / Assert: 基线 check（构造已 snapshot，无变化）
    assert watcher.check() is False
    assert reloads == []

    # 改文件（内容 + mtime ns 精度）
    f.write_text("a: 2", encoding="utf-8")
    os.utime(str(f), ns=(10**9, 10**9))

    # 检测到变化但 debounce 未到 → 不触发
    now[0] = 0.0
    assert watcher.check() is False
    assert reloads == []

    # debounce 到期 → 触发一次
    now[0] = 1.5
    assert watcher.check() is True
    assert reloads == [1]


def test_debounce_merges_rapid_writes(tmp_path):
    """debounce 窗口内的多次快速写入合并为一次 reload。"""
    # Arrange
    f = tmp_path / "config.yaml"
    f.write_text("a: 1", encoding="utf-8")
    now = [0.0]
    reloads = []
    watcher = ConfigWatcher(
        paths=[str(f)],
        reload_callback=lambda: reloads.append(1),
        debounce=1.0,
        time_func=lambda: now[0],
    )
    watcher.check()  # baseline

    # Act：第一次写入 t=0
    f.write_text("a: 2", encoding="utf-8")
    os.utime(str(f), ns=(10**9, 10**9))
    now[0] = 0.0
    watcher.check()  # arm pending=0
    # 第二次写入 t=0.5（debounce 窗口内）
    f.write_text("a: 3", encoding="utf-8")
    os.utime(str(f), ns=(2 * 10**9, 2 * 10**9))
    now[0] = 0.5
    watcher.check()  # re-arm pending=0.5

    # Assert：窗口内不触发
    now[0] = 0.9  # 距上次变化 0.4 < 1.0
    watcher.check()
    assert reloads == []
    # 距上次变化 ≥ debounce → 仅触发一次
    now[0] = 1.6  # 距 0.5 = 1.1 ≥ 1.0
    assert watcher.check() is True
    assert reloads == [1]


def test_no_change_no_reload(tmp_path):
    """mtime 不变 → 多次 check 永不触发 reload。"""
    # Arrange
    f = tmp_path / "config.yaml"
    f.write_text("a: 1", encoding="utf-8")
    now = [0.0]
    reloads = []
    watcher = ConfigWatcher(
        paths=[str(f)],
        reload_callback=lambda: reloads.append(1),
        debounce=1.0,
        time_func=lambda: now[0],
    )

    # Act：时间推进但文件不变
    for t in (0.0, 0.5, 1.5, 5.0, 10.0):
        now[0] = t
        watcher.check()

    # Assert
    assert reloads == []


def test_reload_exception_does_not_break_watcher(tmp_path):
    """reload_callback 抛错时 watcher 不崩；后续文件变化仍能正常触发。"""
    # Arrange
    f = tmp_path / "config.yaml"
    f.write_text("a: 1", encoding="utf-8")
    now = [0.0]
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")

    watcher = ConfigWatcher(
        paths=[str(f)],
        reload_callback=flaky,
        debounce=1.0,
        time_func=lambda: now[0],
    )
    watcher.check()  # baseline

    # Act / Assert：第一次变化 → reload 抛错，被吞，不崩
    f.write_text("a: 2", encoding="utf-8")
    os.utime(str(f), ns=(10**9, 10**9))
    now[0] = 0.0
    watcher.check()  # arm
    now[0] = 1.5
    assert watcher.check() is False  # reload 抛错 → 未成功触发
    assert len(calls) == 1

    # 第二次变化 → reload 成功，watcher 存活
    f.write_text("a: 3", encoding="utf-8")
    os.utime(str(f), ns=(3 * 10**9, 3 * 10**9))
    now[0] = 1.5
    watcher.check()  # re-arm（mtime 又变）
    now[0] = 3.0
    assert watcher.check() is True
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# 线程循环 start()/stop()
# ---------------------------------------------------------------------------

import threading


def test_start_stop_thread_triggers_reload(tmp_path):
    """start() 后改文件 → 线程轮询触发 reload；stop() 干净退出。"""
    # Arrange
    f = tmp_path / "config.yaml"
    f.write_text("a: 1", encoding="utf-8")
    reloaded = threading.Event()
    watcher = ConfigWatcher(
        paths=[str(f)],
        reload_callback=reloaded.set,
        poll_interval=0.02,
        debounce=0.0,
    )

    # Act
    watcher.start()
    try:
        f.write_text("a: 2", encoding="utf-8")
        os.utime(str(f), ns=(10**9, 10**9))
        # Assert：2s 内线程轮询命中变化 → reload
        assert reloaded.wait(timeout=2.0), "线程未在超时内触发 reload"
    finally:
        watcher.stop()

    # Assert：stop 后线程退出
    assert watcher._thread is None


def test_stop_joins_thread(tmp_path):
    """stop() join 线程，调用后线程不再存活。"""
    # Arrange
    f = tmp_path / "config.yaml"
    f.write_text("a: 1", encoding="utf-8")
    watcher = ConfigWatcher(
        paths=[str(f)],
        reload_callback=lambda: None,
        poll_interval=0.01,
    )
    watcher.start()
    thread = watcher._thread
    assert thread is not None and thread.is_alive()

    # Act
    watcher.stop()

    # Assert
    assert not thread.is_alive()


def test_start_stop_idempotent(tmp_path):
    """重复 start()/stop() 不抛错。"""
    # Arrange
    f = tmp_path / "config.yaml"
    f.write_text("a: 1", encoding="utf-8")
    watcher = ConfigWatcher(
        paths=[str(f)],
        reload_callback=lambda: None,
        poll_interval=0.01,
    )

    # Act / Assert
    watcher.start()
    watcher.start()  # no-op
    watcher.stop()
    watcher.stop()  # no-op
