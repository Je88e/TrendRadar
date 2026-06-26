# coding=utf-8
"""
server — 调度器进程内嵌的 Starlette admin app。

路由（设计 §4.1 / §3）：
  GET  /api/config/<file>      → 原文 + ETag 头
  PUT  /api/config/<file>      → staging 校验 → 原子写（threading.Lock 串行化，
                                  关闭 writer 的 TOCTOU 窗口）→ 200
                                  校验失败 422 / ETag 失配 409 / 文件缺失 404
  GET  /api/config/effective   → store.get().config 归一化字典（只读）
  StaticFiles(/admin/)          → trendradar/admin/static/index.html（编辑器）
  StaticFiles(/html/)           → output/html（归档报告）
  StaticFiles(/)                → output/（报告首页，output/index.html）

路径穿越守卫：<file> 必须在白名单（admin 的 HTTP 写盘面，拒绝 `..` / 绝对 /
非配置文件名 → 400）。

run_admin 为 daemon 线程启动器：线程内禁用 uvicorn 信号处理
（install_signal_handlers=lambda:None），否则非主线程注册信号抛 ValueError；
启动异常（端口占用）try/except 吞错 + 日志，不拖垮调度器。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from trendradar.admin.validators import validate_config_text
from trendradar.admin.writer import (
    ETagMismatch,
    atomic_write_with_backup,
    compute_etag,
)

# 编辑器可写的三份配置文件（路径穿越白名单）
ALLOWED_CONFIG_FILES = frozenset(
    {"config.yaml", "frequency_words.txt", "timeline.yaml"}
)


def resolve_config_path(filename: str, config_dir: str) -> Optional[Path]:
    """白名单守卫：仅允许三份配置文件名，返回 config_dir/<name>，否则 None。

    白名单名为固定字面量、无路径分隔符，``config_dir/<name>`` 不可能逃逸，
    故无需 resolve 校验即可保证路径不穿越。``..`` / 绝对路径 / 含 ``/`` 的名
    一律不在白名单 → None（admin 写盘面不得逃出 config_dir）。
    """
    if filename not in ALLOWED_CONFIG_FILES:
        return None
    return Path(config_dir) / filename


def _get_config(filename: str, config_dir: str) -> Response:
    """GET：返回原文 + ETag 头。文件缺失 → 404（compute_etag 抛 FileNotFoundError，债务 #2）。"""
    path = resolve_config_path(filename, config_dir)
    try:
        etag = compute_etag(str(path))
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Response("配置文件不存在", status_code=404)
    return Response(text, media_type="text/plain", headers={"etag": etag})


async def _put_config(
    request: Request, filename: str, config_dir: str, write_lock: threading.Lock
) -> Response:
    """PUT：校验 → 原子写（write_lock 串行化，关闭 writer TOCTOU 窗口，债务 #1）。

    - 校验失败（load_config oracle 抛错）→ 422（不落盘、不备份）
    - ETag 失配（ETagMismatch）→ 409
    - 文件缺失（FileNotFoundError）→ 404（债务 #2）
    - 成功 → 200

    watcher 轮询 mtime 会在后续触发 reload，PUT 不同步 reload（设计 Q2）。
    """
    path = resolve_config_path(filename, config_dir)
    body = (await request.body()).decode("utf-8")
    if_match = request.headers.get("if-match")

    with write_lock:
        result = validate_config_text(filename, body, config_dir=config_dir)
        if not result.ok:
            return Response(
                status_code=422,
                content="配置校验失败:\n" + "\n".join(result.errors),
                media_type="text/plain",
            )
        try:
            atomic_write_with_backup(str(path), body, if_match)
        except ETagMismatch:
            return Response(
                "ETag 失配: 配置已被他人修改，请重新加载", status_code=409
            )
        except FileNotFoundError:
            return Response("配置文件不存在", status_code=404)
    return Response(status_code=200)


