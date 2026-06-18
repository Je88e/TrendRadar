# coding=utf-8
"""
地区归一化器

把 AI 输出的中文地区名（国家/省/市）转成地图渲染所需的 code：
- 国家 → ISO alpha-2 + ECharts 世界图英文名
- 中国 省/市 → adcode（国标行政区划码）
- 海外 省/市 → 仅保留中文名，无 adcode（见 ADR-0001）

归一化失败（名字不在对照表）时优雅降级：照存名字、code 留 NULL，
不阻断流程（见 ADR-0002）。

数据源：trendradar/regions/data/{countries.json, china.json}（由
scripts/build_regions_data.py 快照生成）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# 中国 ISO alpha-2，用于判定是否进入省市 adcode 查找
_CHINA_CODE = "CN"


@dataclass(frozen=True)
class NormalizedRegion:
    """归一化后的单条新闻地区结果，对应 region_classify_results 一行。"""

    level: str                            # unknown / country / province / city（已小写）
    country: Optional[str]                # 规范中文全称；失败时为原始输入
    country_code: Optional[str]           # ISO alpha-2；失败 NULL
    country_echarts: Optional[str]        # ECharts 世界图英文名；失败 NULL
    province: Optional[str]               # 规范中文全称；海外仅名
    province_adcode: Optional[str]        # 仅中国；海外 NULL
    city: Optional[str]                   # 规范中文全称；海外仅名
    city_adcode: Optional[str]            # 仅中国；海外 NULL


class RegionNormalizer:
    """地区名 → code 归一化器。不可变索引，线程安全。

    测试可直接构造（注入小数据集）；生产用 from_data_dir()。
    """

    def __init__(self, countries: List[Dict[str, Any]], china: Dict[str, Any]):
        # 国家：name + aliases → 记录（首个命中优先，setdefault 防别名覆盖正式名）
        self._country_index: Dict[str, Dict[str, Any]] = {}
        for c in countries:
            rec = {
                "code": c["code"],
                "name": c["name"],
                "echarts": c.get("echarts_name"),
            }
            self._country_index.setdefault(c["name"].strip().lower(), rec)
            for alias in c.get("aliases", []):
                self._country_index.setdefault(alias.strip().lower(), rec)

        # 中国省/市：name + aliases → 记录，市挂在省下
        self._province_index: Dict[str, Dict[str, Any]] = {}
        for p in china.get("provinces", []):
            cities: Dict[str, Dict[str, Any]] = {}
            for city in p.get("cities", []):
                crec = {"adcode": city["adcode"], "name": city["name"]}
                cities.setdefault(city["name"].strip().lower(), crec)
                for alias in city.get("aliases", []):
                    cities.setdefault(alias.strip().lower(), crec)

            prec = {"adcode": p["adcode"], "name": p["name"], "cities": cities}
            self._province_index.setdefault(p["name"].strip().lower(), prec)
            for alias in p.get("aliases", []):
                self._province_index.setdefault(alias.strip().lower(), prec)

    @classmethod
    def from_data_dir(cls, data_dir: str | Path) -> "RegionNormalizer":
        """从数据目录加载 countries.json + china.json 构建归一化器。"""
        d = Path(data_dir)
        countries = json.loads((d / "countries.json").read_text(encoding="utf-8"))
        china = json.loads((d / "china.json").read_text(encoding="utf-8"))
        return cls(countries=countries, china=china)

    def get_country_echarts_map(self) -> Dict[str, str]:
        """返回 ISO alpha-2 → ECharts 世界图英文名 映射。

        报告世界 choropleth 渲染用：ECharts world 地图的 feature name 是英文国名，
        需把分类结果的 country_code 映射到 echarts_name 才能上色。
        归一化表里缺 echarts_name 的国家不出现（该节点不上色但不报错）。
        """
        mapping: Dict[str, str] = {}
        for rec in self._country_index.values():
            code = rec.get("code")
            echarts = rec.get("echarts")
            if code and echarts:
                mapping.setdefault(code, echarts)
        return mapping

    @staticmethod
    def _key(name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        s = name.strip().lower()
        return s or None

    def normalize(
        self,
        level: Optional[str],
        country: Optional[str],
        province: Optional[str],
        city: Optional[str],
    ) -> NormalizedRegion:
        """把一条 AI 输出归一化为 NormalizedRegion。

        失败优雅降级：查不到的层级照存原始名字，code 留 NULL。
        """
        lvl = (level or "").strip().lower()

        crec = self._country_index.get(self._key(country)) if country else None
        country_name = crec["name"] if crec else (country.strip() if country else None)
        country_code = crec["code"] if crec else None
        country_echarts = crec["echarts"] if crec else None

        province_name = province.strip() if province else None
        city_name = city.strip() if city else None
        province_adcode: Optional[str] = None
        city_adcode: Optional[str] = None

        # 仅中国解析省市 adcode（ADR-0001：海外省/市无 adcode）
        if crec and crec["code"] == _CHINA_CODE and province:
            prec = self._province_index.get(self._key(province))
            if prec:
                province_name = prec["name"]
                province_adcode = prec["adcode"]
                if city:
                    city_rec = prec["cities"].get(self._key(city))
                    if city_rec:
                        city_name = city_rec["name"]
                        city_adcode = city_rec["adcode"]

        return NormalizedRegion(
            level=lvl,
            country=country_name,
            country_code=country_code,
            country_echarts=country_echarts,
            province=province_name,
            province_adcode=province_adcode,
            city=city_name,
            city_adcode=city_adcode,
        )
