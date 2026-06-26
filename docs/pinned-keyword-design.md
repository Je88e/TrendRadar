# 固定词组功能设计方案

> 状态：已实现（TDD，20 测试 GREEN；热榜 + RSS 占位均落地，analyzer 未改）
> 相关：[CONTEXT.md](../CONTEXT.md)、[ADR-0003](adr/0003-pin-keyword-config-location.md)
> 版本目标：6.10.x

## 1. 目标

客户关注特定企业/品牌，即使本轮 0 匹配也希望在报告里**固定占位**（「暂无相关新闻」），而非随空词组一起被丢弃。固定是词组的展示属性，随词组的 stats 流到所有以词组为轴的报告区域。

**非目标**：固定不是新的报告区域（不与 hotlist/rss/standalone 并列）；不改 new_items（来源轴）与 standalone（平台/源轴）的聚合方式；不改 `frequency_words.txt` 语法。

## 2. 关键决策（详见 ADR-0003 + 本文档 grill 记录）

| # | 决策 | 选择 |
|---|---|---|
| Q1 | 固定粒度 | 固定**单个词组**（非命名分区） |
| Q2 | 开关位置 | `config.yaml`，非 frequency_words 内联 |
| Q3 | 匹配键 | `display_name`，**要求显式别名** |
| Q4 | 配置键 | `report.display.pinned_keywords: [str]`（独立 `display:` 子键，与关键词视图展示整形归一处） |
| Q5/7 | 生效面 | 仅 HTML（热榜 keyword 视图 + RSS 段）；通知跳过 count==0 |
| Q6 | 占位渲染 | 复用 word-group/feed-group chrome + 静默行 `📌 暂无相关新闻` |
| Q8 | 报告模式 | daily/current/incremental 均生效（HTML 生成不受 `has_any_content` 门控）；不强制推送 |
| Q9 | 排序/Tab/总计 | 沿用现有排序（count=0 自然沉底）；Tab 栏含固定项；count=0 不影响计数总和 |
| Q-empty | 仅固定空时的段可见性 | RSS 段保留可见（放宽 `total_count==0` 门） |
| Q11 | 固定 vs 激活 | 固定仅作用于已加载词组；不复活被注释词组 |
| Q12 | 边缘 | 重复别名匹配全部并记数；AI/翻译自然跳过空词组；未命中告警不中断；缺省/空列表=功能关闭；standalone 不受影响；`全部新闻` 回退模式无固定目标 |

## 3. 数据流与生效面

词组（如「华为」）经 `analyzer.py` 产出 keyword-grouped `stats`，被**两处**消费：
- 热榜 keyword 视图 → `word-group`（`html.py:1670` 循环）
- RSS 段 → `feed-group`（`html.py:1899` 循环，注释明示「与热榜格式一致」）

注意：热榜与 RSS 是**两份独立的 keyword-grouped stats**。热榜 `stats` 在 `analyzer` 保留 count==0 词组、由 `generator.py:103` 丢弃；RSS `rss_items` 来自 `count_rss_frequency`，该函数在 `analyzer.py:672` `if data["count"] == 0: continue` 处**丢弃** count==0 词组。因此固定空词组不会自然出现在 `rss_items`，需在 generator 侧 `enrich_rss_stats_with_pinned` 重新注入（见 §4），**不改 analyzer**（§4 约束）。

两处当前都丢空词组（热榜在 `generator.py:103` `if stat["count"] <= 0: continue`；RSS 在 `html.py:1902 if not titles: continue` + `:1887 if total_count == 0: return ""` 整段隐藏）。固定 = 让被标记词组在这三处门控中放行，渲染占位。

new_items（`new-source-group`，来源轴）与 standalone（平台/源轴）不以词组为轴，固定不生效。

## 4. 实现触点

