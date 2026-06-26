# coding=utf-8
"""固定词组 HTML 占位渲染测试（AAA 结构）。

热榜 word-group：count==0 固定词组渲染占位行
（header 正常 word-name + 0 条；body 单行 📌 暂无相关新闻），
非空固定词组照常渲染且 header 无 📌。
"""

from trendradar.report.html import render_html_content


def _title(name="t1"):
    return {
        "title": name, "source_name": "src", "time_display": "",
        "count": 1, "ranks": [1], "rank_threshold": 3,
        "url": "", "mobile_url": "", "is_new": False,
    }


def _report_data(stats):
    return {
        "stats": stats,
        "new_titles": [],
        "failed_ids": [],
        "total_new_count": 0,
    }


class TestHotlistPinnedPlaceholder:
    def test_pinned_empty_renders_placeholder(self):
        rd = _report_data([
            {"word": "华为", "count": 0, "titles": [], "percentage": 0, "pinned": True},
        ])
        html = render_html_content(rd, total_titles=0, display_mode="keyword")
        # header 正常：word-name + 0 条
        assert "华为" in html
        assert "0 条" in html
        # body 占位行（查元素，非 CSS 类名定义）
        assert '<div class="news-empty-placeholder">' in html
        assert "暂无相关新闻" in html

    def test_non_empty_pinned_no_placeholder_no_pin_in_header(self):
        rd = _report_data([
            {"word": "华为", "count": 1, "titles": [_title()], "percentage": 100, "pinned": True},
        ])
        html = render_html_content(rd, total_titles=1, display_mode="keyword")
        # 非空：无占位元素
        assert '<div class="news-empty-placeholder">' not in html
        # 词组名前无 📌 标记（占位文本才含 📌）
        assert 'word-name">📌' not in html
