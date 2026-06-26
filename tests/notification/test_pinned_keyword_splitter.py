# coding=utf-8
"""固定词组分批渲染守卫测试（AAA 结构）。

split_content_into_batches 热榜路径：count==0 固定空词组不进任何分批，
序列号 [i/N] 不断层。RSS 平台轴（rss_items）不经 pinned，不在此测。
"""

from trendradar.notification.splitter import split_content_into_batches


def _title(name="t1"):
    return {
        "title": name, "source_name": "src", "time_display": "",
        "count": 1, "ranks": [1], "rank_threshold": 3,
        "url": "", "mobile_url": "", "is_new": False,
    }


def _report_data():
    return {
        "stats": [
            {"word": "华为", "count": 0, "titles": [], "percentage": 0, "pinned": True},
            {"word": "Apple", "count": 1, "titles": [_title()], "percentage": 100},
        ],
        "new_titles": [],
        "failed_ids": [],
        "total_new_count": 0,
    }


class TestSplitterPinnedGuard:
    def test_hotlist_skips_pinned_empty_continuous_sequence(self):
        batches = split_content_into_batches(
            report_data=_report_data(),
            format_type="feishu",
            max_bytes=100000,
        )
        joined = "\n".join(batches)
        assert "华为" not in joined
        assert "Apple" in joined
        assert "[1/1]" in joined
        assert "[1/2]" not in joined
        assert "[2/2]" not in joined
