# coding=utf-8
"""固定词组 generator 旁路测试（AAA 结构）。

覆盖 prepare_report_data：
- 非固定空词组仍丢弃（向后兼容）
- 固定空词组保留 + pinned=True
- 固定词组有匹配时正常保留（无 pinned 标记）
- 未命中告警 / 重复 display_name 全匹配
"""

from trendradar.report.generator import prepare_report_data


def _stat(word, count, titles=None):
    """构造最小 stat 输入（filter 路径只读 word/count/titles/percentage）。"""
    return {"word": word, "count": count, "titles": titles or [], "percentage": 0}


def _title(name="t"):
    return {
        "title": name, "source_name": "src", "time_display": "",
        "count": 1, "ranks": [1], "rank_threshold": 3,
        "url": "", "mobileUrl": "",
    }


class TestPinnedBypass:
    def test_non_pinned_empty_dropped(self):
        # count==0 且非固定 → 丢弃（保留既有行为）
        stats = [_stat("foo", 0)]
        out = prepare_report_data(stats, pinned_keywords=set())
        assert out["stats"] == []

    def test_pinned_empty_kept_and_flagged(self):
        # count==0 但 word 在 pinned 集合 → 保留 + pinned=True，titles=[]
        stats = [_stat("华为", 0)]
        out = prepare_report_data(stats, pinned_keywords={"华为"})
        assert len(out["stats"]) == 1
        s = out["stats"][0]
        assert s["word"] == "华为"
        assert s["count"] == 0
        assert s["titles"] == []
        assert s.get("pinned") is True

    def test_pinned_with_matches_kept_no_flag(self):
        # 固定词组本轮有匹配 → 正常保留，不加 pinned 标记（避免噪声）
        stats = [_stat("华为", 1, [_title()])]
        out = prepare_report_data(stats, pinned_keywords={"华为"})
        assert len(out["stats"]) == 1
        s = out["stats"][0]
        assert s["count"] == 1
        assert "pinned" not in s
        assert len(s["titles"]) == 1

    def test_unmatched_pinned_warns_and_skips(self, capsys):
        # pinned 中存在词组本轮未加载/未匹配 → 告警且不中断，不出现在输出
        stats = [_stat("华为", 1, [_title()])]
        out = prepare_report_data(stats, pinned_keywords={"华为", "Ghost"})
        words = [s["word"] for s in out["stats"]]
        assert "Ghost" not in words
        captured = capsys.readouterr().out
        assert "[pinned]" in captured
        assert "Ghost" in captured

    def test_duplicate_display_name_matches_all(self):
        # 重复 display_name：固定匹配所有同名词组（不拒绝、不取首）
        stats = [_stat("华为", 0), _stat("华为", 0)]
        out = prepare_report_data(stats, pinned_keywords={"华为"})
        assert len(out["stats"]) == 2
        assert all(s.get("pinned") is True for s in out["stats"])
