# coding=utf-8
"""地区地图 payload 构建与 HTML 渲染（阶段 5）。

- build_region_map_payload: active 结果树 → design 6.1 payload 树
- render_region_map_html: payload → ECharts 地图区 HTML（世界 choropleth + 中国/省/市钻取）

设计契约见 docs/region-classify-design.md §6。
"""

import json
from typing import Any, Dict, List, Optional, Set, Tuple

CHINA_CODE = "CN"


# 渲染阶段筛选键：(source_name, title) 复合。
# active 项与 filtered stats 的 title 条目都带这两个字段；
# 单用 title 会把异源同名误并，复合键更精确。
NewsKey = Tuple[str, str]


def collect_filtered_keys(
    stats: Optional[List[Dict[str, Any]]],
    rss_stats: Optional[List[Dict[str, Any]]] = None,
) -> Set[NewsKey]:
    """从筛选后的 stats（热榜）与 rss_stats（RSS）提取 (source_name, title) 键集。

    stats 来源：count_word_frequency（keyword 模式）或
    convert_ai_filter_to_report_data（ai 模式），两者都只含通过筛选的标题。
    每条 title 条目结构见 core/analyzer.py 与 context.py 的 title_entry。
    """
    keys: Set[NewsKey] = set()
    for group in (stats or []):
        for t in group.get("titles") or []:
            if not isinstance(t, dict):
                continue
            title = (t.get("title") or "").strip()
            source = (t.get("source_name") or "").strip()
            if title:
                keys.add((source, title))
    for group in (rss_stats or []):
        for t in group.get("titles") or []:
            if not isinstance(t, dict):
                continue
            title = (t.get("title") or "").strip()
            source = (t.get("source_name") or "").strip()
            if title:
                keys.add((source, title))
    return keys


def _to_news_item(r: Dict[str, Any]) -> Dict[str, Any]:
    """active 项 → 前端 news_item（复用现有字段 + 省/市文本标签）。"""
    confidence = r.get("confidence") or 0
    try:
        confidence = round(float(confidence), 2)
    except (TypeError, ValueError):
        confidence = 0
    return {
        "title": r.get("title", "") or "",
        "url": r.get("url", "") or "",
        "source_name": r.get("source_name", "") or "",
        "ranks": list(r.get("ranks") or []),
        "source_type": r.get("source_type", "hotlist"),
        "province": r.get("province") or "",
        "city": r.get("city") or "",
        "confidence": confidence,
    }


def _sort_nodes(nodes: List[Dict[str, Any]], key_name: str) -> List[Dict[str, Any]]:
    """节点按 count 降序，count 相等按 name 升序（稳定排序）。"""
    return sorted(nodes, key=lambda n: (-n["count"], n.get(key_name, "")))


def build_region_map_payload(
    active_results: Optional[Dict[str, List[Dict[str, Any]]]],
    echarts_names: Optional[Dict[str, str]] = None,
    allowed_keys: Optional[Set[NewsKey]] = None,
) -> Dict[str, Any]:
    """active 结果树 → design 6.1 payload 树。

    中国（country_code == 'CN'）：provinces → cities → items 全树（逐级钻取）。
    海外：仅国家层（无 provinces），province/city 文本进 items 元数据。
    unknown 桶：level == 'unknown' 或无 country_code 的项。

    Args:
        active_results: storage.get_active_region_classify_results() 返回的
            {"hotlist": [...], "rss": [...]} 树，可能为 None/空。
        echarts_names: ISO alpha-2 → ECharts 世界图英文名 映射（normalizer
            提供）。注入到世界国家节点的 echarts_name，供 choropleth 上色；
            缺省时不上色但节点仍渲染。
        allowed_keys: 渲染阶段筛选键集（(source_name, title)）。None=不过滤
            （向后兼容）；非 None 时仅保留命中的 active 项，使地区地图与
            兴趣筛选结果对齐。空集 → 全部滤掉。键集由
            collect_filtered_keys(stats, rss_stats) 产出。

    Returns:
        {"world": [...], "unknown": {"count": int, "items": [...]}}
    """
    active_results = active_results or {}
    echarts_names = echarts_names or {}
    raw_items: List[Dict[str, Any]] = list(
        (active_results.get("hotlist") or [])
    ) + list((active_results.get("rss") or []))

    # 渲染阶段筛选：对齐兴趣筛选后的 stats，避免地区地图展示未命中资讯
    if allowed_keys is not None:
        items = [
            r for r in raw_items
            if ((r.get("source_name") or "").strip(),
                (r.get("title") or "").strip()) in allowed_keys
        ]
    else:
        items = raw_items

    # country_code → 国家节点（构建期用临时结构，输出前扁平化）
    countries: Dict[str, Dict[str, Any]] = {}
    unknown_items: List[Dict[str, Any]] = []

    for r in items:
        code = (r.get("country_code") or "").strip()
        level = (r.get("level") or "").strip()
        news_item = _to_news_item(r)

        # unknown 桶：level 标记 unknown 或归一化失败无 code
        if not code or level == "unknown":
            unknown_items.append(news_item)
            continue

        country = countries.get(code)
        if country is None:
            country = {
                "code": code,
                "name": r.get("country") or code,
                "echarts_name": echarts_names.get(code, ""),
                "count": 0,
            }
            if code == CHINA_CODE:
                # 中国全树：省 → 市 → items + 国级桶（level=country，无省归属）
                country["provinces"] = {}  # adcode-or-name → 省节点
                country["country_level_items"] = []  # level=country 中国新闻
            else:
                # 海外：平铺 items
                country["items"] = []
            countries[code] = country

        country["count"] += 1

        if code == CHINA_CODE:
            _nest_china_item(country, r, news_item)
        else:
            country["items"].append(news_item)

    # 扁平化 + 排序
    world: List[Dict[str, Any]] = []
    for country in countries.values():
        if country["code"] == CHINA_CODE:
            country["provinces"] = _flatten_china_provinces(country["provinces"])
        world.append(country)
    world = _sort_nodes(world, "name")

    return {
        "world": world,
        "unknown": {"count": len(unknown_items), "items": unknown_items},
    }


