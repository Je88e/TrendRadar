# 在线配置管理后台设计方案

> 状态：设计完成，待实现（TDD）
> 相关：[CONTEXT.md](../CONTEXT.md)、[ADR-0004](adr/0004-online-config-admin.md)
> 版本目标：6.11.x
> Grill 记录：10 轮问答，决策见 §2

## 1. 目标

把现有 `docs/index.html`（纯客户端 YAML 编辑器，仅能从 GitHub raw 拉取 + 复制粘贴）改造成**在线配置后台**：服务运行时可通过浏览器访问，编辑 `config.yaml` / `frequency_words.txt` / `timeline.yaml`，**保存即生效**（无需重启），且保留原始 YAML 注释与格式。

**非目标**：
- 不做用户体系 / 权限分级（默认 localhost 仅本机访问，远端暴露由用户自行加反向代理鉴权，见 Q5=C）。
- 不替换 MCP server（MCP 进程保持只读 `config_mgmt`，与本后台解耦）。
- 不改 `config.yaml` 的 schema（仅新增管理后台相关 env：`ADMIN_ENABLED` / `ADMIN_HOST` / `ADMIN_PORT`）。
- 不改 `frequency_words.txt` 语法。
- 不做配置版本分发（多实例间同步配置超出本期范围）。

## 2. 关键决策（详见 ADR-0004 + 本文档 grill 记录）

| # | 决策 | 选择 |
|---|---|---|
| Q1 | 托管进程 | HTTP 后台**嵌入调度器进程**（`python -m trendradar`），非 MCP 进程、非新进程 |
| Q2 | 重载触发 | **文件轮询（mtime 变化 + debounce）**，非 PUT 同步、非原生 FS 事件 |
| Q3 | 重载范围 | **整体重建 `AppContext`**，旧实例 drain（在飞周期跑完再 GC），非增量 diff |
| Q4 | 写入粒度 | **整文件原样写入**（编辑器权威，服务端不做 `yaml.safe_dump`），保注释；staging 校验 + 备份 + ETag |
| Q5 | 鉴权 | **默认 localhost 无鉴权**；`ADMIN_HOST=0.0.0.0` 远端暴露由用户自担风险（反代/隧道加鉴权） |
| Q6 | 并发模型 | HTTP + 文件轮询各跑 **daemon 线程**；`ConfigStore` 持当前 `AppContext`，加锁原子换 |
| Q7 | 编辑数据面 | 编辑器编辑**原始文件字符串**；`/api/config/effective` 只读返回归一化字典；保留「加载官网最新配置」按钮 |
| Q8 | 校验深度 | **以 `load_config()` 干跑为 oracle**：YAML 语法 + schema 占位 + loader 实跑 staging 路径，捕获异常与静默强转告警 |
| Q9 | 框架/端口/开关 | **Starlette + uvicorn**（复用 fastmcp 传递依赖），端口 **8080**（env 可配），**默认开启 localhost** |
| Q10 | 编辑器文件位置 | **迁入 `trendradar/admin/static/`**（随包发布），`docs/` 回归纯仓库文档 |

**补充确认项**（非 fork，spec）：
- `frequency_words.txt` / `timeline.yaml` 走同一 GET/PUT 模式；校验 = staging 干跑（`load_frequency_words` / YAML 解析 + `Scheduler` 构造）。
- 现有 MCP `config_mgmt.get_current_config`（只读）**保持不动**，文件即 SoT，二者解耦。**MCP 跨进程陈旧**（见 §10 决议）：MCP 进程 `AppContext` 在其启动时装载，admin 编辑后 MCP 不重读——`get_current_config` 反映 MCP 启动时刻配置，admin 编辑要让 MCP 看到需重启 MCP。
- 编辑器 JS 改造：`fetchWithFallback(REMOTE_*)` → 本地 `/api/...`；`copyResult()` → PUT；localStorage 保留为草稿；可视化面板 / 模块导航 / Tab 不动。
- 无鉴权 UI（Q5=C），无登录页。
- **存储配置不在线生效**：`storage.get_storage_manager()` 是模块级全局单例（首次创建即固定），所有 `AppContext` 共享同一实例。因此 `STORAGE.*`（BACKEND / DATA_DIR / RETENTION_DAYS / REMOTE.*）编辑后**不随 reload 生效，需重启**。admin UI 对存储段标注「需重启生效」。其余配置（平台/RSS/通知/筛选/AI/调度/地区/显示）随 reload 生效。

