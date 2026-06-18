# 地区分类功能设计方案

> 状态：实现中 — 阶段 0、1 完成（见「实现进度」）
> 相关：[CONTEXT.md](../CONTEXT.md)、[ADR-0001](adr/0001-tiered-region-drilldown.md)、[ADR-0002](adr/0002-ai-name-normalization.md)
> 版本目标：6.9.1 → 6.10.0

## 实现进度（持续更新）

- ✅ **阶段 0 — 归一化数据资产**：`trendradar/regions/normalizer.py`（`RegionNormalizer` + `NormalizedRegion` frozen dataclass）+ `tests/regions/test_normalizer.py`（**10 测试 GREEN**）+ `scripts/build_regions_data.py`（DataV + mledoze 快照）+ `trendradar/regions/data/{china,countries}.json`（34 省 / 363 市 / 250 国，已生成并用真实数据验证）
- ✅ **阶段 1 — Schema**：`trendradar/storage/region_classify_schema.sql`（两表 + 索引）+ `tests/storage/test_region_classify_schema.py`（**5 测试 GREEN**）+ `trendradar/storage/sqlite_mixin.py` 接入（`_get_region_classify_schema_path` + news 库 init 时 executescript）
- ✅ **阶段 2 — AI 模块**：`trendradar/ai/region.py`（`RegionClassifier` + `classify_batch`/`_parse_response`/`_extract_json`，镜像 filter.py）+ `config/region_classify/prompt.txt`（`{country_list}`/`{news_count}`/`{news_list}` 占位 + JSON 数组契约）+ `tests/ai/test_region.py`（**17 测试 GREEN**：13 parse + 4 classify_batch）。归一化复用 `RegionNormalizer`，非法 level 强转 unknown，confidence clamp [0,1]，AI 异常返 None。
- ✅ **阶段 3 — 配置接线**：`loader.py` `_load_region_classify_config`（大写键 + `REGION_CLASSIFY_ENABLED` 环境变量优先）+ `_load_display_config` 认 `region_map`（开关关时从 `region_order` 移除）+ `context.py` `region_classify_config`/`region_classify_enabled`/`region_map_enabled` 属性 + `get_region_classifier()` 懒构造单例（注入 normalizer + 全量国家全称 country_list）+ `config.yaml` `region_classify` 块（默认 `enabled: false`）+ display `region_map` 开关（默认 false，注释化 region_order 项）+ 测试 `tests/core/test_region_classify_config.py`（8）+ `tests/core/test_context_region.py`（7）
- ✅ **阶段 4 — 触发**：存储层 `region_classify` CRUD（`sqlite_mixin` 4 impl + `base`/`local`/`remote`/`manager` 透传：去重查询/UPSERT 结果/标记已分析/active JOIN 详情，含热榜+RSS 两库 + rank_history）+ `context.run_region_classify()`（gated by enabled；content_hash 去重，标题变更触发重分类，失败批次不标记留待重试；批量分类→落库→返 active 树）+ 测试 `tests/storage/test_region_classify_storage.py`（7）+ `tests/core/test_run_region_classify.py`（6）
- ✅ **阶段 5 — 报告渲染**：payload 构建器 `trendradar/report/region.py`（`build_region_map_payload`：active 树 → design 6.1 树，含中国全树/海外平铺/unknown 桶/count 累计）+ ECharts 世界 choropleth + 中国/省/市钻取 JS（`render_region_map_html`，固定 5.5.x CDN，DataV 运行时 fetch GeoJSON，响应式高，XSS-safe JSON inlining）+ `render_html_content` `region_map` 参数接线 + `context.get_region_map_payload()`（normalizer 注入 echarts 世界名映射）+ `__main__.py` 触发分类 + 传 payload 入 generator + **阶段 6** 通知 exclude（renderer/splitter 过滤 `region_map`）→ 测试 `tests/report/test_region.py`（**17 GREEN**）、`tests/core/test_context_region.py`（+3 新增）、`tests/notification/test_region_exclusion.py`（**3 GREEN**）
- ✅ **阶段 6 — Display/通知**：`renderer.py`/`splitter.py` 过滤 `region_map`（`NOTIFICATION_EXCLUDED_REGIONS`），地区地图不进飞书/TG/邮件通知
- ✅ **阶段 7 — 测试补齐**：边缘用例（confidence None→0 / rounding / 空标题 fallback / unknown-only / world-only）+ 集成往返（build→render HTML 结构验证 / ECharts CDN 完整性 / XSS script 块数量）+ normalizer `get_country_echarts_map` 测试（ISO alpha-2 键 / 空值排除 / 幂等）→ **+15 测试**（report 12 + normalizer 4 = 总量 98）
16	- ✅ **阶段 8 — 收尾**：版本 6.9.1 → 6.10.0（`trendradar/__init__.py` + `pyproject.toml` + `README.md` 徽章）

### 偏离记录

