# coding=utf-8
"""地区地图区不进通知：splitter/renderer 必须过滤 region_map（阶段 6）。"""

from trendradar.notification.renderer import render_feishu_content, render_dingtalk_content
from trendradar.notification.splitter import split_content_into_batches


def _empty_report_data():
    return {"stats": [], "new_titles": [], "failed_ids": [], "total_new_count": 0}


class TestRegionMapExcludedFromNotifications:
    def test_feishu_excludes_region_map(self):
        """region_order 含 region_map → 渲染结果不含地图标记/报错。"""
        rd = _empty_report_data()
        html = render_feishu_content(
            report_data=rd, mode="daily",
            region_order=["hotlist", "region_map", "ai_analysis"],
        )
        assert "region-map-section" not in html
        assert "按地区分布" not in html

    def test_dingtalk_excludes_region_map(self):
        rd = _empty_report_data()
        html = render_dingtalk_content(
            report_data=rd, mode="daily",
            region_order=["hotlist", "region_map"],
        )
        assert "region-map-section" not in html

    def test_splitter_excludes_region_map(self):
        rd = _empty_report_data()
        batches = split_content_into_batches(
            report_data=rd, format_type="default", mode="daily",
            region_order=["hotlist", "region_map", "ai_analysis"],
            batch_sizes={"default": 4000},
        )
        joined = "".join(batches) if batches else ""
        assert "region-map-section" not in joined