## 3. 架构与数据流

```
┌─────────────────────────── 调度器进程 (python -m trendradar) ───────────────────────────┐
│                                                                                          │
│  主线程: NewsAnalyzer 调度循环                                                            │
│    每周期开头: ctx = ConfigStore.get()   ← 不再缓存 self.ctx                              │
│    crawl → filter → analyze → render → push（全程用同一 ctx 快照）                         │
│                                                                                          │
│  daemon 线程 1: uvicorn (Starlette)   :8080  127.0.0.1                                   │
│    GET  /api/config/<file>           → 读原始文件 + ETag                                  │
│    PUT  /api/config/<file>           → staging 校验 → 备份 → 原子替换 → 200               │
│    GET  /api/config/effective        → ConfigStore.get().config 归一化字典（只读）          │
│    GET  /api/status                  → {uptime, last_reload, mtime, active_cycle}        │
│    StaticFiles(/)                    → trendradar/admin/static/index.html                │
│                                                                                          │
│  daemon 线程 2: ConfigWatcher (轮询)                                                      │
│    每 2s 检查 config.yaml/timeline.yaml/frequency_words.txt 的 mtime                      │
│    变化 → debounce 1s → 触发 ConfigStore.reload()                                         │
│                                                                                          │
│  ConfigStore (线程安全, threading.RLock)                                                  │
│    _ctx: AppContext          ← 当前生效                                                   │
│    get() → AppContext        ← 主线程每周期取                                              │
│    reload(): 在锁外 build 新 AppContext（load_config + AppContext(config)），锁内换引用     │
│    旧 AppContext 不主动关闭；在飞周期跑完自然 GC（drain）                                   │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘

        ▲ 浏览器 (http://localhost:8080)
        │  editor (static/index.html)
        │   ├─ 「加载服务配置」→ GET /api/config/<file>      （本地后端）
        │   ├─ 「加载官网最新配置」→ fetch GitHub raw         （保留，reset/migrate 用）
        │   └─ 「保存」→ PUT /api/config/<file>               （整文件原样）
        │
        └─ 外部编辑 (vim / git pull / deploy)
              └─ 直接写文件 → ConfigWatcher 轮询发现 → reload
```

**关键不变量**：
- 文件 = 唯一 SoT。所有写入（PUT / vim / git）都落盘，watcher 统一触发重载。
- 编辑器从不直接写文件（浏览器无文件系统能力），必经 PUT。
- `ConfigStore.get()` 返回的 `AppContext` 在调用方生命周期内稳定（reload 换新实例，不就地改）。
- 在飞周期持有旧 `AppContext` 快照跑完，下一周期取新。
- **`storage_manager` 是模块级全局单例**（`storage/manager.py` 的 `_storage_manager`），非 per-AppContext。reload 建新 `AppContext` 但 `get_storage_manager()` 仍返回同一全局实例 → `STORAGE.*` 配置不随 reload 生效，需重启（见 §2）。`_scheduler` / `_region_classifier` / `_region_normalizer` 是 per-AppContext 的纯配置/数据对象，重建廉价且无句柄，drain（GC）安全；`LocalStorageBackend` 有 `__del__`→`cleanup()`，即使 `force_new` 创建多实例也能在 GC 时关连接。

## 4. 实现触点

### 4.1 新增模块

