# coding=utf-8
"""RegionClassifier AI 模块测试（AAA 结构）。

覆盖：_parse_response 全级别 / 边缘 / 容错、classify_batch 批次编排。
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from trendradar.ai.region import RegionClassifier
from trendradar.regions.normalizer import RegionNormalizer

# ── 小型归一化数据（结构与真实数据一致）──
COUNTRIES = [
    {"code": "CN", "name": "中国", "echarts_name": "China", "aliases": ["中华人民共和国"]},
    {"code": "US", "name": "美国", "echarts_name": "United States", "aliases": ["美利坚合众国"]},
    {"code": "JP", "name": "日本", "echarts_name": "Japan", "aliases": []},
]
CHINA = {
    "provinces": [
        {
            "adcode": "440000", "name": "广东省", "aliases": ["广东"],
            "cities": [
                {"adcode": "440100", "name": "广州市", "aliases": ["广州"]},
                {"adcode": "440300", "name": "深圳市", "aliases": ["深圳"]},
            ],
        },
        {"adcode": "110000", "name": "北京市", "aliases": ["北京"], "cities": []},
    ]
}


@pytest.fixture
def normalizer():
    return RegionNormalizer(countries=COUNTRIES, china=CHINA)


def _classifier(normalizer, ai_config=None):
    """构造最小 RegionClassifier，不依赖真实 AIClient。"""
    from unittest.mock import MagicMock

    return RegionClassifier(
        ai_config=ai_config or {"MODEL": "test/test", "API_KEY": "test"},
        normalizer=normalizer,
        region_classify_config={"BATCH_SIZE": 200, "BATCH_INTERVAL": 1},
        get_time_func=lambda: "2025-01-01T00:00:00",
        country_list="中国、美国、日本",
        debug=True,
    )


class TestParseResponse:
    """_parse_response 解析行为测试（阶段 2 核心）。"""

    # ── 正常路径 ──

    def test_city_level_with_adcodes(self, normalizer):
        """中国省会城市：AI 输出完整 → 归一化出 country/province/city adcode。"""
        raw = '[{"id":1,"level":"city","country":"中国","province":"广东省","city":"广州市","confidence":0.9}]'
        clf = _classifier(normalizer)
        results = clf._parse_response(raw, {1})
        assert len(results) == 1
        r = results[0]
        assert r["id"] == 1
        assert r["level"] == "city"
        assert r["country"] == "中国"
        assert r["country_code"] == "CN"
        assert r["country_echarts"] == "China"
        assert r["province"] == "广东省"
        assert r["province_adcode"] == "440000"
        assert r["city"] == "广州市"
        assert r["city_adcode"] == "440100"
        assert r["confidence"] == 0.9

    def test_country_level_overseas(self, normalizer):
        """海外国家级：有 country + code，无 province/city。"""
        raw = '[{"id":2,"level":"country","country":"美国","confidence":0.7}]'
        clf = _classifier(normalizer)
        results = clf._parse_response(raw, {2})
        r = results[0]
        assert r["level"] == "country"
        assert r["country"] == "美国"
        assert r["country_code"] == "US"
        assert r["country_echarts"] == "United States"
        assert r["province"] is None
        assert r["province_adcode"] is None
        assert r["city"] is None
        assert r["city_adcode"] is None

    def test_unknown_level(self, normalizer):
        """unknown：仅 id+level+confidence，无地区字段。"""
        raw = '[{"id":3,"level":"unknown","confidence":0.1}]'
        clf = _classifier(normalizer)
        results = clf._parse_response(raw, {3})
        r = results[0]
        assert r["level"] == "unknown"
        assert r["country"] is None
        assert r["country_code"] is None
        assert r["confidence"] == 0.1

    def test_province_level(self, normalizer):
        """省级：AI 输出省份 → 有 province adcode，无 city。"""
        raw = '[{"id":4,"level":"province","country":"中国","province":"广东省","confidence":0.8}]'
        clf = _classifier(normalizer)
        results = clf._parse_response(raw, {4})
        r = results[0]
        assert r["level"] == "province"
        assert r["province"] == "广东省"
        assert r["province_adcode"] == "440000"
        assert r["city"] is None
        assert r["city_adcode"] is None

    # ── 容错 ──

    def test_out_of_range_level_coerced_to_unknown(self, normalizer):
        """非法 level（如 continent）→ 强转为 unknown。"""
        raw = '[{"id":5,"level":"continent","country":"亚洲","confidence":0.5}]'
        clf = _classifier(normalizer)
        results = clf._parse_response(raw, {5})
        assert len(results) == 1
        assert results[0]["level"] == "unknown"
        assert results[0]["country"] is None

    def test_missing_confidence_default(self, normalizer):
        """AI 缺 confidence → 默认 0.0。"""
        raw = '[{"id":6,"level":"unknown"}]'
        clf = _classifier(normalizer)
        results = clf._parse_response(raw, {6})
        assert results[0]["confidence"] == 0.0

    def test_confidence_clamped(self, normalizer):
        """confidence 超 [0,1] → clamp。"""
        raw = '[{"id":7,"level":"unknown","confidence":2.5}]'
        clf = _classifier(normalizer)
        results = clf._parse_response(raw, {7})
        assert results[0]["confidence"] == 1.0

        raw2 = '[{"id":8,"level":"unknown","confidence":-0.3}]'
        results2 = clf._parse_response(raw2, {8})
        assert results2[0]["confidence"] == 0.0

    def test_skips_unknown_ids(self, normalizer):
        """AI 返回的 id 不在期望集合中 → 跳过。"""
        raw = '[{"id":99,"level":"city","country":"中国","province":"广东省","city":"广州市","confidence":0.9}]'
        clf = _classifier(normalizer)
        results = clf._parse_response(raw, {1, 2})
        assert results == []

    def test_missing_country_graceful_fallback(self, normalizer):
        """AI 输出 level=country 但未给 country 字段 → 容错。"""
        raw = '[{"id":9,"level":"country","confidence":0.6}]'
        clf = _classifier(normalizer)
        results = clf._parse_response(raw, {9})
        assert len(results) == 1
        assert results[0]["country"] is None
        assert results[0]["country_code"] is None

    # ── JSON 提取 ──

    def test_extracts_code_fenced_json(self, normalizer):
        """```json 包裹 + 前后 prose → 仍提取。"""
        raw = 'Here is the result:\n```json\n[{"id":10,"level":"country","country":"日本","confidence":0.6}]\n```\nDone.'
        clf = _classifier(normalizer)
        results = clf._parse_response(raw, {10})
        r = results[0]
        assert r["country"] == "日本"
        assert r["country_code"] == "JP"

    def test_extracts_plain_triple_backtick(self, normalizer):
        """仅 ``` 包裹（无 json 标记）→ 提取。"""
        raw = '```\n[{"id":11,"level":"unknown","confidence":0.3}]\n```'
        clf = _classifier(normalizer)
        results = clf._parse_response(raw, {11})
        assert len(results) == 1
        assert results[0]["level"] == "unknown"

    def test_invalid_json_returns_empty(self, normalizer):
        """非 JSON 响应 → 返回空列表（不抛异常）。"""
        raw = "Sorry, I cannot process this request."
        clf = _classifier(normalizer)
        results = clf._parse_response(raw, {1})
        assert results == []

    def test_empty_response_returns_empty(self, normalizer):
        clf = _classifier(normalizer)
        assert clf._parse_response("", {1}) == []
        assert clf._parse_response(None, {1}) == []


class TestClassifyBatch:
    """classify_batch 批次编排测试（mock AIClient 无真实网络调用）。"""

    def _mock_response(self, clf, json_text):
        """Patch clf.client.chat 返回指定 JSON 文本。"""
        clf.client.chat = MagicMock(return_value=json_text)

    def test_single_batch_returns_normalized(self, normalizer):
        """单批：mock AI → 返回归一化结果，含 unknown。"""
        ai_json = (
            '[{"id": 1, "level": "city", "country": "中国", "province": "广东省", "city": "广州市", "confidence": 0.9},'
            '{"id": 2, "level": "country", "country": "美国", "confidence": 0.6},'
            '{"id": 3, "level": "unknown", "confidence": 0.2}]'
        )
        clf = _classifier(normalizer)
        self._mock_response(clf, ai_json)

        titles = [
            {"id": 1, "title": "广州GDP增长", "source": "hotlist"},
            {"id": 2, "title": "美国CPI数据", "source": "hotlist"},
            {"id": 3, "title": "今天天气不错", "source": "hotlist"},
        ]
        results = clf.classify_batch(titles)
        assert results is not None
        assert len(results) == 3

        # 验证一条完整归一化
        city = next(r for r in results if r["id"] == 1)
        assert city["city_adcode"] == "440100"

        overseas = next(r for r in results if r["id"] == 2)
        assert overseas["country_code"] == "US"
        assert overseas["province"] is None

        unknown = next(r for r in results if r["id"] == 3)
        assert unknown["level"] == "unknown"
        assert unknown["country"] is None

    def test_client_raises_returns_none(self, normalizer):
        """AI 调用异常 → 返回 None（与返回[]区分，调用方可重试）。"""
        clf = _classifier(normalizer)
        clf.client.chat = MagicMock(side_effect=ConnectionError("API down"))

        titles = [{"id": 1, "title": "测试", "source": "test"}]
        results = clf.classify_batch(titles)
        assert results is None

    def test_empty_titles_returns_empty_list(self, normalizer):
        """空标题列表 → 直接返回 []。"""
        clf = _classifier(normalizer)
        results = clf.classify_batch([])
        assert results == []

    def test_all_titles_sent_to_ai(self, normalizer):
        """classify_batch 将全部标题一次性发给 AI（分批在 analyzer 层调度）。"""
        clf = _classifier(normalizer)
        titles = [
            {"id": i, "title": f"新闻{i}", "source": "test"}
            for i in range(1, 5)
        ]
        items = [{"id": i, "level": "unknown", "confidence": 0.1} for i in range(1, 5)]
        self._mock_response(clf, json.dumps(items, ensure_ascii=False))

        results = clf.classify_batch(titles)
        assert results is not None
        assert len(results) == 4
        assert clf.client.chat.call_count == 1

