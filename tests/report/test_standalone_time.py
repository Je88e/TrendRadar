# coding=utf-8
"""HTML 报告 RSS 独立展示区时区渲染回归测试。

回归对象：trendradar/report/html.py 中 render_standalone_html 的 RSS
published_at 时间渲染，经 utils.time.format_iso_time_friendly 换算。

时区语义（与 utils.time 一致）：
- aware（带偏移 / Z）→ 按源时区换算到配置时区。
- naive（无偏移）→ 视作配置时区墙钟原样呈现。

历史 bug：旧实现把 naive 当 UTC，foodmate 裸 pubDate `2026-06-26 10:43:43`
（CST 墙钟）被多加 8 小时；本测试钉死修复后的正确渲染。
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


def test_standalone_rss_naive_treated_as_configured_timezone_wallclock():
    # Arrange — naive 00:20 视作 Shanghai 墙钟，原样渲染，不再 +8
    standalone_data = _rss_standalone("2025-12-29T00:20:00")

    # Act
    html = render_html_content(
        _empty_report_data(),
        total_titles=0,
        standalone_data=standalone_data,
        timezone=SHANGHAI,
        show_new_section=False,
    )

    # Assert — naive 墙钟原值出现，不出现 +8 后的 08:20
    assert "00:20" in html
    assert "08:20" not in html


def test_standalone_rss_naive_foodmate_bare_wallclock_not_shifted():
    # Arrange — foodmate 真实 pubDate（CST 墙钟，无偏移）经 parser 存为 naive ISO
    standalone_data = _rss_standalone("2026-06-26T10:43:43")

    # Act
    html = render_html_content(
        _empty_report_data(),
        total_titles=0,
        standalone_data=standalone_data,
        timezone=SHANGHAI,
        show_new_section=False,
    )

    # Assert — 必须 10:43；旧 +8 bug 会渲染 18:43
    assert "10:43" in html
    assert "18:43" not in html


def test_standalone_rss_aware_offset_converts_to_configured_timezone():
    # Arrange — aware UTC 00:20 -> Shanghai 08:20
    standalone_data = _rss_standalone("2025-12-29T00:20:00+00:00")

    # Act
    html = render_html_content(
        _empty_report_data(),
        total_titles=0,
        standalone_data=standalone_data,
        timezone=SHANGHAI,
        show_new_section=False,
    )

    # Assert — aware 正确换算
    assert "08:20" in html
    assert "00:20" not in html


def test_standalone_rss_aware_positive_offset_no_double_shift():
    # Arrange — +08:00 的 22:45 -> Shanghai 22:45（偏移差为 0，验证不被二次 +8）
    standalone_data = _rss_standalone("2026-06-26T22:45:00+08:00")

    # Act
    html = render_html_content(
        _empty_report_data(),
        total_titles=0,
        standalone_data=standalone_data,
        timezone=SHANGHAI,
        show_new_section=False,
    )

    # Assert
    assert "22:45" in html


def test_standalone_rss_aware_date_rollover_reflects_offset():
    # Arrange — UTC 20:00 -> Shanghai 次日 04:00（aware，验证日期翻转）
    standalone_data = _rss_standalone("2025-12-29T20:00:00+00:00")

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
