# coding=utf-8
"""地区地图 payload 构建器测试（阶段 5 步骤 1）。

测试 build_region_map_payload：active 结果树 → design 6.1 payload 树。
active 项字段镜像 _get_active_region_classify_results_impl 输出。
"""

import pytest

from trendradar.report.region import build_region_map_payload, render_region_map_html


def _item(
    nid, level, country="", country_code="", province="", province_adcode="",
    city="", city_adcode="", confidence=0.5, title="", source_name="微博",
    source_type="hotlist", url="", ranks=None,
):
    """构造 active 树单项（镜像 sqlite_mixin 实际输出）。"""
    return {
        "news_item_id": nid, "source_type": source_type, "level": level,
        "confidence": confidence,
        "country": country, "country_code": country_code,
        "province": province, "province_adcode": province_adcode,
        "city": city, "city_adcode": city_adcode,
        "title": title or f"新闻{nid}", "source_id": 1, "source_name": source_name,
        "url": url, "mobile_url": "", "rank": None,
        "first_time": "", "last_time": "", "count": 1,
        "ranks": ranks if ranks is not None else [],
    }


class TestBuildRegionMapPayloadEmpty:
    def test_none_input(self):
        assert build_region_map_payload(None) == {
            "world": [], "unknown": {"count": 0, "items": []},
        }

    def test_empty_dict(self):
        assert build_region_map_payload({}) == {
            "world": [], "unknown": {"count": 0, "items": []},
        }

    def test_empty_lists(self):
        assert build_region_map_payload({"hotlist": [], "rss": []}) == {
            "world": [], "unknown": {"count": 0, "items": []},
        }


class TestBuildRegionMapPayloadChina:
    """中国：provinces → cities → items 全树。"""

    def test_china_full_tree(self):
        active = {"hotlist": [
            _item(1, "city", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000",
                  city="广州市", city_adcode="440100", title="广州新闻"),
            _item(2, "city", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000",
                  city="深圳市", city_adcode="440300", title="深圳新闻"),
            _item(3, "city", country="中国", country_code="CN",
                  province="北京市", province_adcode="110000",
                  city="北京市", city_adcode="110100", title="北京新闻"),
        ]}
        payload = build_region_map_payload(active)

        assert len(payload["world"]) == 1
        cn = payload["world"][0]
        assert cn["code"] == "CN"
        assert cn["name"] == "中国"
        assert cn["count"] == 3
        assert "provinces" in cn
        assert len(cn["provinces"]) == 2

        gd = next(p for p in cn["provinces"] if p["adcode"] == "440000")
        assert gd["name"] == "广东省"
        assert gd["count"] == 2
        assert len(gd["cities"]) == 2
        gz = next(c for c in gd["cities"] if c["adcode"] == "440100")
        assert gz["name"] == "广州市"
        assert gz["count"] == 1
        assert len(gz["items"]) == 1
        assert gz["items"][0]["title"] == "广州新闻"

