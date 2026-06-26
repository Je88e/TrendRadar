# coding=utf-8
"""server.py 测试 — Starlette admin app（设计 §4.1、§6 test_server / test_server_uvicorn）。

路由：
  GET  /api/config/<file>      → 原文 + ETag
  PUT  /api/config/<file>      → staging 校验 → 原子写（threading.Lock 串行化）→ 200
                                  校验失败 422 / ETag 失配 409 / 文件缺失 404
  GET  /api/config/effective   → store.get().config 归一化字典（只读）
  StaticFiles(/)               → trendradar/admin/static/index.html

路径穿越守卫：非白名单文件名 / `..` / 绝对路径 → 400（admin 的 HTTP 写盘面）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from trendradar.admin.server import (
    ALLOWED_CONFIG_FILES,
    create_app,
    resolve_config_path,
)


class _StubStore:
    """最小 store 替身：持一个 .config dict，供 effective 路由读。"""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {"REPORT": {"mode": "daily"}}

    def get(self) -> "_StubStore":
        return self


@pytest.fixture()
def app(tmp_path: Path):
    return create_app(store=_StubStore(), config_dir=str(tmp_path))


@pytest.fixture()
def client(app):
    return TestClient(app)


# ---------------------------------------------------------------------------
# E1 — 路径穿越守卫
# ---------------------------------------------------------------------------


def test_get_unknown_filename_rejected_400(client):
    """非白名单文件名 → 400（不泄露是否存在）。"""
    # Act
    resp = client.get("/api/config/evil.yaml")

    # Assert
    assert resp.status_code == 400


def test_resolve_rejects_traversal(tmp_path):
    """resolve_config_path 对穿越/绝对/非白名单名返回 None；白名单返回 config_dir 下路径。

    `..` / 绝对路径 / 含分隔符 / 非配置名一律拒绝 —— admin 写盘面不得逃出 config_dir。
    """
    # Act / Assert
    for bad in ("..", ".", "../secret", "/etc/passwd", "sub/config.yaml",
                "config.yaml/.", "evil.yaml", ""):
        assert resolve_config_path(bad, str(tmp_path)) is None, bad

    # 白名单 → 恰好 config_dir/<name>（不逃逸）
    for name in ALLOWED_CONFIG_FILES:
        resolved = resolve_config_path(name, str(tmp_path))
        assert resolved == tmp_path / name


def test_allowed_filenames_constant():
    """白名单恰好为三份配置文件。"""
    # Assert
    assert ALLOWED_CONFIG_FILES == frozenset(
        {"config.yaml", "frequency_words.txt", "timeline.yaml"}
    )


# ---------------------------------------------------------------------------
# E2 — GET raw + ETag
# ---------------------------------------------------------------------------


def test_get_returns_raw_text_and_etag(tmp_path):
    """GET /api/config/config.yaml → 原文字节 + ETag=sha256(bytes) 头。"""
    # Arrange
    content = "# comment\nREPORT:\n  mode: daily\n"
    (tmp_path / "config.yaml").write_text(content, encoding="utf-8")
    app = create_app(store=_StubStore(), config_dir=str(tmp_path))
    client = TestClient(app)
    from trendradar.admin.writer import compute_etag

    expected_etag = compute_etag(str(tmp_path / "config.yaml"))

    # Act
    resp = client.get("/api/config/config.yaml")

    # Assert
    assert resp.status_code == 200
    assert resp.text == content
    assert resp.headers["etag"] == expected_etag


def test_get_missing_file_returns_404(tmp_path):
    """GET 白名单但文件不存在 → 404（compute_etag 抛 FileNotFoundError，债务 #2）。"""
    # Arrange
    app = create_app(store=_StubStore(), config_dir=str(tmp_path))
    client = TestClient(app)

    # Act
    resp = client.get("/api/config/config.yaml")

    # Assert
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# E3 — PUT 校验失败 422（且不落盘）
# ---------------------------------------------------------------------------


def test_put_validate_fail_returns_422_and_no_write(config_dir_with_files):
    """PUT 非法 YAML → 422，原文件不变，无备份产生。"""
    # Arrange
    config_dir = config_dir_with_files
    app = create_app(store=_StubStore(), config_dir=str(config_dir))
    client = TestClient(app)
    original = (config_dir / "config.yaml").read_text(encoding="utf-8")
    from trendradar.admin.writer import compute_etag

    etag = compute_etag(str(config_dir / "config.yaml"))

    # Act：YAML 语法错（冒号不闭合的 mapping 值）
    resp = client.put(
        "/api/config/config.yaml",
        content="REPORT: [unclosed\n",
        headers={"If-Match": etag},
    )

    # Assert
    assert resp.status_code == 422
    assert (config_dir / "config.yaml").read_text(encoding="utf-8") == original
    backup_dir = config_dir / ".backups"
    assert not backup_dir.exists() or list(backup_dir.glob("*")) == []