| 文件 | 职责 |
|---|---|
| `trendradar/admin/__init__.py` | 包入口 |
| `trendradar/admin/store.py` | `ConfigStore`：线程安全持有 `AppContext`，`get()` / `reload()` |
| `trendradar/admin/watcher.py` | `ConfigWatcher`：轮询 mtime + debounce，触发 `store.reload()`；原生事件不可靠环境（WSL2/Docker bind-mount）用纯 mtime 轮询，零依赖（不引入 watchdog） |
| `trendradar/admin/server.py` | Starlette app：路由 + StaticFiles 挂载 + uvicorn 启动函数 `run_admin_thread(host, port, store)`。**线程内启动 uvicorn 必须禁用信号处理**：构造 `uvicorn.Config(app, host, port)` → `server = Server(config)` → `server.install_signal_handlers = lambda: None` → `server.run()`。否则非主线程注册 SIGINT/SIGTERM 抛 `ValueError: signal only works in main thread`。启动失败（端口占用等）`try/except` 捕获 + 日志，**不抛回主线程、不拖垮调度器**；admin 缺席调度照常跑 |
| `trendradar/admin/validators.py` | `validate_config_text(name, text)` / `validate_frequency_text` / `validate_timeline_text`：写 staging 路径 → 调 `load_config(quiet=True)` / `load_frequency_words` / YAML 解析 → 收集异常 + 静默强转告警 → 清 staging |
| `trendradar/admin/writer.py` | `atomic_write_with_backup(path, text, etag)`：ETag = **文件字节 sha256 十六进制**（非 mtime——同秒重写在 NTFS / WSL `/mnt/d` 粗粒度 mtime 下碰撞，失配漏检）。`If-Match` 校验失配→409；通过→备份到 `config/.backups/<name>.<ts>.bak`（原子列出 + 删超近 5）→ `tempfile` + `os.replace` 原子替换 |
| `trendradar/admin/static/index.html` | `git mv docs/index.html` 迁入 |
| `trendradar/admin/static/assets/{style.css,script.js,weixin.webp}` | `git mv docs/assets/*` 迁入 |

### 4.2 改造既有

| 文件 | 改动 |
|---|---|
| `trendradar/core/loader.py` | (1) `load_config(config_path=None, quiet=False)`：**显式透传 `quiet` 到各 `_load_*`**（`if not quiet: print(...)`），**不用 `redirect_stdout`**——后者会吞掉第三方库（pyyaml/litellm 等）的正常 stdout，且测试难断言。默认 `quiet=False` = 现行为（向后兼容）。(2) **`STORAGE_RETENTION_DAYS` 环境变量覆盖移入此处**（现错误地在 `NewsAnalyzer.__init__` 就地 mutate config，见 H3）：env 覆盖应在配置归一化层，而非分析器构造期，否则 reload 后 env 覆盖丢失。(3) 可选 `return_warnings=True` 返回 `(config, warnings)`，暴露静默强转（如负 `max_age_days` 纠正为 3）供校验层告警 |
| `trendradar/__main__.py` | `NewsAnalyzer` 去 `__init__` 缓存。经核对 `:65-160`，**实际 6 个配置派生属性**（非 10）：`self.request_interval` / `self.report_mode` / `self.rank_threshold` / `self.proxy_url` / `self.data_fetcher` / `self.storage_manager`（`is_github_actions` / `is_docker_container` / `update_info` 为环境/运行态，保留）。改为持有 `self.store: ConfigStore`，每周期开头 `ctx = self.store.get()` 后取：request_interval / report_mode / rank_threshold / proxy_url 读 `ctx.config[...]`；`storage_manager` = `ctx.get_storage_manager()`（全局单例，周期内稳定）；**`data_fetcher` 必须每周期按当前 `proxy_url` + `ctx.config["PLATFORMS_API_URL"]` 重建**（否则改 `USE_PROXY` / `DEFAULT_PROXY` / `PLATFORMS_API_URL` 不生效，H1）。`STORAGE_RETENTION_DAYS` env 处理移走（见 loader 行，H3） |
| `trendradar/__main__.py`（入口） | 启动时构造 `ConfigStore(initial_ctx)` → 启动 admin 线程（`ADMIN_ENABLED` 默认 true，`ADMIN_HOST` 默认 `127.0.0.1`，`ADMIN_PORT` 默认 8080）→ 启动 watcher 线程 → 进主循环 |
| `docs/assets/script.js`（迁入 static 后） | (1) `fetchWithFallback(REMOTE_CONFIG_URL)` 的「加载服务配置」分支改 fetch `/api/config/config.yaml`（同源，相对路径）；保留「加载官网最新配置」按钮指向 REMOTE_*。(2) `copyResult()` 改 `saveToServer()`：PUT `/api/config/<file>` 带 `If-Match: <etag>`，处理 409（失配提示重载）。(3) 新增 `loadEffective()`（可选调试视图）。localStorage 保留为未保存草稿 |
| `config/config.yaml`（注释） | 顶部加注释说明管理后台 env（`ADMIN_ENABLED` / `ADMIN_HOST` / `ADMIN_PORT`），不新增 YAML 键（后台配置走 env，避免「配置守护配置」循环，见 Q5） |
| `requirements.txt` / `pyproject.toml` | 无新依赖（starlette/uvicorn 经 fastmcp 已传递引入；watcher 用 stdlib 轮询） |
| `start-http.sh` / `start-http.bat` | 注释补充：管理后台默认 `http://localhost:8080`，与 MCP `:3333` 分离；远端访问需自加反代鉴权 |

