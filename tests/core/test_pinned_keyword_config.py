# coding=utf-8
"""固定词组（pinned_keywords）配置加载测试（AAA 结构）。

覆盖：_load_report_config 中 report.display.pinned_keywords 的
默认空（功能关闭）/ 列表加载 / 值保持 display_name 原样（不大写）。
"""

import pytest

from trendradar.core.loader import _load_report_config


class TestLoadPinnedKeywords:
    def test_default_empty_when_block_absent(self):
        # report.display 缺失 → PINNED_KEYWORDS 为空集合，功能关闭
        cfg = _load_report_config({})
        assert cfg["PINNED_KEYWORDS"] == set()

    def test_list_loads_as_set_preserving_display_name(self):
        # report.display.pinned_keywords 列表 → 集合；值保持 display_name 原样（中文/大小写不变）
        raw = {"report": {"display": {"pinned_keywords": ["华为", "Apple"]}}}
        cfg = _load_report_config(raw)
        assert cfg["PINNED_KEYWORDS"] == {"华为", "Apple"}

    def test_empty_list_means_feature_off(self):
        raw = {"report": {"display": {"pinned_keywords": []}}}
        cfg = _load_report_config(raw)
        assert cfg["PINNED_KEYWORDS"] == set()