# ---------------------------------------------------------------------------
# E4 — PUT 成功 200 + 落盘
# ---------------------------------------------------------------------------


def test_put_success_returns_200_and_writes(config_dir_with_files):
    """PUT 合法内容 + 正确 If-Match → 200，文件更新为新内容。"""
    # Arrange
    config_dir = config_dir_with_files
    app = create_app(store=_StubStore(), config_dir=str(config_dir))
    client = TestClient(app)
    from trendradar.admin.writer import compute_etag

    original = (config_dir / "config.yaml").read_text(encoding="utf-8")
    etag = compute_etag(str(config_dir / "config.yaml"))
    new_body = original + "\n# 在线后台追加注释\n"  # 合法 YAML（注释）

    # Act
    resp = client.put(
        "/api/config/config.yaml",
        content=new_body,
        headers={"If-Match": etag},
    )

    # Assert
    assert resp.status_code == 200
    assert (config_dir / "config.yaml").read_text(encoding="utf-8") == new_body


# ---------------------------------------------------------------------------
# E5 — PUT ETag 失配 409 / 文件缺失 404
# ---------------------------------------------------------------------------


def test_put_stale_etag_returns_409(config_dir_with_files):
    """PUT 过期 If-Match → 409，原文件不变。"""
    # Arrange
    config_dir = config_dir_with_files
    app = create_app(store=_StubStore(), config_dir=str(config_dir))
    client = TestClient(app)
    original = (config_dir / "config.yaml").read_text(encoding="utf-8")
    new_body = original + "\n# stale edit\n"

    # Act：If-Match 为过期值
    resp = client.put(
        "/api/config/config.yaml",
        content=new_body,
        headers={"If-Match": "stale-etag"},
    )

    # Assert
    assert resp.status_code == 409
    assert (config_dir / "config.yaml").read_text(encoding="utf-8") == original


def test_put_missing_file_returns_404(real_config_dir):
    """PUT 到不存在的 config.yaml → 404（校验通过后 atomic_write 抛 FileNotFoundError）。"""
    # Arrange：real_config_dir 有 sibling 但无 config.yaml
    config_dir = real_config_dir
    app = create_app(store=_StubStore(), config_dir=str(config_dir))
    client = TestClient(app)
    repo_config = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
    valid_body = repo_config.read_text(encoding="utf-8")

    # Act
    resp = client.put(
        "/api/config/config.yaml",
        content=valid_body,
        headers={"If-Match": "anything"},
    )

    # Assert
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# E6 — GET /api/config/effective（归一化字典，只读）
# ---------------------------------------------------------------------------


def test_get_effective_returns_normalized_config(tmp_path):
    """GET /api/config/effective → store.get().config 的 JSON 归一化字典。"""
    # Arrange
    config = {"REPORT": {"mode": "daily"}, "RANK_THRESHOLD": 30}
    app = create_app(store=_StubStore(config=config), config_dir=str(tmp_path))
    client = TestClient(app)

    # Act
    resp = client.get("/api/config/effective")

    # Assert
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == config


def test_get_effective_serializes_set_value(tmp_path):
    """config 含 set（如 PINNED_KEYWORDS）→ 归一化为 list，不抛 500。

    回归：JSONResponse 不支持 set，原实现直接传 set 值的 dict 触发
    ``TypeError: Object of type set is not JSON serializable``。
    """
    # Arrange
    config = {"REPORT": {"mode": "daily"}, "PINNED_KEYWORDS": {"AI", "芯片"}}
    app = create_app(store=_StubStore(config=config), config_dir=str(tmp_path))
    client = TestClient(app)

    # Act
    resp = client.get("/api/config/effective")

    # Assert
    assert resp.status_code == 200
    body = resp.json()
    assert sorted(body["PINNED_KEYWORDS"]) == ["AI", "芯片"]


# ---------------------------------------------------------------------------
# E7 — StaticFiles 挂载 /（编辑器静态资源）
# ---------------------------------------------------------------------------


def test_static_files_serves_index(tmp_path):
    """GET / → static_dir/index.html（html=True 自动落 index）。"""
    # Arrange
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text(
        "<!doctype html><html><body>admin editor</body></html>",
        encoding="utf-8",
    )
    app = create_app(
        store=_StubStore(), config_dir=str(tmp_path), static_dir=str(static)
    )
    client = TestClient(app)

    # Act
    resp = client.get("/")

    # Assert
    assert resp.status_code == 200
    assert "admin editor" in resp.text


def test_static_files_serves_asset(tmp_path):
    """GET /assets/style.css → 静态资源（编辑器 assets 子目录）。"""
    # Arrange
    static = tmp_path / "static"
    assets = static / "assets"
    assets.mkdir(parents=True)
    (static / "index.html").write_text("idx", encoding="utf-8")
    (assets / "style.css").write_text("body { margin: 0; }", encoding="utf-8")
    app = create_app(
        store=_StubStore(), config_dir=str(tmp_path), static_dir=str(static)
    )
    client = TestClient(app)

    # Act
    resp = client.get("/assets/style.css")

    # Assert
    assert resp.status_code == 200
    assert "margin" in resp.text