### 4.3 不动

- `mcp_server/` 全部（MCP 只读 `config_mgmt` 与本后台解耦）。
- `trendradar/core/loader.py` 的配置语义、env 覆盖优先级、`_load_*` 字段映射（仅加 `quiet` 透传）。
- `frequency_words.txt` 语法、`timeline.yaml` schema。
- 报告生成 / 通知 / 爬虫 / AI 全链路（只改 `AppContext` 的获取方式）。

## 5. 校验细节（Q8 展开）

`validate_config_text("config.yaml", text)` 流程：
1. `yaml.safe_load(text)` → 语法错则返回 `{ok: False, errors: ["YAML 语法: ..."]}`。
2. **写 staging 时镜像全部三文件**（B1）：`config/.staging-<pid>/config.yaml`（=被校验文本）+ `config/.staging-<pid>/timeline.yaml`（拷真文件）+ `config/.staging-<pid>/frequency_words.txt`（拷真文件）。仅写 `config.yaml` 会让 `load_config(staging_path)` 按 `staging_path.parent` 解析 sibling，找不到 `.staging/timeline.yaml` → 校验 oracle 失真（或静默回落默认值，假通过）。
3. 调 `load_config(staging_path, quiet=True)`（相对路径在 `.staging-<pid>/` 内有效）：
   - 抛异常 → `{ok: False, errors: [str(e)]}`。
   - 静默强转（如 `max_age_days` 负数纠正）→ 收为 `warnings`（非阻塞）。
4. 删整个 `config/.staging-<pid>/`（`shutil.rmtree`，`finally` 兜底，校验失败不留痕）。
5. 返回 `{ok: True, warnings: [...]}`。

`validate_frequency_text`：纯文本语法（`[组名]` + 关键词行），staging 单文件干跑 `load_frequency_words(staging_path)` 即可（无 sibling 依赖）。

`validate_timeline_text`：`yaml.safe_load` + `Scheduler(timeline_data=...)` 试构造，捕获调度异常（单文件，无 sibling 依赖）。

**staging 隔离**：`.staging-<pid>/` 在真 config 目录下，sibling 相对路径有效；用完即删（`finally`）；并发校验用调用方 PID/线程 ID 子目录隔离避免互踩。

## 6. 测试计划（TDD，目标 80%+）

