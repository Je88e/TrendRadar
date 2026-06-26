# coding=utf-8
"""固定词组通知渲染守卫测试（AAA 结构）。

覆盖 render_feishu_content / render_dingtalk_content：
- count==0 的固定空词组不出现在通知正文
- 序列号 [i/N] 不断层（N = 非空 stats 数，非总数）
"""

from trendradar.notification.renderer import (
    render_dingtalk_content,
    render_feishu_content,
)


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


class TestRendererPinnedGuard:
    def test_feishu_skips_pinned_empty_continuous_sequence(self):
        out = render_feishu_content(_report_data())
        # 固定空词组不进正文
        assert "华为" not in out
        assert "Apple" in out
        # 序列号连续：非空仅 1 项 → [1/1]，而非 [1/2]
        assert "[1/1]" in out
        assert "[1/2]" not in out
        assert "[2/2]" not in out

    def test_dingtalk_skips_pinned_empty_continuous_sequence(self):
        out = render_dingtalk_content(_report_data())
        assert "华为" not in out
        assert "Apple" in out
        assert "[1/1]" in out
        assert "[1/2]" not in out