# ---------------------------------------------------------------------------
# E8 — serve 模式路由：/ → 报告首页，/admin/ → 编辑器，/html/ → 归档报告
# ---------------------------------------------------------------------------


def test_serve_mode_routes_reports_and_admin(tmp_path):
    """output_dir 非 None → / → output/index.html，/admin/ → 编辑器，/html/ → 归档。"""
    # Arrange
    output = tmp_path / "output"
    output.mkdir()
    (output / "index.html").write_text("<h1>report index</h1>", encoding="utf-8")
    html_dir = output / "html"
    html_dir.mkdir()
    (html_dir / "index.html").write_text("<h1>archived reports</h1>", encoding="utf-8")
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("admin editor", encoding="utf-8")

    app = create_app(
        store=_StubStore(), config_dir=str(tmp_path),
        static_dir=str(static), output_dir=str(output),
    )
    client = TestClient(app, follow_redirects=True)

    # Act / Assert: / → 报告首页
    resp = client.get("/")
    assert resp.status_code == 200
    assert "report index" in resp.text

    # Act / Assert: /admin/ → 编辑器
    resp = client.get("/admin/")
    assert resp.status_code == 200
    assert "admin editor" in resp.text

    # Act / Assert: /admin（无尾斜杠）→ 307 → /admin/（消除漏输斜杠的 404 摩擦）
    # 编辑器内部仍落 /admin/ 前缀；redirect 仅修正入口，不改前缀语义
    no_redirect_client = TestClient(app, follow_redirects=False)
    resp_admin_no_slash = no_redirect_client.get("/admin")
    assert resp_admin_no_slash.status_code == 307
    assert resp_admin_no_slash.headers["location"] == "/admin/"

    # Act / Assert: /html/ → 归档报告
    resp = client.get("/html/")
    assert resp.status_code == 200
    assert "archived reports" in resp.text


def test_no_output_dir_serves_admin_at_root(tmp_path):
    """output_dir 未传 → / 仍是编辑器（向后兼容）。"""
    # Arrange
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("admin editor", encoding="utf-8")
    app = create_app(
        store=_StubStore(), config_dir=str(tmp_path), static_dir=str(static),
    )
    client = TestClient(app)

    # Act: / → 编辑器（无 output_dir 时）
    resp = client.get("/")
    assert resp.status_code == 200
    assert "admin editor" in resp.text

    # Act: /admin/ → 404（output_dir 未设置，/admin/ 路由未注册）
    resp = client.get("/admin/")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# F1 — run_admin daemon 线程（禁信号处理 + 端口占用吞错）
# ---------------------------------------------------------------------------


def test_build_server_disables_signal_handlers_in_worker_thread(tmp_path):
    """_build_server 后 install_signal_handlers 在非主线程可调用（lambda:None，无 ValueError）。"""
    # Arrange
    import threading as _t

    import trendradar.admin.server as srv

    app = create_app(store=_StubStore(), config_dir=str(tmp_path))
    server = srv._build_server(app, "127.0.0.1", 0)

    err: dict[str, BaseException] = {}

    def call() -> None:
        try:
            server.install_signal_handlers()
        except BaseException as e:  # noqa: BLE001
            err["e"] = e

    # Act
    worker = _t.Thread(target=call)
    worker.start()
    worker.join(timeout=5)

    # Assert：非主线程调用不抛 ValueError: signal only works in main thread
    assert "e" not in err, err


def test_serve_swallows_startup_error(monkeypatch, tmp_path, capsys):
    """_serve：uvicorn 启动异常（端口占用等）被 try/except 吞，不抛回，仅日志。"""
    # Arrange
    import uvicorn

    import trendradar.admin.server as srv

    def boom(self: object) -> None:
        raise OSError("[Errno 98] Address already in use")

    monkeypatch.setattr(uvicorn.Server, "run", boom)
    app = create_app(store=_StubStore(), config_dir=str(tmp_path))

    # Act：不应抛出
    srv._serve(app, "127.0.0.1", 9999)

    # Assert：异常被吞并打印（调度器继续，admin 是便利层）
    out = capsys.readouterr().out
    assert "失败" in out
    assert "Address already in use" in out


def test_run_admin_returns_daemon_thread(monkeypatch, tmp_path):
    """run_admin 返回 daemon 线程（_serve 被 mock 为 no-op，验证线程语义不触网）。"""
    # Arrange
    import trendradar.admin.server as srv

    monkeypatch.setattr(srv, "_serve", lambda *a, **k: None)

    # Act
    thread = srv.run_admin(
        "127.0.0.1", 8080, _StubStore(), config_dir=str(tmp_path)
    )

    # Assert
    assert thread.daemon is True
    thread.join(timeout=5)
    assert not thread.is_alive()
