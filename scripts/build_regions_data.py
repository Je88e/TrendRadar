# coding=utf-8
"""
地区归一化数据生成脚本（DEV 工具，不入运行时）

从公开数据源快照生成两份静态 JSON，供 RegionNormalizer 使用：
- trendradar/regions/data/china.json   ← DataV GeoAtlas（省/市 adcode + 派生简称）
- trendradar/regions/data/countries.json ← mledoze/countries（ISO + 中文名 + 英文名）

用法：
    uv run python scripts/build_regions_data.py

需联网。行政区划变更后重跑即可。
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import requests

# ---- 数据源 ----
DATAV_BASE = "https://geo.datav.aliyun.com/areas_v3/bound"
CHINA_ADCODE = 100000  # 全国
COUNTRIES_URL = "https://raw.githubusercontent.com/mledoze/countries/master/countries.json"

DATA_DIR = Path(__file__).resolve().parent.parent / "trendradar" / "regions" / "data"

# 中国省级行政区后缀（用于派生简称别名）
_PROVINCE_SUFFIX = re.compile(r"(壮族自治区|维吾尔自治区|回族自治区|藏族自治区|自治区|特别行政区|省)$")
# 地级市/自治州/地区/盟后缀
_CITY_SUFFIX = re.compile(r"(自治州|地区|盟|市)$")

# ECharts 世界图英文名与 mledoze name.common 的已知差异修正
# （ECharts world.json 用了部分非标准/缩写名，phase 5 注册地图时以本字段为准）
_ECHARTS_NAME_FIXUP: Dict[str, str] = {
    "United States": "United States of America",
    "South Korea": "South Korea",
    "North Korea": "North Korea",
    "Democratic Republic of the Congo": "Dem. Rep. Congo",
    "Republic of the Congo": "Congo",
    "Dominican Republic": "Dominican Rep.",
    "Bosnia and Herzegovina": "Bosnia and Herz.",
    "Equatorial Guinea": "Eq. Guinea",
    "Western Sahara": "W. Sahara",
    "Central African Republic": "Central African Rep.",
    "South Sudan": "South Sudan",
    "Solomon Islands": "Solomon Is.",
    "Falkland Islands": "Falkland Is.",
    "Czechia": "Czech Rep.",
    "Lao People's Democratic Republic": "Laos",
    "Syrian Arab Republic": "Syria",
    "Eswatini": "eSwatini",
    "United Republic of Tanzania": "Tanzania",
    "Myanmar": "Myanmar",
}


def _get_json(url: str, retries: int = 3) -> Any:
    last_err: Exception | None = None
    for i in range(retries):
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1 + i)
    raise RuntimeError(f"获取失败 {url}: {last_err}")


def _province_alias(name: str) -> str | None:
    stripped = _PROVINCE_SUFFIX.sub("", name)
    return stripped or None


def _city_alias(name: str) -> str | None:
    stripped = _CITY_SUFFIX.sub("", name)
    if not stripped or stripped == name:
        return None
    return stripped


def build_china() -> Dict[str, Any]:
    """从 DataV 抓全国省/市树。"""
    root = _get_json(f"{DATAV_BASE}/{CHINA_ADCODE}_full.json")
    provinces_out: List[Dict[str, Any]] = []

    for feat in root.get("features", []):
        props = feat.get("properties", {})
        if props.get("level") != "province":
            continue
        padcode = str(props["adcode"])
        pname = props["name"]
        aliases = [a for a in {_province_alias(pname)} if a]

        # 抓该省下级（地级市；直辖市/特区则含 district）
        cities_out: List[Dict[str, Any]] = []
        try:
            sub = _get_json(f"{DATAV_BASE}/{padcode}_full.json")
        except RuntimeError as e:
            print(f"  [warn] 跳过 {pname}({padcode}) 下级: {e}", file=sys.stderr)
            sub = {"features": []}

        for cfeat in sub.get("features", []):
            cprops = cfeat.get("properties", {})
            clevel = cprops.get("level")
            # level=city（地级市/自治州/地区/盟）或 level=district（直辖市的区）
            if clevel not in ("city", "district"):
                continue
            # 直辖市的 district 不作为「市」（避免北京市→东城区 当市）
            if clevel == "district":
                continue
            cadcode = str(cprops["adcode"])
            cname = cprops["name"]
            caliases = [a for a in {_city_alias(cname)} if a]
            cities_out.append(
                {"adcode": cadcode, "name": cname, "aliases": caliases}
            )

        provinces_out.append(
            {"adcode": padcode, "name": pname, "aliases": aliases, "cities": cities_out}
        )
        print(f"  省 {pname}({padcode}): {len(cities_out)} 市")
        time.sleep(0.2)  # 礼貌限速

    return {"provinces": provinces_out}


def build_countries() -> List[Dict[str, Any]]:
    """从 mledoze/countries 抓 ISO + 中文名 + 英文名。"""
    raw = _get_json(COUNTRIES_URL)
    out: List[Dict[str, Any]] = []
    for c in raw:
        code = c.get("cca2")
        if not code or len(code) != 2:
            continue
        common_en = c.get("name", {}).get("common", "")
        zho = c.get("translations", {}).get("zho", {})
        zh_common = zho.get("common", "").strip()
        zh_official = zho.get("official", "").strip()
        if not zh_common:
            continue  # 无中文名的国家不收录
        aliases = [zh_official] if zh_official and zh_official != zh_common else []
        echarts = _ECHARTS_NAME_FIXUP.get(common_en, common_en)
        out.append(
            {
                "code": code.upper(),
                "name": zh_common,
                "echarts_name": echarts,
                "aliases": aliases,
            }
        )
    # 按中文名排序，便于阅读
    out.sort(key=lambda x: x["name"])
    return out


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/2] 生成 china.json (DataV)...")
    china = build_china()
    (DATA_DIR / "china.json").write_text(
        json.dumps(china, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    prov_n = len(china["provinces"])
    city_n = sum(len(p["cities"]) for p in china["provinces"])
    print(f"    省 {prov_n}, 市 {city_n}")

    print("[2/2] 生成 countries.json (mledoze)...")
    countries = build_countries()
    (DATA_DIR / "countries.json").write_text(
        json.dumps(countries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"    国家 {len(countries)}")

    print(f"\n完成，输出: {DATA_DIR}")


if __name__ == "__main__":
    main()
