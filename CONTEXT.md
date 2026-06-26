# TrendRadar

热点新闻聚合/筛选/分析工具：抓取多平台热榜与 RSS，按关键词或 AI 兴趣筛选，渲染为静态 HTML 报告并推送通知。

## Language

### 地区

新闻所涉的地理位置层级，自顶向下为 国家 → 省 → 市。
_Avoid_: 区域（当指地理义时；「区域」在本项目另指报告布局段落，见下）

### 地区层级 (level)

一条新闻被地区分类时确定的最细地理层级，取值：`unknown`（无地理信号）/ `country` / `province` / `city`。AI 自主决定层级，能到市则到市，不确定时止于国家或标记 unknown。

### 地区分类

新闻抓取后用 AI 给每条新闻确定单一主地区路径（country / country.province / country.province.city）的过程。与兴趣筛选正交（地理 vs 兴趣）。英文标识符为 `region_classify`（表名、配置键、模块名）。
_Avoid_: 区域分类（中文地理义统一用「地区」）

### 报告区域 (region)

`display` 配置里报告的布局段落，如 hotlist / rss / new_items / standalone / ai_analysis / region_map。英文标识符 `region_order` / `regions`。
_Avoid_: 地区（当指布局段落时）

### 词组 (word group)

`frequency_words.txt` 里一组关键词（`[组别名]` + 若干关键词/正则/必须词/过滤词），热榜关键词视图与 RSS 段都按它聚合，渲染为一个可折叠块（热榜 `word-group` / RSS `feed-group`）。每个词组有 `group_key`（原始词拼接，机读、含正则管道符）与 `display_name`（别名，人读、渲染用）。英文标识符 `word_group` / `group_key` / `display_name`。
_Avoid_: 栏目（口语化；精确术语为「词组」）

### 固定 (pinned)

词组的一种展示策略：被标记的词组即使本轮 0 匹配也在报告中渲染占位（「暂无相关新闻」），满足"客户关注的特定企业即使没新闻也要露脸"。固定作用于**词组**，随词组的 stats 流到所有以词组为轴的报告区域（热榜 keyword 视图 + RSS 段）；不是新的报告区域。固定 ≠ 激活：被注释/未加载的词组无法固定（固定只能匹配已加载词组的 `display_name`）。英文标识符 `pinned_keywords`。
_Avoid_: 固定区域（固定不是报告区域，是词组属性）

### 归一化对照表

内置静态数据：国家中文全称 → ISO alpha-2 + ECharts 世界图英文名；中国省/市全称 → adcode（含简称别名）。Python 用它把 AI 输出的中文名转成地图渲染所需的 code。区别于运行时 fetch 的 GeoJSON 形状数据。

### 管理后台 (admin)

调度器进程 `python -m trendradar --serve` 内嵌的 HTTP 服务，默认绑 `127.0.0.1:8080`。**必须带 `--serve` 标志**（opt-in 长驻模式）；不带 `--serve` 时进程单发即退，无后台（兼容 cron/GA 一次性部署）。提供配置编辑器静态资源 + `/api/config/*` 读写接口，支持在线编辑 `config.yaml` / `frequency_words.txt` / `timeline.yaml` 并保存即生效（无需重启）。与 MCP server（`:3333`，独立进程）分离。鉴权策略：默认 localhost 无鉴权；`ADMIN_HOST=0.0.0.0` 远端暴露由部署者自加反代/隧道鉴权。配置走 env（`ADMIN_ENABLED` / `ADMIN_HOST` / `ADMIN_PORT`），不入 `config.yaml`（避免「配置守护配置」循环）。英文标识符 `admin`。详见 [ADR-0004](docs/adr/0004-online-config-admin.md)。
_Avoid_: 配置服务（管理后台是编辑器+REST，非通用配置服务）

### ConfigStore

线程安全的 `AppContext` 持有者（`threading.RLock`）。`get()` 返回当前 `AppContext` 快照（调用方生命周期内稳定）；`reload()` 在锁外 build 新 `AppContext`、锁内换引用，旧实例 drain（在飞周期跑完后 GC）。调度器主线程每周期开头从 `ConfigStore.get()` 取 ctx，不再 `__init__` 缓存。文件为唯一 SoT，所有写入（PUT / vim / git）落盘后由 `ConfigWatcher` mtime 轮询触发 `reload`。

### ConfigWatcher

mtime 轮询守护线程（`trendradar-config-watcher`），每 2 秒检查三份配置文件的 `st_mtime_ns`，变化 → debounce（默认 1 秒）→ 触发 `ConfigStore.reload()`。纯 mtime 轮询，不依赖 inotify/watchdog，WSL2 / Docker bind-mount 跨平台一致。`start()` 启动 daemon 线程，`stop()` 中断并 join。

### 原始配置 (raw config) vs 有效配置 (effective config)

- **原始配置**：磁盘上 `config.yaml` / `frequency_words.txt` / `timeline.yaml` 的原文（含注释与格式），是编辑器的编辑面，`GET /api/config/<file>` 返回此形态。
- **有效配置**：`load_config()` 归一化后的字典（env 覆盖 + 默认值 + 静默强转），调度器实际消费的形态，`GET /api/config/effective` 只读返回，调试用。

二者差异源于 `loader.py` 的 env 覆盖优先级与静默强转（如负 `max_age_days` 纠正为 3）。

## Relationships

- **地区分类 ↔ 兴趣筛选**：正交。地区分类不依赖 `filter.method`（keyword/ai 均可独立开启）。
- **地区 → 前端地图**：中国地区各级均有 adcode，可逐级色块钻取；海外地区止于国家级（ISO code），省/市仅存为文本元数据，不渲染色块。
- **词组 ↔ 报告区域**：词组是热榜 keyword 视图与 RSS 段共享的聚合轴（同一份 keyword-grouped `stats`）；new_items 按来源聚合、standalone 按平台/RSS 源聚合，二者不以词组为轴。
- **固定 ↔ 词组**：固定是词组的展示属性，不是报告区域。固定词组随 stats 流到热榜 keyword 视图 + RSS 段；未匹配/被注释的词组不可固定。
- **管理后台 ↔ MCP server**：两个独立进程、两个端口（`:8080` vs `:3333`）。后台嵌入调度器进程（配置消费方），MCP 保持只读 `config_mgmt`。文件是唯一 SoT，二者均从文件读，写入仅经后台 PUT（MCP 不写）。
- **原始配置 ↔ 有效配置**：编辑器编辑原始配置（保注释），调度器消费有效配置（归一化）。env 覆盖与静默强转是差异源，调试时以 `/api/config/effective` 对照排查「为何改了 YAML 行为不变」。