| 文件 | 改动 |
|---|---|
| `config/config.yaml` | `report.display` 子键新增 `pinned_keywords: []`（缺省空，注释说明需词组有显式别名） |
| `trendradar/core/loader.py` | 加载 `report.display.pinned_keywords` → `PINNED_KEYWORDS: set[str]`（大写键约定，`_load_report_config`）；无独立 schema 校验（report 配置无 schema 层） |
| `trendradar/report/generator.py:103` | 固定旁路：`if stat["count"] <= 0 and stat["word"] not in pinned_set: continue`；保留的固定空词组打 `stat["pinned"] = True`（并回填到 processed_stats） |
| `trendradar/report/generator.py`（新增 `enrich_rss_stats_with_pinned`） | RSS 固定空词组补充：`count_rss_frequency` 在 `analyzer.py:672` 丢弃 count==0 词组，故此处按 display_name 重新注入 `{word, count:0, titles:[], pinned:True}`，使 RSS feed-group 渲染占位；静默（未命中告警由热榜路径负责，避免重复）；不改 analyzer |
| `trendradar/context.py`（`render_html`） | 调用 `enrich_rss_stats_with_pinned` 处理 `rss_items`/`rss_new_items` 后再渲染（不可变：返回新列表） |
| `trendradar/report/html.py` hotlist 循环（`:1670`） | 固定空词组（`titles==[]`）渲染占位行：header 正常（`word-name` + `0 条`），body 单行静默 `📌 暂无相关新闻` |
| `trendradar/report/html.py` RSS `render_rss_stats_html` | `:1899` `if total_count == 0 and not has_pinned: return ""`（仅固定空也保留 RSS 段）；`:1914` `if not titles and not stat.get("pinned"): continue`（固定空放行）+ 占位行 |
| `trendradar/notification/renderer.py:52-81,194-222` | `visible_stats = [s for s in stats if s["count"] > 0]` 守卫（固定旁路打破「generator 预过滤掉 count==0」前提）；序列号基于 `len(visible_stats)` |
| `trendradar/notification/splitter.py` | 同上守卫（hotlist 路径遍历处加 `visible_stats` 过滤）；RSS 通知路径为扁平 feed 轴，固定不生效 |
| `trendradar/core/frequency.py` | **不改**（固定不内联，词法分析器无感） |
| `trendradar/core/analyzer.py` | **不改**（热榜 stats 仍含 count=0 词组，display_name 已在 `:461` 解析；RSS count==0 在 `:672` 丢弃但由 generator 下游 `enrich_rss_stats_with_pinned` 重新注入，故 analyzer 无需改动） |

固定匹配点选 `generator.py`（`stat["word"]` 即 `display_name`，无需再传 word_groups）。未命中：`print("[pinned] 'X' 未匹配到任何词组，跳过")`，镜像 `frequency.py:62` 告警风格，不中断。

## 5. 占位渲染规格（Q6）

- **热榜 word-group**：`<div class="word-group">` header 照常（`word-name` + `word-count` 徽章，count=0 → `count_class=""`），body 单行 `<div class="news-empty-placeholder">📌 暂无相关新闻</div>`。
- **RSS feed-group**：同构，header `feed-name` + `0 条`，body 同一占位行。
- 新增 1 个静默 CSS 类（`.news-empty-placeholder`，muted 色 + 暗色模式变体）。无虚线边框/卡片/标签等额外装饰（Q6 选 A，非 C）。
- **非空固定词组**：照常渲染，header **无 📌**（标记仅出现在占位时，避免噪声）。

## 6. 边缘与不变量（Q12）

- **重复 `display_name`**：固定匹配所有同名词组，日志 `pinned '华为' → 2 组`。不拒绝、不取首。
- **AI 分析 / 翻译**：固定空词组 `titles=[]`，AI 输入遍历 titles 自然无贡献；dispatcher 翻译循环（`:119`）自然跳过。无需改动。
- **未命中**：`pinned_keywords` 条目匹配不到已加载词组 → 告警 + 跳过，继续运行。
- **缺省/空**：键缺失或 `[]` → 功能关闭，零行为变化，向后兼容。
- **standalone**：平台/源轴，固定不生效。
- **`全部新闻` 回退**（frequency words 空）：无真实词组，任何 `pinned_keywords` 全部未命中告警。
- **通知总条数**：`renderer.py:184/196` 的 `total_count = len(stats)` 含固定空项 → 序列显示 `[i/N]` 会含空项；加 `count==0` 守卫后空项不出现在正文，但 `len(stats)` 仍计它 → 需用「非空 stats 数」或守卫后重计，避免序号断层（实现时核对）。

## 7. 测试计划（TDD，目标 80%+）

- **config 加载**：`pinned_keywords` 缺省空 / 列表 / 大写键 / 环境变量（若支持）。
- **匹配**：有别名词组命中 / 无别名词组不命中 / 被注释词组不命中 / 重复别名匹配全部并记数。
- **generator 旁路**：固定空词组保留 + `pinned=True`；非固定空词组仍丢弃；固定词组有匹配时正常。
- **html 占位**：热榜 word-group 占位结构 / RSS feed-group 占位结构 / 非空固定无 📌 / CSS 类存在。
- **段可见性**：仅固定空时 RSS 段不隐藏（`has_pinned` 放宽）；热榜 `if report_data["stats"]` 已自然满足。
- **通知守卫**：renderer/splitter 跳过 count==0（含固定空）；序列号不断层。
- **排序/Tab**：固定空项在默认 count 排序沉底；`sort_by_position_first` 时按定义位；Tab 栏含固定项 `华为 (0)`；`全部` 计数不含 count=0。
- **告警**：未命中 print 内容；不中断流程。
- **回归**：`pinned_keywords=[]` 时所有现有报告输出 byte-for-byte 不变（向后兼容门）。

## 8. 用户操作清单（落地步骤）

1. 在 `frequency_words.txt` 取消注释要固定的企业/品牌词组（如 `/华为|任正非|.../ => 华为`）—— 必须有 `=> 别名` 或 `[组别名]`。
2. 在 `config.yaml` `report.display.pinned_keywords:` 列入这些别名。
3. 运行；检查日志有无 `[pinned] ... 未匹配` 告警（有则说明别名写错或词组仍被注释）。
