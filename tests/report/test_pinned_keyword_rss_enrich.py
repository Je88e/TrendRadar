# coding=utf-8
"""固定词组 RSS 统计补充测试（AAA 结构）。

count_rss_frequency（analyzer）在 count==0 丢弃词组（:672），
固定词组因此不在 rss_items。enrich_rss_stats_with_pinned 按
display_name 重新注入固定空词组占位（pinned=True），不改 analyzer（§4）。
"""

from trendradar.report.generator import enrich_rss_stats_with_pinned


class TestEnrichRssWithPinned:
    def test_absent_pinned_kw_appended_as_empty_placeholder(self):
        rss_stats = [{"word": "苹果", "count": 2, "titles": [{"title": "x"}], "percentage": 100}]
        result = enrich_rss_stats_with_pinned(rss_stats, {"华为"})
        # 原有条目保留
        assert result[0]["word"] == "苹果"
        # 固定空词组追加在末尾
        pinned = [s for s in result if s["word"] == "华为"]
        assert len(pinned) == 1
        assert pinned[0]["count"] == 0
        assert pinned[0]["titles"] == []
        assert pinned[0]["pinned"] is True

    def test_present_pinned_kw_not_duplicated(self):
        rss_stats = [{"word": "华为", "count": 3, "titles": [{"title": "x"}], "percentage": 100}]
        result = enrich_rss_stats_with_pinned(rss_stats, {"华为"})
        huawei = [s for s in result if s["word"] == "华为"]
        assert len(huawei) == 1
        # 原有匹配数保留，不重置为 0
        assert huawei[0]["count"] == 3

    def test_empty_pinned_set_returns_copy_unchanged(self):
        rss_stats = [{"word": "苹果", "count": 1, "titles": [], "percentage": 100}]
        result = enrich_rss_stats_with_pinned(rss_stats, set())
        assert result == rss_stats
        # 不可变：返回新列表对象（非同一引用）
        assert result is not rss_stats

    def test_does_not_mutate_input(self):
        rss_stats = [{"word": "苹果", "count": 1, "titles": [], "percentage": 100}]
        original = list(rss_stats)
        enrich_rss_stats_with_pinned(rss_stats, {"华为"})
        assert rss_stats == original
