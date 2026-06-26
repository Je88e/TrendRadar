# coding=utf-8
"""固定词组 RSS feed-group 占位渲染测试（AAA 结构）。

RSS feed-group：count==0 固定词组渲染占位行
（header feed-name + 0 条；body 单行 📌 暂无相关新闻），
仅固定空时 RSS 段仍可见（放宽 total_count==0 门）。
非空 RSS 词组照常渲染无占位。
"""

from trendradar.report.html import render_html_content


def _rss_item(name="t1"):
    return {
        "title": name, "source_name": "Feed", "time_display": "",
        "count": 1, "ranks": [1], "rank_threshold": 3,
        "url": "", "mobile_url": "", "is_new": False,
    }


class TestRssPinnedPlaceholder:
    def test_pinned_empty_renders_feed_group_placeholder(self):
        # 仅一个固定空词组：RSS 段必须可见并渲染占位
        rss_items = [
            {"word": "华为", "count": 0, "titles": [], "percentage": 0, "pinned": True},
        ]
        html = render_html_content(
            {"stats": [], "new_titles": [], "failed_ids": [], "total_new_count": 0},
            total_titles=0,
            display_mode="keyword",
            rss_items=rss_items,
        )
        # RSS 段可见（未被 total_count==0 整段隐藏）：渲染元素存在
        assert '<div class="rss-section">' in html
        # feed-group header：feed-name + 0 条
        assert "华为" in html
        assert "0 条" in html
        # body 占位行
        assert '<div class="news-empty-placeholder">' in html
        assert "暂无相关新闻" in html

    def test_non_empty_rss_no_placeholder(self):
        rss_items = [
            {"word": "华为", "count": 1, "titles": [_rss_item()], "percentage": 100, "pinned": True},
        ]
        html = render_html_content(
            {"stats": [], "new_titles": [], "failed_ids": [], "total_new_count": 0},
            total_titles=1,
            display_mode="keyword",
            rss_items=rss_items,
        )
        assert '<div class="news-empty-placeholder">' not in html

    def test_only_non_pinned_empty_rss_section_hidden(self):
        # 非固定空词组（无 pinned 标记）：整段隐藏（保持原行为）
        rss_items = [
            {"word": "杂项", "count": 0, "titles": [], "percentage": 0},
        ]
        html = render_html_content(
            {"stats": [], "new_titles": [], "failed_ids": [], "total_new_count": 0},
            total_titles=0,
            display_mode="keyword",
            rss_items=rss_items,
        )
        # RSS 段被 total_count==0 门隐藏（用渲染元素断言，非 CSS 类名/标题串）
        assert '<div class="rss-section">' not in html
