# coding=utf-8
"""NewsAnalyzer 集成测试 — 去 self.ctx 缓存、每周期 ConfigStore.get()（设计 §4.2、§6）。

NewsAnalyzer.__init__ 重（建 storage、打印），故用 __new__ 跳过构造，仅测
_refresh_derived(ctx) 的派生值刷新语义。覆盖：
  - 6 个派生属性从 ctx 读
  - 重复调用用新 ctx 更新（proxy toggle、request_interval）
  - data_fetcher 每次重建（H1：改 USE_PROXY/DEFAULT_PROXY/PLATFORMS_API_URL 下周期生效）
  - storage_manager = ctx.get_storage_manager()（全局单例，id 稳定）
"""

from __future__ import annotations

import pytest

from trendradar.__main__ import NewsAnalyzer
from trendradar.crawler import DataFetcher


class _StubCtx:
    """最小 AppContext 替身：暴露 _refresh_derived 用到的接口。"""

    def __init__(self, config: dict, rank_threshold: int, storage: object):
        self.config = config
        self.rank_threshold = rank_threshold
        self._storage = storage

    def get_storage_manager(self) -> object:
        return self._storage


def _make_analyzer() -> NewsAnalyzer:
    """绕过 __init__（避免 storage/打印副作用），仅设 _refresh_derived 依赖的属性。"""
    a = NewsAnalyzer.__new__(NewsAnalyzer)
    a.is_github_actions = False
    a.is_docker_container = False
    a.update_info = None
    a.frequency_file = None
    a.filter_method = None
    a.interests_file = None
    return a


def test_refresh_derived_reads_six_attrs_from_ctx():
    """_refresh_derived 把 6 个派生属性从 ctx 读到 self。"""
    # Arrange
    storage = object()
    ctx = _StubCtx(
        config={
            "REQUEST_INTERVAL": 1234,
            "REPORT_MODE": "incremental",
            "USE_PROXY": False,
            "DEFAULT_PROXY": "http://proxy:8888",
            "PLATFORMS_API_URL": "http://api.example.com",
        },
        rank_threshold=42,
        storage=storage,
    )
    a = _make_analyzer()

    # Act
    a._refresh_derived(ctx)

    # Assert
    assert a.request_interval == 1234
    assert a.report_mode == "incremental"
    assert a.rank_threshold == 42
    assert a.proxy_url is None  # USE_PROXY=False
    assert isinstance(a.data_fetcher, DataFetcher)
    assert a.storage_manager is storage


def test_refresh_derived_proxy_toggle_between_cycles():
    """跨周期 USE_PROXY 切换 → proxy_url 随新 ctx 变化（H1）。"""
    # Arrange
    storage = object()
    a = _make_analyzer()
    ctx_off = _StubCtx(
        config={
            "REQUEST_INTERVAL": 100,
            "REPORT_MODE": "daily",
            "USE_PROXY": False,
            "DEFAULT_PROXY": "http://p:1",
            "PLATFORMS_API_URL": "",
        },
        rank_threshold=10,
        storage=storage,
    )
    ctx_on = _StubCtx(
        config={
            "REQUEST_INTERVAL": 200,
            "REPORT_MODE": "daily",
            "USE_PROXY": True,
            "DEFAULT_PROXY": "http://p:2",
            "PLATFORMS_API_URL": "",
        },
        rank_threshold=20,
        storage=storage,
    )

    # Act / Assert：第一周期 proxy off
    a._refresh_derived(ctx_off)
    assert a.proxy_url is None
    assert a.request_interval == 100
    # 第二周期 proxy on（reload 后新 ctx）
    a._refresh_derived(ctx_on)
    assert a.proxy_url == "http://p:2"
    assert a.request_interval == 200
    assert a.rank_threshold == 20