按阶段先写测试（RED）再实现（GREEN）。pytest，按现有 `tests/` 目录结构分。

| 测试文件 | 覆盖 |
|---|---|
| `tests/admin/test_store.py` | `ConfigStore.get()` 返回稳定快照；`reload()` 后 `get()` 返回新实例；并发 `get()`/`reload()` 加锁无竞态（threading stress） |
| `tests/admin/test_watcher.py` | mtime 变化触发 reload；debounce 合并多次快速写入；mtime 不变不触发；`reload()` 异常不崩 watcher 线程 |
| `tests/admin/test_validators.py` | 合法 config 通过；语法错拒绝；loader 抛异常拒绝；静默强转收为 warning；staging 用完即删；frequency/timeline 同构 |
| `tests/admin/test_writer.py` | 原子写入（中途 crash 不留半文件）；备份生成 + 近 5 轮转；ETag 失配返回 409；并发写唯一胜出 |
| `tests/admin/test_server.py` | `GET /api/config/config.yaml` 返回原文 + ETag；`PUT` 校验失败 422 + 不落盘；`PUT` 成功 200 + 触发 watcher reload；`GET /api/config/effective` 返回归一化字典；StaticFiles 返回 index.html；GET `../` 路径穿越拒绝 |
| `tests/admin/test_loader_quiet.py` | `load_config(quiet=True)` 不输出 stdout；`quiet=False` 保持现行为（回归） |
| `tests/admin/test_main_integration.py` | `NewsAnalyzer` 每周期取新 ctx；reload 后下一周期用新配置（mock store）；**`data_fetcher` 每周期按当前 proxy_url/api_url 重建**（改 USE_PROXY 后下周期生效）；**`storage_manager` reload 后仍同一全局单例**（断言 id 不变，STORAGE.* 编辑不重建） |
| `tests/admin/test_server_uvicorn.py` | `run_admin_thread` 在非主线程启动不抛 `signal only works in main thread`；端口占用时 `try/except` 吞错 + 日志，主调度循环不受影响 |
| `tests/admin/test_etag.py` | ETag = sha256(字节)；同秒两次不同内容写 → ETag 不同 → 第二次 If-Match 失配 409（防 mtime 碰撞漏检） |
| `tests/admin/test_staging_mirror.py` | staging 镜像三文件；`.staging-<pid>/timeline.yaml` 存在；校验后 staging 目录删除；并发两请求用独立子目录不互踩 |

## 7. 分阶段交付

**阶段 0 — 准备**
- `git mv docs/index.html docs/assets trendradar/admin/static/`
- 建 `trendradar/admin/__init__.py`

**阶段 1 — 后端骨架（TDD）**
- `ConfigStore` + 测试
- `load_config(quiet=...)` 改造 + 回归测试
- `ConfigWatcher`（轮询）+ 测试

**阶段 2 — 校验 + 写入（TDD）**
- `validators.py` + `writer.py` + 测试
- staging 目录策略

**阶段 3 — HTTP 层（TDD）**
- Starlette app + 路由 + StaticFiles
- `run_admin_thread()`
- 端到端 server 测试

**阶段 4 — 调度器集成**
- `NewsAnalyzer` 去 `self.ctx` 缓存，改 `self.store.get()` 每周期取
- 入口启动 admin + watcher 线程
- 集成测试

**阶段 5 — 编辑器 JS 改造**
- 「加载服务配置」/「保存」接本地 API
- ETag 失配处理
- localStorage 草稿保留
- 手测 + Playwright 回归（可选）

**阶段 6 — 文档 + 收尾**
- 本设计文档定稿
- ADR-0004
- CONTEXT.md 词汇（见下）
- `start-http.*` / README 注释
- 全量 `pytest` GREEN

## 8. CONTEXT.md 词汇新增

新增条目（待 grill 过程中术语稳定后落盘）：

