# coding=utf-8
"""
应用上下文模块

提供配置上下文类，封装所有依赖配置的操作，消除全局状态和包装函数。
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from trendradar.utils.time import (
    DEFAULT_TIMEZONE,
    get_configured_time,
    format_date_folder,
    format_time_filename,
    get_current_time_display,
    convert_time_for_display,
    format_iso_time_friendly,
    is_within_days,
)
from trendradar.core import (
    load_frequency_words,
    matches_word_groups,
    read_all_today_titles,
    detect_latest_new_titles,
    count_word_frequency,
    Scheduler,
)
from trendradar.report import (
    prepare_report_data,
    generate_html_report,
    render_html_content,
    enrich_rss_stats_with_pinned,
)
from trendradar.report.region import build_region_map_payload, collect_filtered_keys
from trendradar.notification import (
    render_feishu_content,
    render_dingtalk_content,
    split_content_into_batches,
    NotificationDispatcher,
)
from trendradar.ai import AITranslator
from trendradar.ai.filter import AIFilterResult
from trendradar.ai.filter_pipeline import AIFilterPipeline, _TagExtractionError
from trendradar.ai.region import RegionClassifier
from trendradar.regions.normalizer import RegionNormalizer
from trendradar.storage import get_storage_manager


class AppContext:
    """
    应用上下文类

    封装所有依赖配置的操作，提供统一的接口。
    消除对全局 CONFIG 的依赖，提高可测试性。

    使用示例:
        config = load_config()
        ctx = AppContext(config)

        # 时间操作
        now = ctx.get_time()
        date_folder = ctx.format_date()

        # 存储操作
        storage = ctx.get_storage_manager()

        # 报告生成
        html = ctx.generate_html_report(stats, total_titles, ...)
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化应用上下文

        Args:
            config: 完整的配置字典
        """
        self.config = config
        self._storage_manager = None
        self._scheduler = None
        self._region_classifier = None
        self._region_normalizer = None

    # === 配置访问 ===

    @property
    def timezone(self) -> str:
        """获取配置的时区"""
        return self.config.get("TIMEZONE", DEFAULT_TIMEZONE)

    @property
    def rank_threshold(self) -> int:
        """获取排名阈值"""
        return self.config.get("RANK_THRESHOLD", 50)

    @property
    def weight_config(self) -> Dict:
        """获取权重配置"""
        return self.config.get("WEIGHT_CONFIG", {})

    @property
    def platforms(self) -> List[Dict]:
        """获取平台配置列表"""
        return self.config.get("PLATFORMS", [])

    @property
    def platform_ids(self) -> List[str]:
        """获取平台ID列表"""
        return [p["id"] for p in self.platforms]

    @property
    def rss_config(self) -> Dict:
        """获取 RSS 配置"""
        return self.config.get("RSS", {})

    @property
    def rss_enabled(self) -> bool:
        """RSS 是否启用"""
        return self.rss_config.get("ENABLED", False)

    @property
    def rss_feeds(self) -> List[Dict]:
        """获取 RSS 源列表"""
        return self.rss_config.get("FEEDS", [])

    @property
    def display_mode(self) -> str:
        """获取显示模式 (keyword | platform)"""
        return self.config.get("DISPLAY_MODE", "keyword")

    @property
    def show_new_section(self) -> bool:
        """是否显示新增热点区域"""
        return self.config.get("DISPLAY", {}).get("REGIONS", {}).get("NEW_ITEMS", True)

    @property
    def region_order(self) -> List[str]:
        """获取区域显示顺序"""
        default_order = ["hotlist", "rss", "new_items", "standalone", "ai_analysis"]
        return self.config.get("DISPLAY", {}).get("REGION_ORDER", default_order)

    @property
    def filter_method(self) -> str:
        """获取筛选策略: keyword | ai"""
        return self.config.get("FILTER", {}).get("METHOD", "keyword")

    @property
    def ai_priority_sort_enabled(self) -> bool:
        """AI 模式标签排序开关（与 keyword 的 sort_by_position_first 解耦）"""
        return self.config.get("FILTER", {}).get("PRIORITY_SORT_ENABLED", False)

    @property
    def ai_filter_config(self) -> Dict:
        """获取 AI 筛选配置"""
        return self.config.get("AI_FILTER", {})

    @property
    def ai_filter_enabled(self) -> bool:
        """AI 筛选是否启用（基于 filter.method 判断）"""
        return self.filter_method == "ai"

    @property
    def region_classify_config(self) -> Dict:
        """获取地区分类配置"""
        return self.config.get("REGION_CLASSIFY", {})

    @property
    def region_classify_enabled(self) -> bool:
        """地区分类是否启用（opt-in，默认关）"""
        return self.region_classify_config.get("ENABLED", False)

    @property
    def region_map_enabled(self) -> bool:
        """报告 region_map 区是否显示（display 层开关，默认关）"""
        return self.config.get("DISPLAY", {}).get("REGIONS", {}).get("REGION_MAP", False)

    def get_region_classifier(self) -> Optional[RegionClassifier]:
        """懒构造 RegionClassifier 单例（注入 normalizer + country_list）。

        开关关闭 → 返回 None，不构造（零成本）。
        normalizer 从内置数据资产加载；country_list 由全量国家全称拼接，
        注入提示词 {country_list} 占位。
        """
        if not self.region_classify_enabled:
            return None

        if self._region_classifier is None:
            # 用 normalizer.py 同级 data/ 目录
            from trendradar.regions import normalizer as _norm_mod
            data_dir = Path(_norm_mod.__file__).parent / "data"
            normalizer = RegionNormalizer.from_data_dir(data_dir)

            # country_list：全量国家全称（逗号分隔），约束 AI 出规范国名
            import json
            countries = json.loads((data_dir / "countries.json").read_text(encoding="utf-8"))
            country_list = "、".join(c["name"] for c in countries)

            rc = self.region_classify_config
            self._region_classifier = RegionClassifier(
                ai_config=self.config.get("AI", {}),
                normalizer=normalizer,
                region_classify_config=rc,
                get_time_func=lambda: self.get_time().isoformat(),
                country_list=country_list,
                debug=self.config.get("DEBUG", False),
            )
        return self._region_classifier

    def _get_region_normalizer(self) -> RegionNormalizer:
        """懒构造归一化器单例（纯数据资产，不依赖 region_classify 开关）。

        地区地图展示层（region_map）可能独立于分类开关启用，展示历史结果，
        故单独构造，避免与 get_region_classifier 的 enabled 门控耦合。
        """
        if self._region_normalizer is None:
            from trendradar.regions import normalizer as _norm_mod
            data_dir = Path(_norm_mod.__file__).parent / "data"
            self._region_normalizer = RegionNormalizer.from_data_dir(data_dir)
        return self._region_normalizer

    def get_region_map_payload(
        self,
        stats: Optional[List[Dict]] = None,
        rss_items: Optional[List[Dict]] = None,
    ) -> Optional[Dict[str, Any]]:
        """构建地区地图 payload（design 6.1 树），供 HTML 渲染。

        开关关（region_map_enabled=False）→ None（不渲染该区）。
        否则从 storage 取 active 结果树 + 注入 echarts 世界名映射，构建 payload。

        渲染阶段筛选：传入 stats/rss_items（与热榜/RSS 区同源，均已通过兴趣
        筛选）时，payload 仅保留命中的 active 项，使地区地图与报告其他区一致。
        两者都缺省 → 不过滤（向后兼容旧调用与测试）。
        """
        if not self.region_map_enabled:
            return None
        storage = self.get_storage_manager()
        active = storage.get_active_region_classify_results()
        echarts_names = self._get_region_normalizer().get_country_echarts_map()
        # 任一显式传入即启用筛选（含空 list，表示该区本轮无命中）
        if stats is not None or rss_items is not None:
            allowed_keys = collect_filtered_keys(stats, rss_items)
            return build_region_map_payload(
                active, echarts_names=echarts_names, allowed_keys=allowed_keys
            )
        return build_region_map_payload(active, echarts_names=echarts_names)

    # === 时间操作 ===

    def get_time(self) -> datetime:
        """获取当前配置时区的时间"""
        return get_configured_time(self.timezone)

    def format_date(self) -> str:
        """格式化日期文件夹 (YYYY-MM-DD)"""
        return format_date_folder(timezone=self.timezone)

    def format_time(self) -> str:
        """格式化时间文件名 (HH-MM)"""
        return format_time_filename(self.timezone)

    def get_time_display(self) -> str:
        """获取时间显示 (HH:MM)"""
        return get_current_time_display(self.timezone)

    @staticmethod
    def convert_time_display(time_str: str) -> str:
        """将 HH-MM 转换为 HH:MM"""
        return convert_time_for_display(time_str)

    # === 存储操作 ===

    def get_storage_manager(self):
        """获取存储管理器（延迟初始化，单例）"""
        if self._storage_manager is None:
            storage_config = self.config.get("STORAGE", {})
            remote_config = storage_config.get("REMOTE", {})
            local_config = storage_config.get("LOCAL", {})
            pull_config = storage_config.get("PULL", {})

            self._storage_manager = get_storage_manager(
                backend_type=storage_config.get("BACKEND", "auto"),
                data_dir=local_config.get("DATA_DIR", "output"),
                enable_txt=storage_config.get("FORMATS", {}).get("TXT", True),
                enable_html=storage_config.get("FORMATS", {}).get("HTML", True),
                remote_config={
                    "bucket_name": remote_config.get("BUCKET_NAME", ""),
                    "access_key_id": remote_config.get("ACCESS_KEY_ID", ""),
                    "secret_access_key": remote_config.get("SECRET_ACCESS_KEY", ""),
                    "endpoint_url": remote_config.get("ENDPOINT_URL", ""),
                    "region": remote_config.get("REGION", ""),
                },
                local_retention_days=local_config.get("RETENTION_DAYS", 0),
                remote_retention_days=remote_config.get("RETENTION_DAYS", 0),
                pull_enabled=pull_config.get("ENABLED", False),
                pull_days=pull_config.get("DAYS", 7),
                timezone=self.timezone,
            )
        return self._storage_manager

    def get_output_path(self, subfolder: str, filename: str) -> str:
        """获取输出路径（扁平化结构：output/类型/日期/文件名）"""
        output_dir = Path("output") / subfolder / self.format_date()
        output_dir.mkdir(parents=True, exist_ok=True)
        return str(output_dir / filename)

    # === 数据处理 ===

    def read_today_titles(
        self, platform_ids: Optional[List[str]] = None, quiet: bool = False
    ) -> Tuple[Dict, Dict, Dict]:
        """读取当天所有标题"""
        return read_all_today_titles(self.get_storage_manager(), platform_ids, quiet=quiet)

    def detect_new_titles(
        self, platform_ids: Optional[List[str]] = None, quiet: bool = False
    ) -> Dict:
        """检测最新批次的新增标题"""
        return detect_latest_new_titles(self.get_storage_manager(), platform_ids, quiet=quiet)

    def is_first_crawl(self) -> bool:
        """检测是否是当天第一次爬取"""
        return self.get_storage_manager().is_first_crawl_today()

    # === 频率词处理 ===

    def load_frequency_words(
        self, frequency_file: Optional[str] = None
    ) -> Tuple[List[Dict], List[str], List[str]]:
        """加载频率词配置"""
        return load_frequency_words(frequency_file)

    def matches_word_groups(
        self,
        title: str,
        word_groups: List[Dict],
        filter_words: List[str],
        global_filters: Optional[List[str]] = None,
    ) -> bool:
        """检查标题是否匹配词组规则"""
        return matches_word_groups(title, word_groups, filter_words, global_filters)

    # === 统计分析 ===

    def count_frequency(
        self,
        results: Dict,
        word_groups: List[Dict],
        filter_words: List[str],
        id_to_name: Dict,
        title_info: Optional[Dict] = None,
        new_titles: Optional[Dict] = None,
        mode: str = "daily",
        global_filters: Optional[List[str]] = None,
        quiet: bool = False,
    ) -> Tuple[List[Dict], int]:
        """统计词频"""
        return count_word_frequency(
            results=results,
            word_groups=word_groups,
            filter_words=filter_words,
            id_to_name=id_to_name,
            title_info=title_info,
            rank_threshold=self.rank_threshold,
            new_titles=new_titles,
            mode=mode,
            global_filters=global_filters,
            weight_config=self.weight_config,
            max_news_per_keyword=self.config.get("MAX_NEWS_PER_KEYWORD", 0),
            sort_by_position_first=self.config.get("SORT_BY_POSITION_FIRST", False),
            is_first_crawl_func=self.is_first_crawl,
            convert_time_func=self.convert_time_display,
            quiet=quiet,
        )

    # === 报告生成 ===

    def prepare_report(
        self,
        stats: List[Dict],
        failed_ids: Optional[List] = None,
        new_titles: Optional[Dict] = None,
        id_to_name: Optional[Dict] = None,
        mode: str = "daily",
        frequency_file: Optional[str] = None,
    ) -> Dict:
        """准备报告数据"""
        return prepare_report_data(
            stats=stats,
            failed_ids=failed_ids,
            new_titles=new_titles,
            id_to_name=id_to_name,
            mode=mode,
            rank_threshold=self.rank_threshold,
            show_new_section=self.show_new_section,
            pinned_keywords=self.config.get("PINNED_KEYWORDS", set()),
        )

    def generate_html(
        self,
        stats: List[Dict],
        total_titles: int,
        failed_ids: Optional[List] = None,
        new_titles: Optional[Dict] = None,
        id_to_name: Optional[Dict] = None,
        mode: str = "daily",
        update_info: Optional[Dict] = None,
        rss_items: Optional[List[Dict]] = None,
        rss_new_items: Optional[List[Dict]] = None,
        ai_analysis: Optional[Any] = None,
        standalone_data: Optional[Dict] = None,
        frequency_file: Optional[str] = None,
        report_metadata: Optional[Dict] = None,
        translate_report_func: Optional[Any] = None,
        region_map: Optional[Dict[str, Any]] = None,
    ) -> str:
        """生成HTML报告"""
        return generate_html_report(
            stats=stats,
            total_titles=total_titles,
            failed_ids=failed_ids,
            new_titles=new_titles,
            id_to_name=id_to_name,
            mode=mode,
            update_info=update_info,
            rank_threshold=self.rank_threshold,
            output_dir="output",
            date_folder=self.format_date(),
            time_filename=self.format_time(),
            render_html_func=lambda *args, **kwargs: self.render_html(*args, rss_items=rss_items, rss_new_items=rss_new_items, ai_analysis=ai_analysis, standalone_data=standalone_data, region_map=region_map, **kwargs),
            report_metadata=report_metadata,
            translate_report_func=translate_report_func,
            pinned_keywords=self.config.get("PINNED_KEYWORDS", set()),
        )

    def render_html(
        self,
        report_data: Dict,
        total_titles: int,
        mode: str = "daily",
        update_info: Optional[Dict] = None,
        rss_items: Optional[List[Dict]] = None,
        rss_new_items: Optional[List[Dict]] = None,
        ai_analysis: Optional[Any] = None,
        standalone_data: Optional[Dict] = None,
        region_map: Optional[Dict[str, Any]] = None,
    ) -> str:
        """渲染HTML内容"""
        # 固定词组：为 RSS 关键词统计补充固定空词组占位（不改 analyzer，§4）
        pinned_keywords = self.config.get("PINNED_KEYWORDS", set())
        rss_items = enrich_rss_stats_with_pinned(rss_items, pinned_keywords)
        rss_new_items = enrich_rss_stats_with_pinned(rss_new_items, pinned_keywords)
        return render_html_content(
            report_data=report_data,
            total_titles=total_titles,
            mode=mode,
            update_info=update_info,
            region_order=self.region_order,
            get_time_func=self.get_time,
            rss_items=rss_items,
            rss_new_items=rss_new_items,
            display_mode=self.display_mode,
            ai_analysis=ai_analysis,
            show_new_section=self.show_new_section,
            standalone_data=standalone_data,
            region_map=region_map,
            timezone=self.timezone,
        )

    # === 通知内容渲染 ===

    def render_feishu(
        self,
        report_data: Dict,
        update_info: Optional[Dict] = None,
        mode: str = "daily",
    ) -> str:
        """渲染飞书内容"""
        return render_feishu_content(
            report_data=report_data,
            update_info=update_info,
            mode=mode,
            separator=self.config.get("FEISHU_MESSAGE_SEPARATOR", "---"),
            region_order=self.region_order,
            get_time_func=self.get_time,
            show_new_section=self.show_new_section,
        )

    def render_dingtalk(
        self,
        report_data: Dict,
        update_info: Optional[Dict] = None,
        mode: str = "daily",
    ) -> str:
        """渲染钉钉内容"""
        return render_dingtalk_content(
            report_data=report_data,
            update_info=update_info,
            mode=mode,
            region_order=self.region_order,
            get_time_func=self.get_time,
            show_new_section=self.show_new_section,
        )

    def split_content(
        self,
        report_data: Dict,
        format_type: str,
        update_info: Optional[Dict] = None,
        max_bytes: Optional[int] = None,
        mode: str = "daily",
        rss_items: Optional[list] = None,
        rss_new_items: Optional[list] = None,
        ai_content: Optional[str] = None,
        standalone_data: Optional[Dict] = None,
        ai_stats: Optional[Dict] = None,
        report_type: str = "热点分析报告",
    ) -> List[str]:
        """分批处理消息内容（支持热榜+RSS合并+AI分析+独立展示区）

        Args:
            report_data: 报告数据
            format_type: 格式类型
            update_info: 更新信息
            max_bytes: 最大字节数
            mode: 报告模式
            rss_items: RSS 统计条目列表
            rss_new_items: RSS 新增条目列表
            ai_content: AI 分析内容（已渲染的字符串）
            standalone_data: 独立展示区数据
            ai_stats: AI 分析统计数据
            report_type: 报告类型

        Returns:
            分批后的消息内容列表
        """
        return split_content_into_batches(
            report_data=report_data,
            format_type=format_type,
            update_info=update_info,
            max_bytes=max_bytes,
            mode=mode,
            batch_sizes={
                "dingtalk": self.config.get("DINGTALK_BATCH_SIZE", 20000),
                "feishu": self.config.get("FEISHU_BATCH_SIZE", 29000),
                "default": self.config.get("MESSAGE_BATCH_SIZE", 4000),
            },
            feishu_separator=self.config.get("FEISHU_MESSAGE_SEPARATOR", "---"),
            region_order=self.region_order,
            get_time_func=self.get_time,
            rss_items=rss_items,
            rss_new_items=rss_new_items,
            timezone=self.config.get("TIMEZONE", DEFAULT_TIMEZONE),
            display_mode=self.display_mode,
            ai_content=ai_content,
            standalone_data=standalone_data,
            rank_threshold=self.rank_threshold,
            ai_stats=ai_stats,
            report_type=report_type,
            show_new_section=self.show_new_section,
        )

    # === 通知发送 ===

    def create_notification_dispatcher(self) -> NotificationDispatcher:
        """创建通知调度器"""
        # 创建翻译器（如果启用）
        translator = None
        trans_config = self.config.get("AI_TRANSLATION", {})
        if trans_config.get("ENABLED", False):
            ai_config = self.config.get("AI", {})
            translator = AITranslator(trans_config, ai_config)

        return NotificationDispatcher(
            config=self.config,
            get_time_func=self.get_time,
            split_content_func=self.split_content,
            translator=translator,
        )

    def create_scheduler(self) -> Scheduler:
        """
        创建调度器（延迟初始化，单例）

        基于 config.yaml 的 schedule 段 + timeline.yaml 构建。
        """
        if self._scheduler is None:
            schedule_config = self.config.get("SCHEDULE", {})
            timeline_data = self.config.get("_TIMELINE_DATA", {})

            self._scheduler = Scheduler(
                schedule_config=schedule_config,
                timeline_data=timeline_data,
                storage_backend=self.get_storage_manager(),
                get_time_func=self.get_time,
                fallback_report_mode=self.config.get("REPORT_MODE", "current"),
            )
        return self._scheduler

    # === AI 智能筛选 ===

    def _get_ai_filter_pipeline(self) -> "AIFilterPipeline":
        return AIFilterPipeline(
            config=self.config,
            storage_manager=self.get_storage_manager(),
            get_time_func=self.get_time,
        )

    def run_ai_filter(self, interests_file: Optional[str] = None) -> Optional[AIFilterResult]:
        """执行 AI 智能筛选完整流程"""
        if not self.ai_filter_enabled:
            return None
        try:
            return self._get_ai_filter_pipeline().run(interests_file)
        except _TagExtractionError:
            return AIFilterResult(success=False, error="标签提取失败")

    # === 地区分类 ===

    def run_region_classify(self) -> Optional[Dict[str, List[Dict]]]:
        """执行地区分类完整流程（gated by region_classify_enabled）。

        1. 收集 hotlist + rss 新闻（含新鲜度过滤）
        2. content_hash 去重（标题变更触发重分类，见 ADR-0002）
        3. 批量调 AI 分类（RegionClassifier.classify_batch）
        4. 落库（UPSERT）+ 标记已分析
        5. 返回 active 结果树（供报告渲染）

        开关关闭 → None。失败批次不标记已分析，下次重试。
        """
        if not self.region_classify_enabled:
            return None

        import hashlib

        classifier = self.get_region_classifier()
        storage = self.get_storage_manager()
        date = self.format_date()
        rc = self.region_classify_config
        batch_size = rc.get("BATCH_SIZE", 200)
        batch_interval = rc.get("BATCH_INTERVAL", 1)

        # 1. 收集 hotlist
        all_hotlist = storage.get_all_news_ids()
        analyzed_hotlist = storage.get_region_classify_analyzed("hotlist")
        # 去重：hash 不同（标题变更/未分析）才分类
        pending_hotlist = [
            n for n in all_hotlist
            if analyzed_hotlist.get(n["id"]) != hashlib.md5(
                n["title"].encode("utf-8")).hexdigest()
        ]

        # RSS（含新鲜度过滤，与 ai_filter 一致）
        pending_rss = []
        if self.rss_enabled:
            all_rss = storage.get_all_rss_ids()
            analyzed_rss = storage.get_region_classify_analyzed("rss")
            pending_rss = [
                n for n in all_rss
                if analyzed_rss.get(n["id"]) != hashlib.md5(
                    n["title"].encode("utf-8")).hexdigest()
            ]

        total_pending = len(pending_hotlist) + len(pending_rss)
        print(f"[RegionClassify] 热榜待分类 {len(pending_hotlist)} 条, RSS 待分类 {len(pending_rss)} 条")

        if total_pending == 0:
            print("[RegionClassify] 没有新增新闻需要分类")

        # 2. 批量分类
        import time as _time
        all_results: List[Dict] = []
        analyzed_records: List[tuple] = []  # (news_id, source_type, content_hash, level)

        def _process(source_type: str, pending: List[Dict]) -> None:
            batch_count = 0
            for i in range(0, len(pending), batch_size):
                if batch_count > 0 and batch_interval > 0:
                    print(f"[RegionClassify] 批次间隔等待 {batch_interval} 秒...")
                    _time.sleep(batch_interval)
                batch = pending[i:i + batch_size]
                titles_for_ai = [
                    {"id": n["id"], "title": n["title"],
                     "source": n.get("source_name", "")}
                    for n in batch
                ]
                batch_results = classifier.classify_batch(titles_for_ai)
                batch_count += 1
                if batch_results is None:
                    # 调用失败：不标记该批次，留待下次重试
                    print(f"[RegionClassify] {source_type} 批次 {batch_count}: "
                          f"{len(batch)} 条 → 分类失败，将在下次运行重试")
                    continue
                for r in batch_results:
                    r["source_type"] = source_type
                all_results.extend(batch_results)
                # 标记已分析（全部成功分类的 id，含 unknown）
                for n in batch:
                    chash = hashlib.md5(n["title"].encode("utf-8")).hexdigest()
                    level = next(
                        (r["level"] for r in batch_results if r["id"] == n["id"]),
                        "unknown",
                    )
                    analyzed_records.append((n["id"], source_type, chash, level))
                print(f"[RegionClassify] {source_type} 批次 {batch_count}: "
                      f"{len(batch)} 条 → {len(batch_results)} 条分类")

        _process("hotlist", pending_hotlist)
        _process("rss", pending_rss)

        # 3. 落库 + 标记已分析
        if all_results:
            saved = storage.save_region_classify_results(all_results)
            print(f"[RegionClassify] 保存 {saved} 条分类结果")

        if analyzed_records:
            marked = storage.mark_region_classify_analyzed(
                analyzed_records, source_type="hotlist"  # records 自带 source_type
            )
            print(f"[RegionClassify] 标记 {marked} 条已分析")

        # 4. 返回 active 结果树（供报告渲染）
        return storage.get_active_region_classify_results()

    def convert_ai_filter_to_report_data(
        self,
        ai_filter_result: AIFilterResult,
        mode: str = "daily",
        new_titles: Optional[Dict] = None,
        rss_new_urls: Optional[set] = None,
    ) -> tuple:
        """将 AI 筛选结果转换为与关键词匹配相同的数据结构"""
        return self._get_ai_filter_pipeline().convert_to_report_data(
            ai_filter_result, mode, new_titles, rss_new_urls,
        )

    # === 资源清理 ===

    def cleanup(self):
        """清理资源"""
        if self._storage_manager:
            self._storage_manager.cleanup_old_data()
            self._storage_manager.cleanup()
            self._storage_manager = None
