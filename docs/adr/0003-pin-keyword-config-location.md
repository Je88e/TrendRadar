# 固定词组配置位置：config.yaml 列表按 display_name 匹配

「固定词组」（pinned，即使 0 匹配也渲染占位）的开关写在 `config.yaml` 的 `report.pinned_keywords` 列表里，按词组的 `display_name`（别名）匹配；**不**像 `max_count`(`@N`) 那样内联在 `frequency_words.txt`。匹配目标必须拥有显式别名（`[组别名]` 或 `=> 别名`），否则视为未命中并告警跳过。

这是真权衡的产物。直觉上固定应当跟 `max_count` 一样内联 —— 它们都是词组级、display 层的属性。但内联需要一个「在词组定义处写死」的标记，而把开关搬进 `frequency_words.txt` 并不能解决本决策真正的约束：**词组缺少一个稳定的、人可写的跨文件标识符**。`group_key` 是原始词拼接，对正则词组形如 `华为|任正非|余承东|鸿蒙|\bHUAWEI\b|...`，管道符与转义混在一起，不可写、不可读；`display_name` 是别名，人可写但可变（重命名别名即漂移）。`standalone` 能用 `config.yaml` 平台/RSS ID 列表，是因为平台/源 ID 稳定；词组没有等价物。

把开关放在 `config.yaml` 并以 `display_name` 为键、要求显式别名，是三点妥协：(1) 别名即渲染名，用户在报告里看到的「华为」就是 `config.yaml` 里写的「华为」，认知耦合最紧 —— 重命名别名时，用户是在改「报告里显示的名字」，自然会同步改配置；(2) 要求显式别名才能固定，排除了 `display_name` 退化成词拼接的歧义情况，被固定者本就是「重要的、客户面向的名字」，给它别名是自然之举；(3) 未命中告警（`[pinned] 'X' 未匹配到任何词组，跳过`）把漂移的代价变成显式日志，而非静默失效。

难逆转：`generator.py` 的固定旁路（热榜 `prepare_report_data`）与 RSS `enrich_rss_stats_with_pinned`、`html.py` 的占位渲染、通知层 `count==0` 守卫、`loader.py` 的配置键五处共同编码「`display_name` 是固定的唯一锚点」。若日后改成内联或改用 `group_key`，需迁移现有 `pinned_keywords` 配置并改这五处。无此背景，未来读者会困惑「为何 `max_count` 内联而固定不内联，且固定还要要求别名」。

## Considered Options

- **内联在 `frequency_words.txt`（如组别名前缀/独立标记行）**：否决。词组无稳定可写标识符；内联标记虽避免跨文件引用，但与「按渲染名匹配」的直觉耦合更弱，且给已负重载的 frequency 语法（`+`/`!`/`@`/`[]`/`=>`）再加一个 sigil。被「无稳定 ID」一票否决。
- **`config.yaml` 列表按 `group_key` 匹配**：否决。`group_key` 对正则词组含管道符与 `\b` 转义，不可写；企业/品牌词组绝大多数是正则，此键不可用。
- **`config.yaml` 列表按 `display_name` 匹配，不要求别名**：否决。无别名词组的 `display_name` 退化为词拼接，多词组易碰撞，且渲染名不稳定。
- **`config.yaml` 列表按 `display_name` 匹配 + 要求显式别名（本决策）**：采纳。

## Consequences

- 固定只能作用于拥有显式别名的词组；无别名词组不可固定（需先加 `[组别名]` 或 `=> 别名`）。
- 被注释/未加载的词组不在 `word_groups` 中，固定无法匹配 —— 固定 ≠ 激活，用户需先取消注释再固定（见设计文档 Q11）。
- 重命名词组别名会令对应 `pinned_keywords` 条目失效，由启动时告警暴露。
- `display_name` 重复时，固定匹配所有同名词组并记录命中数（不拒绝、不取首）。
- 配置键落位 `report.display.pinned_keywords`（独立 `display:` 子键，收纳关键词视图展示整形旋钮）。实现时将固定与 `max_news_per_keyword` / `sort_by_position_first` 分层：后两者是「热榜排序/限量」旋钮（`report:` 同层），固定是「展示占位」旋钮（`report.display:` 子键）。
