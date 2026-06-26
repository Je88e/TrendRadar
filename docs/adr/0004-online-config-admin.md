# 在线配置后台：嵌入调度器进程 + 文件轮询重载 + 整文件原样写入

配置管理后台（管理用 HTTP 服务 + 在线编辑器）嵌入 **调度器进程**（`python -m trendradar`），以 **mtime 轮询 + debounce** 触发 `AppContext` 整体重载，编辑器经 `PUT /api/config/<file>` **整文件原样写入**磁盘（服务端不做 `yaml.safe_dump`，注释得以保留），`load_config()` 干跑作为校验 oracle。默认 `127.0.0.1:8080` 无鉴权。

这是真权衡的产物。直觉方案有三：(1) 在已绑定 `0.0.0.0:3333` 的 MCP server（FastMCP）上挂静态资源 + REST，复用已有 HTTP 端口；(2) PUT 同步重建 `AppContext`，保存即生效，无需文件监听；(3) 服务端 `yaml.safe_dump` 规整化配置，统一格式。三者皆否决。

**否决(1) 嵌入 MCP 进程**：MCP 进程与调度器进程是两个独立进程。若后台在 MCP 进程写文件，调度器进程的 `AppContext`（启动时一次性 `load_config()` 装载）不会刷新——除非再引入文件监听或 IPC 把变更推给调度器。这恰恰是本期要消灭的 bug 形态：写入「成功」但运行中的分析器无视，直到重启。后台必须住在配置的**消费方**（调度器），写与重载在同一进程内闭环。

**否决(2) PUT 同步重载**：同步重载只覆盖「经 PUT 的写入」一条路径；外部写入（`vim`、`git pull`、deploy 拷贝）不会触发。文件是唯一 SoT，则所有写入路径都应触发重载，否则「直接改文件不生效」会反复困扰用户。文件轮询（mtime + debounce）统一了所有触发源。额外考虑：运行环境是 WSL2 / Docker bind-mount，原生 inotify 在 9P 与 bind-mount 上丢事件，故选 **纯 stdlib mtime 轮询**（每 2s 查 mtime，变化后 debounce 1s），不引入 watchdog、不依赖平台事件机制，跨环境一致。

**否决(3) 服务端 `safe_dump`**：编辑器（`script.js` 头注释明示）的核心价值是「原始 YAML 注释与格式 100% 保留」，靠客户端字符串操作维持。若服务端解析后重新 dump，注释尽失，编辑器价值归零。故写入路径只接受**原样字符串**，服务端是「校验 + 备份 + 原子替换」的哑管道，`writer.py` 禁止 parse 后 dump。注释保留由「编辑器权威 + 服务端不二次格式化」共同保证。

并发模型选 **daemon 线程**（HTTP 与 watcher 各一线程，主线程跑调度循环），不选「调度循环改 asyncio」：调度链路（crawl→filter→analyze→render→push）满是阻塞 I/O（`requests`、`time.sleep`、同步 LiteLLM、SQLite），改 async 需把每一处阻塞调用包 `run_in_executor` 或换异步库，爆炸半径与回归风险远超收益。线程方案零改调度链路，仅要求主线程每周期从 `ConfigStore.get()` 取 `AppContext`（不再 `__init__` 缓存），改动局限在 `__main__.py:65-160` 的派生值清点。GIL 争夺可忽略——三方皆 I/O bound（等网络、等 DB）。

重载语义选 **整体重建 + drain 旧**（不增量 diff、不就地改单例）：`AppContext` 持有 `_storage_manager`（SQLite/S3 句柄）、`_scheduler`、`_region_classifier`（AI client + normalizer 数据）、`_region_normalizer` 四个单例，各自绑定其构建时的配置切片。增量 diff（仅当某切片变化才重建对应单例）需为每个单例维护字段→重建的映射，遗漏一字段即留陈旧单例（如 AI client 仍用旧 api_key）。整体重建以可忽略的成本（重开 SQLite ~ms、重读 normalizer JSON ~KB、AI client 无状态）换「单例恒与其构建配置一致」的不变量。drain 旧：reload 在锁外 build 新 `AppContext`，锁内换引用，旧实例让在飞周期跑完后自然 GC，不强制关闭——避免中途切换 DB 句柄致在飞推送半截。

鉴权选 **默认 localhost 无鉴权**（不 token、不读 `config.yaml`）：token 若存 `config.yaml` 则「配置守护配置」循环（用户改掉了自己的鉴权密钥）；token 存 localStorage 有 XSS 风险（编辑器从 CDN 拉 Tailwind/FontAwesome/js-yaml）。localhost 绑定以网络边界为防御，零新鉴权代码。远端访问（`ADMIN_HOST=0.0.0.0`）显式 opt-in，文档与启动日志告警，鉴权由用户自加反向代理（nginx basic auth / Cloudflare Access / SSH 隧道）——这是部署者职责，不混入应用。

