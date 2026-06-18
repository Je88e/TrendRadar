# coding=utf-8
"""地区地图 payload 构建与 HTML 渲染（阶段 5）。

- build_region_map_payload: active 结果树 → design 6.1 payload 树
- render_region_map_html: payload → ECharts 地图区 HTML（世界 choropleth + 中国/省/市钻取）

设计契约见 docs/region-classify-design.md §6。
"""

import json
from typing import Any, Dict, List, Optional

CHINA_CODE = "CN"
# 中国项但未细分到省时归入的兜底省/市桶名（adcode 空）
_OTHER = ""


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

    Returns:
        {"world": [...], "unknown": {"count": int, "items": [...]}}
    """
    active_results = active_results or {}
    echarts_names = echarts_names or {}
    items: List[Dict[str, Any]] = list(
        (active_results.get("hotlist") or [])
    ) + list((active_results.get("rss") or []))

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
                # 中国全树：省 → 市 → items
                country["provinces"] = {}  # adcode-or-name → 省节点
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
    """把中国项归入 省 → 市 → items 嵌套树。"""
    provinces: Dict[str, Dict[str, Any]] = country["provinces"]

    prov_key = (r.get("province_adcode") or "").strip()
    prov_name = (r.get("province") or "").strip()
    if not prov_key and not prov_name:
        prov_key = prov_name = _OTHER
    elif not prov_key:
        prov_key = prov_name  # 无 adcode 用名做键

    province = provinces.get(prov_key)
    if province is None:
        province = {
            "adcode": (r.get("province_adcode") or "").strip(),
            "name": prov_name,
            "count": 0,
            "cities": {},  # adcode-or-name → 市节点
        }
        provinces[prov_key] = province
    province["count"] += 1

    cities: Dict[str, Dict[str, Any]] = province["cities"]
    city_key = (r.get("city_adcode") or "").strip()
    city_name = (r.get("city") or "").strip()
    if not city_key and not city_name:
        city_key = city_name = _OTHER
    elif not city_key:
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
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


# ECharts + 地图资源 CDN（设计 §6.2/§10：固定 5.5.x；world 用 ECharts 官方，
# 中国省/市运行时 fetch DataV）
_ECHARTS_CDN = "https://cdn.jsdelivr.net/npm/echarts@5.5.2/dist/echarts.min.js"
_WORLD_MAP_URL = "https://fastly.jsdelivr.net/npm/echarts@4.9.0/map/json/world.json"
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
        .rm-header{display:flex;align-items:center;justify-content:space-between;padding:16px 0 8px;}
        .rm-title{font-size:18px;font-weight:700;color:#1f2937;}
        body.dark-mode .rm-title{color:#e5e7eb;}
        .rm-count{font-size:13px;color:#6b7280;background:#f3f4f6;padding:2px 10px;border-radius:10px;}
        body.dark-mode .rm-count{background:#374151;color:#d1d5db;}
        .rm-crumb{display:flex;flex-wrap:wrap;align-items:center;gap:4px;font-size:13px;color:#6b7280;padding:4px 0 8px;}
        .rm-crumb a{color:#4f46e5;cursor:pointer;text-decoration:none;}
        .rm-crumb a:hover{text-decoration:underline;}
        .rm-crumb .sep{color:#d1d5db;}
        .rm-chart-wrap{width:100%;height:420px;background:#fff;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;}
        body.dark-mode .rm-chart-wrap{background:#1f2937;border-color:#374151;}
        .rm-body{display:flex;flex-direction:column;gap:10px;}
        .rm-panel{border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;}
        body.dark-mode .rm-panel{border-color:#374151;}
        .rm-panel-head{padding:10px 14px;font-size:14px;font-weight:600;background:#f9fafb;color:#374151;display:flex;justify-content:space-between;align-items:center;}
        body.dark-mode .rm-panel-head{background:#111827;color:#e5e7eb;}
        .rm-panel-empty{padding:18px;text-align:center;color:#9ca3af;font-size:13px;}
        .rm-list{max-height:360px;overflow-y:auto;}
        .rm-item{display:flex;gap:10px;padding:10px 14px;border-top:1px solid #f3f4f6;align-items:flex-start;}
        body.dark-mode .rm-item{border-color:#374151;}
        .rm-item:first-child{border-top:none;}
        .rm-item-src{flex-shrink:0;font-size:11px;color:#4f46e5;background:#eef2ff;padding:1px 7px;border-radius:8px;margin-top:2px;max-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
        body.dark-mode .rm-item-src{background:#312e81;color:#c7d2fe;}
        .rm-item-main{flex:1;min-width:0;}
        .rm-item-title{font-size:14px;line-height:1.5;word-break:break-word;}
        .rm-item-title a{color:#1f2937;text-decoration:none;}
        body.dark-mode .rm-item-title a{color:#e5e7eb;}
        .rm-item-title a:hover{color:#4f46e5;}
        .rm-item-meta{font-size:11px;color:#9ca3af;margin-top:2px;}
        .rm-item-rank{color:#ef4444;font-weight:600;}
        .rm-unknown{margin-top:8px;border:1px solid #e5e7eb;border-radius:8px;}
        body.dark-mode .rm-unknown{border-color:#374151;}
        .rm-unknown summary{padding:10px 14px;cursor:pointer;font-size:14px;font-weight:600;color:#374151;background:#f9fafb;}
        body.dark-mode .rm-unknown summary{color:#e5e7eb;background:#111827;}
        .rm-error{padding:40px;text-align:center;color:#9ca3af;}
        @media (max-width:480px){.rm-chart-wrap{height:320px;}}
    """

    # 注意：JS 体大量使用 {}，故用普通字符串 + 占位符注入，避免 f-string 转义地狱
    js = r"""
        <script src="__ECHARTS__"></script>
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
          var WORLD_URL = "__WORLD__";
          var DATAV = "__DATAV__";
          var stack = [{label:'世界', level:'world'}];

          function el(tag, cls, text){
            var n = document.createElement(tag);
            if(cls) n.className = cls;
            if(text != null) n.textContent = text;
            return n;
          }
          function escapeOnce(s){ return String(s==null?'':s); }

          function renderCrumb(){
            crumbEl.innerHTML = '';
            stack.forEach(function(s, i){
              if(i>0) crumbEl.appendChild(el('span','sep','›'));
              var a = el('a', null, s.label);
              a.addEventListener('click', function(){ drillTo(i); });
              crumbEl.appendChild(a);
            });
          }

          function loadJson(url, ok, fail){
            fetch(url, {cache:'force-cache'}).then(function(r){
              if(!r.ok) throw new Error('HTTP '+r.status);
              return r.json();
            }).then(ok).catch(function(e){
              fail ? fail(e) : showMsg('地图加载失败：'+url);
            });
          }

          function maxCount(rows){ return rows.reduce(function(m,x){return Math.max(m, x.value||0);},0) || 1; }

          function paint(mapName, rows, onGeo){
            chartEl.removeAttribute('_echarts_instance_');
            var inst = echarts.getInstanceByDom(chartEl) || echarts.init(chartEl);
            inst.setOption({
              tooltip:{ formatter:function(p){ return p.name+'：'+(p.value||0)+' 条'; } },
              visualMap:{ left:'right', min:0, max:maxCount(rows),
                inRange:{ color:['#e0e7ff','#6366f1','#312e81'] },
                text:['多','少'], calculable:true },
              series:[{ type:'map', map:mapName, roam:true,
                label:{ show:true, fontSize:10 },
                emphasis:{ label:{show:true}, itemStyle:{areaColor:'#f59e0b'} },
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

          // 渲染世界级
          function renderWorld(){
            stack = [{label:'世界', level:'world'}];
            renderCrumb();
            loadJson(WORLD_URL, function(geo){
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
              });
              showMsg('点击国家查看新闻；中国可下钻省/市');
            });
          }

          // 渲染中国省级
          function renderChina(cnNode){
            loadJson(DATAV+'100000_full.json', function(geo){
              if(!echarts.getMap('china')) echarts.registerMap('china', geo);
              var rows = (cnNode.provinces||[]).filter(function(p){return p.adcode && p.name;})
                .map(function(p){return {name:p.name, value:p.count};});
              stack = [{label:'世界', level:'world'}, {label:'中国', level:'china', node:cnNode}];
              renderCrumb();
              paint('china', rows, function(name){
                var prov = (cnNode.provinces||[]).find(function(p){return p.name===name;});
                if(prov && prov.cities && prov.cities.length) renderProvince(cnNode, prov);
                else if(prov) showItems(flatItems(prov.cities), prov.name, prov.count);
              });
            }, function(){ showMsg('中国地图加载失败'); });
          }

          // 渲染省级 → 市级
          function renderProvince(cnNode, provNode){
            loadJson(DATAV+provNode.adcode+'_full.json', function(geo){
              var mapKey = 'prov_'+provNode.adcode;
              if(!echarts.getMap(mapKey)) echarts.registerMap(mapKey, geo);
              var rows = (provNode.cities||[]).filter(function(c){return c.name;})
                .map(function(c){return {name:c.name, value:c.count};});
              stack = [{label:'世界', level:'world'},
                       {label:'中国', level:'china', node:cnNode},
                       {label:provNode.name, level:'province', node:provNode, cn:cnNode}];
              renderCrumb();
              paint(mapKey, rows, function(name){
                var city = (provNode.cities||[]).find(function(c){return c.name===name;});
                if(city) showItems(city.items||[], city.name, city.count);
              });
            }, function(){ showMsg('省级地图加载失败'); });
          }

          function flatItems(cities){
            var out=[]; (cities||[]).forEach(function(c){ (c.items||[]).forEach(function(i){out.push(i);}); });
            return out;
          }

          function showItems(items, title, count){
            panelEl.innerHTML = '';
            var head = el('div','rm-panel-head');
            head.appendChild(el('span', null, title));
            head.appendChild(el('span', null, (count!=null?count:items.length)+' 条'));
            panelEl.appendChild(head);
            if(!items.length){
              panelEl.appendChild(el('div','rm-panel-empty','暂无新闻'));
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
            panelEl.appendChild(list);
          }

          function drillTo(idx){
            var target = stack[idx];
            if(!target) return;
            if(target.level==='world') renderWorld();
            else if(target.level==='china') renderChina(target.node);
            else if(target.level==='province') renderProvince(target.cn, target.node);
          }

          function renderUnknown(){
            var det = document.getElementById('rmUnknown');
            if(!det) return;
            var head = det.querySelector('.rm-unk-head');
            var unk = DATA.unknown||{count:0, items:[]};
            head.textContent = '未识别地区（'+unk.count+' 条）';
            det.addEventListener('toggle', function(){
              if(det.open) showItems(unk.items||[], '未识别地区', unk.count);
            });
          }

          if(typeof echarts === 'undefined'){
            chartEl.innerHTML = '';
            chartEl.appendChild(el('div','rm-error','地图组件加载失败（ECharts CDN 不可达）'));
          } else {
            renderWorld();
          }
          renderUnknown();
        })();
        </script>
    """

    js = (
        js.replace("__ECHARTS__", _ECHARTS_CDN)
        .replace("__WORLD__", _WORLD_MAP_URL)
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
                        <div class="rm-chart-wrap" id="rmChart"></div>
                        <div class="rm-panel" id="rmPanel">
                            <div class="rm-panel-empty">点击地图查看新闻</div>
                        </div>
                        {unknown_html}
                    </div>
                    {js}
                </div>"""