- **建表改无条件**：本设计原写「开关开才建表」，实际镜像现有 `ai_filter`（news 库 init 时无条件建，`CREATE TABLE IF NOT EXISTS` 幂等、空表零成本、与 ai_filter 行为一致）。已实施，无需回改。
- **render_region_map_html 落位 `trendradar/report/region.py`（非 `html.py`）**：本设计原指定 `html.py` 独立函数，实际落位 `region.py` 与 payload builder 共处（按文件组织原则；`html.py` 3221 行已达上限）。`html.py` `render_html_content` 导入 `render_region_map_html` 并接线 region_contents，功能等价。
15	- 全量测试现状：`uv run pytest tests/ -q` → **98 passed**（normalizer 14 + schema 5 + region parse 13 + classify_batch 4 + loader config 8 + context region 10 + storage region 7 + run_region_classify 6 + report region 28 + notification exclusion 3）。

## 1. 目标

新闻抓取后用 AI 给每条新闻打「地区」标签（国家/省/市），并在 HTML 报告中新增「按地区展示」交互式地图区，支持钻取查看新闻。与现有兴趣筛选正交，可配置开关，默认关闭，对原流程零侵入。

## 2. 关键决策（详见 ADR）

- **分级钻取**（ADR-0001）：世界 → 国家色块；中国可钻省→市色块；海外止于国家级，其省/市仅文本元数据，不渲染散点。
- **AI 出中文名 + Python 归一化**（ADR-0002）：AI 输出规范中文全称，Python 用内置对照表转 adcode/ISO；不让 AI 直出 code。
- **报告静态渲染**：报告是 `generate_html_report` 每次覆盖的静态 HTML（GitHub Pages / Docker 挂载），靠 CDN 脚本 + 内联数据在浏览器渲染。地图用 ECharts，GeoJSON 形状运行时从 DataV fetch。
- **地图仅 web**：region_map 区不进飞书/TG/邮件通知（通知走 `notification/splitter.py` 另一套）。

## 3. 数据模型

镜像 `ai_filter_schema.sql` 两表结构，适配「单地区/新闻」+「内容绑定缓存」。

```sql
-- 地区分类结果表（一条新闻 = 一行，单主地区路径）
CREATE TABLE IF NOT EXISTS region_classify_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_item_id INTEGER NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'hotlist',   -- hotlist / rss
    level TEXT NOT NULL,                           -- unknown / country / province / city
    country TEXT,          -- 规范中文名：中国 / 美国
    country_code TEXT,     -- ISO alpha-2：CN / US（归一化后；失败 NULL）
    province TEXT,         -- 广东省 / 加利福尼亚州（海外仅名）
    province_adcode TEXT,  -- 仅中国：440000
    city TEXT,             -- 广州市 / 旧金山（海外仅名）
    city_adcode TEXT,      -- 仅中国：440100
    confidence REAL DEFAULT 0,
    status TEXT DEFAULT 'active',                  -- active / deprecated
    deprecated_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(news_item_id, source_type)              -- 单地区 → 每条新闻唯一
);

-- 已分析去重表（内容绑定）
CREATE TABLE IF NOT EXISTS region_classify_analyzed_news (
    news_item_id INTEGER NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'hotlist',
    content_hash TEXT NOT NULL,   -- title 维度 hash；标题变 → 重分类
    level TEXT NOT NULL,          -- 最近一次 level（含 unknown）
    created_at TEXT NOT NULL,
    PRIMARY KEY (news_item_id, source_type)
);
```

索引照搬 ai_filter 模式（status / news_item_id）。建表懒建：开关开启时才迁移。

## 4. 归一化对照表（内置静态资产）

两套数据，勿混：
- **对照表**（名字→code）：内置静态，Python 归一化用。
- **GeoJSON 形状**：运行时 fetch（DataV），ECharts 渲染色块用。

对照表覆盖：
- 中国 省（~34）→ adcode + 全称 + 简称别名
- 中国 市/地级（~340）→ adcode + 全称 + 简称别名
- 国家（全量 ~195 UN 成员）→ 中文名全称 + ISO alpha-2 + ECharts 世界图英文名 + 简称别名
- 海外省/市：不入表

来源：dev 时快照 DataV（`100000_full.json` + 各省 `{adcode}_full.json`）+ ISO 3166 中文国家表 + ECharts world feature 名 → 提交静态 JSON。

失败回退：AI 吐的名字查不到 → 照存名字、code NULL、该地区不渲染色块但新闻仍进列表（优雅降级，不阻断）。

## 5. AI 契约

### 5.1 提示词

`config/region_classify/prompt.txt`（system + user 模板），含 `{country_list}` 占位（注入全量国家全称清单，约束 AI 直出规范国名）。省市名不进提示词（340 个过多），靠内置别名表归一化。

分类规则要点：每条新闻单一主地区路径；AI 自主决定 level（能到市到市，不确定止于国家，无地理信号标 unknown）；confidence 0~1 仅记录不硬过滤；只按标题判断不臆测。

