# coding=utf-8
"""RegionNormalizer 单元测试（AAA 结构）。

覆盖：中国省市全称/简称 → adcode、国家 → ISO+ECharts 名、
海外省市仅文本无 adcode、unknown、归一化失败优雅降级。
"""

import pytest

from trendradar.regions.normalizer import RegionNormalizer

# 代表性小数据集（结构与真实 china.json/countries.json 一致）
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
def norm():
    return RegionNormalizer(countries=COUNTRIES, china=CHINA)


class TestChinaCityLevel:
    def test_full_names_resolve_adcodes(self, norm):
        # Arrange / Act
        r = norm.normalize("city", "中国", "广东省", "广州市")
        # Assert
        assert r.country_code == "CN"
        assert r.country_echarts == "China"
        assert r.country == "中国"
        assert r.province_adcode == "440000"
        assert r.province == "广东省"
        assert r.city_adcode == "440100"
        assert r.city == "广州市"

    def test_short_aliases_normalize_to_full(self, norm):
        # Act
        r = norm.normalize("city", "中国", "广东", "广州")
        # Assert
        assert r.province_adcode == "440000"
        assert r.province == "广东省"
        assert r.city_adcode == "440100"
        assert r.city == "广州市"


class TestCountryOnly:
    def test_overseas_country_resolves_iso(self, norm):
        r = norm.normalize("country", "美国", None, None)
        assert r.country_code == "US"
        assert r.country_echarts == "United States"
        assert r.province is None and r.city is None
        assert r.province_adcode is None and r.city_adcode is None

    def test_country_alias(self, norm):
        r = norm.normalize("country", "美利坚合众国", None, None)
        assert r.country_code == "US"
        assert r.country == "美国"


class TestOverseasNoAdcode:
    """ADR-0001：海外止于国家级，省/市仅文本，无 adcode。"""

    def test_overseas_province_city_text_only(self, norm):
        r = norm.normalize("city", "美国", "加利福尼亚州", "旧金山")
        assert r.country_code == "US"
        assert r.province == "加利福尼亚州"
        assert r.province_adcode is None
        assert r.city == "旧金山"
        assert r.city_adcode is None


class TestUnknown:
    def test_unknown_level_yields_empty(self, norm):
        r = norm.normalize("unknown", None, None, None)
        assert r.country is None
        assert r.country_code is None
        assert r.country_echarts is None
        assert r.province is None and r.city is None


class TestGracefulFallback:
    """ADR-0002：归一化失败不阻断，照存名字，code 留 NULL。"""

    def test_unknown_country_keeps_name_no_code(self, norm):
        r = norm.normalize("country", "亚特兰蒂斯", None, None)
        assert r.country == "亚特兰蒂斯"
        assert r.country_code is None
        assert r.country_echarts is None

    def test_china_province_not_in_table(self, norm):
        r = norm.normalize("province", "中国", "某个新省", None)
        assert r.country_code == "CN"
        assert r.province == "某个新省"
        assert r.province_adcode is None

    def test_china_city_not_in_table(self, norm):
        r = norm.normalize("city", "中国", "广东省", "某新城")
        assert r.country_code == "CN"
        assert r.province_adcode == "440000"
        assert r.city == "某新城"
        assert r.city_adcode is None

    def test_level_case_insensitive(self, norm):
        r = norm.normalize("CITY", "中国", "广东省", "广州市")
        assert r.city_adcode == "440100"


class TestGetCountryEchartsMap:
    def test_returns_code_to_echarts_name(self, norm):
        m = norm.get_country_echarts_map()
        assert isinstance(m, dict)
        assert len(m) >= 3  # 至少三个真实国家
        assert m["CN"] == "China"
        assert m["US"]  # 非空

    def test_no_echarts_name_excluded(self, norm):
        """echarts_name 缺失的国家不应出现在映射中。"""
        m = norm.get_country_echarts_map()
        assert "" not in m
        assert None not in m.values()
        # 所有值非空
        for code, name in m.items():
            assert name, f"code {code} has empty echarts_name"

    def test_keys_are_iso_alpha2(self, norm):
        """所有 key 为 2 大写字母 ISO alpha-2 码。"""
        import re
        m = norm.get_country_echarts_map()
        alpha2_re = re.compile(r"^[A-Z]{2}$")
        for code in m:
            assert alpha2_re.match(code), f"不是 ISO alpha-2: {code}"

    def test_idempotent(self, norm):
        m1 = norm.get_country_echarts_map()
        m2 = norm.get_country_echarts_map()
        assert m1 == m2  # 相同对象或等价
