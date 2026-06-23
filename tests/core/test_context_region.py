# coding=utf-8
"""AppContext 地区分类接入测试（AAA 结构）。

覆盖：region_classify 配置属性、region_map 显示开关联动、
get_region_classifier 懒构造（注入 normalizer + country_list）。
"""

from unittest.mock import patch

import pytest

from trendradar.context import AppContext


def _make_config(region_classify=None, regions=None, region_order=None):
    return {
        "REGION_CLASSIFY": region_classify or {"ENABLED": False, "BATCH_SIZE": 200,
                                               "BATCH_INTERVAL": 2, "PROMPT_FILE": "prompt.txt"},
        "DISPLAY": {
            "REGION_ORDER": region_order or ["hotlist", "ai_analysis"],
            "REGIONS": regions or {"HOTLIST": True, "NEW_ITEMS": True, "RSS": True,
                                    "STANDALONE": False, "AI_ANALYSIS": True, "REGION_MAP": False},
        },
        "AI": {"MODEL": "test/test", "API_KEY": "test"},
    }


@pytest.fixture
def ctx():
    return AppContext(_make_config())


class TestRegionClassifyConfig:
    def test_region_classify_config_property(self, ctx):
        cfg = ctx.region_classify_config
        assert cfg["ENABLED"] is False
        assert cfg["BATCH_SIZE"] == 200

    def test_region_classify_enabled_reads_flag(self):
        c = AppContext(_make_config(region_classify={"ENABLED": True}))
        assert c.region_classify_enabled is True

    def test_region_map_enabled_reflects_display(self):
        c = AppContext(_make_config(
            regions={"HOTLIST": True, "NEW_ITEMS": True, "RSS": True,
                     "STANDALONE": False, "AI_ANALYSIS": True, "REGION_MAP": True},
        ))
        assert c.region_map_enabled is True

    def test_region_map_disabled_by_default(self, ctx):
        assert ctx.region_map_enabled is False


class TestGetRegionClassifier:
    def test_returns_none_when_disabled(self, ctx):
        assert ctx.get_region_classifier() is None

    def test_builds_classifier_when_enabled(self):
        """enabled=true → 构造 RegionClassifier（注入 normalizer + country_list）。"""
        config = _make_config(region_classify={"ENABLED": True, "BATCH_SIZE": 200,
                                               "BATCH_INTERVAL": 2, "PROMPT_FILE": "prompt.txt"})
        c = AppContext(config)
        clf = c.get_region_classifier()
        assert clf is not None
        # 归一化器与国家列表已注入
        assert clf.normalizer is not None
        assert clf._country_list  # 非空字符串（含真实国名）
        assert "中国" in clf._country_list

    def test_classifier_cached(self):
        """get_region_classifier 懒构造单例。"""
        config = _make_config(region_classify={"ENABLED": True})
        c = AppContext(config)
        clf1 = c.get_region_classifier()
        clf2 = c.get_region_classifier()
        assert clf1 is clf2


class TestGetRegionMapPayload:
    def _enabled_ctx(self):
        return AppContext(_make_config(
            regions={"HOTLIST": True, "NEW_ITEMS": True, "RSS": True,
                     "STANDALONE": False, "AI_ANALYSIS": True, "REGION_MAP": True},
        ))

    def test_returns_none_when_disabled(self, ctx):
        assert ctx.get_region_map_payload() is None

    def test_builds_payload_when_enabled(self):
        c = self._enabled_ctx()
        active = {"hotlist": [
            {"news_item_id": 1, "source_type": "hotlist", "level": "city",
             "confidence": 0.9, "country": "中国", "country_code": "CN",
             "province": "广东省", "province_adcode": "440000",
             "city": "广州市", "city_adcode": "440100",
             "title": "广州新闻", "source_name": "微博", "url": "",
             "ranks": [1], "rank": None},
        ], "rss": []}
        with patch.object(c, "get_storage_manager") as m_storage:
            m_storage.return_value.get_active_region_classify_results.return_value = active
            payload = c.get_region_map_payload()
        assert payload is not None
        assert payload["world"][0]["code"] == "CN"
        # echarts 世界名已注入（normalizer 真实数据）
        assert payload["world"][0]["echarts_name"] == "China"
        assert payload["world"][0]["provinces"][0]["cities"][0]["items"][0]["title"] == "广州新闻"

    def test_empty_active_when_enabled(self):
        c = self._enabled_ctx()
        with patch.object(c, "get_storage_manager") as m_storage:
            m_storage.return_value.get_active_region_classify_results.return_value = {"hotlist": [], "rss": []}
            payload = c.get_region_map_payload()
        assert payload == {"world": [], "unknown": {"count": 0, "items": []}}

    def test_filters_active_by_stats_when_provided(self):
        """传入 stats/rss_items → payload 仅含命中的 (source_name, title)。"""
        c = self._enabled_ctx()
        active = {"hotlist": [
            {"news_item_id": 1, "source_type": "hotlist", "level": "city",
             "confidence": 0.9, "country": "中国", "country_code": "CN",
             "province": "广东省", "province_adcode": "440000",
             "city": "广州市", "city_adcode": "440100",
             "title": "命中", "source_name": "微博", "url": "",
             "ranks": [1], "rank": None},
            {"news_item_id": 2, "source_type": "hotlist", "level": "city",
             "confidence": 0.9, "country": "中国", "country_code": "CN",
             "province": "北京市", "province_adcode": "110000",
             "city": "北京市", "city_adcode": "110100",
             "title": "未命中", "source_name": "知乎", "url": "",
             "ranks": [1], "rank": None},
        ], "rss": []}
        stats = [{"word": "关键词", "count": 1, "titles": [
            {"title": "命中", "source_name": "微博"},
        ]}]
        with patch.object(c, "get_storage_manager") as m_storage:
            m_storage.return_value.get_active_region_classify_results.return_value = active
            payload = c.get_region_map_payload(stats=stats, rss_items=[])
        # 仅"命中"保留 → 广东省，北京市被滤掉
        cn = payload["world"][0]
        assert cn["count"] == 1
        provs = [p["adcode"] for p in cn["provinces"]]
        assert provs == ["440000"]

    def test_no_filter_when_stats_omitted(self):
        """stats/rss_items 都缺省 → 不过滤（向后兼容旧调用）。"""
        c = self._enabled_ctx()
        active = {"hotlist": [
            {"news_item_id": 1, "source_type": "hotlist", "level": "country",
             "confidence": 0.9, "country": "美国", "country_code": "US",
             "title": "A", "source_name": "微博", "url": "",
             "ranks": [], "rank": None},
        ], "rss": []}
        with patch.object(c, "get_storage_manager") as m_storage:
            m_storage.return_value.get_active_region_classify_results.return_value = active
            payload = c.get_region_map_payload()
        assert payload["world"][0]["count"] == 1  # 未滤掉