def test_data_fetcher_rebuilt_each_cycle():
    """data_fetcher 每周期新实例（非缓存，否则 proxy/api_url 改不生效）。"""
    # Arrange
    storage = object()
    ctx = _StubCtx(
        config={
            "REQUEST_INTERVAL": 100,
            "REPORT_MODE": "daily",
            "USE_PROXY": False,
            "DEFAULT_PROXY": "",
            "PLATFORMS_API_URL": "http://api.x",
        },
        rank_threshold=5,
        storage=storage,
    )
    a = _make_analyzer()

    # Act
    a._refresh_derived(ctx)
    first = a.data_fetcher
    a._refresh_derived(ctx)
    second = a.data_fetcher

    # Assert：新实例（每次重建）
    assert first is not second


def test_storage_manager_identity_stable_across_reload():
    """storage_manager 走全局单例：reload（新 ctx）后仍是同一对象（STORAGE.* 不重建）。"""
    # Arrange：ctx.get_storage_manager() 恒返回同一 storage（模拟模块级全局单例）
    storage = object()
    ctx_a = _StubCtx(
        config={
            "REQUEST_INTERVAL": 1,
            "REPORT_MODE": "daily",
            "USE_PROXY": False,
            "DEFAULT_PROXY": "",
            "PLATFORMS_API_URL": "",
        },
        rank_threshold=1,
        storage=storage,
    )
    ctx_b = _StubCtx(
        config=dict(ctx_a.config),
        rank_threshold=2,
        storage=storage,  # 同一单例
    )
    a = _make_analyzer()

    # Act
    a._refresh_derived(ctx_a)
    first = a.storage_manager
    a._refresh_derived(ctx_b)
    second = a.storage_manager

    # Assert：id 不变（全局单例，reload 不重建）
    assert first is second is storage


def test_ctx_property_returns_current_snapshot():
    """ctx 属性返回 _refresh_derived 设置的当前快照（per-cycle 不变，reload 换新）。"""
    # Arrange
    storage = object()
    ctx = _StubCtx(
        config={
            "REQUEST_INTERVAL": 1,
            "REPORT_MODE": "daily",
            "USE_PROXY": False,
            "DEFAULT_PROXY": "",
            "PLATFORMS_API_URL": "",
        },
        rank_threshold=1,
        storage=storage,
    )
    a = _make_analyzer()

    # Act
    a._refresh_derived(ctx)

    # Assert
    assert a.ctx is ctx


# ---------------------------------------------------------------------------
# G1b — serve 调度循环（scheduler.resolve().collect 门控 run()）
# ---------------------------------------------------------------------------

import threading
from types import SimpleNamespace


class _StubStore:
    """最小 ConfigStore 替身：get() 恒返回同一 ctx（reload 行为由它测不涉及）。"""

    def __init__(self, ctx):
        self._ctx = ctx

    def get(self):
        return self._ctx


def _serve_ctx(collect: bool, config: dict | None = None) -> _StubCtx:
    """带 create_scheduler 的 stub ctx：resolve() 返回 collect 可控的 schedule。"""
    ctx = _StubCtx(
        config=config or {
            "REQUEST_INTERVAL": 100,
            "REPORT_MODE": "daily",
            "USE_PROXY": False,
            "DEFAULT_PROXY": "",
            "PLATFORMS_API_URL": "",
        },
        rank_threshold=1,
        storage=object(),
    )
    schedule = SimpleNamespace(collect=collect)
    ctx.create_scheduler = lambda: SimpleNamespace(resolve=lambda: schedule)
    return ctx


def _run_serve_in_thread(analyzer, *, stop_event, sleep_func, poll_interval=0.01):
    """跑 serve 到 stop（sleep_func 内驱动 stop），join 返回。"""
    thread = threading.Thread(
        target=analyzer.serve,
        kwargs=dict(
            poll_interval=poll_interval,
            stop_event=stop_event,
            sleep_func=sleep_func,
        ),
        daemon=True,
    )
    thread.start()
    thread.join(timeout=10)
    return thread


def test_serve_runs_cycle_when_collect_true(monkeypatch):
    """serve：schedule.collect=True → 调用一次 run()（命中调度窗口）。"""
    # Arrange
    a = _make_analyzer()
    ctx = _serve_ctx(collect=True)
    a.store = _StubStore(ctx)
    runs = []
    monkeypatch.setattr(a, "run", lambda: runs.append(1))
    stop = threading.Event()

    def sleep_func(_s):
        stop.set()  # 第一个 tick 后停

    # Act
    _run_serve_in_thread(a, stop_event=stop, sleep_func=sleep_func)

    # Assert
    assert runs == [1]