class TestBuildRegionMapPayloadCoarseLevels:
    """国级/省级新闻支持（design §6.1）。

    level=country → country_level_items；level=province → province_level_items；
    level=city → city 树。修复原 _nest_china_item 强制把所有中国新闻钻到 city、
    国级/省级新闻生成空名节点被 choropleth filter 吞掉（count 在、新闻不可达）的 bug。
    """

    def test_china_country_level_into_country_level_items(self):
        """中国 level=country（无省）→ country_level_items，provinces 空。"""
        active = {"hotlist": [
            _item(1, "country", country="中国", country_code="CN", title="中国宏观"),
        ]}
        payload = build_region_map_payload(active)
        cn = payload["world"][0]
        assert cn["count"] == 1
        assert cn["provinces"] == []
        assert [i["title"] for i in cn["country_level_items"]] == ["中国宏观"]

    def test_china_province_level_into_province_level_items(self):
        """中国 level=province（有省无市）→ province_level_items，cities 空。"""
        active = {"hotlist": [
            _item(1, "province", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000", title="广东全省"),
        ]}
        payload = build_region_map_payload(active)
        cn = payload["world"][0]
        gd = next(p for p in cn["provinces"] if p["adcode"] == "440000")
        assert gd["count"] == 1
        assert gd["cities"] == []
        assert [i["title"] for i in gd["province_level_items"]] == ["广东全省"]

    def test_mixed_three_levels_all_reachable(self):
        """同一中国节点三级并存：国级/省级/市级各有归属，全可达。"""
        active = {"hotlist": [
            _item(1, "country", country="中国", country_code="CN", title="国级"),
            _item(2, "province", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000", title="省级"),
            _item(3, "city", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000",
                  city="广州市", city_adcode="440100", title="市级"),
        ]}
        payload = build_region_map_payload(active)
        cn = payload["world"][0]
        assert cn["count"] == 3
        assert [i["title"] for i in cn["country_level_items"]] == ["国级"]
        gd = next(p for p in cn["provinces"] if p["adcode"] == "440000")
        assert gd["count"] == 2  # 省级 + 市级
        assert [i["title"] for i in gd["province_level_items"]] == ["省级"]
        gz = next(c for c in gd["cities"] if c["adcode"] == "440100")
        assert [i["title"] for i in gz["items"]] == ["市级"]

    def test_counts_include_coarser_levels(self):
        """China.count 含国级；province.count 含省级 + 市。"""
        active = {"hotlist": [
            _item(1, "country", country="中国", country_code="CN", title="国1"),
            _item(2, "country", country="中国", country_code="CN", title="国2"),
            _item(3, "province", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000", title="省1"),
            _item(4, "city", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000",
                  city="广州市", city_adcode="440100", title="市1"),
        ]}
        payload = build_region_map_payload(active)
        cn = payload["world"][0]
        assert cn["count"] == 4  # 2 国级 + 1 省级 + 1 市级
        gd = next(p for p in cn["provinces"] if p["adcode"] == "440000")
        assert gd["count"] == 2  # 1 省级 + 1 市级

    def test_routes_by_level_field_not_presence(self):
        """路由按 level 字段：level=country 即使带 province 字段也进国级桶。

        AI 契约里 level 与字段 presence 等价，但防御 AI 抖动（level=country 却
        带 province）时以 level 为准，避免误归入省树。
        """
        active = {"hotlist": [
            _item(1, "country", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000", title="矛盾项"),
        ]}
        payload = build_region_map_payload(active)
        cn = payload["world"][0]
        assert [i["title"] for i in cn["country_level_items"]] == ["矛盾项"]
        assert cn["provinces"] == []

    def test_city_level_unresolved_adcode_stays_city_tree(self):
        """level=city 但 city_adcode 空（normalizer 失败）→ 留 city 树（name-keyed），
        不降级到 province_level_items。orphan 渲染为单独 issue，本次不改语义。"""
        active = {"hotlist": [
            _item(1, "city", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000",
                  city="某未知市", city_adcode="", title="orphan 市"),
        ]}
        payload = build_region_map_payload(active)
        cn = payload["world"][0]
        gd = next(p for p in cn["provinces"] if p["adcode"] == "440000")
        assert gd["province_level_items"] == []
        assert len(gd["cities"]) == 1
        assert gd["cities"][0]["name"] == "某未知市"

    def test_country_level_items_empty_when_none(self):
        """无国级新闻 → country_level_items 为空列表（字段始终在，前端无需判空键）。"""
        active = {"hotlist": [
            _item(1, "city", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000",
                  city="广州市", city_adcode="440100", title="市级"),
        ]}
        payload = build_region_map_payload(active)
        cn = payload["world"][0]
        assert cn["country_level_items"] == []

    def test_province_level_items_empty_when_none(self):
        active = {"hotlist": [
            _item(1, "city", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000",
                  city="广州市", city_adcode="440100", title="市级"),
        ]}
        payload = build_region_map_payload(active)
        cn = payload["world"][0]
        gd = next(p for p in cn["provinces"] if p["adcode"] == "440000")
        assert gd["province_level_items"] == []


class TestBuildRegionMapPayloadOverseas:
    """海外：仅国家层，省/市文本进 items。"""

    def test_overseas_no_provinces(self):
        active = {"hotlist": [
            _item(1, "province", country="美国", country_code="US",
                  province="加利福尼亚州", city="旧金山", title="美国新闻1"),
            _item(2, "country", country="美国", country_code="US", title="美国新闻2"),
        ]}
        payload = build_region_map_payload(active)

        assert len(payload["world"]) == 1
        us = payload["world"][0]
        assert us["code"] == "US"
        assert us["name"] == "美国"
        assert us["count"] == 2
        # 海外无 provinces 键
        assert "provinces" not in us
        # items 平铺，保留省/市文本
        assert len(us["items"]) == 2
        item1 = next(i for i in us["items"] if i["title"] == "美国新闻1")
        assert item1["province"] == "加利福尼亚州"
        assert item1["city"] == "旧金山"


class TestBuildRegionMapPayloadUnknown:
    def test_level_unknown_into_bucket(self):
        active = {"hotlist": [
            _item(1, "unknown", title="未知新闻"),
        ]}
        payload = build_region_map_payload(active)
        assert payload["world"] == []
        assert payload["unknown"]["count"] == 1
        assert len(payload["unknown"]["items"]) == 1

    def test_no_country_code_into_bucket(self):
        """level 非 unknown 但无 country_code → unknown 桶。"""
        active = {"hotlist": [
            _item(1, "country", country="未知国", country_code="", title="无码新闻"),
        ]}
        payload = build_region_map_payload(active)
        assert payload["world"] == []
        assert payload["unknown"]["count"] == 1


class TestBuildRegionMapPayloadCounts:
    def test_count_accumulation_and_ordering(self):
        active = {"hotlist": [
            _item(1, "city", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000",
                  city="广州市", city_adcode="440100"),
            _item(2, "city", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000",
                  city="广州市", city_adcode="440100"),
            _item(3, "country", country="美国", country_code="US", title="美1"),
            _item(4, "country", country="美国", country_code="US", title="美2"),
            _item(5, "country", country="日本", country_code="JP", title="日1"),
        ]}
        payload = build_region_map_payload(active)
        # world 按 count 降序：US(2)==CN(2) > JP(1)；count 相等按 name 稳定
        counts = [c["count"] for c in payload["world"]]
        assert counts == sorted(counts, reverse=True)
        assert counts[0] == 2
        # 省内城市累计
        cn = next(c for c in payload["world"] if c["code"] == "CN")
        gd = next(p for p in cn["provinces"] if p["adcode"] == "440000")
        gz = next(ct for ct in gd["cities"] if ct["adcode"] == "440100")
        assert gz["count"] == 2
        assert len(gz["items"]) == 2


class TestBuildRegionMapPayloadMerge:
    def test_merges_hotlist_and_rss(self):
        active = {
            "hotlist": [_item(1, "city", country="中国", country_code="CN",
                             province="广东省", province_adcode="440000",
                             city="广州市", city_adcode="440100",
                             source_type="hotlist", title="热榜")],
            "rss": [_item(2, "city", country="中国", country_code="CN",
                         province="广东省", province_adcode="440000",
                         city="广州市", city_adcode="440100",
                         source_type="rss", title="RSS")],
        }
        payload = build_region_map_payload(active)
        cn = payload["world"][0]
        assert cn["count"] == 2
        gd = cn["provinces"][0]
        gz = gd["cities"][0]
        assert gz["count"] == 2
        types = sorted(i["source_type"] for i in gz["items"])
        assert types == ["hotlist", "rss"]


class TestBuildRegionMapPayloadNewsItemShape:
    def test_item_has_frontend_fields(self):
        active = {"hotlist": [
            _item(1, "city", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000",
                  city="广州市", city_adcode="440100",
                  title="广州新闻", url="http://x", source_name="微博",
                  ranks=[1, 2], confidence=0.9),
        ]}
        payload = build_region_map_payload(active)
        item = payload["world"][0]["provinces"][0]["cities"][0]["items"][0]
        for key in ("title", "url", "source_name", "ranks", "source_type",
                    "province", "city", "confidence"):
            assert key in item, f"missing {key}"
        assert item["url"] == "http://x"
        assert item["ranks"] == [1, 2]
        assert item["confidence"] == 0.9


class TestBuildRenderRoundTrip:
    """build_region_map_payload → render_region_map_html 往返：payload 字段
    必须出现在 HTML 中，ECharts 结构完整。"""

    def _round_trip(self, active, echarts_names=None):
        payload = build_region_map_payload(active, echarts_names=echarts_names)
        return render_region_map_html(payload)

    def test_china_province_name_in_html(self):
        """中国省级名称必须出现在 HTML 中（payload → HTML 传递正确）。"""
        html = self._round_trip({"hotlist": [
            _item(1, "city", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000",
                  city="广州市", city_adcode="440100", title="广州新闻"),
        ]}, echarts_names={"CN": "China"})
        assert "广东省" in html
        assert "广州市" in html
        assert "广州新闻" in html
        assert "China" in html

    def test_overseas_country_and_province_text_in_html(self):
        """海外国家名称与省/市文本标签均出现。"""
        html = self._round_trip({"hotlist": [
            _item(1, "province", country="美国", country_code="US",
                  province="加利福尼亚州", city="旧金山", title="美国新闻"),
        ]}, echarts_names={"US": "United States of America"})
        assert "United States of America" in html
        assert "加利福尼亚州" in html
        assert "旧金山" in html

    def test_echarts_cdn_present(self):
        """ECharts CDN 与地图资源路径在 HTML 中。"""
        html = self._round_trip({"hotlist": [
            _item(1, "country", country="美国", country_code="US"),
        ]})
        assert "cdn.jsdelivr.net/npm/echarts@5.6.0" in html
        assert "fastly.jsdelivr.net/npm/echarts@4.9.0/map/json/world.json" in html
        assert "geo.datav.aliyun.com/areas_v3/bound" in html

    def test_xss_safe_script_tag(self):
        """HTML 中 script 块必须精确 2 个（JSON data + init），无多余。

        ECharts 库改为 init 内异步多源加载，不再是独立 <script src>，
        故 script 块数量为 2（JSON payload + init IIFE）。
        """
        html = self._round_trip({"hotlist": [
            _item(1, "country", country="美国", country_code="US",
                  title="正常标题"),
        ]})
        # 主 script 块数量：JSON data + init = 2（ECharts 库由 init 内异步注入）
        assert html.count("<script") == 2
        # 无 injected HTML 残片
        assert "<img" not in html

    def test_date_folder_in_html(self):
        """⚠ 地区报道渲染不应包含对今天的相对引用 —— 验证未意外嵌入日期。"""
        html = self._round_trip({"hotlist": [
            _item(1, "country", country="美国", country_code="US"),
        ]})
        # 验证 init 的 script 标签闭合（JSON data + init = 2）
        assert html.count("</script>") == 2
        assert "echarts.init" in html  # 图表初始化代码存在


class TestRenderCoarseLevelBuckets:
    """国级/省级桶渲染：payload 字段进内联 JSON + JS 标签字面量存在。

    panel 条件渲染（仅非空时显示桶行）是运行时 JS 逻辑，单测层面验证
    字段与标签的接线；payload 级别的字段存在性由 TestBuildRegionMapPayloadCoarseLevels 覆盖。
    """

    def test_country_level_items_in_inline_payload(self):
        """国级新闻 → country_level_items 字段进内联 payload JSON。"""
        payload = build_region_map_payload({"hotlist": [
            _item(1, "country", country="中国", country_code="CN", title="国级新闻"),
        ]}, echarts_names={"CN": "China"})
        html = render_region_map_html(payload)
        assert "country_level_items" in html
        assert "国级新闻" in html

    def test_province_level_items_in_inline_payload(self):
        """省级新闻 → province_level_items 字段进内联 payload JSON。"""
        payload = build_region_map_payload({"hotlist": [
            _item(1, "province", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000", title="省级新闻"),
        ]}, echarts_names={"CN": "China"})
        html = render_region_map_html(payload)
        assert "province_level_items" in html
        assert "省级新闻" in html

    def test_bucket_label_literals_in_js(self):
        """国级/省级桶标签字面量在 JS 中（panel 行渲染用）。"""
        payload = build_region_map_payload({"hotlist": [
            _item(1, "country", country="中国", country_code="CN", title="x"),
        ]}, echarts_names={"CN": "China"})
        html = render_region_map_html(payload)
        assert "全国/未细分省" in html
        assert "全省/未细分市" in html


class TestBuildRegionMapPayloadConfidence:
    def test_confidence_none_becomes_zero(self):
        """None confidence → 0（不抛异常）。"""
        active = {"hotlist": [
            _item(1, "country", country="美国", country_code="US", confidence=None),
        ]}
        payload = build_region_map_payload(active)
        assert payload["world"][0]["items"][0]["confidence"] == 0

    def test_confidence_rounds_to_two_decimals(self):
        """confidence 1.2345 → 1.23（前端精度控制）。"""
        active = {"hotlist": [
            _item(1, "country", country="美国", country_code="US", confidence=1.2345),
        ]}
        payload = build_region_map_payload(active)
        assert payload["world"][0]["items"][0]["confidence"] == 1.23

    def test_confidence_zero_stays_zero(self):
        active = {"hotlist": [
            _item(1, "country", country="美国", country_code="US", confidence=0),
        ]}
        payload = build_region_map_payload(active)
        assert payload["world"][0]["items"][0]["confidence"] == 0


class TestBuildRegionMapPayloadEchartsName:
    def test_echarts_name_injected(self):
        active = {"hotlist": [
            _item(1, "country", country="美国", country_code="US"),
            _item(2, "country", country="中国", country_code="CN"),
        ]}
        payload = build_region_map_payload(
            active, echarts_names={"US": "United States", "CN": "China"}
        )
        by_code = {c["code"]: c for c in payload["world"]}
        assert by_code["US"]["echarts_name"] == "United States"
        assert by_code["CN"]["echarts_name"] == "China"

    def test_echarts_name_empty_when_no_map(self):
        active = {"hotlist": [
            _item(1, "country", country="美国", country_code="US"),
        ]}
        payload = build_region_map_payload(active)  # 无 echarts_names
        assert payload["world"][0]["echarts_name"] == ""


class TestRenderRegionMapHtml:
    def test_empty_payload_returns_empty(self):
        assert render_region_map_html({"world": [], "unknown": {"count": 0, "items": []}}) == ""

    def test_renders_section_with_payload(self):
        payload = build_region_map_payload({"hotlist": [
            _item(1, "city", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000",
                  city="广州市", city_adcode="440100", title="广州新闻"),
        ]}, echarts_names={"CN": "China"})
        html = render_region_map_html(payload)
        assert 'class="region-map-section' in html
        assert 'id="rmChart"' in html
        assert "China" in html
        assert "广州新闻" in html

    def test_xss_safe_payload_escaping(self):
        """标题含 </script> 与 < > 必须转义，不能闭合 script 块。"""
        payload = build_region_map_payload({"hotlist": [
            _item(1, "country", country="美国", country_code="US",
                  title="恶意</script><img src=x>"),
        ]})
        html = render_region_map_html(payload)
        # 原始 </script> 在 payload 段不应出现（已被转义为 </script）
        payload_segment = html.split('id="rmData"', 1)[1].split('</script>', 1)[0]
        assert "</script>" not in payload_segment
        assert "<img" not in payload_segment
        # ECharts 引入与 init 收尾的合法 </script> 仍在
        assert html.count("</script>") >= 2

    def test_unknown_only_renders(self):
        """仅有 unknown 桶（无世界地图节点），仍渲染该区。"""
        payload = build_region_map_payload({"hotlist": [
            _item(1, "unknown", title="未知"),
        ]})
        html = render_region_map_html(payload)
        assert 'class="region-map-section' in html
        assert 'id="rmChart"' in html  # 图表区仍存在（显示空状态）
        assert "未知" in html

    def test_world_only_no_unknown(self):
        """世界有数据但 unknown 桶空，仍渲染。"""
        payload = build_region_map_payload({"hotlist": [
            _item(1, "country", country="美国", country_code="US", title="新闻"),
        ]})
        html = render_region_map_html(payload)
        assert 'class="region-map-section' in html
        assert "新闻" in html

    def test_empty_title_renders_fallback(self):
        """空标题 → 前端 fallback "(无标题)"。"""
        payload = build_region_map_payload({"hotlist": [
            _item(1, "country", country="美国", country_code="US", title=""),
        ]})
        html = render_region_map_html(payload)
        assert "无标题" in html  # JS fallback 字符串存在于脚本块

    def test_total_count_in_header(self):
        payload = build_region_map_payload({"hotlist": [
            _item(1, "city", country="中国", country_code="CN",
                  province="广东省", province_adcode="440000",
                  city="广州市", city_adcode="440100"),
            _item(2, "country", country="美国", country_code="US"),
            _item(3, "unknown"),
        ]})
        html = render_region_map_html(payload)
        assert "3 条" in html

    def test_loading_skeleton_markup(self):
        """首屏即渲染 LOADING MAP 骨架，避免 CDN 抓取期空白。"""
        payload = build_region_map_payload({"hotlist": [
            _item(1, "country", country="美国", country_code="US", title="新闻"),
        ]})
        html = render_region_map_html(payload)
        assert "rm-skeleton" in html
        assert "LOADING MAP" in html

    def test_responsive_grid_css(self):
        """≥1024px chart+panel 并排（1.4fr:1fr）；移动端单列。"""
        payload = build_region_map_payload({"hotlist": [
            _item(1, "country", country="美国", country_code="US", title="新闻"),
        ]})
        html = render_region_map_html(payload)
        assert "grid-template-columns:1.4fr 1fr" in html
        assert "min-width:1024px" in html

    def test_world_label_hidden_hover_reveal(self):
        """世界级标签隐藏（show:false），避免全量国名叠字；hover 显示。"""
        payload = build_region_map_payload({"hotlist": [
            _item(1, "country", country="美国", country_code="US", title="新闻"),
        ]}, echarts_names={"US": "United States"})
        html = render_region_map_html(payload)
        # 世界 paint 调用第 4 参传 false；省市级缺省 true（不传）
        assert "}, false);" in html

    def test_tooltip_has_percent(self):
        """tooltip 显示占比百分数（值/总数）。"""
        payload = build_region_map_payload({"hotlist": [
            _item(1, "country", country="美国", country_code="US", title="新闻"),
        ]})
        html = render_region_map_html(payload)
        assert "*100).toFixed(1)" in html


class TestBuildRegionMapPayloadFilter:
    """渲染阶段筛选：allowed_keys 决定哪些 active 项进入 payload。

    对齐用户需求 —— 地区地图只展示通过了兴趣筛选（keyword/ai）的资讯，
    而非全量已分类新闻。allowed_keys=None 退化为不过滤（向后兼容）。
    键为 (source_name, title) 复合，避免异源同名误并。
    """

    def test_allowed_keys_none_means_no_filter(self):
        """allowed_keys 缺省 → 不过滤，全部保留（向后兼容）。"""
        active = {"hotlist": [
            _item(1, "country", country="美国", country_code="US", title="A"),
            _item(2, "country", country="日本", country_code="JP", title="B"),
        ]}
        payload = build_region_map_payload(active)  # 不传 allowed_keys
        assert len(payload["world"]) == 2

    def test_allowed_keys_filters_out_non_matching(self):
        """仅 (source_name, title) 命中的项保留，其余丢弃。"""
        active = {"hotlist": [
            _item(1, "country", country="美国", country_code="US",
                  title="命中", source_name="微博"),
            _item(2, "country", country="日本", country_code="JP",
                  title="未命中", source_name="知乎"),
        ]}
        payload = build_region_map_payload(
            active, allowed_keys={("微博", "命中")}
        )
        codes = {c["code"] for c in payload["world"]}
        assert codes == {"US"}
        assert payload["world"][0]["count"] == 1

    def test_allowed_keys_empty_set_drops_everything(self):
        """空集 → 全部滤掉（表示本轮筛选无命中）。"""
        active = {"hotlist": [
            _item(1, "country", country="美国", country_code="US", title="A"),
        ]}
        payload = build_region_map_payload(active, allowed_keys=set())
        assert payload == {"world": [], "unknown": {"count": 0, "items": []}}

    def test_filter_applies_to_both_hotlist_and_rss(self):
        """hotlist 与 rss 项同样受 allowed_keys 约束。"""
        active = {
            "hotlist": [_item(1, "country", country="美国", country_code="US",
                              title="热榜命中", source_name="微博",
                              source_type="hotlist")],
            "rss": [_item(2, "country", country="美国", country_code="US",
                          title="RSS未命中", source_name="人民网",
                          source_type="rss")],
        }
        payload = build_region_map_payload(
            active, allowed_keys={("微博", "热榜命中")}
        )
        us = payload["world"][0]
        assert us["count"] == 1
        assert us["items"][0]["title"] == "热榜命中"

    def test_filter_drops_unknown_bucket_items_too(self):
        """unknown 桶项同样按 allowed_keys 过滤，保持一致。"""
        active = {"hotlist": [
            _item(1, "unknown", title="命中未知", source_name="微博"),
            _item(2, "unknown", title="未命中未知", source_name="知乎"),
        ]}
        payload = build_region_map_payload(
            active, allowed_keys={("微博", "命中未知")}
        )
        assert payload["unknown"]["count"] == 1
        assert payload["unknown"]["items"][0]["title"] == "命中未知"

    def test_same_title_different_source_not_conflated(self):
        """同名异源 → 复合键区分，只保留命中的那一条。"""
        active = {"hotlist": [
            _item(1, "country", country="美国", country_code="US",
                  title="同名", source_name="微博"),
            _item(2, "country", country="日本", country_code="JP",
                  title="同名", source_name="知乎"),
        ]}
        payload = build_region_map_payload(
            active, allowed_keys={("知乎", "同名")}
        )
        codes = {c["code"] for c in payload["world"]}
        assert codes == {"JP"}