def _nest_china_item(
    country: Dict[str, Any],
    r: Dict[str, Any],
    news_item: Dict[str, Any],
) -> None:
    """把中国项按 level 归位（design §6.1 三级支持）。

    路由按 level 字段（非 presence），防御 AI 抖动：
    - level=country → country_level_items（无省归属，直接挂中国节点）
    - level=province → province_level_items（有省无市）
    - level=city（含 normalizer 失败的 orphan：city_adcode 空、name 在）
      → 省 → 市 → items 嵌套树（orphan 用 name 做 key，留 city 树）
    - 缺省归属信号的边角（无 province 名）→ 兜底回 country_level_items
    """
    level = (r.get("level") or "").strip()
    provinces: Dict[str, Dict[str, Any]] = country["provinces"]

    # 国级：无省归属，直接挂中国节点
    if level == "country":
        country["country_level_items"].append(news_item)
        return

    # 省级 / 市级：都需要省节点
    prov_key = (r.get("province_adcode") or "").strip()
    prov_name = (r.get("province") or "").strip()
    if not prov_key and not prov_name:
        # 无省归属信号 → 兜底国级桶
        country["country_level_items"].append(news_item)
        return
    if not prov_key:
        prov_key = prov_name  # 无 adcode 用名做键

    province = provinces.get(prov_key)
    if province is None:
        province = {
            "adcode": (r.get("province_adcode") or "").strip(),
            "name": prov_name,
            "count": 0,
            "cities": {},  # adcode-or-name → 市节点
            "province_level_items": [],  # level=province 省级新闻
        }
        provinces[prov_key] = province
    province["count"] += 1

    # 省级：有省无市，挂省节点
    if level == "province":
        province["province_level_items"].append(news_item)
        return

    # city（含 orphan：level=city 但 city_adcode 空，name-keyed 留 city 树）
    cities: Dict[str, Dict[str, Any]] = province["cities"]
    city_key = (r.get("city_adcode") or "").strip()
    city_name = (r.get("city") or "").strip()
    if not city_key and not city_name:
        # level=city 但无市名（异常）→ 兜底省级桶
        province["province_level_items"].append(news_item)
        return
    if not city_key:
        city_key = city_name

    city = cities.get(city_key)
    if city is None:
        city = {
            "adcode": (r.get("city_adcode") or "").strip(),
            "name": city_name,
            "count": 0,
            "items": [],
        }
        cities[city_key] = city
    city["count"] += 1
    city["items"].append(news_item)