def test_serve_skips_cycle_when_collect_false(monkeypatch, capsys):
    """serve：schedule.collect=False → 不调 run()，仅日志跳过。"""
    # Arrange
    a = _make_analyzer()
    ctx = _serve_ctx(collect=False)
    a.store = _StubStore(ctx)
    runs = []
    monkeypatch.setattr(a, "run", lambda: runs.append(1))
    stop = threading.Event()

    def sleep_func(_s):
        stop.set()

    # Act
    _run_serve_in_thread(a, stop_event=stop, sleep_func=sleep_func)

    # Assert
    assert runs == []
    out = capsys.readouterr().out
    assert "不执行" in out or "跳过" in out


def test_serve_polls_repeatedly_until_stopped(monkeypatch):
    """serve：多个 tick 循环，collect 切换 → 命中 tick 调 run()，stop 后退出。"""
    # Arrange
    a = _make_analyzer()
    ctx = _serve_ctx(collect=True)
    a.store = _StubStore(ctx)
    runs = []
    monkeypatch.setattr(a, "run", lambda: runs.append(1))
    stop = threading.Event()
    ticks = []

    def sleep_func(_s):
        ticks.append(1)
        if len(ticks) >= 3:
            stop.set()

    # Act：循环 ≥3 tick（每次 collect=True）
    _run_serve_in_thread(a, stop_event=stop, sleep_func=sleep_func)

    # Assert：每 tick 命中都 run()，≥3 次
    assert len(runs) >= 3


# ---------------------------------------------------------------------------
# G1c — main() serve 模式装配（纯 helper：路径解析 + admin env）
# ---------------------------------------------------------------------------

from trendradar.__main__ import _read_admin_env, _resolve_config_paths


def test_resolve_config_paths_default(monkeypatch):
    """默认：CONFIG_PATH 环境变量或 config/config.yaml；config_dir=config。"""
    # Arrange
    monkeypatch.delenv("CONFIG_PATH", raising=False)

    # Act
    path, config_dir, paths = _resolve_config_paths()

    # Assert
    assert path == "config/config.yaml"
    assert config_dir == "config"
    assert paths == ["config/config.yaml", "config/frequency_words.txt", "config/timeline.yaml"]


def test_resolve_config_paths_custom(monkeypatch):
    """自定义 config_path → config_dir 与三文件路径随之解析。"""
    # Arrange
    monkeypatch.setenv("CONFIG_PATH", "/etc/trendradar/config.yaml")

    # Act
    path, config_dir, paths = _resolve_config_paths()

    # Assert
    assert path == "/etc/trendradar/config.yaml"
    assert config_dir == "/etc/trendradar"
    assert paths == [
        "/etc/trendradar/config.yaml",
        "/etc/trendradar/frequency_words.txt",
        "/etc/trendradar/timeline.yaml",
    ]


def test_read_admin_env_defaults(monkeypatch):
    """默认：enabled=true，host=127.0.0.1，port=8080。"""
    # Arrange
    for k in ("ADMIN_ENABLED", "ADMIN_HOST", "WEBSERVER_PORT"):
        monkeypatch.delenv(k, raising=False)

    # Act
    enabled, host, port = _read_admin_env()

    # Assert
    assert enabled is True
    assert host == "127.0.0.1"
    assert port == 8080


def test_read_admin_env_override_and_disable(monkeypatch):
    """env 覆盖：ADMIN_ENABLED=false → 关闭；host/port 可配。"""
    # Arrange
    monkeypatch.setenv("ADMIN_ENABLED", "false")
    monkeypatch.setenv("ADMIN_HOST", "0.0.0.0")
    monkeypatch.setenv("WEBSERVER_PORT", "9090")

    # Act
    enabled, host, port = _read_admin_env()

    # Assert
    assert enabled is False
    assert host == "0.0.0.0"
    assert port == 9090