### 5.2 AI 输出（中间格式，统一数组，含 unknown）

```json
[
  {"id":12,"level":"city","country":"中国","province":"广东省","city":"广州市","confidence":0.9},
  {"id":13,"level":"country","country":"美国","confidence":0.7},
  {"id":14,"level":"unknown","confidence":0.2}
]
```

- `unknown`：仅 id+level+confidence（无国家字段）
- `country`：+country
- `province`：+province
- `city`：+city
- 返回所有处理过的 id（含 unknown），不靠缺席推断（区别于 ai_filter 只返命中）

## 6. 前端地图契约

### 6.1 Python 归一化后喂前端的树（最终 payload，内联进 HTML）

```json
{
  "world": [
    {"code":"CN","name":"中国","count":12,
     "provinces":[{"adcode":"440000","name":"广东省","count":5,
       "cities":[{"adcode":"440100","name":"广州市","count":3,"items":[<news_item>...]}]}]},
    {"code":"US","name":"美国","count":3}
  ],
  "unknown": {"count":7,"items":[<news_item>...]}
}
```

- 中国：provinces→cities→items 全树（逐级钻取）
- 海外：仅国家层（无 provinces）
- `<news_item>` 复用现有字段（title/url/source_name/ranks/...），点地区展开复用 `news-item` 样式

### 6.2 渲染行为

- ECharts（固定 `5.5.x`）+ `world` / `china` 注册 map。CDN 加 head（与 html2canvas 并列）。
- 世界图 choropleth，色深 = 新闻数。默认世界视图，面包屑 `世界 > 中国 > 广东省` 返回。
- 中国国家 click → 运行时 fetch DataV `{adcode}_full.json` 渲省份块 → 省块 click → 市块。
- 海外国家 click → 无下钻，仅展开该国新闻列表（含省/市文字标签）。
- unknown 桶：地图下折叠列表。
- 窄屏/宽屏均渲染（响应式高）。

## 7. 配置

```yaml
region_classify:
  enabled: false          # 默认关，opt-in
  batch_size: 200
  batch_interval: 2
  prompt_file: "prompt.txt"   # config/region_classify/ 目录下
```

- `display.region_order` 默认末尾 ai_analysis 前插 `region_map`
- `display.regions` 加 `region_map: true`
- 开关关 → region_map 不进 region_order（视作 false），无 AI 调用/建表/报告区

## 8. 模块/文件映射

| 关注点 | 位置 |
|---|---|
| 归一化数据 | `trendradar/regions/data/{china.json,countries.json}` |
| 归一化器 | `trendradar/regions/normalizer.py` |
| 数据生成脚本 | `scripts/build_regions_data.py`（dev 工具，不入运行时） |
| Schema | `trendradar/storage/region_classify_schema.sql` |
| 建表迁移 | `trendradar/storage/manager.py` |
| AI 模块 | `trendradar/ai/region.py`（`RegionClassifier`） |
| 提示词 | `config/region_classify/prompt.txt` |
| 配置加载 | `trendradar/core/loader.py`（`_load_region_classify_config`） |
| 触发 | `trendradar/core/analyzer.py`（analyze 阶段，filter 后/报告前） |
| Payload 构建 | `trendradar/report/helpers.py` 或 `region.py` |
| HTML 渲染 | `trendradar/report/html.py`（`render_region_map_html` + ECharts JS） |
| 报告组装 | `trendradar/report/generator.py` |
| 上下文注入 | `trendradar/context.py` |

## 9. 实现阶段（依赖序）

0. **归一化数据资产**：建 `scripts/build_regions_data.py` 快照 DataV + ISO → 生成 `china.json`/`countries.json`；写 `normalizer.py`。
1. **Schema**：`region_classify_schema.sql` + manager 懒建迁移。
2. **AI 模块**：`prompt.txt` + `region.py`（`classify_batch`/`_parse_response`/归一化）。
3. **配置接线**：`config.yaml` `region_classify` 块 + loader + context。
4. **触发**：analyzer 收集报告展示集 → 去重 → 批分类 → 归一化 → 落库（全 gated by enabled）。
5. **报告渲染**：html.py `render_region_map_html` + ECharts + 钻取 JS + payload 构建 + generator 传递。
6. **Display 配置**：region_order/regions 认 `region_map`；splitter 跳过 region_map（不进通知）。
7. **测试**：normalizer / `_parse_response` / payload 树 / 开关+去重集成（pytest，80%+）。
8. **收尾**：README + version bump 6.10.0。

## 10. 边角 / 已确认

- ECharts 固定 5.5.x；world/china map 从 ECharts 官方或 DataV 注册。
- 海外无 per-city 散点（坐标库不存在，见 ADR-0001）。
- 去重缓存只绑新闻内容（content_hash），归一化表/提示词改动不触发全量重分类。
- 通知 splitter：region_map 非通知 region，跳过。
- 默认 opt-in，新用户零成本。
