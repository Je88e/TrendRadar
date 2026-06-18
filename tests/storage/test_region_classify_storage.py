# coding=utf-8
"""region_classify 存储层集成测试（in-memory via LocalStorageBackend）。

覆盖：去重查询、结果保存（含 upsert）、已分析标记、active 结果读取（JOIN news 详情）。
"""

import hashlib

import pytest

from trendradar.storage.local import LocalStorageBackend


@pytest.fixture
def backend(tmp_path):
    """临时目录构造后端，schema 自动建表。"""
    return LocalStorageBackend(data_dir=str(tmp_path), enable_txt=False, enable_html=False)


def _seed_news(backend, date, titles):
    """插几条 news_items 并返回 [{id,title,source_name,...}]。"""
    conn = backend._get_connection(date)
    now = backend._get_configured_time().strftime("%Y-%m-%d %H:%M:%S")
    items = []
    for i, title in enumerate(titles, start=1):
        conn.execute(
            "INSERT INTO news_items(platform_id, url, title, rank, first_crawl_time, "
            "last_crawl_time, crawl_count) VALUES(?,?,?,?,?,?,?)",
            ("test", f"http://x/{i}", title, 0, now, now, 1),
        )
        items.append({"id": i, "title": title})
    conn.commit()
    return items


def _title_hash(title: str) -> str:
    return hashlib.md5(title.encode("utf-8")).hexdigest()


class TestGetRegionClassifyAnalyzed:
    def test_empty_when_nothing_analyzed(self, backend):
        analyzed = backend.get_region_classify_analyzed("hotlist", date="2025-01-01")
        assert analyzed == {}

    def test_returns_news_id_to_hash_map(self, backend):
        date = "2025-01-01"
        _seed_news(backend, date, ["广州新闻", "美国新闻"])
        records = [
            (1, "hotlist", _title_hash("广州新闻"), "city"),
            (2, "hotlist", _title_hash("美国新闻"), "country"),
        ]
        backend.mark_region_classify_analyzed(records, source_type="hotlist", date=date)
        analyzed = backend.get_region_classify_analyzed("hotlist", date=date)
        assert analyzed[1] == _title_hash("广州新闻")
        assert analyzed[2] == _title_hash("美国新闻")

    def test_filters_by_source_type(self, backend):
        date = "2025-01-01"
        _seed_news(backend, date, ["x"])
        backend.mark_region_classify_analyzed(
            [(1, "hotlist", "h1", "city")], source_type="hotlist", date=date
        )
        # 查 rss 应为空
        assert backend.get_region_classify_analyzed("rss", date=date) == {}


class TestSaveRegionClassifyResults:
    def test_saves_and_returns_count(self, backend):
        date = "2025-01-01"
        _seed_news(backend, date, ["广州新闻"])
        results = [{
            "id": 1, "source_type": "hotlist", "level": "city",
            "country": "中国", "country_code": "CN", "country_echarts": "China",
            "province": "广东省", "province_adcode": "440000",
            "city": "广州市", "city_adcode": "440100", "confidence": 0.9,
        }]
        saved = backend.save_region_classify_results(results, date)
        assert saved == 1

    def test_upsert_on_same_news_source(self, backend):
        """同 (news_item_id, source_type) → UPSERT 覆盖（标题变更重分类）。"""
        date = "2025-01-01"
        _seed_news(backend, date, ["x"])
        r1 = {"id": 1, "source_type": "hotlist", "level": "country",
              "country": "美国", "country_code": "US", "country_echarts": "United States",
              "province": None, "province_adcode": None, "city": None, "city_adcode": None,
              "confidence": 0.6}
        backend.save_region_classify_results([r1], date)

        r2 = dict(r1, level="city", country="中国", country_code="CN",
                  country_echarts="China", province="广东省", province_adcode="440000",
                  city="广州市", city_adcode="440100", confidence=0.95)
        backend.save_region_classify_results([r2], date)

        active = backend.get_active_region_classify_results(date)
        hotlist = [r for r in active["hotlist"] if r["news_item_id"] == 1]
        assert len(hotlist) == 1  # 无重复
        assert hotlist[0]["level"] == "city"
        assert hotlist[0]["city_adcode"] == "440100"


class TestMarkRegionClassifyAnalyzed:
    def test_marks_multiple(self, backend):
        date = "2025-01-01"
        _seed_news(backend, date, ["a", "b"])
        records = [
            (1, "hotlist", "ha", "city"),
            (2, "hotlist", "hb", "unknown"),
        ]
        n = backend.mark_region_classify_analyzed(records, source_type="hotlist", date=date)
        assert n == 2
        analyzed = backend.get_region_classify_analyzed("hotlist", date=date)
        assert set(analyzed.keys()) == {1, 2}


class TestGetActiveRegionClassifyResults:
    def test_returns_tree_with_news_details(self, backend):
        date = "2025-01-01"
        _seed_news(backend, date, ["广州新闻", "美国新闻", "无地区"])
        results = [
            {"id": 1, "source_type": "hotlist", "level": "city",
             "country": "中国", "country_code": "CN", "country_echarts": "China",
             "province": "广东省", "province_adcode": "440000",
             "city": "广州市", "city_adcode": "440100", "confidence": 0.9},
            {"id": 2, "source_type": "hotlist", "level": "country",
             "country": "美国", "country_code": "US", "country_echarts": "United States",
             "province": None, "province_adcode": None, "city": None, "city_adcode": None,
             "confidence": 0.7},
            {"id": 3, "source_type": "hotlist", "level": "unknown",
             "country": None, "country_code": None, "country_echarts": None,
             "province": None, "province_adcode": None, "city": None, "city_adcode": None,
             "confidence": 0.1},
        ]
        backend.save_region_classify_results(results, date)
        active = backend.get_active_region_classify_results(date)
        assert "hotlist" in active
        assert len(active["hotlist"]) == 3
        # 含新闻详情
        city = next(r for r in active["hotlist"] if r["news_item_id"] == 1)
        assert city["title"] == "广州新闻"
        assert city["level"] == "city"
        assert city["city_adcode"] == "440100"