def create_app(
    store,
    config_dir: str,
    *,
    static_dir: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Starlette:
    """构造 admin app。store = ConfigStore（或测试替身）；config_dir = 配置目录。

    PUT 校验→写→（watcher 轮询触发 reload）包在 _write_lock 内串行化，关闭
    atomic_write_with_backup 的 TOCTOU 窗口（设计 §6 test_server，Slice D 债务 #1）。

    output_dir 非 None（serve 模式）时路由布局：
      /        → output_dir（报告首页 output/index.html）
      /html/   → output_dir/html（归档报告）
      /admin/  → static_dir（编辑器）
      /api/... → 配置读写（不变）
    output_dir 为 None 时（向后兼容）：
      /        → static_dir（编辑器）
      /api/... → 配置读写
    """
    write_lock = threading.Lock()

    async def effective(_request: Request) -> Response:
        """GET /api/config/effective：返回 store.get().config 归一化字典（只读，调试用）。

        config 可能含非 JSON 类型（如 PINNED_KEYWORDS 为 set），先经
        ``json.dumps(default=list)`` 归一化（set → list）再回灌，避免 500。
        """
        cfg = getattr(store.get(), "config", {})
        return JSONResponse(json.loads(json.dumps(cfg, default=list)))

    async def config_file(request: Request) -> Response:
        filename = request.path_params["filename"]
        if resolve_config_path(filename, config_dir) is None:
            return Response("非法配置文件名", status_code=400)
        method = request.method
        if method == "GET":
            return _get_config(filename, config_dir)
        if method == "PUT":
            return await _put_config(request, filename, config_dir, write_lock)
        return Response(status_code=405)

    routes = [
        Route("/api/config/effective", effective, methods=["GET"]),
        Route("/api/config/{filename}", config_file, methods=["GET", "PUT"]),
    ]

    if output_dir is not None:
        # serve 模式：报告首页 / → output_dir，编辑器 /admin/ → static_dir
        # 注意：必须带尾斜杠 /admin/（相对路径 assets/script.js 依赖此前缀）
        reports_html = str(Path(output_dir) / "html")
        if static_dir is not None:
            # /admin（无尾斜杠）→ 307 → /admin/：编辑器内部仍落 /admin/ 前缀，
            # 仅消除用户漏输斜杠的 404 摩擦（路由顺序：redirect 先于 Mount 注册）
            routes.append(
                Route(
                    "/admin",
                    lambda _req: RedirectResponse(url="/admin/", status_code=307),
                    methods=["GET"],
                )
            )
            routes.append(
                Mount("/admin/", app=StaticFiles(directory=static_dir, html=True))
            )
        routes.append(
            Mount("/html/", app=StaticFiles(directory=reports_html, html=True))
        )
        routes.append(
            Mount("/", app=StaticFiles(directory=output_dir, html=True))
        )
    elif static_dir is not None:
        # 无 output_dir：编辑器挂 /（向后兼容）
        routes.append(Mount("/", app=StaticFiles(directory=static_dir, html=True)))

    app = Starlette(routes=routes)
    app.state.store = store
    app.state.config_dir = config_dir
    app.state.write_lock = write_lock
    return app


def _build_server(app: Starlette, host: str, port: int) -> uvicorn.Server:
    """构造 uvicorn Server 并禁用信号处理（daemon 线程内注册信号抛 ValueError）。

    design §4.1/§9：非主线程调 ``signal.signal`` 抛 ``ValueError: signal only
    works in main thread``；置 ``install_signal_handlers`` 为 no-op 规避。
    """
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
    return server


def _serve(app: Starlette, host: str, port: int) -> None:
    """daemon 线程目标：运行 uvicorn，启动异常吞错 + 日志（不拖垮调度器）。"""
    server = _build_server(app, host, port)
    try:
        server.run()
    except Exception as e:  # noqa: BLE001 — 端口占用/绑定失败等，admin 缺席调度照常跑
        print(f"[admin] 后台启动失败（调度器继续）: {e}")


def run_admin(
    host: str,
    port: int,
    store,
    *,
    config_dir: str,
    static_dir: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> threading.Thread:
    """启动 admin 为 daemon 线程并返回该线程（非阻塞）。

    默认 static_dir = 包内 trendradar/admin/static（随发布的编辑器资源）。
    output_dir 非 None 时：/ → 报告首页，/html/ → 归档报告，/admin/ → 编辑器。
    """
    if static_dir is None:
        static_dir = str(Path(__file__).resolve().parent / "static")
    app = create_app(
        store, config_dir, static_dir=static_dir, output_dir=output_dir
    )
    thread = threading.Thread(
        target=_serve,
        args=(app, host, port),
        name="trendradar-admin",
        daemon=True,
    )
    thread.start()
    return thread
