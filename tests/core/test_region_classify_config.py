# coding=utf-8
"""地区分类配置加载测试（AAA 结构）。

覆盖：_load_region_classify_config 默认/自定义/环境变量、
_display_config 认 region_map（开关关时不进 region_order）。
"""

import os

import pytest

from trendradar.core.loader import (
    _load_display_config,
    _load_region_classify_config,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """清掉环境变量，避免污染默认值测试。"""
    for key in ("REGION_CLASSIFY_ENABLED",):
        monkeypatch.delenv(key, raising=False)


# ── _load_region_classify_config ──


class TestLoadRegionClassifyConfig:
    def test_defaults_when_block_absent(self):
        cfg = _load_region_classify_config({})
        assert cfg["ENABLED"] is False
        assert cfg["BATCH_SIZE"] == 200
        assert cfg["BATCH_INTERVAL"] == 2
        assert cfg["PROMPT_FILE"] == "prompt.txt"

    def test_explicit_values(self):
        raw = {
            "region_classify": {
                "enabled": True,
                "batch_size": 50,
                "batch_interval": 3,
                "prompt_file": "custom_prompt.txt",
            }
        }
        cfg = _load_region_classify_config(raw)
        assert cfg["ENABLED"] is True
        assert cfg["BATCH_SIZE"] == 50
        assert cfg["BATCH_INTERVAL"] == 3
        assert cfg["PROMPT_FILE"] == "custom_prompt.txt"

    def test_env_enabled_overrides(self, monkeypatch):
        monkeypatch.setenv("REGION_CLASSIFY_ENABLED", "true")
        cfg = _load_region_classify_config({})
        assert cfg["ENABLED"] is True

    def test_env_disabled_overrides(self, monkeypatch):
        # 配置写 true，但环境变量 false → 环境变量优先
        monkeypatch.setenv("REGION_CLASSIFY_ENABLED", "false")
        raw = {"region_classify": {"enabled": True}}
        cfg = _load_region_classify_config(raw)
        assert cfg["ENABLED"] is False


# ─_ display config region_map 接入 ──


class TestDisplayRegionMap:
    def test_region_map_absent_from_order_when_not_in_config(self):
        """region_map 不在 region_order 配置中 → 不出现。"""
        raw = {"display": {"regions": {"region_map": True}}}
        cfg = _load_display_config(raw)
        assert "region_map" not in cfg["REGION_ORDER"]
        assert cfg["REGIONS"]["REGION_MAP"] is True

    def test_region_map_in_order_preserved_when_enabled(self):
        """region_map 在 region_order 且开关 true → 保留在顺序中。"""
        raw = {
            "display": {
                "region_order": ["hotlist", "region_map", "ai_analysis"],
                "regions": {"region_map": True},
            }
        }
        cfg = _load_display_config(raw)
        assert "region_map" in cfg["REGION_ORDER"]

    def test_region_map_dropped_from_order_when_disabled(self):
        """region_map 在 region_order 但 regions.region_map=false → 从顺序移除。"""
        raw = {
            "display": {
                "region_order": ["hotlist", "region_map", "ai_analysis"],
                "regions": {"region_map": False},
            }
        }
        cfg = _load_display_config(raw)
        assert "region_map" not in cfg["REGION_ORDER"]
        assert cfg["REGIONS"]["REGION_MAP"] is False

    def test_region_map_default_false(self):
        cfg = _load_display_config({})
        assert cfg["REGIONS"]["REGION_MAP"] is False
        assert "region_map" not in cfg["REGION_ORDER"]
