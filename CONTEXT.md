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

### 归一化对照表

内置静态数据：国家中文全称 → ISO alpha-2 + ECharts 世界图英文名；中国省/市全称 → adcode（含简称别名）。Python 用它把 AI 输出的中文名转成地图渲染所需的 code。区别于运行时 fetch 的 GeoJSON 形状数据。

## Relationships

- **地区分类 ↔ 兴趣筛选**：正交。地区分类不依赖 `filter.method`（keyword/ai 均可独立开启）。
- **地区 → 前端地图**：中国地区各级均有 adcode，可逐级色块钻取；海外地区止于国家级（ISO code），省/市仅存为文本元数据，不渲染色块。