def _flatten_china_provinces(
    provinces: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """省节点字典 → 排序列表，城市一并扁平化排序。"""
    flat: List[Dict[str, Any]] = []
    for prov in provinces.values():
        prov["cities"] = _sort_nodes(
            [c for c in prov["cities"].values()], "name"
        )
        flat.append(prov)
    return _sort_nodes(flat, "name")


def _safe_json_for_script(obj: Any) -> str:
    """JSON 序列化并转义，安全内联进 HTML <script type="application/json">。

    application/json 脚本块不会被当 JS 解析，但 HTML 解析器仍扫描 </script>，
    故转义 < >（→ \\u003c / \\u003e，经 JSON.parse 仍还原为 < >，无信息损失）。
    同时转义 U+2028/2029（个别解析器敏感）。& 不需转（script 原始文本）。
    """
    raw = json.dumps(obj, ensure_ascii=False)
    return (
        raw.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


# ECharts 库 + 地图 GeoJSON 多源 CDN：逐个回退，全部失败才降级文本兜底。
# ⚠ 版本必须真实存在于 npm registry。曾误用 5.5.2（npm 上不存在）→ 所有源 404
# → 库永远加载失败 → 用户恒见文本兜底。5.6.0 为 5.x 末版稳定（6.x 有破坏性变更）。
# 改版本前务必 curl registry.npmjs.org/echarts/<ver> 核对，并 curl 每个 CDN URL。
# 国际源在前、国内源（bootcdn 字节 / staticfile 七牛）在后，兼顾海外与国内网络。
_ECHARTS_CDN_SOURCES = [
    "https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js",
    "https://fastly.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js",
    "https://unpkg.com/echarts@5.6.0/dist/echarts.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/echarts/5.6.0/echarts.min.js",
    "https://cdn.bootcdn.net/ajax/libs/echarts/5.6.0/echarts.min.js",   # 字节 CDN（国内可达）
    "https://cdn.staticfile.org/echarts/5.6.0/echarts.min.js",   # 七牛（国内）
]
# 世界地图 GeoJSON：ECharts 5 已移除内置地图，用 4.9 仓库 + GitHub 镜像。
# （DataV 仅提供中国省/市边界，无 world.json，曾误列导致 404。）
_WORLD_MAP_URLS = [
    "https://fastly.jsdelivr.net/npm/echarts@4.9.0/map/json/world.json",
    "https://cdn.jsdelivr.net/npm/echarts@4.9.0/map/json/world.json",
    "https://unpkg.com/echarts@4.9.0/map/json/world.json",
    "https://raw.githubusercontent.com/apache/echarts/4.9.0/map/json/world.json",  # GitHub 镜像
]
_DATAV_BASE = "https://geo.datav.aliyun.com/areas_v3/bound"


def render_region_map_html(payload: Dict[str, Any]) -> str:
    """payload → 地区地图区 HTML（世界 choropleth + 中国/省/市钻取 + unknown 桶）。

    payload 为空（无世界国家且无 unknown 项）时返回空串，不渲染该区。

    安全性：payload 内联为 application/json（_safe_json_for_script 转义）；
    新闻标题在 JS 侧用 textContent 渲染，不经 innerHTML，杜绝 XSS。
    """
    world = payload.get("world") or []
    unknown = payload.get("unknown") or {"count": 0, "items": []}
    unknown_items = unknown.get("items") or []
    if not world and not unknown_items:
        return ""

    total = sum(int(c.get("count", 0)) for c in world) + len(unknown_items)
    payload_json = _safe_json_for_script(payload)

    css = """

        .region-map-section{margin:0;padding:0;}
        .rm-header{display:flex;align-items:baseline;justify-content:space-between;padding:16px 0 10px;border-bottom:2px solid var(--rule-ink);position:relative;}
        .rm-header::after{content:"";position:absolute;left:0;bottom:-2px;width:48px;height:2px;background:var(--accent);}
        .rm-title{font-family:var(--font-display);font-size:20px;font-weight:600;font-variation-settings:"opsz" 60;color:var(--ink);letter-spacing:-0.01em;}
        body.dark-mode .rm-title{color:var(--ink);}
        .rm-count{font-family:var(--font-mono);font-size:12px;color:var(--muted);background:var(--surface-2);border:1px solid var(--rule);padding:2px 10px;border-radius:1px;letter-spacing:0.04em;}
        body.dark-mode .rm-count{background:var(--surface-2);color:var(--ink-2);border-color:var(--rule);}
        .rm-crumb{display:flex;flex-wrap:wrap;align-items:center;gap:4px;font-family:var(--font-mono);font-size:12px;color:var(--muted);padding:8px 0;}
        .rm-crumb a{color:var(--accent);cursor:pointer;text-decoration:none;border-bottom:1px solid transparent;}
        .rm-crumb a:hover{border-bottom-color:var(--accent);}
        .rm-crumb .sep{color:var(--muted-2);}
        .rm-crumb-cur{color:var(--ink);font-weight:600;}
        .rm-chart-wrap{width:100%;height:320px;background:var(--surface-2);border:1px solid var(--rule);border-radius:2px;overflow:hidden;position:relative;}
        body.dark-mode .rm-chart-wrap{background:var(--surface-2);border-color:var(--rule);}
        /* ≥1024px：chart+panel 并排（chart 主，1.4fr）；<1024px 单列堆叠 */
        .rm-body{display:grid;grid-template-columns:1fr;gap:10px;}
        @media (min-width:1024px){
          .rm-body{grid-template-columns:1.4fr 1fr;align-items:start;}
          .rm-chart-wrap{height:520px;}
          /* unknown 桶跨两列，保持底部全宽 */
          .rm-unknown{grid-column:1 / -1;}
        }
        /* 首屏骨架：CDN 抓取期占位，避免空白 */
        .rm-skeleton{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:8px;font-family:var(--font-mono);font-size:11px;letter-spacing:0.16em;color:var(--muted);text-transform:uppercase;pointer-events:none;}
        .rm-skeleton .dot{display:inline-block;width:4px;height:4px;border-radius:50%;background:var(--accent);animation:rm-pulse 1.2s infinite ease-in-out;}
        .rm-skeleton .dot:nth-child(2){animation-delay:0.15s;}
        .rm-skeleton .dot:nth-child(3){animation-delay:0.3s;}
        @keyframes rm-pulse{0%,80%,100%{opacity:0.25;}40%{opacity:1;}}
        @media (prefers-reduced-motion:reduce){.rm-skeleton .dot{animation:none;opacity:0.6;}}
        .rm-panel{border:1px solid var(--rule);border-radius:2px;overflow:hidden;background:var(--surface);}
        body.dark-mode .rm-panel{border-color:var(--rule);}
        .rm-panel-head{padding:10px 14px;font-family:var(--font-mono);font-size:11px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;background:var(--surface-2);color:var(--accent);display:flex;justify-content:space-between;align-items:center;}
        body.dark-mode .rm-panel-head{background:var(--surface-2);color:var(--accent);}
        .rm-panel-empty{padding:18px;text-align:center;color:var(--muted);font-family:var(--font-body);font-size:13px;font-style:italic;}
        .rm-list{max-height:360px;overflow-y:auto;}
        .rm-item{display:flex;gap:10px;padding:10px 14px;border-top:1px solid var(--rule-soft);align-items:flex-start;}
        body.dark-mode .rm-item{border-color:var(--rule);}
        .rm-item:first-child{border-top:none;}
        .rm-item-src{flex-shrink:0;font-family:var(--font-mono);font-size:10px;color:var(--accent);background:var(--surface-3);padding:2px 8px;border-radius:1px;margin-top:2px;max-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;letter-spacing:0.06em;text-transform:uppercase;}
        body.dark-mode .rm-item-src{background:var(--surface-3);color:var(--accent);}
        .rm-item-main{flex:1;min-width:0;}
        .rm-item-title{font-family:var(--font-body);font-size:14px;font-weight:500;line-height:1.5;word-break:break-word;}
        .rm-item-title a{color:var(--ink);text-decoration:none;background-image:linear-gradient(var(--accent),var(--accent));background-size:0% 1px;background-position:0 100%;background-repeat:no-repeat;transition:background-size 0.25s ease,color 0.15s ease;}
        body.dark-mode .rm-item-title a{color:var(--ink);}
        .rm-item-title a:hover{color:var(--accent);background-size:100% 1px;}
        .rm-item-meta{font-family:var(--font-mono);font-size:10.5px;color:var(--muted);margin-top:3px;letter-spacing:0.02em;}
        .rm-item-rank{color:var(--accent);font-weight:600;}
        .rm-unknown{margin-top:10px;border:1px solid var(--rule);border-radius:2px;background:var(--surface);}
        body.dark-mode .rm-unknown{border-color:var(--rule);background:var(--surface);}
        .rm-unknown summary{padding:10px 14px;cursor:pointer;font-family:var(--font-mono);font-size:12px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;color:var(--muted);background:var(--surface-2);}
        body.dark-mode .rm-unknown summary{color:var(--muted);background:var(--surface-2);}
        .rm-error{padding:40px;text-align:center;color:var(--muted);font-style:italic;}
        @media (max-width:480px){.rm-chart-wrap{height:320px;}}

    """

    # 注意：JS 体大量使用 {}，故用普通字符串 + 占位符注入，避免 f-string 转义地狱
    js = r"""
        <script type="application/json" id="rmData">__PAYLOAD__</script>
        <script>
        (function(){
          var dataEl = document.getElementById('rmData');
          if(!dataEl) return;
          var DATA;
          try { DATA = JSON.parse(dataEl.textContent); } catch(e){ return; }
          var chartEl = document.getElementById('rmChart');
          var panelEl = document.getElementById('rmPanel');
          var crumbEl = document.getElementById('rmCrumb');
          var isDark = document.body.classList.contains('dark-mode');
          var labelColor = isDark ? '#EEE4CE' : '#161009';
          var TOTAL = (DATA.world||[]).reduce(function(s,c){return s+(c.count||0);},0)
                    + ((DATA.unknown && DATA.unknown.count)||0);
          var ECHARTS_SOURCES = __ECHARTS_SOURCES__;
          var WORLD_URLS = __WORLD_URLS__;
          var DATAV = "__DATAV__";
          var stack = [{label:'世界', level:'world'}];

          function el(tag, cls, text){
            var n = document.createElement(tag);
            if(cls) n.className = cls;
            if(text != null) n.textContent = text;
            return n;
          }

          function renderCrumb(){
            crumbEl.innerHTML = '';
            stack.forEach(function(s, i){
              if(i>0) crumbEl.appendChild(el('span','sep','›'));
              if(i === stack.length - 1){
                // 最末一级=当前位置，纯文本不可点（点击它无处可去）
                crumbEl.appendChild(el('span', 'rm-crumb-cur', s.label));
              } else {
                var a = el('a', null, s.label);
                a.addEventListener('click', function(){ drillTo(i); });
                crumbEl.appendChild(a);
              }
            });
          }

          // DataV Aliyun OSS 有 Referer 防盗链：localhost/datav 自有域放行，
          // 其他 Referer（含 Docker 服务器 IP/域名）→ 403。服务端无 Referer → 200。
          // 故 DataV 抓取强制 no-referrer，浏览器不发 Referer，绕过防盗链白名单。
          // 仅作用于 loadJson（DataV 专用路径）；loadJsonFirst（jsdelivr/npm 等
          // 公共 CDN）无防盗链，保持默认。
          function loadJson(url, ok, fail){
            fetch(url, {cache:'force-cache', referrerPolicy:'no-referrer'}).then(function(r){
              if(!r.ok) throw new Error('HTTP '+r.status);
              return r.json();
            }).then(ok).catch(function(e){
              fail ? fail(e) : showMsg('地图加载失败：'+url);
            });
          }

          // 多源 GeoJSON 回退：逐个 fetch 直到成功或全部失败
          function loadJsonFirst(urls, ok, fail){
            var i = 0;
            function attempt(){
              if(i >= urls.length){ fail && fail(); return; }
              var url = urls[i++];
              fetch(url, {cache:'force-cache'}).then(function(r){
                if(!r.ok) throw new Error('HTTP '+r.status);
                return r.json();
              }).then(ok).catch(function(){ attempt(); });
            }
            attempt();
          }

          function maxCount(rows){ return rows.reduce(function(m,x){return Math.max(m, x.value||0);},0) || 1; }

          function paint(mapName, rows, onGeo, labelShow){
            // labelShow：世界级 false（隐藏全量国名，hover 显示），省市级缺省 true
            if(labelShow == null) labelShow = true;
            chartEl.removeAttribute('_echarts_instance_');
            chartEl.innerHTML = '';  // 清掉首屏骨架
            var inst = echarts.getInstanceByDom(chartEl) || echarts.init(chartEl);
            inst.setOption({
              tooltip:{ formatter:function(p){
                var v = p.value||0;
                var pct = TOTAL ? (v/TOTAL*100).toFixed(1) : '0.0';
                return p.name+'：'+v+' 条 ('+pct+'%)';
              } },
              visualMap:{ left:'right', min:0, max:maxCount(rows),
                inRange:{ color:['#F3EAD2','#E08A0E','#C2290E'] },
                text:['多','少'], calculable:true },
              series:[{ type:'map', map:mapName, roam:true,
                label:{ show:labelShow, fontSize:10, color:labelColor },
                emphasis:{ label:{show:true, color:labelColor}, itemStyle:{areaColor:'#E08A0E'} },
                data: rows }]
            }, true);
            inst.off('click');
            inst.on('click', function(p){ if(p.seriesType==='map') onGeo(p.name); });
            window.addEventListener('resize', function(){ inst.resize(); });
            return inst;
          }

          function showMsg(msg){
            panelEl.innerHTML = '';
            panelEl.appendChild(el('div','rm-panel-empty', msg));
          }

          // 国级/省级桶 panel 行：无 adcode → 无地图色块 → 地图点不到，
          // 故在 panel 列一条可点条目。点击走 showItems（与形状点击同路径，面包屑可返回）。
          function showBucketRow(items, label){
            panelEl.innerHTML = '';
            var list = el('div','rm-list');
            var row = el('div','rm-item');
            row.style.cursor = 'pointer';
            var src = el('div','rm-item-src', '本级');
            var main = el('div','rm-item-main');
            var t = el('div','rm-item-title');
            t.textContent = label + ' · ' + items.length + ' 条';
            main.appendChild(t);
            row.appendChild(src); row.appendChild(main);
            row.addEventListener('click', function(){ showItems(items, label, items.length); });
            list.appendChild(row);
            panelEl.appendChild(list);
          }

          // 渲染世界级
          function renderWorld(){
            stack = [{label:'世界', level:'world'}];
            renderCrumb();
            loadJsonFirst(WORLD_URLS, function(geo){
              if(!echarts.getMap('world')) echarts.registerMap('world', geo);
              var rows = (DATA.world||[]).filter(function(c){return c.echarts_name;})
                .map(function(c){return {name:c.echarts_name, value:c.count};});
              paint('world', rows, function(name){
                var node = (DATA.world||[]).find(function(c){return c.echarts_name===name;});
                if(!node) return;
                if(node.code==='CN' && node.provinces && node.provinces.length){
                  renderChina(node);
                } else if(node.items){
                  showItems(node.items, node.name, node.count);
                }
              }, false);
              showMsg('点击国家查看新闻；中国可下钻省/市');
            }, function(){ showMsg('世界地图 GeoJSON 加载失败（所有源不可达）'); });
          }

          // 渲染中国省级
          function renderChina(cnNode){
            stack = [{label:'世界', level:'world'}, {label:'中国', level:'china', node:cnNode}];
            renderCrumb();
            // panel：国级桶（无省归属新闻）或 hint，与地图加载解耦——地图失败桶仍可达
            var cli = cnNode.country_level_items || [];
            if(cli.length) showBucketRow(cli, '全国/未细分省');
            else showMsg('点击省份查看新闻；可下钻市');
            loadJson(DATAV+'100000_full.json', function(geo){
              if(!echarts.getMap('china')) echarts.registerMap('china', geo);
              var rows = (cnNode.provinces||[]).filter(function(p){return p.adcode && p.name;})
                .map(function(p){return {name:p.name, value:p.count};});
              paint('china', rows, function(name){
                var prov = (cnNode.provinces||[]).find(function(p){return p.name===name;});
                // 始终下钻 renderProvince：它处理 cities + province_level_items 桶，
                // 不再短路 showItems（原短路会漏掉省级新闻）
                if(prov) renderProvince(cnNode, prov);
              });
            }, function(){
              chartEl.innerHTML = '';
              chartEl.appendChild(el('div','rm-error','中国地图加载失败'));
            });
          }

          // 渲染省级 → 市级
          function renderProvince(cnNode, provNode){
            stack = [{label:'世界', level:'world'},
                     {label:'中国', level:'china', node:cnNode},
                     {label:provNode.name, level:'province', node:provNode, cn:cnNode}];
            renderCrumb();
            // panel：省级桶（有省无市新闻）或 hint，与地图加载解耦
            var pli = provNode.province_level_items || [];
            if(pli.length) showBucketRow(pli, '全省/未细分市');
            else showMsg('点击城市查看新闻');
            // 无 adcode（normalizer 失败）→ 跳过地图，panel 桶仍可达
            if(!provNode.adcode){
              chartEl.innerHTML = '';
              chartEl.appendChild(el('div','rm-error','省级地图加载失败'));
              return;
            }
            loadJson(DATAV+provNode.adcode+'_full.json', function(geo){
              var mapKey = 'prov_'+provNode.adcode;
              if(!echarts.getMap(mapKey)) echarts.registerMap(mapKey, geo);
              var rows = (provNode.cities||[]).filter(function(c){return c.name;})
                .map(function(c){return {name:c.name, value:c.count};});
              paint(mapKey, rows, function(name){
                var city = (provNode.cities||[]).find(function(c){return c.name===name;});
                if(city) showItems(city.items||[], city.name, city.count);
              });
            }, function(){
              chartEl.innerHTML = '';
              chartEl.appendChild(el('div','rm-error','省级地图加载失败'));
            });
          }

          function flatItems(cities){
            var out=[]; (cities||[]).forEach(function(c){ (c.items||[]).forEach(function(i){out.push(i);}); });
            return out;
          }

          // 把新闻列表渲染进指定容器（复用于 panel 和 unknown 详情体）
          function renderItemsInto(container, items, title, count){
            container.innerHTML = '';
            var head = el('div','rm-panel-head');
            head.appendChild(el('span', null, title));
            head.appendChild(el('span', null, (count!=null?count:items.length)+' 条'));
            container.appendChild(head);
            if(!items.length){
              container.appendChild(el('div','rm-panel-empty','暂无新闻'));
              return;
            }
            var list = el('div','rm-list');
            items.forEach(function(it){
              var row = el('div','rm-item');
              var src = el('div','rm-item-src', it.source_name||it.source_type||'');
              var main = el('div','rm-item-main');
              var t = el('div','rm-item-title');
              if(it.url){
                var a = el('a'); a.href = it.url; a.target='_blank'; a.rel='noopener';
                a.textContent = it.title||'(无标题)'; t.appendChild(a);
              } else { t.textContent = it.title||'(无标题)'; }
              main.appendChild(t);
              var meta = el('div','rm-item-meta');
              var bits = [];
              if(it.ranks && it.ranks.length) bits.push('排名 '+it.ranks.join('/'));
              if(it.province || it.city){
                var loc = [it.province, it.city].filter(Boolean).join(' ');
                if(loc) bits.push(loc);
              }
              meta.textContent = bits.join(' · ');
              main.appendChild(meta);
              row.appendChild(src); row.appendChild(main);
              list.appendChild(row);
            });
            container.appendChild(list);
          }

          function showItems(items, title, count){
            // 叶子层（新闻列表）：在当前父级 stack 上压入当前位置，
            // 面包屑末项显示本层标题（不可点），点击父级即可返回。
            // 连续点不同叶子时先弹掉旧叶子，避免堆叠。
            if(stack.length && stack[stack.length-1].level === 'items'){
              stack.pop();
            }
            stack.push({label: title || '新闻', level:'items'});
            renderCrumb();
            renderItemsInto(panelEl, items, title, count);
          }

          function drillTo(idx){
            var target = stack[idx];
            if(!target) return;
            // 地图模式与文本兜底模式各自有独立 level，按 level 路由回对应渲染函数
            if(target.level==='world') renderWorld();
            else if(target.level==='world-fallback') renderFallbackList();
            else if(target.level==='china') renderChina(target.node);
            else if(target.level==='china-fallback') renderChinaFallback(target.node);
            else if(target.level==='province') renderProvince(target.cn, target.node);
          }

          function renderUnknown(){
            var det = document.getElementById('rmUnknown');
            if(!det) return;
            var head = det.querySelector('.rm-unk-head');
            var body = document.getElementById('rmUnkBody');
            var unk = DATA.unknown||{count:0, items:[]};
            head.textContent = '未识别地区（'+unk.count+' 条）';
            det.addEventListener('toggle', function(){
              if(!body) return;
              if(det.open){
                // 展开时把列表渲染进 details 体内（而非上方 panel）
                renderItemsInto(body, unk.items||[], '未识别地区', unk.count);
              } else {
                // 收回时清空，避免残留看起来"无法收回"
                body.innerHTML = '';
              }
            });
          }

          // ECharts 库多源异步加载：逐个注入直到成功或全部失败
          function loadEcharts(done){
            if(typeof echarts !== 'undefined'){ done(true); return; }
            var i = 0;
            function attempt(){
              if(i >= ECHARTS_SOURCES.length){ done(false); return; }
              var s = document.createElement('script');
              s.src = ECHARTS_SOURCES[i++];
              s.onload = function(){
                if(typeof echarts !== 'undefined') done(true);
                else attempt();
              };
              s.onerror = attempt;
              document.head.appendChild(s);
            }
            attempt();
          }

          // ECharts 全失败时的文本兜底：chart 区提示，panel 渲染可点击国家列表。
          // 与地图模式共用 stack/面包屑，确保兜底下也能逐级返回（修复"点进省无法返回"）。
          function renderFallbackList(){
            chartEl.innerHTML = '';
            chartEl.appendChild(el('div','rm-error','地图组件加载失败（所有 CDN 不可达），以下为文本列表'));
            stack = [{label:'世界', level:'world-fallback'}];
            renderCrumb();
            var world = DATA.world || [];
            panelEl.innerHTML = '';
            var head = el('div','rm-panel-head');
            head.appendChild(el('span', null, '地区列表（文本兜底）'));
            head.appendChild(el('span', null, world.length + ' 个'));
            panelEl.appendChild(head);
            if(!world.length){
              panelEl.appendChild(el('div','rm-panel-empty','暂无地区数据'));
              return;
            }
            var list = el('div','rm-list');
            world.forEach(function(c){
              var row = el('div','rm-item');
              row.style.cursor = 'pointer';
              var src = el('div','rm-item-src', c.code||'');
              var main = el('div','rm-item-main');
              var t = el('div','rm-item-title');
              t.textContent = (c.name||c.code||'') + ' · ' + (c.count||0) + ' 条';
              main.appendChild(t);
              row.appendChild(src); row.appendChild(main);
              row.addEventListener('click', function(){
                if(c.code==='CN' && c.provinces && c.provinces.length){
                  renderChinaFallback(c);
                } else if(c.items && c.items.length){
                  showItems(c.items, c.name, c.count);
                } else {
                  showItems([], c.name, c.count);
                }
              });
              list.appendChild(row);
            });
            panelEl.appendChild(list);
          }

          // 文本兜底的中国钻取（ECharts 不可用）：省列表 → 点击看新闻。
          // 压入 [世界, 中国] 两级面包屑，点"中国"返省级列表，点"世界"返国家列表。
          function renderChinaFallback(cnNode){
            stack = [{label:'世界', level:'world-fallback'},
                     {label: cnNode.name||'中国', level:'china-fallback', node: cnNode}];
            renderCrumb();
            var provinces = cnNode.provinces || [];
            panelEl.innerHTML = '';
            var head = el('div','rm-panel-head');
            head.appendChild(el('span', null, (cnNode.name||'中国') + ' · 省级'));
            head.appendChild(el('span', null, provinces.length + ' 个'));
            panelEl.appendChild(head);
            if(!provinces.length){
              panelEl.appendChild(el('div','rm-panel-empty','暂无省级数据'));
              return;
            }
            var list = el('div','rm-list');
            provinces.forEach(function(p){
              var row = el('div','rm-item');
              row.style.cursor = 'pointer';
              var src = el('div','rm-item-src', p.adcode||'');
              var main = el('div','rm-item-main');
              var t = el('div','rm-item-title');
              t.textContent = (p.name||'(未细分)') + ' · ' + (p.count||0) + ' 条';
              main.appendChild(t);
              row.appendChild(src); row.appendChild(main);
              row.addEventListener('click', function(){
                showItems(flatItems(p.cities), p.name, p.count);
              });
              list.appendChild(row);
            });
            panelEl.appendChild(list);
          }

          loadEcharts(function(ok){
            if(ok) renderWorld();
            else renderFallbackList();
            renderUnknown();
          });
        })();
        </script>
    """

    js = (
        js.replace("__ECHARTS_SOURCES__", json.dumps(_ECHARTS_CDN_SOURCES, ensure_ascii=False))
        .replace("__WORLD_URLS__", json.dumps(_WORLD_MAP_URLS, ensure_ascii=False))
        .replace("__DATAV__", _DATAV_BASE + "/")
        .replace("__PAYLOAD__", payload_json)
    )

    unknown_html = ""
    if unknown_items:
        unknown_html = (
            '<details class="rm-unknown" id="rmUnknown">'
            '<summary><span class="rm-unk-head">未识别地区</span></summary>'
            '<div id="rmUnkBody"></div></details>'
        )

    return f"""
                <div class="region-map-section section-divider">
                    <style>{css}</style>
                    <div class="rm-header">
                        <div class="rm-title">按地区分布</div>
                        <div class="rm-count">{total} 条</div>
                    </div>
                    <div class="rm-crumb" id="rmCrumb"></div>
                    <div class="rm-body">
                        <div class="rm-chart-wrap" id="rmChart"><div class="rm-skeleton">LOADING MAP<span class="dot"></span><span class="dot"></span><span class="dot"></span></div></div>
                        <div class="rm-panel" id="rmPanel">
                            <div class="rm-panel-empty">点击地图查看新闻</div>
                        </div>
                        {unknown_html}
                    </div>
                    {js}
                </div>"""