- **管理后台 (admin)**：调度器进程内嵌的 HTTP 服务（默认 `127.0.0.1:8080`），提供配置编辑器静态资源 + `/api/config/*` 读写接口。与 MCP server（`:3333`）分离。
- **ConfigStore**：线程安全的 `AppContext` 持有者，`get()` 返回当前快照，`reload()` 原子换新。
- **原始配置 (raw config)**：磁盘上 `config.yaml` / `frequency_words.txt` / `timeline.yaml` 的原文（含注释），编辑器的编辑面。
- **有效配置 (effective config)**：`load_config()` 归一化后的字典（env 覆盖 + 默认值 + 静默强转），调度器实际消费的形态。`/api/config/effective` 只读暴露，调试用。

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| WSL2 / Docker bind-mount 上原生 FS 事件丢失 | **纯 mtime 轮询**，不依赖 inotify/watchdog，跨平台一致 |
| `self.ctx` 缓存残留导致 reload 不生效 | 阶段 4 严格清点 `__main__.py:65-160` 全部派生值，逐一改每周期取；集成测试覆盖 reload 后新周期用新配置 |
| `load_config` 静默强转掩盖用户错误 | `quiet` 之外加 `return_warnings`，校验层把强转收为非阻塞 warning 返给编辑器 |
| 整文件 PUT 失注释（若误用 safe_dump） | 写入路径只接原样字符串，`writer.py` 禁止 parse+dump；测试断言注释保留 |
| 远端暴露被滥用（Q5=C） | 默认 localhost；`ADMIN_HOST=0.0.0.0` 在文档显著警告 + 启动日志告警 |
| ETag 失配频繁（多编辑器并发） | 409 + 编辑器提示「配置已被他人修改，请重新加载」；本地草稿不丢 |
| ~~重载周期中 storage_manager 切换丢 DB 句柄~~ | **不适用**：`storage_manager` 是模块级全局单例，reload 不重建（见 §3/§2）。`LocalStorageBackend.__del__`→`cleanup()` 为兜底，仅 `force_new` 多实例场景才涉及句柄生命周期，本期不走该路径 |
| Docker 容器内 `127.0.0.1:8080` 仅绑容器回环，宿主访问不到 | 文档明示：容器内 admin 需 `ADMIN_HOST=0.0.0.0` + `-p 8080:8080` + **部署者自加反代/隧道鉴权**（Q5=C 的 localhost 防御在容器化部署下失效，网络边界外移到反代层） |
| admin 端口占用 / 绑定失败拖垮调度器 | `run_admin_thread` 内 `try/except` 捕获 uvicorn 启动异常 + 日志；admin 缺席，调度器继续（admin 是便利层，非关键路径） |
| `STORAGE.*` 编辑后用户以为生效但实际需重启 | admin UI 对 STORAGE 段标注「需重启生效」；启动日志 + `/api/status` 暴露「storage 单例创建时刻配置」供对照 |
| MCP 进程 `config_mgmt` 报告陈旧配置 | 文档 + 启动日志明示「MCP 反映其进程启动时刻配置」；admin 编辑后需重启 MCP（或后续迭代 MCP 每次调用重读，本期不做） |

## 10. 开放问题（实现期再决）

- `return_warnings` 的 API 形态（`Tuple[dict, list]` vs out-param）—— 阶段 1 定。
- 「有效配置」调试视图是否进编辑器 UI，还是仅 `/api/config/effective` JSON —— 阶段 5 定。
- 是否在 `/api/status` 暴露「当前在飞周期」用于编辑器提示「保存将在下个周期生效」—— 阶段 3 定。
- **MCP `config_mgmt` 陈旧（H4，已决议）**：本期 MCP 进程保持启动时刻装载，不做每次重读。admin 编辑后 MCP `get_current_config` 反映旧值——文档 + 启动日志明示，编辑生效需重启 MCP。理由：MCP 是只读诊断面，文件仍是 SoT；给 MCP 加每次重读属另一期改动，不在本期 admin 范围。
