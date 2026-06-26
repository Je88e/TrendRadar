# coding=utf-8
"""HTML 报告 RSS 新增区域 display.regions.new_items 门控回归测试。

回归对象：trendradar/report/html.py:render_html_content 中 RSS 新增更新区块
（rss_new_html）必须遵守 show_new_section 开关。

历史 bug：rss_new_html 仅判断 `if rss_new_items`，未门控 show_new_section。
display.regions.new_items=false 时 RSS 新增区域仍现身；叠加固定词组占位注入
（context.py enrich_rss_stats_with_pinned）后，即使本轮 0 真实新增 RSS，
固定占位也使该区域非空 → 区域可见。语义应为 display.regions > 固定词组。

对照：热榜新增（new_titles_html）在 html.py:1805 已正确门控；通知路径在
dispatcher.py:416 已正确门控；本测试钉死 HTML RSS 新增路径的同一行为。
"""

from trendradar.report.html import render_html_content

SHANGHAI = "Asia/Shanghai"


def _empty_report_data() -> dict:
    """render_html_content 要求的最小 report_data 契约。"""
    return {
        "stats": [],
        "failed_ids": [],
        "new_titles": [],
        "total_new_count": 0,
    }


def _rss_new_with_real_items() -> list:
    """RSS 新增条目（关键词分组，与 rss_items 同构），含真实匹配。"""
    return [
        {
            "word": "测试词",
            "count": 1,
            "titles": [
                {
                    "title": "真实新增 RSS 标题",
                    "source_name": "Feed",
                    "time_display": "06-26 08:00",
                    "url": "https://example.com/a",
                    "is_new": True,
                }
            ],
        }
    ]


def _rss_new_with_only_pinned() -> list:
    """RSS 新增条目：仅固定空词组占位（count=0，pinned=True，titles=[]）。"""
    return [
        {
            "word": "天味食品",
            "count": 0,
            "titles": [],
            "pinned": True,
        }
    ]


def test_rss_new_hidden_when_show_new_section_false_with_real_items():
    # Arrange — 有真实新增 RSS 但 new_items 区域关闭
    # Act
    html = render_html_content(
        _empty_report_data(),
        total_titles=0,
        rss_new_items=_rss_new_with_real_items(),
        timezone=SHANGHAI,
        show_new_section=False,
    )

    # Assert — RSS 新增区域整体不出现
    assert "RSS 新增更新" not in html
    assert "真实新增 RSS 标题" not in html


def test_rss_new_hidden_when_show_new_section_false_with_only_pinned():
    # Arrange — 仅固定词组占位，new_items 区域关闭（回归报告的 bug 场景）
    # Act
    html = render_html_content(
        _empty_report_data(),
        total_titles=0,
        rss_new_items=_rss_new_with_only_pinned(),
        timezone=SHANGHAI,
        show_new_section=False,
    )

    # Assert — display.regions > 固定词组：固定占位不破墙而出
    assert "RSS 新增更新" not in html
    assert "天味食品" not in html


def test_rss_new_shown_when_show_new_section_true_with_real_items():
    # Arrange — new_items 区域开启，有真实新增 RSS（控制组，保证门控未误杀）
    # Act
    html = render_html_content(
        _empty_report_data(),
        total_titles=0,
        rss_new_items=_rss_new_with_real_items(),
        timezone=SHANGHAI,
        show_new_section=True,
    )

    # Assert
    assert "RSS 新增更新" in html
    assert "真实新增 RSS 标题" in html
