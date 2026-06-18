# coding=utf-8
"""run_region_classify 触发流程测试（AAA 结构）。

Mock RegionClassifier + storage，验证编排：去重 / 批分类 / 落库 / 返回 active 树。
不发起真实 AI 请求。
"""

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from trendradar.context import AppContext


def _title_hash(title: str) -> str:
    return hashlib.md5(title.encode("utf-8")).hexdigest()


def _config(enabled=True):
    return {
        "REGION_CLASSIFY": {"ENABLED": enabled, "BATCH_SIZE": 200,
                            "BATCH_INTERVAL": 0, "PROMPT_FILE": "prompt.txt"},
        "DISPLAY": {"REGION_ORDER": [], "REGIONS": {"REGION_MAP": enabled}},
        "AI": {"MODEL": "test/test", "API_KEY": "test"},
        "RSS": {"ENABLED": False},
        "TIMEZONE": "UTC",
    }


@pytest.fixture
def ctx():
    c = AppContext(_config())
    # 注入 mock storage
    c._storage_manager = MagicMock()
    c._storage_manager.backend_name = "mock"
    return c


class TestRunRegionClassifyGate:
    def test_disabled_returns_none(self):
        c = AppContext(_config(enabled=False))
        c._storage_manager = MagicMock()
        assert c.run_region_classify() is None

    def test_no_news_returns_empty_tree(self, ctx):
        """无待分类新闻 → 返回空 active 树（不调 AI）。"""
        ctx._storage_manager.get_all_news_ids.return_value = []
        ctx._storage_manager.get_region_classify_analyzed.return_value = {}
        ctx._storage_manager.get_active_region_classify_results.return_value = {"hotlist": []}

        with patch.object(ctx, "get_region_classifier") as mock_clf:
            result = ctx.run_region_classify()
            # 无待分类 → classifier.classify_batch 不应被调用
            mock_clf.return_value.classify_batch.assert_not_called()

        assert result == {"hotlist": []}


class TestRunRegionClassifyDedup:
    def test_skips_already_analyzed(self, ctx):
        """content_hash 命中已分析记录 → 跳过（不重复发给 AI）。"""
        news = [
            {"id": 1, "title": "已分析", "source_name": "test"},
            {"id": 2, "title": "新新闻", "source_name": "test"},
        ]
        ctx._storage_manager.get_all_news_ids.return_value = news
        # id=1 已分析
        ctx._storage_manager.get_region_classify_analyzed.return_value = {
            1: _title_hash("已分析"),
        }
        ctx._storage_manager.get_active_region_classify_results.return_value = {"hotlist": []}

        mock_clf = MagicMock()
        mock_clf.classify_batch.return_value = [
            {"id": 2, "level": "city", "country": "中国", "country_code": "CN",
             "country_echarts": "China", "province": "广东省", "province_adcode": "440000",
             "city": "广州市", "city_adcode": "440100", "confidence": 0.9},
        ]

        with patch.object(ctx, "get_region_classifier", return_value=mock_clf):
            ctx.run_region_classify()

        # 只发了 id=2 给 AI（1 条）
        called_titles = mock_clf.classify_batch.call_args[0][0]
        assert [t["id"] for t in called_titles] == [2]


class TestRunRegionClassifyReclassify:
    def test_title_changed_triggers_reclassify(self, ctx):
        """标题变更（hash 不同）→ 视为未分析 → 重新分类。"""
        news = [{"id": 1, "title": "新标题", "source_name": "test"}]
        ctx._storage_manager.get_all_news_ids.return_value = news
        # DB 记录的是旧标题 hash
        ctx._storage_manager.get_region_classify_analyzed.return_value = {
            1: _title_hash("旧标题"),
        }
        ctx._storage_manager.get_active_region_classify_results.return_value = {"hotlist": []}

        mock_clf = MagicMock()
        mock_clf.classify_batch.return_value = [
            {"id": 1, "level": "city", "country": "中国", "country_code": "CN",
             "country_echarts": "China", "province": "广东省", "province_adcode": "440000",
             "city": "广州市", "city_adcode": "440100", "confidence": 0.9},
        ]

        with patch.object(ctx, "get_region_classifier", return_value=mock_clf):
            ctx.run_region_classify()

        # id=1 被重新发给 AI
        called_titles = mock_clf.classify_batch.call_args[0][0]
        assert [t["id"] for t in called_titles] == [1]


class TestRunRegionClassifyPersist:
    def test_saves_results_and_marks_analyzed(self, ctx):
        """分类成功 → 落库 + 标记已分析。"""
        news = [{"id": 1, "title": "x", "source_name": "test"}]
        ctx._storage_manager.get_all_news_ids.return_value = news
        ctx._storage_manager.get_region_classify_analyzed.return_value = {}
        ctx._storage_manager.get_active_region_classify_results.return_value = {"hotlist": []}

        mock_clf = MagicMock()
        results = [{"id": 1, "level": "city", "country": "中国", "country_code": "CN",
                    "country_echarts": "China", "province": "广东省", "province_adcode": "440000",
                    "city": "广州市", "city_adcode": "440100", "confidence": 0.9}]
        mock_clf.classify_batch.return_value = results

        with patch.object(ctx, "get_region_classifier", return_value=mock_clf):
            ctx.run_region_classify()

        # 结果落库（save_region_classify_results 被调用）
        ctx._storage_manager.save_region_classify_results.assert_called_once()
        saved = ctx._storage_manager.save_region_classify_results.call_args[0][0]
        assert saved[0]["id"] == 1
        assert saved[0]["source_type"] == "hotlist"

        # 已分析标记
        ctx._storage_manager.mark_region_classify_analyzed.assert_called_once()
        records = ctx._storage_manager.mark_region_classify_analyzed.call_args[0][0]
        assert records[0][0] == 1  # news_id
        assert records[0][2] == _title_hash("x")  # content_hash

    def test_failed_batch_not_marked_analyzed(self, ctx):
        """AI 调用失败（classify_batch 返 None）→ 不标记已分析（下次重试）。"""
        news = [{"id": 1, "title": "x", "source_name": "test"}]
        ctx._storage_manager.get_all_news_ids.return_value = news
        ctx._storage_manager.get_region_classify_analyzed.return_value = {}
        ctx._storage_manager.get_active_region_classify_results.return_value = {"hotlist": []}

        mock_clf = MagicMock()
        mock_clf.classify_batch.return_value = None  # 失败

        with patch.object(ctx, "get_region_classifier", return_value=mock_clf):
            ctx.run_region_classify()

        ctx._storage_manager.save_region_classify_results.assert_not_called()
        ctx._storage_manager.mark_region_classify_analyzed.assert_not_called()