难逆转：`NewsAnalyzer` 去 `self.ctx` 缓存（约 10 处派生值改每周期取）、`ConfigStore` 作为 `AppContext` 唯一持有者、`load_config(quiet=...)` 签名扩展、编辑器文件迁入 `trendradar/admin/static/`、Starlette 路由 shape 五处共同编码「后台=调度器内嵌 + 文件 SoT + 整文件原样」。若日后改回 MCP 进程托管或改异步单线程，需迁移这五处 + 重新评估 WSL2 文件事件可靠性。无此背景，未来读者会困惑「为何后台不与 MCP 同进程、为何用轮询而非 inotify、为何服务端不规整 YAML、为何无鉴权 UI」。

## Considered Options

- **嵌入 MCP 进程（FastMCP :3333 挂静态 + REST）**：否决，跨进程配置陈旧。
- **新独立 HTTP 进程 + IPC**：否决，两进程配置陈旧的同病，且多一进程编排。
- **PUT 同步重载**：否决，只覆盖 PUT 一路，外部写入不触发。
- **watchdog/inotify 原生事件**：否决，WSL2 / Docker bind-mount 丢事件；改用 stdlib mtime 轮询。
- **服务端 `yaml.safe_dump` 规整**：否决，注释尽失，编辑器价值归零。
- **`ruamel.yaml` 服务端 round-trip 保注释**：否决，重依赖 + 脆弱，不如「编辑器权威 + 服务端原样写」。
- **调度循环改 asyncio 单线程**：否决，阻塞 I/O 链路全需 async 化，回归风险远超收益。
- **增量 diff 重载（仅变切片重建单例）**：否决，字段→单例映射易遗漏留陈旧。
- **整体重建 + cancel 在飞周期**：否决，丢半截推送（飞书/钉钉批次）。
- **token 鉴权（config.yaml / env / localStorage）**：否决，循环依赖 / XSS / 复杂度，localhost 已足。
- **读开放 + 写 token**：否决，GET 经 webhook URL / API key 泄密。
- **本决策（嵌入调度器 + mtime 轮询 + 整体重建 drain + 整文件原样 + localhost 无鉴权）**：采纳。

## Consequences

- 管理后台与 MCP server 分离：`:8080`（调度器进程）vs `:3333`（MCP 进程），各绑各的 host。
- 所有配置写入（PUT / vim / git / deploy）经文件落盘 + watcher 统一触发重载；文件是唯一 SoT。
- `NewsAnalyzer` 不再 `__init__` 缓存配置派生值；每周期开头 `ctx = ConfigStore.get()`。
- 在飞周期持旧 `AppContext` 快照跑完，下一周期取新；用户感知「保存后下个周期生效」。
- `load_config` 签名扩 `quiet=False`（向后兼容）；可选 `return_warnings` 暴露静默强转。
- 编辑器文件迁 `trendradar/admin/static/`，随包发布（pip / Docker）自带，`docs/` 回归纯仓库文档。
- 远端暴露 `ADMIN_HOST=0.0.0.0` 需用户自加反代鉴权；应用不内置 token / 登录页。
- 无新重依赖：starlette/uvicorn 经 fastmcp 传递引入，watcher 用 stdlib 轮询。
- 配置 schema 不变；仅新增 `ADMIN_ENABLED` / `ADMIN_HOST` / `ADMIN_PORT` 三个 env（不入 YAML，避免循环）。
- **存储配置不在 admin 在线生效范围**：`storage.get_storage_manager()` 是模块级全局单例（`_storage_manager`），`AppContext.get_storage_manager()` 不传 `force_new` → 所有 `AppContext` 共享同一实例，reload 不重建。`STORAGE.*` 编辑需重启。`LocalStorageBackend.__del__`→`cleanup()` 兜底关连接，drain 安全。
- **uvicorn 须在线程内禁用信号处理**（`server.install_signal_handlers = lambda: None`），否则非主线程注册信号抛 `ValueError: signal only works in main thread`。启动异常 `try/except` 隔离，不拖垮调度器。
- **`NewsAnalyzer.__init__` 实际 6 个配置派生属性需去缓存**（非原估 10）：`request_interval` / `report_mode` / `rank_threshold` / `proxy_url` / `data_fetcher` / `storage_manager`。其中 `data_fetcher` 须每周期按当前 proxy 重建（否则 `USE_PROXY` / `DEFAULT_PROXY` / `PLATFORMS_API_URL` 编辑不生效）；`storage_manager` 走全局单例。
- **ETag = 文件字节 sha256**（非 mtime），防 NTFS / WSL `/mnt/d` 粗粒度 mtime 同秒重写碰撞漏检。
- **staging 校验须镜像三文件**（config.yaml + timeline.yaml + frequency_words.txt）到 `.staging-<pid>/`，否则 `load_config(staging_path)` 解析不到 sibling，oracle 失真。
- **`STORAGE_RETENTION_DAYS` env 覆盖从 `NewsAnalyzer.__init__` 移入 `load_config`**：原就地 mutate 既破坏不可变性，又使 reload 后 env 覆盖丢失。
- **MCP `config_mgmt` 反映 MCP 进程启动时刻配置**：admin 编辑后 MCP 不重读，需重启 MCP（本期范围外给 MCP 加每次重读）。
