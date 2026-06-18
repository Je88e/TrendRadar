# coding=utf-8
"""
AI 地区分类模块

通过 AI 对新闻标题进行地区分类（国家/省/市），
出规范中文全称，由 RegionNormalizer 归一化为 code。

镜像 trendradar/ai/filter.py 的结构与约定。
"""

import json
import time
from typing import Any, Callable, Dict, List, Optional, Set

from trendradar.ai.client import AIClient
from trendradar.ai.prompt_loader import load_prompt_template
from trendradar.regions.normalizer import RegionNormalizer

# 合法 level 值（其他值强转为 unknown）
_VALID_LEVELS = frozenset({"unknown", "country", "province", "city"})


class RegionClassifier:
    """AI 地区分类器。

    构造参数：
      - ai_config: AI 模型配置（传给 AIClient，复用全局 ai 段）
      - normalizer: RegionNormalizer 实例
      - region_classify_config: {"BATCH_SIZE": int, "BATCH_INTERVAL": int, ...}
      - get_time_func: () -> str，时间戳工厂
      - country_list: 全量国家规范全称，注入提示词 {country_list} 占位
      - debug: 打印 prompt/response 调试信息
    """

    def __init__(
        self,
        ai_config: Dict[str, Any],
        normalizer: RegionNormalizer,
        region_classify_config: Dict[str, Any],
        get_time_func: Callable[[], str],
        country_list: str = "",
        debug: bool = False,
    ):
        self.client = AIClient(ai_config)
        self.normalizer = normalizer
        self.batch_size = region_classify_config.get("BATCH_SIZE", 200)
        self.batch_interval = region_classify_config.get("BATCH_INTERVAL", 1)
        self.get_time_func = get_time_func
        self._country_list = country_list
        self.debug = debug

        # 加载提示词
        self.classify_system, self.classify_user = load_prompt_template(
            region_classify_config.get("PROMPT_FILE", "prompt.txt"),
            config_subdir="region_classify",
            label="地区分类",
        )

    # ── JSON 提取（镜像 filter.py 思路）──

    @staticmethod
    def _extract_json(response: Optional[str]) -> Optional[str]:
        if not response or not response.strip():
            return None

        json_str = response.strip()

        if "```json" in json_str:
            parts = json_str.split("```json", 1)
            if len(parts) > 1:
                code_block = parts[1]
                end_idx = code_block.find("```")
                json_str = code_block[:end_idx] if end_idx != -1 else code_block
        elif "```" in json_str:
            parts = json_str.split("```", 2)
            if len(parts) >= 2:
                json_str = parts[1]

        json_str = json_str.strip()
        return json_str if json_str else None

    # ── 响应解析 + 归一化 ──

    def _parse_response(
        self,
        response: Optional[str],
        expected_ids: Set[int],
    ) -> List[Dict[str, Any]]:
        """解析 AI 分类响应，逐条归一化后返回。

        Args:
            response: AI 原始响应文本
            expected_ids: 本批有效的 news_item_id 集合

        Returns:
            归一化后的地区结果列表，每项对应 region_classify_results 一行。
            JSON 解析失败 / 空响应 → 空列表。
        """
        json_str = self._extract_json(response)
        if not json_str:
            if self.debug:
                print(f"[RegionClassify][DEBUG] 无法从响应提取 JSON，前 500 字符: {(response or '')[:500]}")
            return []

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            if self.debug:
                print(f"[RegionClassify][DEBUG] JSON 解析失败: {e}")
            return []

        if not isinstance(data, list):
            if self.debug:
                print(f"[RegionClassify][DEBUG] 响应顶层非数组，类型: {type(data).__name__}")
            return []

        results: List[Dict[str, Any]] = []
        skipped_ids = 0
        skipped_level = 0

        for item in data:
            if not isinstance(item, dict):
                continue

            item_id = item.get("id")
            if item_id not in expected_ids:
                skipped_ids += 1
                continue

            # level 校验
            level = (item.get("level") or "").strip().lower()
            if level not in _VALID_LEVELS:
                level = "unknown"
                skipped_level += 1

            # confidence 解析
            raw_conf = item.get("confidence", 0.0)
            try:
                confidence = max(0.0, min(1.0, float(raw_conf)))
            except (ValueError, TypeError):
                confidence = 0.0

            # 归一化：非 unknown → normalizer
            if level == "unknown":
                norm = self.normalizer.normalize("unknown", None, None, None)
            else:
                country = item.get("country")
                province = item.get("province")
                city = item.get("city")
                norm = self.normalizer.normalize(level, country, province, city)

            results.append({
                "id": item_id,
                "level": level,
                "country": norm.country,
                "country_code": norm.country_code,
                "country_echarts": norm.country_echarts,
                "province": norm.province,
                "province_adcode": norm.province_adcode,
                "city": norm.city,
                "city_adcode": norm.city_adcode,
                "confidence": confidence,
            })

        if self.debug:
            print(f"[RegionClassify][DEBUG] --- 解析结果 ---")
            print(f"[RegionClassify][DEBUG] AI 返回 {len(data)} 项, 有效 {len(results)} 项")
            if skipped_ids:
                print(f"[RegionClassify][DEBUG] 跳过无效 id: {skipped_ids}")
            if skipped_level:
                print(f"[RegionClassify][DEBUG] 非法 level 强转 unknown: {skipped_level}")

        return results

    # ── 批次分类 ──

    def classify_batch(
        self,
        titles: List[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        """对一批新闻标题做地区分类（单批直接调 AI）。

        Args:
            titles: [{"id": news_item_id, "title": str, "source": str}]

        Returns:
            归一化后的地区结果列表（含 unknown）。
            AI 调用失败 → None（调用方应标记失败以便重试）。
        """
        if not titles:
            return []

        if not self.classify_user:
            print("[RegionClassify] 分类提示词模板为空")
            return None

        # 构建新闻列表
        news_list = "\n".join(
            f"{t['id']}. [{t.get('source', '')}] {t['title']}"
            for t in titles
        )

        user_prompt = self.classify_user
        user_prompt = user_prompt.replace("{country_list}", self._country_list)
        user_prompt = user_prompt.replace("{news_count}", str(len(titles)))
        user_prompt = user_prompt.replace("{news_list}", news_list)

        messages: List[Dict[str, str]] = []
        if self.classify_system:
            messages.append({"role": "system", "content": self.classify_system})
        messages.append({"role": "user", "content": user_prompt})

        if self.debug:
            total_chars = sum(len(m["content"]) for m in messages)
            print(f"\n[RegionClassify][DEBUG] === Prompt (标题数={len(titles)}, 长度={total_chars} 字符) ===")
            for m in messages:
                content = m["content"]
                lines = content.split("\n")
                if len(lines) > 30:
                    head = lines[:15]
                    tail = lines[-10:]
                    omitted = len(lines) - 25
                    truncated = "\n".join(head) + f"\n... (省略 {omitted} 行) ...\n" + "\n".join(tail)
                    print(f"[{m['role']}]\n{truncated}")
                else:
                    print(f"[{m['role']}]\n{content}")
            print(f"[RegionClassify][DEBUG] === Prompt 结束 ===")

        try:
            response = self.client.chat(messages)

            if self.debug:
                print(f"\n[RegionClassify][DEBUG] === AI 原始响应 ===")
                try:
                    j = self._extract_json(response)
                    if j:
                        parsed = json.loads(j)
                        if isinstance(parsed, list):
                            lines = [json.dumps(item, ensure_ascii=False) for item in parsed]
                            print("[\n  " + ",\n  ".join(lines) + "\n]")
                        else:
                            print(json.dumps(parsed, ensure_ascii=False, indent=2))
                    else:
                        print(response)
                except Exception:
                    print(response)
                print(f"[RegionClassify][DEBUG] === 响应结束 ===")

            title_ids = {t["id"] for t in titles}
            return self._parse_response(response, title_ids)
        except Exception as e:
            print(f"[RegionClassify] 分类请求失败: {type(e).__name__}: {e}")
            return None
