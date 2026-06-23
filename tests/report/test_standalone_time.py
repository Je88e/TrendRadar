# coding=utf-8
"""HTML 报告 RSS 独立展示区时区渲染回归测试。

回归对象：trendradar/report/html.py 中 render_standalone_html 的 RSS
published_at 时间渲染。修复前直接 strftime 无时区转换，显示 UTC 墙钟时间
（东八区少 8 小时）；修复后通过 format_iso_time_friendly 转到配置时区。
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


def _rss_standalone(published_at: str) -> dict:
    return {
        "platforms": [],
        "rss_feeds": [
            {
                "id": "hacker-news",
                "name": "Hacker News",
                "items": [
                    {
                        "title": "sample title",
                        "url": "https://example.com/x",
                        "published_at": published_at,
                        "author": "someone",
                    }
                ],
            }
        ],
    }


def test_standalone_rss_naive_utc_converts_to_configured_timezone():
    # Arrange — UTC 00:20 存储（naive），应渲染为 Shanghai 08:20
    standalone_data = _rss_standalone("2025-12-29T00:20:00")

    # Act
    html = render_html_content(
        _empty_report_data(),
        total_titles=0,
        standalone_data=standalone_data,
        timezone=SHANGHAI,
        show_new_section=False,
    )

    # Assert — 配置时区时间出现，UTC 原值不出现
    assert "08:20" in html
    assert "00:20" not in html


def test_standalone_rss_aware_offset_converts_to_configured_timezone():
    # Arrange — aware UTC（回退解析路径产物），同样应渲染为 Shanghai 08:20
    standalone_data = _rss_standalone("2025-12-29T00:20:00+00:00")

    # Act
    html = render_html_content(
        _empty_report_data(),
        total_titles=0,
        standalone_data=standalone_data,
        timezone=SHANGHAI,
        show_new_section=False,
    )

    # Assert
    assert "08:20" in html
    assert "00:20" not in html


def test_standalone_rss_date_rollover_reflects_offset():
    # Arrange — UTC 20:00 -> Shanghai 次日 04:00（验证日期也跟随翻转）
    standalone_data = _rss_standalone("2025-12-29T20:00:00")

    # Act
    html = render_html_content(
        _empty_report_data(),
        total_titles=0,
        standalone_data=standalone_data,
        timezone=SHANGHAI,
        show_new_section=False,
    )

    # Assert
    assert "12-30 04:00" in html
