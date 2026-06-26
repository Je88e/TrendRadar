# coding=utf-8
"""
HTML 报告渲染模块

提供 HTML 格式的热点新闻报告生成功能
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

from trendradar.report.helpers import html_escape, calculate_rank_trend
from trendradar.report.region import render_region_map_html
from trendradar.utils.time import (
    DEFAULT_TIMEZONE,
    convert_time_for_display,
    format_iso_time_friendly,
)
from trendradar.ai.formatter import render_ai_analysis_html_rich


def render_html_content(
    report_data: Dict,
    total_titles: int,
    mode: str = "daily",
    update_info: Optional[Dict] = None,
    *,
    region_order: Optional[List[str]] = None,
    get_time_func: Optional[Callable[[], datetime]] = None,
    rss_items: Optional[List[Dict]] = None,
    rss_new_items: Optional[List[Dict]] = None,
    display_mode: str = "keyword",
    standalone_data: Optional[Dict] = None,
    ai_analysis: Optional[Any] = None,
    show_new_section: bool = True,
    region_map: Optional[Dict[str, Any]] = None,
    timezone: str = DEFAULT_TIMEZONE,
) -> str:
    """渲染HTML内容

    Args:
        report_data: 报告数据字典，包含 stats, new_titles, failed_ids, total_new_count
        total_titles: 新闻总数
        mode: 报告模式 ("daily", "current", "incremental")
        update_info: 更新信息（可选）
        region_order: 区域显示顺序列表
        get_time_func: 获取当前时间的函数（可选，默认使用 datetime.now）
        rss_items: RSS 统计条目列表（可选）
        rss_new_items: RSS 新增条目列表（可选）
        display_mode: 显示模式 ("keyword"=按关键词分组, "platform"=按平台分组)
        standalone_data: 独立展示区数据（可选），包含 platforms 和 rss_feeds
        ai_analysis: AI 分析结果对象（可选），AIAnalysisResult 实例
        show_new_section: 是否显示新增热点区域
        region_map: 地区地图 payload（可选，design 6.1 树）；None 或空树时不渲染该区

    Returns:
        渲染后的 HTML 字符串
    """
    # 默认区域顺序
    default_region_order = ["hotlist", "rss", "new_items", "standalone", "ai_analysis"]
    if region_order is None:
        region_order = default_region_order

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>热点新闻分析</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js" integrity="sha512-BNaRQnYJYiPSqHHDb58B0yaPfCu+Wgds8Gp/gU33kqBtgNS4tSPHuGibyoeqMV/TJlSKda6FXzoEyYGjTe+vXA==" crossorigin="anonymous" referrerpolicy="no-referrer"></script>
        <style>
            /* ===== TrendRadar · Editorial Briefing skin =====
               Aesthetic: newsroom intelligence briefing.
               Display: Fraunces (variable serif). Body: Hanken Grotesk.
               Mono (ranks/counts/time): JetBrains Mono. CJK: Noto Serif/Sans SC.
               Palette: warm newsprint cream + deep ink + vermillion signal + amber.
               Dark: midnight ink + signal amber + warm parchment text.
               All existing class names / DOM hooks preserved — visual reskin only. */

            @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300..900;1,9..144,300..900&family=Hanken+Grotesk:wght@300..800&family=JetBrains+Mono:wght@400..600&family=Noto+Sans+SC:wght@300..800&family=Noto+Serif+SC:wght@300..900&display=swap');

            :root {
                --font-display: 'Fraunces', 'Noto Serif SC', Georgia, 'Songti SC', serif;
                --font-body: 'Hanken Grotesk', 'Noto Sans SC', -apple-system, system-ui, sans-serif;
                --font-mono: 'JetBrains Mono', 'SF Mono', 'Consolas', monospace;

                /* Light — warm newsprint */
                --bg: #ECE4D2;
                --bg-2: #E4D9C0;
                --surface: #FBF5E6;
                --surface-2: #F3EAD2;
                --surface-3: #EDE2C4;
                --ink: #161009;
                --ink-2: #3B2F1F;
                --muted: #7A6A4F;
                --muted-2: #9C8A6C;
                --rule: #D6C7A4;
                --rule-soft: #E5D9B8;
                --rule-ink: #1C140A;
                --accent: #C2290E;        /* vermillion */
                --accent-2: #E08A0E;      /* amber */
                --signal: #1E6B4C;        /* count green */
                --link: #A8230E;
                --link-visited: #6F1A0A;
                --chip-bg: #F0E4C6;
                --chip-ink: #3B2F1F;
                --shadow-hard: 5px 5px 0 rgba(22,16,9,0.07);
                --shadow-hard-lg: 8px 8px 0 rgba(22,16,9,0.09);
                --shadow-soft: 0 1px 0 rgba(22,16,9,0.05);
                --grain-opacity: 0.55;
            }

            body.dark-mode {
                --bg: #0A0C11;
                --bg-2: #0E1218;
                --surface: #14181F;
                --surface-2: #1B202A;
                --surface-3: #222833;
                --ink: #EEE4CE;
                --ink-2: #C8BBA0;
                --muted: #877B66;
                --muted-2: #6B604E;
                --rule: #2A313D;
                --rule-soft: #1F242E;
                --rule-ink: #EEE4CE;
                --accent: #FF6E3B;
                --accent-2: #FFB627;
                --signal: #5BD4A1;
                --link: #FF8C5C;
                --link-visited: #FFB627;
                --chip-bg: #232A36;
                --chip-ink: #C8BBA0;
                --shadow-hard: 5px 5px 0 rgba(0,0,0,0.55);
                --shadow-hard-lg: 8px 8px 0 rgba(0,0,0,0.65);
                --shadow-soft: 0 1px 0 rgba(0,0,0,0.4);
                --grain-opacity: 0.4;
            }

            * { box-sizing: border-box; }

            html, body { background: var(--bg); }

            body {
                font-family: var(--font-body);
                margin: 0;
                padding: 28px 16px 60px;
                background:
                    radial-gradient(120% 80% at 15% 0%, var(--bg-2) 0%, transparent 55%),
                    radial-gradient(100% 60% at 100% 100%, var(--bg-2) 0%, transparent 60%),
                    var(--bg);
                color: var(--ink-2);
                line-height: 1.55;
                font-feature-settings: "ss01", "cv11", "kern";
                -webkit-font-smoothing: antialiased;
                text-rendering: optimizeLegibility;
            }

            /* Paper grain overlay — fixed, subtle */
            body::before {
                content: "";
                position: fixed;
                inset: 0;
                pointer-events: none;
                z-index: 0;
                opacity: var(--grain-opacity);
                background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0.1 0 0 0 0 0.08 0 0 0 0 0.05 0 0 0 0.42 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>");
                background-size: 220px 220px;
                mix-blend-mode: multiply;
            }
            body.dark-mode::before { mix-blend-mode: screen; }

            .container {
                max-width: 640px;
                margin: 0 auto;
                background: var(--surface);
                border-radius: 4px;
                overflow: hidden;
                box-shadow: var(--shadow-hard-lg);
                border: 1px solid var(--rule);
                position: relative;
                z-index: 1;
            }

            /* ===== Masthead ===== */
            .header {
                background: var(--ink);
                color: var(--surface);
                padding: 30px 28px 28px;
                text-align: left;
                position: relative;
                overflow: visible;
                border-bottom: 4px solid var(--accent);
            }
            body.dark-mode .header {
                background: linear-gradient(180deg, #06080B 0%, #11151C 100%);
                color: var(--ink);
            }

            /* Vermillion masthead bar (left edge signal) */
            .header::before {
                content: "";
                position: absolute;
                left: 0; top: 0; bottom: 0;
                width: 6px;
                background: var(--accent);
            }

            .header-watermark {
                position: absolute;
                top: 50%;
                right: -8px;
                transform: translateY(-50%);
                font-family: var(--font-display);
                font-style: italic;
                font-size: clamp(56px, 12vw, 120px);
                font-weight: 300;
                letter-spacing: -0.04em;
                color: rgba(251, 245, 230, 0.06);
                pointer-events: none;
                z-index: 1;
                white-space: nowrap;
                -webkit-mask-image: radial-gradient(circle 0px at 50% 50%, rgba(0,0,0,1) 0%, rgba(0,0,0,0) 100%);
                mask-image: radial-gradient(circle 0px at 50% 50%, rgba(0,0,0,1) 0%, rgba(0,0,0,0) 100%);
                transition: -webkit-mask-image 0.3s ease, mask-image 0.3s ease;
                user-select: none;
            }
            body.dark-mode .header-watermark { color: rgba(238, 228, 206, 0.05); }

            .save-buttons {
                position: absolute;
                top: 18px;
                right: 18px;
                display: flex;
                gap: 8px;
                z-index: 10;
            }

            .save-btn-group { position: relative; display: flex; }

            .save-btn,
            .toggle-wide-btn,
            .toggle-dark-btn {
                background: transparent;
                border: 1px solid rgba(251, 245, 230, 0.32);
                color: var(--surface);
                padding: 9px 16px;
                cursor: pointer;
                font-family: var(--font-body);
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                transition: background 0.18s ease, color 0.18s ease, border-color 0.18s ease;
                backdrop-filter: blur(10px);
                white-space: nowrap;
                min-height: 36px;
                line-height: 1;
            }
            body.dark-mode .save-btn,
            body.dark-mode .toggle-wide-btn,
            body.dark-mode .toggle-dark-btn {
                color: var(--ink);
                border-color: rgba(238, 228, 206, 0.28);
            }
            .save-btn {
                border-radius: 2px 0 0 2px;
                border-right: none;
            }
            .save-btn:hover,
            .toggle-wide-btn:hover,
            .toggle-dark-btn:hover {
                background: var(--accent);
                border-color: var(--accent);
                color: #FBF5E6;
            }
            body.dark-mode .save-btn:hover,
            body.dark-mode .toggle-wide-btn:hover,
            body.dark-mode .toggle-dark-btn:hover {
                color: #11151C;
            }
            .save-btn:active,
            .toggle-wide-btn:active,
            .toggle-dark-btn:active { transform: translateY(1px); }
            .save-btn:disabled { opacity: 0.5; cursor: not-allowed; }

            .toggle-wide-btn,
            .toggle-dark-btn {
                border-radius: 2px;
                padding: 9px 12px;
                font-size: 14px;
                letter-spacing: 0;
                text-transform: none;
            }

            .save-dropdown-trigger {
                background: transparent;
                border: 1px solid rgba(251, 245, 230, 0.32);
                border-left: 1px solid rgba(251, 245, 230, 0.18);
                color: var(--surface);
                padding: 9px 11px;
                border-radius: 0 2px 2px 0;
                cursor: pointer;
                font-size: 11px;
                transition: background 0.18s ease;
                backdrop-filter: blur(10px);
                min-height: 36px;
                display: flex;
                align-items: center;
            }
            body.dark-mode .save-dropdown-trigger {
                color: var(--ink);
                border-color: rgba(238, 228, 206, 0.28);
                border-left-color: rgba(238, 228, 206, 0.14);
            }
            .save-btn-group:hover .save-btn,
            .save-btn-group:hover .save-dropdown-trigger {
                background: var(--accent);
                border-color: var(--accent);
                color: #FBF5E6;
            }
            body.dark-mode .save-btn-group:hover .save-btn,
            body.dark-mode .save-btn-group:hover .save-dropdown-trigger {
                color: #11151C;
            }

            .save-dropdown-menu {
                position: absolute;
                top: 100%;
                right: 0;
                margin-top: 6px;
                background: var(--surface);
                border: 1px solid var(--rule);
                border-radius: 3px;
                padding: 4px;
                min-width: 168px;
                opacity: 0;
                visibility: hidden;
                transform: translateY(-4px);
                transition: opacity 0.18s ease, transform 0.18s ease, visibility 0.18s;
                box-shadow: var(--shadow-hard);
            }
            .save-btn-group:hover .save-dropdown-menu,
            .save-dropdown-menu:hover {
                opacity: 1;
                visibility: visible;
                transform: translateY(0);
            }
            .save-dropdown-item {
                display: flex;
                align-items: center;
                width: 100%;
                padding: 9px 12px;
                background: none;
                border: none;
                color: var(--ink-2);
                font-family: var(--font-body);
                font-size: 13px;
                cursor: pointer;
                border-radius: 2px;
                text-align: left;
                transition: background 0.14s, color 0.14s;
                white-space: nowrap;
            }
            .save-dropdown-item:hover {
                background: var(--surface-2);
                color: var(--accent);
            }
            .dropdown-icon {
                width: 14px;
                height: 14px;
                margin-right: 9px;
                vertical-align: -2px;
                flex-shrink: 0;
                color: var(--muted);
            }
            .save-dropdown-item:hover .dropdown-icon { color: var(--accent); }

            .header-title {
                font-family: var(--font-display);
                font-size: clamp(28px, 6.5vw, 42px);
                font-weight: 600;
                font-variation-settings: "opsz" 120, "SOFT" 30;
                letter-spacing: -0.02em;
                line-height: 1.05;
                margin: 0;
                position: relative;
                z-index: 2;
                color: var(--surface);
            }
            body.dark-mode .header-title { color: var(--ink); }

            .header-eyebrow {
                position: relative;
                z-index: 2;
                font-family: var(--font-mono);
                font-size: 10.5px;
                font-weight: 500;
                letter-spacing: 0.28em;
                text-transform: uppercase;
                color: var(--accent-2);
                margin-bottom: 10px;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .header-eyebrow::before {
                content: "";
                display: inline-block;
                width: 18px;
                height: 1px;
                background: var(--accent-2);
            }

            .header-sub {
                position: relative;
                z-index: 2;
                font-family: var(--font-display);
                font-style: italic;
                font-size: 14px;
                font-weight: 300;
                color: var(--muted-2);
                margin: 6px 0 22px;
                letter-spacing: 0.01em;
            }
            body.dark-mode .header-sub { color: var(--muted); }

            .header-info {
                position: relative;
                z-index: 2;
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 1px;
                background: rgba(251, 245, 230, 0.08);
                border: 1px solid rgba(251, 245, 230, 0.1);
                border-radius: 2px;
                overflow: hidden;
                font-size: 13px;
            }
            body.dark-mode .header-info {
                background: rgba(238, 228, 206, 0.04);
                border-color: rgba(238, 228, 206, 0.08);
            }

            .info-item {
                text-align: left;
                padding: 10px 12px;
                background: var(--ink);
                display: flex;
                flex-direction: column;
                gap: 3px;
                min-width: 0;
            }
            body.dark-mode .info-item { background: #0E1218; }

            .info-label {
                font-family: var(--font-mono);
                font-size: 9.5px;
                letter-spacing: 0.14em;
                text-transform: uppercase;
                color: var(--muted-2);
                opacity: 0.85;
            }
            body.dark-mode .info-label { color: var(--muted); }

            .info-value {
                font-family: var(--font-mono);
                font-weight: 500;
                font-size: 14px;
                color: var(--surface);
                letter-spacing: -0.01em;
            }
            body.dark-mode .info-value { color: var(--ink); }

            .content { padding: 30px 28px 12px; }

            /* ===== Word group (stats) ===== */
            .word-group { margin-bottom: 36px; }
            .word-group:first-child { margin-top: 0; }

            /* 固定空词组占位行（静默，无装饰；--muted-2 在 dark-mode 下自动覆盖） */
            .news-empty-placeholder {
                padding: 10px 4px;
                color: var(--muted-2);
                font-size: 14px;
            }

            .word-header {
                display: flex;
                align-items: baseline;
                justify-content: space-between;
                margin-bottom: 14px;
                padding-bottom: 10px;
                border-bottom: 2px solid var(--rule-ink);
                position: relative;
            }
            .word-header::after {
                content: "";
                position: absolute;
                left: 0; bottom: -2px;
                width: 44px;
                height: 2px;
                background: var(--accent);
            }

            .word-info {
                display: flex;
                align-items: baseline;
                gap: 12px;
                flex-wrap: wrap;
            }

            .word-name {
                font-family: var(--font-display);
                font-size: 22px;
                font-weight: 600;
                font-variation-settings: "opsz" 60;
                letter-spacing: -0.01em;
                color: var(--ink);
                line-height: 1.2;
            }

            .word-count {
                font-family: var(--font-mono);
                color: var(--muted);
                font-size: 12px;
                font-weight: 500;
                letter-spacing: 0.02em;
            }
            .word-count.hot { color: var(--accent); font-weight: 600; }
            .word-count.warm { color: var(--accent-2); font-weight: 600; }

            .word-index {
                font-family: var(--font-mono);
                color: var(--muted-2);
                font-size: 11px;
                letter-spacing: 0.06em;
                text-transform: uppercase;
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .collapse-icon {
                display: none;
                margin-right: 4px;
                font-size: 10px;
                color: var(--accent);
                transition: transform 0.2s;
                user-select: none;
            }
            .word-header.collapsible { cursor: pointer; }
            .word-header.collapsible .collapse-icon { display: inline; }
            .word-header.collapsible:hover {
                background: var(--surface-2);
                border-radius: 2px;
                margin: 0 -10px 14px -10px;
                padding: 8px 10px;
            }
            .word-group.collapsed .news-item { display: none; }
            .word-group.collapsed .collapse-icon { transform: rotate(-90deg); }

            /* ===== News item ===== */
            .news-item {
                margin-bottom: 0;
                padding: 14px 0;
                border-bottom: 1px solid var(--rule-soft);
                position: relative;
                display: flex;
                gap: 14px;
                align-items: flex-start;
            }
            .news-item:last-child { border-bottom: none; }
            .news-item.new::after {
                content: "NEW";
                position: absolute;
                top: 14px;
                right: 0;
                background: var(--accent);
                color: #FBF5E6;
                font-family: var(--font-mono);
                font-size: 9px;
                font-weight: 600;
                padding: 3px 6px;
                border-radius: 1px;
                letter-spacing: 0.12em;
            }

            .news-number {
                color: var(--muted);
                font-family: var(--font-mono);
                font-size: 12px;
                font-weight: 500;
                min-width: 26px;
                text-align: center;
                flex-shrink: 0;
                background: var(--surface-2);
                border: 1px solid var(--rule);
                border-radius: 2px;
                width: 26px;
                height: 26px;
                display: flex;
                align-items: center;
                justify-content: center;
                align-self: flex-start;
                margin-top: 2px;
                position: relative;
                cursor: pointer;
                transition: background 0.15s, color 0.15s, border-color 0.15s;
            }
            .news-number .num-text { transition: opacity 0.15s; }
            .news-number .copy-icon {
                position: absolute;
                opacity: 0;
                transition: opacity 0.15s;
            }
            .news-item:hover .news-number .num-text { opacity: 0; }
            .news-item:hover .news-number .copy-icon { opacity: 1; }
            .news-item:hover .news-number {
                background: var(--accent);
                color: #FBF5E6;
                border-color: var(--accent);
            }
            .news-number.copied {
                background: var(--signal) !important;
                border-color: var(--signal) !important;
            }
            .news-number.copied .num-text { opacity: 0 !important; }
            .news-number.copied .copy-icon { opacity: 1 !important; }
            body.dark-mode .news-item:hover .news-number {
                background: var(--accent);
                color: #11151C;
                border-color: var(--accent);
            }
            body.dark-mode .news-number.copied { background: var(--signal) !important; }

            .news-content {
                flex: 1;
                min-width: 0;
                padding-right: 40px;
            }
            .news-item.new .news-content { padding-right: 52px; }

            .news-header {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 5px;
                flex-wrap: wrap;
            }

            .source-name {
                font-family: var(--font-mono);
                color: var(--muted);
                font-size: 10.5px;
                font-weight: 500;
                letter-spacing: 0.06em;
                text-transform: uppercase;
            }

            .keyword-tag {
                color: var(--accent);
                font-family: var(--font-mono);
                font-size: 10.5px;
                font-weight: 500;
                background: var(--surface-3);
                padding: 2px 7px;
                border-radius: 1px;
                letter-spacing: 0.04em;
            }

            .rank-num {
                color: #FBF5E6;
                background: var(--ink-2);
                font-family: var(--font-mono);
                font-size: 10.5px;
                font-weight: 600;
                padding: 2px 7px;
                border-radius: 1px;
                min-width: 22px;
                text-align: center;
                letter-spacing: 0.02em;
            }
            .rank-num.top { background: var(--accent); }
            .rank-num.high { background: var(--accent-2); color: var(--ink); }

            .trend-up, .trend-down {
                font-size: 12px;
                margin-left: 2px;
                vertical-align: middle;
            }

            .time-info {
                color: var(--muted-2);
                font-family: var(--font-mono);
                font-size: 10.5px;
                letter-spacing: 0.02em;
            }

            .count-info {
                color: var(--signal);
                font-family: var(--font-mono);
                font-size: 10.5px;
                font-weight: 600;
                letter-spacing: 0.02em;
            }

            .news-title {
                font-family: var(--font-body);
                font-size: 15px;
                font-weight: 500;
                line-height: 1.5;
                color: var(--ink);
                margin: 0;
                letter-spacing: -0.005em;
            }

            .news-link {
                color: var(--link);
                text-decoration: none;
                background-image: linear-gradient(var(--accent), var(--accent));
                background-size: 0% 1px;
                background-position: 0 100%;
                background-repeat: no-repeat;
                transition: background-size 0.3s ease, color 0.15s ease;
            }
            .news-link:hover {
                color: var(--accent);
                background-size: 100% 1px;
            }
            .news-link:visited { color: var(--link-visited); }
            .news-link:visited:hover { color: var(--accent); }

            /* ===== Section dividers ===== */
            .section-divider {
                margin-top: 36px;
                padding-top: 28px;
                border-top: 1px solid var(--rule);
                position: relative;
            }
            .section-divider::before {
                content: "";
                position: absolute;
                top: -1px; left: 0;
                width: 80px; height: 3px;
                background: var(--ink);
            }

            .hotlist-section { /* */ }

            /* ===== New items ===== */
            .new-section {
                margin-top: 40px;
                padding-top: 28px;
            }
            .new-section-title {
                font-family: var(--font-display);
                color: var(--ink);
                font-size: 20px;
                font-weight: 600;
                font-variation-settings: "opsz" 60;
                margin: 0 0 18px;
                letter-spacing: -0.01em;
                display: flex;
                align-items: baseline;
                gap: 10px;
            }
            .new-section-title::before {
                content: "✦";
                color: var(--accent);
                font-size: 14px;
            }

            .new-source-group { margin-bottom: 22px; }
            .new-source-title {
                font-family: var(--font-mono);
                color: var(--muted);
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                margin: 0 0 10px;
                padding-bottom: 6px;
                border-bottom: 1px dashed var(--rule);
            }

            .new-item {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 8px 0;
                border-bottom: 1px solid var(--rule-soft);
            }
            .new-item:last-child { border-bottom: none; }

            .new-item-number {
                color: var(--muted);
                font-family: var(--font-mono);
                font-size: 11px;
                font-weight: 500;
                min-width: 22px;
                text-align: center;
                flex-shrink: 0;
                background: var(--surface-2);
                border-radius: 2px;
                width: 22px;
                height: 22px;
                display: flex;
                align-items: center;
                justify-content: center;
            }

            .new-item-rank {
                color: #FBF5E6;
                background: var(--ink-2);
                font-family: var(--font-mono);
                font-size: 10px;
                font-weight: 600;
                padding: 2px 6px;
                border-radius: 1px;
                min-width: 22px;
                text-align: center;
                flex-shrink: 0;
            }
            .new-item-rank.top { background: var(--accent); }
            .new-item-rank.high { background: var(--accent-2); color: var(--ink); }

            .new-item-content { flex: 1; min-width: 0; }
            .new-item-title {
                font-family: var(--font-body);
                font-size: 14px;
                font-weight: 500;
                line-height: 1.45;
                color: var(--ink);
                margin: 0;
            }

            /* ===== Error ===== */
            .error-section {
                background: var(--surface-2);
                border: 1px solid var(--rule);
                border-left: 4px solid var(--accent);
                border-radius: 2px;
                padding: 14px 18px;
                margin-bottom: 24px;
            }
            .error-title {
                color: var(--accent);
                font-family: var(--font-display);
                font-size: 15px;
                font-weight: 600;
                margin: 0 0 6px;
            }
            .error-list { list-style: none; padding: 0; margin: 0; }
            .error-item {
                color: var(--ink-2);
                font-family: var(--font-mono);
                font-size: 12px;
                padding: 2px 0;
            }

            /* ===== Footer ===== */
            .footer {
                margin-top: 28px;
                padding: 22px 28px;
                background: var(--surface-2);
                border-top: 1px solid var(--rule);
                text-align: center;
            }
            .footer-content {
                font-family: var(--font-mono);
                font-size: 11px;
                color: var(--muted);
                line-height: 1.7;
                letter-spacing: 0.04em;
            }
            .footer-link {
                color: var(--accent);
                text-decoration: none;
                font-weight: 600;
                transition: color 0.2s ease;
                border-bottom: 1px solid transparent;
            }
            .footer-link:hover {
                color: var(--ink);
                border-bottom-color: var(--accent);
            }
            .project-name {
                font-family: var(--font-display);
                font-weight: 600;
                color: var(--ink);
                letter-spacing: -0.01em;
            }

            /* ===== Responsive ===== */
            @media (max-width: 480px) {
                body { padding: 14px 8px 40px; }
                .header { padding: 26px 18px 22px; }
                .content { padding: 22px 18px 8px; }
                .footer { padding: 18px; }
                .header-info { grid-template-columns: repeat(2, 1fr); }
                .news-header { gap: 6px; }
                .news-content { padding-right: 44px; }
                .news-item.new .news-content { padding-right: 54px; }
                .news-item { gap: 10px; }
                .new-item { gap: 8px; }
                .news-number { width: 24px; height: 24px; font-size: 11px; }
                .word-name { font-size: 19px; }
                .save-buttons {
                    position: static;
                    margin-bottom: 16px;
                    display: flex;
                    gap: 8px;
                    justify-content: flex-start;
                    flex-wrap: wrap;
                }
                .save-btn-group { flex: 0 0 auto; }
                .save-btn { padding: 9px 12px; }
            }

            /* ===== RSS ===== */
            .rss-section { margin-top: 32px; padding-top: 28px; }
            .rss-section-header {
                display: flex;
                align-items: baseline;
                justify-content: space-between;
                margin-bottom: 18px;
                padding-bottom: 10px;
                border-bottom: 2px solid var(--signal);
            }
            .rss-section-title {
                font-family: var(--font-display);
                font-size: 20px;
                font-weight: 600;
                font-variation-settings: "opsz" 60;
                color: var(--signal);
                letter-spacing: -0.01em;
            }
            .rss-section-count {
                color: var(--muted);
                font-family: var(--font-mono);
                font-size: 12px;
                letter-spacing: 0.04em;
            }

            .feed-group { margin-bottom: 22px; }
            .feed-group:last-child { margin-bottom: 0; }
            .feed-header {
                display: flex;
                align-items: baseline;
                justify-content: space-between;
                margin-bottom: 10px;
                padding-bottom: 6px;
                border-bottom: 1px solid var(--rule);
            }
            .feed-name {
                font-family: var(--font-display);
                font-size: 16px;
                font-weight: 600;
                color: var(--ink);
                font-variation-settings: "opsz" 30;
            }
            .feed-count {
                color: var(--muted);
                font-family: var(--font-mono);
                font-size: 11px;
                letter-spacing: 0.04em;
            }

            .rss-item {
                margin-bottom: 10px;
                padding: 12px 14px;
                background: var(--surface-2);
                border-radius: 2px;
                border-left: 3px solid var(--signal);
                transition: background 0.15s;
            }
            .rss-item:last-child { margin-bottom: 0; }
            .rss-item:hover { background: var(--surface-3); }

            .rss-meta {
                display: flex;
                align-items: center;
                gap: 10px;
                margin-bottom: 4px;
                flex-wrap: wrap;
            }
            .rss-time {
                color: var(--muted);
                font-family: var(--font-mono);
                font-size: 10.5px;
                letter-spacing: 0.04em;
            }
            .rss-author {
                color: var(--signal);
                font-family: var(--font-mono);
                font-size: 10.5px;
                font-weight: 600;
                letter-spacing: 0.04em;
                text-transform: uppercase;
            }

            .rss-title {
                font-family: var(--font-body);
                font-size: 14px;
                font-weight: 500;
                line-height: 1.5;
                margin-bottom: 4px;
            }
            .rss-link {
                color: var(--ink);
                text-decoration: none;
                font-weight: 500;
                background-image: linear-gradient(var(--signal), var(--signal));
                background-size: 0% 1px;
                background-position: 0 100%;
                background-repeat: no-repeat;
                transition: background-size 0.25s ease, color 0.15s ease;
            }
            .rss-link:hover {
                color: var(--signal);
                background-size: 100% 1px;
            }

            .rss-summary {
                font-size: 13px;
                color: var(--muted);
                line-height: 1.55;
                margin: 0;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }

            /* ===== Standalone ===== */
            .standalone-section { margin-top: 32px; padding-top: 28px; }
            .standalone-section-header {
                display: flex;
                align-items: baseline;
                justify-content: space-between;
                margin-bottom: 18px;
                padding-bottom: 10px;
                border-bottom: 2px solid var(--rule-ink);
            }
            .standalone-section-title {
                font-family: var(--font-display);
                font-size: 20px;
                font-weight: 600;
                font-variation-settings: "opsz" 60;
                color: var(--ink);
                letter-spacing: -0.01em;
            }
            .standalone-section-count {
                color: var(--muted);
                font-family: var(--font-mono);
                font-size: 12px;
            }
            .standalone-group { margin-bottom: 36px; }
            .standalone-group:last-child { margin-bottom: 0; }
            .standalone-header {
                display: flex;
                align-items: baseline;
                justify-content: space-between;
                margin-bottom: 14px;
                padding-bottom: 8px;
                border-bottom: 1px solid var(--rule);
            }
            .standalone-name {
                font-family: var(--font-display);
                font-size: 17px;
                font-weight: 600;
                color: var(--ink);
                font-variation-settings: "opsz" 40;
            }
            .standalone-count {
                color: var(--muted);
                font-family: var(--font-mono);
                font-size: 11px;
            }

            /* ===== AI analysis ===== */
            .ai-section {
                margin-top: 32px;
                padding: 24px;
                background: var(--surface-2);
                border-radius: 3px;
                border: 1px solid var(--rule);
                border-top: 4px solid var(--accent);
                position: relative;
            }
            .ai-section::before {
                content: "";
                position: absolute;
                top: -4px; right: 0;
                width: 60px; height: 4px;
                background: var(--accent-2);
            }

            .ai-section-header {
                display: flex;
                align-items: baseline;
                gap: 12px;
                margin-bottom: 20px;
                padding-bottom: 12px;
                border-bottom: 1px dashed var(--rule);
            }
            .ai-section-title {
                font-family: var(--font-display);
                font-size: 20px;
                font-weight: 600;
                font-variation-settings: "opsz" 60;
                color: var(--ink);
                letter-spacing: -0.01em;
            }
            .ai-section-badge {
                background: var(--accent);
                color: #FBF5E6;
                font-family: var(--font-mono);
                font-size: 10px;
                font-weight: 600;
                padding: 3px 8px;
                border-radius: 1px;
                letter-spacing: 0.14em;
            }

            .ai-block {
                margin-bottom: 14px;
                padding: 16px 18px;
                background: var(--surface);
                border: 1px solid var(--rule);
                border-radius: 2px;
                position: relative;
            }
            .ai-block:last-child { margin-bottom: 0; }
            .ai-block::before {
                content: "";
                position: absolute;
                left: 0; top: 12px; bottom: 12px;
                width: 2px;
                background: var(--accent-2);
            }
            .ai-block-title {
                font-family: var(--font-mono);
                font-size: 11px;
                font-weight: 600;
                color: var(--accent);
                margin-bottom: 8px;
                letter-spacing: 0.14em;
                text-transform: uppercase;
            }
            .ai-block-content {
                font-family: var(--font-body);
                font-size: 14px;
                line-height: 1.7;
                color: var(--ink-2);
                white-space: pre-wrap;
            }

            .ai-error,
            .ai-warning,
            .ai-info {
                padding: 14px 18px;
                border-radius: 2px;
                font-family: var(--font-body);
                font-size: 14px;
                border-left: 4px solid;
            }
            .ai-error {
                background: var(--surface-2);
                border-color: var(--accent);
                color: var(--accent);
            }
            .ai-warning {
                background: var(--surface-2);
                border-color: var(--accent-2);
                color: var(--accent-2);
            }
            .ai-info {
                background: var(--surface-2);
                border-color: var(--signal);
                color: var(--signal);
            }

            /* ===== Wide mode ===== */
            body.wide-mode .container { max-width: 1200px; }
            body.wide-mode .header-info { grid-template-columns: repeat(4, 1fr); }
            body.wide-mode .content { padding: 36px 44px 16px; }
            body.wide-mode .rss-feeds-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 24px;
            }
            body.wide-mode .feed-group { margin-bottom: 0; }
            body.wide-mode .ai-section .ai-blocks-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 16px;
            }
            body.wide-mode .ai-block { margin-bottom: 0; }
            body.wide-mode .new-section .new-sources-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 24px;
            }
            body.wide-mode .new-source-group { margin-bottom: 0; }
            body.wide-mode .standalone-section .standalone-groups-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 24px;
            }
            body.wide-mode .standalone-group { margin-bottom: 0; }

            /* ===== Tab bar ===== */
            .tab-bar-wrapper {
                position: sticky;
                top: 0;
                z-index: 10;
                background: var(--surface);
                display: none;
                margin-bottom: 20px;
                align-items: stretch;
                border-bottom: 2px solid var(--rule-ink);
            }
            body.wide-mode .tab-bar-wrapper { display: flex; }
            body.wide-mode .tab-bar-wrapper.tab-hidden { display: none; }

            .tab-bar {
                flex: 1;
                min-width: 0;
                display: flex;
                overflow-x: auto;
                white-space: nowrap;
                padding: 8px 0 12px 0;
                -webkit-overflow-scrolling: touch;
                scrollbar-width: none;
                -ms-overflow-style: none;
                gap: 4px;
                mask-image: linear-gradient(to right, transparent, black 24px, black calc(100% - 24px), transparent);
                -webkit-mask-image: linear-gradient(to right, transparent, black 24px, black calc(100% - 24px), transparent);
            }
            .tab-bar::-webkit-scrollbar { display: none; }
            .tab-bar.scroll-start {
                mask-image: linear-gradient(to right, black, black calc(100% - 24px), transparent);
                -webkit-mask-image: linear-gradient(to right, black, black calc(100% - 24px), transparent);
            }
            .tab-bar.scroll-end {
                mask-image: linear-gradient(to right, transparent, black 24px, black);
                -webkit-mask-image: linear-gradient(to right, transparent, black 24px, black);
            }
            .tab-bar.scroll-start.scroll-end,
            .tab-bar.no-overflow {
                mask-image: none;
                -webkit-mask-image: none;
            }

            .tab-arrow {
                flex-shrink: 0;
                width: 28px;
                display: none;
                align-items: center;
                justify-content: center;
                background: none;
                border: none;
                color: var(--muted);
                font-size: 20px;
                font-weight: 300;
                cursor: pointer;
                padding: 0;
                transition: color 0.15s ease;
            }
            .tab-arrow:hover { color: var(--accent); }
            .tab-arrow.visible { display: flex; }

            .tab-scroll-indicator {
                position: absolute;
                bottom: 0;
                left: 0;
                width: 0;
                height: 2px;
                background: var(--accent);
                border-radius: 0 1px 1px 0;
                transition: width 0.1s linear;
            }

            .tab-btn {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 8px 14px;
                border: 1px solid var(--rule);
                background: var(--surface);
                color: var(--ink-2);
                border-radius: 2px;
                cursor: pointer;
                font-family: var(--font-body);
                font-size: 13px;
                font-weight: 500;
                white-space: nowrap;
                transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
                flex-shrink: 0;
            }
            .tab-btn:hover {
                background: var(--surface-2);
                color: var(--ink);
                border-color: var(--muted-2);
            }
            .tab-btn.active {
                background: var(--ink);
                color: var(--surface);
                border-color: var(--ink);
            }
            body.dark-mode .tab-btn.active { background: var(--ink); color: #0E1218; border-color: var(--ink); }
            .tab-count {
                font-family: var(--font-mono);
                font-size: 10.5px;
                background: var(--surface-3);
                color: var(--muted);
                padding: 1px 6px;
                border-radius: 1px;
            }
            .tab-btn.active .tab-count {
                background: rgba(251, 245, 230, 0.18);
                color: var(--surface);
            }
            body.dark-mode .tab-btn.active .tab-count {
                background: rgba(14, 18, 24, 0.2);
                color: #0E1218;
            }

            /* ===== Search ===== */
            .search-bar { display: none; padding: 0 0 16px 0; }
            .search-input {
                width: 100%;
                padding: 10px 14px;
                border: 1px solid var(--rule);
                border-bottom: 2px solid var(--ink);
                border-radius: 2px 2px 0 0;
                background: var(--surface-2);
                color: var(--ink);
                font-family: var(--font-body);
                font-size: 14px;
                outline: none;
                transition: border-color 0.2s, background 0.2s;
                box-sizing: border-box;
            }
            .search-input:focus {
                border-bottom-color: var(--accent);
                background: var(--surface);
            }
            .search-input::placeholder {
                color: var(--muted-2);
                font-style: italic;
            }

            /* ===== FAB ===== */
            .fab-bar {
                position: fixed;
                bottom: 24px;
                right: 24px;
                display: flex;
                flex-direction: column;
                gap: 8px;
                z-index: 100;
                opacity: 0;
                transform: translateY(10px);
                transition: opacity 0.3s, transform 0.3s;
                pointer-events: none;
            }
            .fab-bar.visible {
                opacity: 1;
                transform: translateY(0);
                pointer-events: auto;
            }
            .fab-btn {
                width: 42px;
                height: 42px;
                border-radius: 2px;
                background: var(--ink);
                color: var(--surface);
                border: 1px solid var(--ink);
                cursor: pointer;
                font-size: 16px;
                box-shadow: var(--shadow-hard);
                transition: transform 0.18s, background 0.18s, color 0.18s;
                display: flex;
                align-items: center;
                justify-content: center;
                position: relative;
                font-family: var(--font-body);
            }
            .fab-btn:hover {
                background: var(--accent);
                border-color: var(--accent);
                color: #FBF5E6;
                transform: translate(-2px, -2px);
                box-shadow: 7px 7px 0 rgba(22,16,9,0.12);
            }
            body.dark-mode .fab-btn { background: var(--ink); color: #0E1218; border-color: var(--ink); }
            body.dark-mode .fab-btn:hover {
                background: var(--accent);
                color: #0E1218;
                border-color: var(--accent);
            }

            .fab-tooltip {
                position: absolute;
                bottom: 0;
                right: 52px;
                background: var(--ink);
                color: var(--surface);
                border-radius: 2px;
                padding: 12px 16px;
                white-space: nowrap;
                font-family: var(--font-body);
                font-size: 12px;
                line-height: 1.8;
                box-shadow: var(--shadow-hard);
                border: 1px solid var(--rule);
                opacity: 0;
                visibility: hidden;
                transform: translateY(6px);
                transition: all 0.2s ease;
                pointer-events: none;
            }
            body.dark-mode .fab-tooltip { background: #06080B; color: var(--ink); }
            .fab-btn:hover .fab-tooltip,
            .fab-btn.show-tip .fab-tooltip {
                opacity: 1;
                visibility: visible;
                transform: translateY(0);
                pointer-events: auto;
            }
            .fab-tooltip .tip-row {
                display: flex;
                justify-content: space-between;
                gap: 16px;
                align-items: center;
            }
            .fab-tooltip .tip-key {
                background: rgba(251, 245, 230, 0.12);
                border-radius: 1px;
                padding: 1px 6px;
                font-family: var(--font-mono);
                font-size: 11px;
                margin-left: 8px;
                color: var(--accent-2);
            }
            body.dark-mode .fab-tooltip .tip-key {
                background: rgba(238, 228, 206, 0.1);
                color: var(--accent-2);
            }

            /* ===== Tab switch animation ===== */
            body.wide-mode .word-group[data-tab-index] { animation: tabFadeIn 0.22s ease; }
            @keyframes tabFadeIn {
                from { opacity: 0; transform: translateY(6px); }
                to { opacity: 1; transform: translateY(0); }
            }

            /* ===== Dark-mode overrides (token-driven mostly; few leftovers) ===== */
            body.dark-mode .tab-arrow { color: var(--muted); }
            body.dark-mode .tab-arrow:hover { color: var(--accent-2); }
            body.dark-mode .tab-scroll-indicator { background: var(--accent); }
            body.dark-mode .tab-bar { border-bottom-color: var(--rule-ink); }

            /* ===== Reading progress ===== */
            .reading-progress {
                position: fixed;
                top: 0; left: 0;
                width: 0;
                height: 3px;
                background: linear-gradient(90deg, var(--accent), var(--accent-2));
                z-index: 9999;
                transition: width 0.1s linear;
            }
            body.dark-mode .reading-progress {
                background: linear-gradient(90deg, var(--accent), var(--accent-2));
            }

            /* ===== "New entry" inline badge ===== */
            .badge-new {
                display: inline-block;
                background: var(--accent);
                color: #FBF5E6;
                font-family: var(--font-mono);
                font-size: 9px;
                font-weight: 600;
                padding: 1px 6px;
                border-radius: 1px;
                margin-left: 6px;
                vertical-align: middle;
                letter-spacing: 0.12em;
            }
            body.dark-mode .badge-new { background: var(--accent); color: #11151C; }
        </style>
    </head>
    <body>
        <div class="reading-progress"></div>
        <div class="container">
            <div class="header">
                <div class="header-watermark">TrendRadar</div>
                <div class="save-buttons">
                    <button class="toggle-wide-btn" onclick="toggleWideMode()" title="切换宽屏/窄屏">⛶</button>
                    <button class="toggle-dark-btn" onclick="toggleDarkMode()" title="切换暗色/亮色">☽</button>
                    <div class="save-btn-group">
                        <button class="save-btn" onclick="saveAsImage(event)">导出</button>
                        <button class="save-dropdown-trigger">▾</button>
                        <div class="save-dropdown-menu">
                            <button class="save-dropdown-item" onclick="saveAsImage(event)"><svg class="dropdown-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="12" height="12" rx="2"/><circle cx="8" cy="7.5" r="2.5"/><path d="M12 4h.01"/></svg>整页截图</button>
                            <button class="save-dropdown-item" onclick="saveAsMultipleImages(event)"><svg class="dropdown-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1" y="4" width="10" height="10" rx="1.5"/><path d="M5 4V2.5A1.5 1.5 0 016.5 1h7A1.5 1.5 0 0115 2.5v7a1.5 1.5 0 01-1.5 1.5H12"/></svg>分段截图</button>
                            <button class="save-dropdown-item" onclick="saveAsMarkdown()"><svg class="dropdown-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2.5 2h11A1.5 1.5 0 0115 3.5v9a1.5 1.5 0 01-1.5 1.5h-11A1.5 1.5 0 011 12.5v-9A1.5 1.5 0 012.5 2z"/><path d="M4 11V5l2.5 3L9 5v6"/><path d="M11.5 8v3m0 0l-1.5-2m1.5 2l1.5-2"/></svg>Markdown</button>
                        </div>
                    </div>
                </div>
                <div class="header-eyebrow">INTELLIGENCE BRIEFING</div>
                <div class="header-title">热点新闻分析</div>
                <div class="header-sub">TrendRadar · 信号 · 趋势 · 异动</div>
                <div class="header-info">"""

    # 使用提供的时间函数或默认 datetime.now
    if get_time_func:
        now = get_time_func()
    else:
        now = datetime.now()

    # 处理报告类型显示
    if mode == "current":
        mode_display = "当前榜单"
    elif mode == "incremental":
        mode_display = "增量分析"
    else:
        mode_display = "全天汇总"

    # 计算各项数据
    hot_news_count = sum(len(stat["titles"]) for stat in report_data["stats"])
    new_count = report_data.get("total_new_count", 0)

    # 从元数据获取 RSS 和平台信息
    hotlist_total = report_data.get("hotlist_total", total_titles)
    platform_total = report_data.get("platform_total", 0)
    failed_count = len(report_data.get("failed_ids", []))
    platform_success = platform_total - failed_count if platform_total else 0
    rss_matched = report_data.get("rss_matched_count", 0)
    rss_total = report_data.get("rss_total_count", 0)
    rss_source_total = report_data.get("rss_source_total", 0)
    rss_source_failed = report_data.get("rss_source_failed", 0)
    rss_source_success = max(0, rss_source_total - rss_source_failed)

    # 1. 报告类型
    html += f"""
                    <div class="info-item">
                        <span class="info-label">报告类型</span>
                        <span class="info-value">{mode_display}</span>
                    </div>"""

    # 2. 生成时间
    html += f"""
                    <div class="info-item">
                        <span class="info-label">生成时间</span>
                        <span class="info-value">{now.strftime("%m-%d %H:%M")}</span>
                    </div>"""

    # 3. 热榜命中
    html += f"""
                    <div class="info-item">
                        <span class="info-label">热榜命中</span>
                        <span class="info-value">{hot_news_count} / {hotlist_total}</span>
                    </div>"""

    # 4. RSS 命中
    if rss_source_total > 0:
        rss_value = f"{rss_matched} / {rss_total}"
    else:
        rss_value = "未启用"
    html += f"""
                    <div class="info-item">
                        <span class="info-label">RSS 命中</span>
                        <span class="info-value">{rss_value}</span>
                    </div>"""

    # 5. 热榜平台
    if platform_total > 0:
        platform_value = f"{platform_success}/{platform_total}"
    else:
        platform_value = "--"
    html += f"""
                    <div class="info-item">
                        <span class="info-label">热榜平台</span>
                        <span class="info-value">{platform_value}</span>
                    </div>"""

    # 6. RSS 源
    if rss_source_total > 0:
        rss_source_value = f"{rss_source_success}/{rss_source_total}"
    else:
        rss_source_value = "--"
    html += f"""
                    <div class="info-item">
                        <span class="info-label">RSS 源</span>
                        <span class="info-value">{rss_source_value}</span>
                    </div>"""

    # 7. 新增热点（热榜新增 + RSS 新增）
    rss_new_count = sum(len(stat.get("titles", [])) for stat in (rss_new_items or []))
    total_new = new_count + rss_new_count
    new_value = f"{new_count} + {rss_new_count}" if total_new > 0 else "0"
    html += f"""
                    <div class="info-item">
                        <span class="info-label">新增热点</span>
                        <span class="info-value">{new_value}</span>
                    </div>"""

    # 8. AI 分析
    if ai_analysis and getattr(ai_analysis, "success", False):
        hotlist_analyzed = getattr(ai_analysis, "hotlist_analyzed", 0)
        rss_analyzed = getattr(ai_analysis, "rss_analyzed", 0)
        standalone_analyzed = getattr(ai_analysis, "standalone_analyzed", 0)
        ai_include_rss = getattr(ai_analysis, "include_rss", True)
        ai_include_standalone = getattr(ai_analysis, "include_standalone", False)

        ai_parts = [str(hotlist_analyzed)]
        if ai_include_rss:
            ai_parts.append(str(rss_analyzed))
        if ai_include_standalone:
            ai_parts.append(str(standalone_analyzed))
        ai_value = " + ".join(ai_parts) if sum(int(p) for p in ai_parts) > 0 else "0"
    elif ai_analysis:
        if getattr(ai_analysis, "skipped", False):
            ai_value = "已跳过"
        else:
            ai_value = "待配置"
    else:
        ai_value = "未启用"
    html += f"""
                    <div class="info-item">
                        <span class="info-label">AI 分析</span>
                        <span class="info-value">{ai_value}</span>
                    </div>"""

    html += """
                </div>
            </div>

            <div class="content">
                <div class="search-bar">
                    <input type="text" class="search-input" placeholder="搜索新闻标题..." oninput="handleSearch(this.value)">
                </div>"""

    # 处理失败ID错误信息
    if report_data["failed_ids"]:
        html += """
                <div class="error-section">
                    <div class="error-title">⚠️ 请求失败的平台</div>
                    <ul class="error-list">"""
        for id_value in report_data["failed_ids"]:
            html += f'<li class="error-item">{html_escape(id_value)}</li>'
        html += """
                    </ul>
                </div>"""

    # 生成热点词汇统计部分的HTML
    stats_html = ""
    tab_bar_html = ""
    if report_data["stats"]:
        total_count = len(report_data["stats"])

        # 生成 Tab 栏 HTML
        total_news_count = sum(s["count"] for s in report_data["stats"])
        tab_bar_html = '<div class="tab-bar-wrapper"><div class="tab-bar">'
        tab_bar_html += f'<button class="tab-btn" data-tab-index="all">全部<span class="tab-count">{total_news_count}</span></button>'
        for tab_i, tab_stat in enumerate(report_data["stats"]):
            escaped_tab_word = html_escape(tab_stat["word"])
            tab_count = tab_stat["count"]
            tab_bar_html += f'<button class="tab-btn" data-tab-index="{tab_i}">{escaped_tab_word}<span class="tab-count">{tab_count}</span></button>'
        tab_bar_html += '</div></div>'

        for i, stat in enumerate(report_data["stats"], 1):
            count = stat["count"]

            # 确定热度等级
            if count >= 10:
                count_class = "hot"
            elif count >= 5:
                count_class = "warm"
            else:
                count_class = ""

            escaped_word = html_escape(stat["word"])

            stats_html += f"""
                <div class="word-group" data-tab-index="{i - 1}">
                    <div class="word-header">
                        <div class="word-info">
                            <div class="word-name">{escaped_word}</div>
                            <div class="word-count {count_class}">{count} 条</div>
                        </div>
                        <div class="word-index"><span class="collapse-icon">▼</span>{i}/{total_count}</div>
                    </div>"""

            # 固定空词组占位（count==0：本轮 0 匹配，渲染静默行后跳过新闻列表）
            if count == 0:
                stats_html += """
                    <div class="news-empty-placeholder">📌 暂无相关新闻</div>"""

            # 处理每个词组下的新闻标题，给每条新闻标上序号
            for j, title_data in enumerate(stat["titles"], 1):
                is_new = title_data.get("is_new", False)
                new_class = "new" if is_new else ""

                stats_html += f"""
                    <div class="news-item {new_class}">
                        <div class="news-number">{j}</div>
                        <div class="news-content">
                            <div class="news-header">"""

                # 根据 display_mode 决定显示来源还是关键词
                if display_mode == "keyword":
                    # keyword 模式：显示来源
                    stats_html += f'<span class="source-name">{html_escape(title_data["source_name"])}</span>'
                else:
                    # platform 模式：显示关键词
                    matched_keyword = title_data.get("matched_keyword", "")
                    if matched_keyword:
                        stats_html += f'<span class="keyword-tag">[{html_escape(matched_keyword)}]</span>'

                # 处理排名显示
                ranks = title_data.get("ranks", [])
                if ranks:
                    min_rank = min(ranks)
                    max_rank = max(ranks)
                    rank_threshold = title_data.get("rank_threshold", 10)

                    # 确定排名等级
                    if min_rank <= 3:
                        rank_class = "top"
                    elif min_rank <= rank_threshold:
                        rank_class = "high"
                    else:
                        rank_class = ""

                    if min_rank == max_rank:
                        rank_text = str(min_rank)
                    else:
                        rank_text = f"{min_rank}-{max_rank}"

                    # 计算趋势箭头
                    rank_timeline = title_data.get("rank_timeline", [])
                    trend = calculate_rank_trend(rank_timeline, ranks)
                    trend_html = ""
                    if trend == "up":
                        trend_html = '<span class="trend-up">📈</span>'
                    elif trend == "down":
                        trend_html = '<span class="trend-down">📉</span>'

                    stats_html += f'<span class="rank-num {rank_class}">{rank_text}</span>{trend_html}'

                # 处理时间显示
                time_display = title_data.get("time_display", "")
                if time_display:
                    # 简化时间显示格式，将波浪线替换为~
                    simplified_time = (
                        time_display.replace(" ~ ", "~")
                        .replace("[", "")
                        .replace("]", "")
                    )
                    stats_html += (
                        f'<span class="time-info">{html_escape(simplified_time)}</span>'
                    )

                # 处理出现次数
                count_info = title_data.get("count", 1)
                if count_info > 1:
                    stats_html += f'<span class="count-info">{count_info}次</span>'

                stats_html += """
                            </div>
                            <div class="news-title">"""

                # 处理标题和链接
                escaped_title = html_escape(title_data["title"])
                link_url = title_data.get("mobile_url") or title_data.get("url", "")

                if link_url:
                    escaped_url = html_escape(link_url)
                    stats_html += f'<a href="{escaped_url}" target="_blank" class="news-link">{escaped_title}</a>'
                else:
                    stats_html += escaped_title

                stats_html += """
                            </div>
                        </div>
                    </div>"""

            stats_html += """
                </div>"""

    # 给热榜统计添加外层包装
    if stats_html:
        stats_html = f"""
                <div class="hotlist-section">{tab_bar_html}{stats_html}
                </div>"""

    # 生成新增新闻区域的HTML
    new_titles_html = ""
    if show_new_section and report_data["new_titles"]:
        new_titles_html += f"""
                <div class="new-section">
                    <div class="new-section-title">本次新增热点 (共 {report_data['total_new_count']} 条)</div>
                    <div class="new-sources-grid">"""

        for source_data in report_data["new_titles"]:
            escaped_source = html_escape(source_data["source_name"])
            titles_count = len(source_data["titles"])

            new_titles_html += f"""
                    <div class="new-source-group">
                        <div class="new-source-title">{escaped_source} · {titles_count}条</div>"""

            # 为新增新闻也添加序号
            for idx, title_data in enumerate(source_data["titles"], 1):
                ranks = title_data.get("ranks", [])

                # 处理新增新闻的排名显示
                rank_class = ""
                if ranks:
                    min_rank = min(ranks)
                    if min_rank <= 3:
                        rank_class = "top"
                    elif min_rank <= title_data.get("rank_threshold", 10):
                        rank_class = "high"

                    if len(ranks) == 1:
                        rank_text = str(ranks[0])
                    else:
                        rank_text = f"{min(ranks)}-{max(ranks)}"
                else:
                    rank_text = "?"

                new_titles_html += f"""
                        <div class="new-item">
                            <div class="new-item-number">{idx}</div>
                            <div class="new-item-rank {rank_class}">{rank_text}</div>
                            <div class="new-item-content">
                                <div class="new-item-title">"""

                # 处理新增新闻的链接
                escaped_title = html_escape(title_data["title"])
                link_url = title_data.get("mobile_url") or title_data.get("url", "")

                if link_url:
                    escaped_url = html_escape(link_url)
                    new_titles_html += f'<a href="{escaped_url}" target="_blank" class="news-link">{escaped_title}</a>'
                else:
                    new_titles_html += escaped_title

                new_titles_html += """
                                </div>
                            </div>
                        </div>"""

            new_titles_html += """
                    </div>"""

        new_titles_html += """
                    </div>
                </div>"""

    # 生成 RSS 统计内容
    def render_rss_stats_html(stats: List[Dict], title: str = "RSS 订阅") -> str:
        """渲染 RSS 统计区块 HTML

        Args:
            stats: RSS 分组统计列表，格式与热榜一致：
                [
                    {
                        "word": "关键词",
                        "count": 5,
                        "titles": [
                            {
                                "title": "标题",
                                "source_name": "Feed 名称",
                                "time_display": "12-29 08:20",
                                "url": "...",
                                "is_new": True/False
                            }
                        ]
                    }
                ]
            title: 区块标题

        Returns:
            渲染后的 HTML 字符串
        """
        if not stats:
            return ""

        # 计算总条目数（固定空词组 count=0 不计入总数）
        total_count = sum(stat.get("count", 0) for stat in stats)
        # 仅固定空时也保留 RSS 段（§Q-empty：放宽 total_count==0 门）
        has_pinned = any(stat.get("pinned") for stat in stats)
        if total_count == 0 and not has_pinned:
            return ""

        rss_html = f"""
                <div class="rss-section">
                    <div class="rss-section-header">
                        <div class="rss-section-title">{title}</div>
                        <div class="rss-section-count">{total_count} 条</div>
                    </div>
                    <div class="rss-feeds-grid">"""

        # 按关键词分组渲染（与热榜格式一致）
        for stat in stats:
            keyword = stat.get("word", "")
            titles = stat.get("titles", [])
            # 固定空词组（pinned）放行：渲染占位行（§4 RSS :1902）
            if not titles and not stat.get("pinned"):
                continue

            keyword_count = len(titles)

            rss_html += f"""
                    <div class="feed-group">
                        <div class="feed-header">
                            <div class="feed-name">{html_escape(keyword)}</div>
                            <div class="feed-count">{keyword_count} 条</div>
                        </div>"""

            # 固定空词组占位（count==0：本轮 0 匹配，渲染静默行后跳过新闻列表）
            if not titles:
                rss_html += """
                        <div class="news-empty-placeholder">📌 暂无相关新闻</div>"""

            for title_data in titles:
                item_title = title_data.get("title", "")
                url = title_data.get("url", "")
                time_display = title_data.get("time_display", "")
                source_name = title_data.get("source_name", "")
                is_new = title_data.get("is_new", False)

                rss_html += """
                        <div class="rss-item">
                            <div class="rss-meta">"""

                if time_display:
                    rss_html += f'<span class="rss-time">{html_escape(time_display)}</span>'

                if source_name:
                    rss_html += f'<span class="rss-author">{html_escape(source_name)}</span>'

                if is_new:
                    rss_html += '<span class="rss-author" style="color: #dc2626;">NEW</span>'

                rss_html += """
                            </div>
                            <div class="rss-title">"""

                escaped_title = html_escape(item_title)
                if url:
                    escaped_url = html_escape(url)
                    rss_html += f'<a href="{escaped_url}" target="_blank" class="rss-link">{escaped_title}</a>'
                else:
                    rss_html += escaped_title

                rss_html += """
                            </div>
                        </div>"""

            rss_html += """
                    </div>"""

        rss_html += """
                    </div>
                </div>"""
        return rss_html

    # 生成独立展示区内容
    def render_standalone_html(data: Optional[Dict]) -> str:
        """渲染独立展示区 HTML（复用热点词汇统计区样式）

        Args:
            data: 独立展示数据，格式：
                {
                    "platforms": [
                        {
                            "id": "zhihu",
                            "name": "知乎热榜",
                            "items": [
                                {
                                    "title": "标题",
                                    "url": "链接",
                                    "rank": 1,
                                    "ranks": [1, 2, 1],
                                    "first_time": "08:00",
                                    "last_time": "12:30",
                                    "count": 3,
                                }
                            ]
                        }
                    ],
                    "rss_feeds": [
                        {
                            "id": "hacker-news",
                            "name": "Hacker News",
                            "items": [
                                {
                                    "title": "标题",
                                    "url": "链接",
                                    "published_at": "2025-01-07T08:00:00",
                                    "author": "作者",
                                }
                            ]
                        }
                    ]
                }

        Returns:
            渲染后的 HTML 字符串
        """
        if not data:
            return ""

        platforms = data.get("platforms", [])
        rss_feeds = data.get("rss_feeds", [])

        if not platforms and not rss_feeds:
            return ""

        # 计算总条目数
        total_platform_items = sum(len(p.get("items", [])) for p in platforms)
        total_rss_items = sum(len(f.get("items", [])) for f in rss_feeds)
        total_count = total_platform_items + total_rss_items

        if total_count == 0:
            return ""

        # 收集所有分组信息用于生成 tab
        all_groups = []
        for p in platforms:
            items = p.get("items", [])
            if items:
                all_groups.append({"name": p.get("name", p.get("id", "")), "count": len(items)})
        for f in rss_feeds:
            items = f.get("items", [])
            if items:
                all_groups.append({"name": f.get("name", f.get("id", "")), "count": len(items)})

        standalone_html = f"""
                <div class="standalone-section">
                    <div class="standalone-section-header">
                        <div class="standalone-section-title">独立展示区</div>
                        <div class="standalone-section-count">{total_count} 条</div>
                    </div>"""

        # 生成 tab 栏（2+ 分组时）
        if len(all_groups) >= 2:
            standalone_html += """
                    <div class="tab-bar standalone-tab-bar">"""
            for idx, g in enumerate(all_groups):
                active = ' active' if idx == 0 else ''
                standalone_html += f"""
                        <button class="tab-btn{active}" data-standalone-tab="{idx}">{html_escape(g["name"])}<span class="tab-count">{g["count"]}</span></button>"""
            standalone_html += f"""
                        <button class="tab-btn" data-standalone-tab="all">全部<span class="tab-count">{total_count}</span></button>
                    </div>"""

        standalone_html += """
                    <div class="standalone-groups-grid">"""

        group_idx = 0
        # 渲染热榜平台（复用 word-group 结构）
        for platform in platforms:
            platform_name = platform.get("name", platform.get("id", ""))
            items = platform.get("items", [])
            if not items:
                continue

            standalone_html += f"""
                    <div class="standalone-group" data-standalone-tab="{group_idx}">
                        <div class="standalone-header">
                            <div class="standalone-name">{html_escape(platform_name)}</div>
                            <div class="standalone-count">{len(items)} 条</div>
                        </div>"""

            # 渲染每个条目（复用 news-item 结构）
            for j, item in enumerate(items, 1):
                title = item.get("title", "")
                url = item.get("url", "") or item.get("mobileUrl", "")
                rank = item.get("rank", 0)
                ranks = item.get("ranks", [])
                first_time = item.get("first_time", "")
                last_time = item.get("last_time", "")
                count = item.get("count", 1)

                standalone_html += f"""
                        <div class="news-item">
                            <div class="news-number">{j}</div>
                            <div class="news-content">
                                <div class="news-header">"""

                # 排名显示（复用 rank-num 样式，无 # 前缀）
                if ranks:
                    min_rank = min(ranks)
                    max_rank = max(ranks)

                    # 确定排名等级
                    if min_rank <= 3:
                        rank_class = "top"
                    elif min_rank <= 10:
                        rank_class = "high"
                    else:
                        rank_class = ""

                    if min_rank == max_rank:
                        rank_text = str(min_rank)
                    else:
                        rank_text = f"{min_rank}-{max_rank}"

                    standalone_html += f'<span class="rank-num {rank_class}">{rank_text}</span>'
                elif rank > 0:
                    if rank <= 3:
                        rank_class = "top"
                    elif rank <= 10:
                        rank_class = "high"
                    else:
                        rank_class = ""
                    standalone_html += f'<span class="rank-num {rank_class}">{rank}</span>'

                # 时间显示（复用 time-info 样式，将 HH-MM 转换为 HH:MM）
                if first_time and last_time and first_time != last_time:
                    first_time_display = convert_time_for_display(first_time)
                    last_time_display = convert_time_for_display(last_time)
                    standalone_html += f'<span class="time-info">{html_escape(first_time_display)}~{html_escape(last_time_display)}</span>'
                elif first_time:
                    first_time_display = convert_time_for_display(first_time)
                    standalone_html += f'<span class="time-info">{html_escape(first_time_display)}</span>'

                # 出现次数（复用 count-info 样式）
                if count > 1:
                    standalone_html += f'<span class="count-info">{count}次</span>'

                standalone_html += """
                                </div>
                                <div class="news-title">"""

                # 标题和链接（复用 news-link 样式）
                escaped_title = html_escape(title)
                if url:
                    escaped_url = html_escape(url)
                    standalone_html += f'<a href="{escaped_url}" target="_blank" class="news-link">{escaped_title}</a>'
                else:
                    standalone_html += escaped_title

                standalone_html += """
                                </div>
                            </div>
                        </div>"""

            standalone_html += """
                    </div>"""
            group_idx += 1

        # 渲染 RSS 源（复用相同结构）
        for feed in rss_feeds:
            feed_name = feed.get("name", feed.get("id", ""))
            items = feed.get("items", [])
            if not items:
                continue

            standalone_html += f"""
                    <div class="standalone-group" data-standalone-tab="{group_idx}">
                        <div class="standalone-header">
                            <div class="standalone-name">{html_escape(feed_name)}</div>
                            <div class="standalone-count">{len(items)} 条</div>
                        </div>"""

            for j, item in enumerate(items, 1):
                title = item.get("title", "")
                url = item.get("url", "")
                published_at = item.get("published_at", "")
                author = item.get("author", "")

                standalone_html += f"""
                        <div class="news-item">
                            <div class="news-number">{j}</div>
                            <div class="news-content">
                                <div class="news-header">"""

                # 时间显示：aware（带偏移）换算到配置时区；naive（如 foodmate
                # 裸 CST 墙钟）视作配置时区墙钟原样呈现。详见 utils.time。
                time_display = format_iso_time_friendly(
                    published_at, timezone, include_date=True
                )
                if time_display:
                    standalone_html += f'<span class="time-info">{html_escape(time_display)}</span>'

                # 作者显示
                if author:
                    standalone_html += f'<span class="source-name">{html_escape(author)}</span>'

                standalone_html += """
                                </div>
                                <div class="news-title">"""

                escaped_title = html_escape(title)
                if url:
                    escaped_url = html_escape(url)
                    standalone_html += f'<a href="{escaped_url}" target="_blank" class="news-link">{escaped_title}</a>'
                else:
                    standalone_html += escaped_title

                standalone_html += """
                                </div>
                            </div>
                        </div>"""

            standalone_html += """
                    </div>"""
            group_idx += 1

        standalone_html += """
                    </div>
                </div>"""
        return standalone_html

    # 生成 RSS 统计和新增 HTML
    rss_stats_html = render_rss_stats_html(rss_items, "RSS 订阅") if rss_items else ""
    # RSS 新增区域随 new_items 区域开关：display.regions.new_items=false 时整体不渲染
    # （含固定词组占位 → display.regions > 固定词组）。对照热榜新增 html.py:1805 的同款门控。
    rss_new_html = (
        render_rss_stats_html(rss_new_items, "RSS 新增更新")
        if (show_new_section and rss_new_items)
        else ""
    )

    # 生成独立展示区 HTML
    standalone_html = render_standalone_html(standalone_data)

    # 生成 AI 分析 HTML
    ai_html = render_ai_analysis_html_rich(ai_analysis) if ai_analysis else ""

    # 生成地区地图 HTML（payload 为 None/空树时 render_region_map_html 返回空串）
    region_map_html = render_region_map_html(region_map) if region_map else ""

    # 准备各区域内容映射
    region_contents = {
        "hotlist": stats_html,
        "rss": rss_stats_html,
        "new_items": (new_titles_html, rss_new_html),  # 元组，分别处理
        "standalone": standalone_html,
        "ai_analysis": ai_html,
        "region_map": region_map_html,
    }

    def add_section_divider(content: str) -> str:
        """为内容的外层 div 添加 section-divider 类"""
        if not content or 'class="' not in content:
            return content
        first_class_pos = content.find('class="')
        if first_class_pos != -1:
            insert_pos = first_class_pos + len('class="')
            return content[:insert_pos] + "section-divider " + content[insert_pos:]
        return content

    # 按 region_order 顺序组装内容，动态添加分割线
    has_previous_content = False
    for region in region_order:
        content = region_contents.get(region, "")
        if region == "new_items":
            # 特殊处理 new_items 区域（包含热榜新增和 RSS 新增两部分）
            new_html, rss_new = content
            if new_html:
                if has_previous_content:
                    new_html = add_section_divider(new_html)
                html += new_html
                has_previous_content = True
            if rss_new:
                if has_previous_content:
                    rss_new = add_section_divider(rss_new)
                html += rss_new
                has_previous_content = True
        elif content:
            if has_previous_content:
                content = add_section_divider(content)
            html += content
            has_previous_content = True

    html += """
            </div>

            <div class="footer">
                <div class="footer-content">"""

    if update_info:
        html += f"""
                    <br>
                    <span style="color: #ea580c; font-weight: 500;">
                        发现新版本 {update_info['remote_version']}，当前版本 {update_info['current_version']}
                    </span>"""

    html += """
                </div>
            </div>
        </div>

        <div class="fab-bar">
            <button class="fab-btn" onclick="window.scrollTo({top:0,behavior:'smooth'})" title="返回顶部">↑</button>
            <button class="fab-btn fab-help">
                <span>?</span>
                <div class="fab-tooltip">
                    <div class="tip-row"><span>切换宽屏</span><span class="tip-key">W</span></div>
                    <div class="tip-row"><span>暗色模式</span><span class="tip-key">D</span></div>
                    <div class="tip-row"><span>搜索</span><span class="tip-key">/</span></div>
                    <div class="tip-row"><span>上一个 Tab</span><span class="tip-key">←</span></div>
                    <div class="tip-row"><span>下一个 Tab</span><span class="tip-key">→</span></div>
                    <div class="tip-row"><span>序号可复制</span><span class="tip-key">点击</span></div>
                </div>
            </button>
        </div>

        <script>
            // ===== 浏览器增强功能 =====

            function toggleWideMode() {
                document.body.classList.toggle('wide-mode');
                var isWide = document.body.classList.contains('wide-mode');
                try { localStorage.setItem('trendradar-wide-mode', isWide ? '1' : '0'); } catch(e) {}
                var btn = document.querySelector('.toggle-wide-btn');
                if (btn) btn.textContent = isWide ? '⊡' : '⛶';
                initTabVisibility();
                initCollapseVisibility();
                initStandaloneTabVisibility();
            }

            function toggleDarkMode() {
                var isDark = document.body.classList.toggle('dark-mode');
                try { localStorage.setItem('trendradar-dark-mode', isDark ? '1' : '0'); } catch(e) {}
                var btn = document.querySelector('.toggle-dark-btn');
                if (btn) btn.textContent = isDark ? '☀' : '☽';
            }

            function initTabScroll(tabBar) {
                var wrapper = tabBar.closest('.tab-bar-wrapper') || tabBar.parentNode;
                var leftArrow = wrapper.querySelector('.tab-arrow-left');
                var rightArrow = wrapper.querySelector('.tab-arrow-right');
                var indicator = wrapper.querySelector('.tab-scroll-indicator');
                if (!leftArrow) {
                    leftArrow = document.createElement('button');
                    leftArrow.className = 'tab-arrow tab-arrow-left';
                    leftArrow.innerHTML = '‹';
                    rightArrow = document.createElement('button');
                    rightArrow.className = 'tab-arrow tab-arrow-right';
                    rightArrow.innerHTML = '›';
                    indicator = document.createElement('div');
                    indicator.className = 'tab-scroll-indicator';
                    wrapper.insertBefore(leftArrow, tabBar);
                    tabBar.after(rightArrow);
                    wrapper.appendChild(indicator);
                }
                var scrollStep = 200;
                leftArrow.addEventListener('click', function(e) {
                    e.stopPropagation();
                    tabBar.scrollBy({ left: -scrollStep, behavior: 'smooth' });
                });
                rightArrow.addEventListener('click', function(e) {
                    e.stopPropagation();
                    tabBar.scrollBy({ left: scrollStep, behavior: 'smooth' });
                });
                function updateArrows() {
                    var sl = tabBar.scrollLeft;
                    var sw = tabBar.scrollWidth;
                    var cw = tabBar.clientWidth;
                    var noOverflow = sw <= cw + 1;
                    var atStart = sl <= 1;
                    var atEnd = sl + cw >= sw - 1;
                    leftArrow.classList.toggle('visible', !noOverflow && !atStart);
                    rightArrow.classList.toggle('visible', !noOverflow && !atEnd);
                    tabBar.classList.toggle('scroll-start', atStart);
                    tabBar.classList.toggle('scroll-end', atEnd);
                    tabBar.classList.toggle('no-overflow', noOverflow);
                    var progress = noOverflow ? 0 : sl / (sw - cw);
                    indicator.style.width = (progress * 100) + '%';
                }
                tabBar.addEventListener('scroll', updateArrows, { passive: true });
                tabBar.addEventListener('wheel', function(e) {
                    if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
                        tabBar.scrollLeft += e.deltaY;
                        e.preventDefault();
                    }
                }, { passive: false });
                updateArrows();
                new ResizeObserver(updateArrows).observe(tabBar);
            }

            function initTabs() {
                var wrapper = document.querySelector('.tab-bar-wrapper');
                var tabBar = wrapper ? wrapper.querySelector('.tab-bar') : null;
                if (!tabBar) return;
                var tabs = tabBar.querySelectorAll('.tab-btn');
                var groups = document.querySelectorAll('.word-group[data-tab-index]');
                initTabVisibility();
                initTabScroll(tabBar);

                function activateTab(index, scroll) {
                    tabs.forEach(function(t) { t.classList.remove('active'); });
                    if (index === 'all') {
                        var allBtn = tabBar.querySelector('[data-tab-index="all"]');
                        if (allBtn) {
                            allBtn.classList.add('active');
                            if (scroll !== false) allBtn.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
                        }
                        groups.forEach(function(g) { g.style.display = ''; });
                        try { history.replaceState(null, '', '#all'); } catch(e) {}
                        return;
                    }
                    var idx = parseInt(index);
                    tabs.forEach(function(t) {
                        if (parseInt(t.dataset.tabIndex) === idx) t.classList.add('active');
                    });
                    if (document.body.classList.contains('wide-mode') && !wrapper.classList.contains('tab-hidden')) {
                        groups.forEach(function(g) {
                            g.style.display = (parseInt(g.dataset.tabIndex) === idx) ? '' : 'none';
                        });
                    }
                    var activeBtn = tabBar.querySelector('.tab-btn.active');
                    if (scroll !== false && activeBtn) activeBtn.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
                    try { history.replaceState(null, '', '#tab-' + idx); } catch(e) {}
                }

                tabs.forEach(function(tab) {
                    tab.addEventListener('click', function() {
                        var idx = tab.dataset.tabIndex;
                        activateTab(idx === 'all' ? 'all' : parseInt(idx));
                    });
                });

                tabBar.addEventListener('keydown', function(e) {
                    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
                        var tabsArr = Array.from(tabs);
                        var ci = tabsArr.findIndex(function(t) { return t.classList.contains('active'); });
                        var dir = e.key === 'ArrowRight' ? 1 : -1;
                        var ni = Math.max(0, Math.min(tabsArr.length - 1, ci + dir));
                        var nt = tabsArr[ni];
                        activateTab(nt.dataset.tabIndex === 'all' ? 'all' : parseInt(nt.dataset.tabIndex));
                        nt.focus();
                        e.preventDefault();
                    }
                });

                var hash = window.location.hash;
                if (hash === '#all') { activateTab('all'); }
                else if (hash.indexOf('#tab-') === 0) { activateTab(parseInt(hash.replace('#tab-', ''))); }
                else { activateTab(0, false); }
            }

            function initTabVisibility() {
                var wrapper = document.querySelector('.tab-bar-wrapper');
                if (!wrapper) return;
                var tabBar = wrapper.querySelector('.tab-bar');
                var groups = document.querySelectorAll('.word-group[data-tab-index]');
                var isWide = document.body.classList.contains('wide-mode');
                if (!isWide || groups.length <= 2) {
                    wrapper.classList.add('tab-hidden');
                    groups.forEach(function(g) { g.style.display = ''; });
                } else {
                    wrapper.classList.remove('tab-hidden');
                    var activeTab = tabBar.querySelector('.tab-btn.active');
                    if (activeTab) { activeTab.click(); }
                    else {
                        var firstTab = tabBar.querySelector('.tab-btn[data-tab-index="0"]');
                        if (firstTab) firstTab.click();
                    }
                }
            }

            var handleSearch = (function() {
                var timer = null;
                return function(query) {
                    clearTimeout(timer);
                    timer = setTimeout(function() {
                        query = query.toLowerCase();
                        document.querySelectorAll('.news-item').forEach(function(item) {
                            var title = (item.querySelector('.news-title') || {}).textContent || '';
                            item.style.display = (!query || title.toLowerCase().indexOf(query) !== -1) ? '' : 'none';
                        });
                        document.querySelectorAll('.rss-item').forEach(function(item) {
                            var title = (item.querySelector('.rss-title') || {}).textContent || '';
                            item.style.display = (!query || title.toLowerCase().indexOf(query) !== -1) ? '' : 'none';
                        });
                    }, 200);
                };
            })();

            function initBackToTop() {
                var fabBar = document.querySelector('.fab-bar');
                if (!fabBar) return;
                var ticking = false;
                window.addEventListener('scroll', function() {
                    if (!ticking) {
                        requestAnimationFrame(function() {
                            fabBar.classList.toggle('visible', window.scrollY > 300);
                            ticking = false;
                        });
                        ticking = true;
                    }
                });
            }

            function initCollapse() {
                document.querySelectorAll('.word-header').forEach(function(header) {
                    header.addEventListener('click', function() {
                        var wrapper = document.querySelector('.tab-bar-wrapper');
                        if (document.body.classList.contains('wide-mode') && wrapper && !wrapper.classList.contains('tab-hidden')) return;
                        var group = header.closest('.word-group');
                        if (group) group.classList.toggle('collapsed');
                    });
                });
                initCollapseVisibility();
            }

            function initCollapseVisibility() {
                var headers = document.querySelectorAll('.word-header');
                var wrapper = document.querySelector('.tab-bar-wrapper');
                var isTabMode = document.body.classList.contains('wide-mode') && wrapper && !wrapper.classList.contains('tab-hidden');
                headers.forEach(function(h) {
                    if (isTabMode) { h.classList.remove('collapsible'); }
                    else { h.classList.add('collapsible'); }
                });
                if (isTabMode) {
                    document.querySelectorAll('.word-group.collapsed').forEach(function(g) {
                        g.classList.remove('collapsed');
                    });
                }
            }

            // 独立展示区 Tab 切换
            function initStandaloneTabs() {
                var tabBar = document.querySelector('.standalone-tab-bar');
                if (!tabBar) return;
                var groups = document.querySelectorAll('.standalone-group[data-standalone-tab]');
                var btns = tabBar.querySelectorAll('.tab-btn[data-standalone-tab]');
                initTabScroll(tabBar);

                function activateStandaloneTab(val) {
                    btns.forEach(function(b) {
                        var bVal = b.getAttribute('data-standalone-tab');
                        b.classList.toggle('active', bVal === String(val));
                    });
                    groups.forEach(function(g) {
                        var gVal = g.getAttribute('data-standalone-tab');
                        g.style.display = (val === 'all' || gVal === String(val)) ? '' : 'none';
                    });
                }

                btns.forEach(function(btn) {
                    btn.addEventListener('click', function() {
                        activateStandaloneTab(btn.getAttribute('data-standalone-tab'));
                    });
                });

                // 初始状态
                initStandaloneTabVisibility();
            }

            function initStandaloneTabVisibility() {
                var tabBar = document.querySelector('.standalone-tab-bar');
                if (!tabBar) return;
                var groups = document.querySelectorAll('.standalone-group[data-standalone-tab]');
                var isWide = document.body.classList.contains('wide-mode');
                if (!isWide || groups.length <= 1) {
                    tabBar.classList.add('tab-hidden');
                    groups.forEach(function(g) { g.style.display = ''; });
                } else {
                    tabBar.classList.remove('tab-hidden');
                    var activeBtn = tabBar.querySelector('.tab-btn.active');
                    if (activeBtn) activeBtn.click();
                    else { var first = tabBar.querySelector('.tab-btn'); if (first) first.click(); }
                }
            }

            function prepareForScreenshot() {
                var state = {
                    wasWide: document.body.classList.contains('wide-mode'),
                    hiddenGroups: []
                };
                document.body.classList.remove('wide-mode');
                state.wasDark = document.body.classList.contains('dark-mode');
                document.body.classList.remove('dark-mode');
                document.querySelectorAll('.word-group[data-tab-index]').forEach(function(g, i) {
                    if (g.style.display === 'none') {
                        state.hiddenGroups.push(i);
                        g.style.display = '';
                    }
                });
                state.hiddenStandaloneGroups = [];
                document.querySelectorAll('.standalone-group[data-standalone-tab]').forEach(function(g, i) {
                    if (g.style.display === 'none') {
                        state.hiddenStandaloneGroups.push(i);
                        g.style.display = '';
                    }
                });
                document.querySelectorAll('.tab-bar-wrapper, .standalone-tab-bar, .search-bar, .fab-bar, .toggle-wide-btn').forEach(function(el) {
                    el.dataset.prevDisplay = el.style.display || '';
                    el.style.display = 'none';
                });
                document.querySelectorAll('.toggle-dark-btn').forEach(function(el) {
                    el.dataset.prevDisplay = el.style.display || ''; el.style.display = 'none';
                });
                document.querySelectorAll('.reading-progress').forEach(function(el) { el.style.display = 'none'; });
                document.querySelectorAll('.header-watermark').forEach(function(el) { el.style.display = 'none'; });
                return state;
            }

            function restoreAfterScreenshot(state) {
                if (state.wasWide) document.body.classList.add('wide-mode');
                if (state.wasDark) document.body.classList.add('dark-mode');
                var groups = document.querySelectorAll('.word-group[data-tab-index]');
                state.hiddenGroups.forEach(function(i) {
                    if (groups[i]) groups[i].style.display = 'none';
                });
                var standaloneGroups = document.querySelectorAll('.standalone-group[data-standalone-tab]');
                if (state.hiddenStandaloneGroups) {
                    state.hiddenStandaloneGroups.forEach(function(i) {
                        if (standaloneGroups[i]) standaloneGroups[i].style.display = 'none';
                    });
                }
                document.querySelectorAll('.tab-bar-wrapper, .standalone-tab-bar, .search-bar, .fab-bar, .toggle-wide-btn').forEach(function(el) {
                    el.style.display = el.dataset.prevDisplay || '';
                    delete el.dataset.prevDisplay;
                });
                document.querySelectorAll('.toggle-dark-btn').forEach(function(el) {
                    el.style.display = el.dataset.prevDisplay || ''; delete el.dataset.prevDisplay;
                });
                document.querySelectorAll('.reading-progress').forEach(function(el) { el.style.display = ''; });
                document.querySelectorAll('.header-watermark').forEach(function(el) { el.style.display = ''; });
                initTabVisibility();
                initCollapseVisibility();
                initStandaloneTabVisibility();
                var fabBar = document.querySelector('.fab-bar');
                if (fabBar && window.scrollY > 300) fabBar.classList.add('visible');
            }

            // ===== 截图功能 =====

            async function saveAsImage(e) {
                const button = e.target.closest('.save-dropdown-item') || e.target;
                const originalHTML = button.innerHTML;
                var screenshotState = null;

                try {
                    button.textContent = '生成中...';
                    button.disabled = true;
                    window.scrollTo(0, 0);

                    // 等待页面稳定
                    await new Promise(resolve => setTimeout(resolve, 200));

                    // 截图前准备：切回窄屏布局
                    screenshotState = prepareForScreenshot();

                    // 截图前隐藏按钮
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'hidden';

                    // 再次等待确保按钮完全隐藏
                    await new Promise(resolve => setTimeout(resolve, 100));

                    const container = document.querySelector('.container');

                    const canvas = await html2canvas(container, {
                        backgroundColor: '#ffffff',
                        scale: 1.5,
                        useCORS: true,
                        allowTaint: false,
                        imageTimeout: 10000,
                        removeContainer: false,
                        foreignObjectRendering: false,
                        logging: false,
                        width: container.offsetWidth,
                        height: container.offsetHeight,
                        x: 0,
                        y: 0,
                        scrollX: 0,
                        scrollY: 0,
                        windowWidth: window.innerWidth,
                        windowHeight: window.innerHeight
                    });

                    buttons.style.visibility = 'visible';
                    restoreAfterScreenshot(screenshotState);

                    const link = document.createElement('a');
                    const now = new Date();
                    const filename = `TrendRadar_热点新闻分析_${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}.png`;

                    link.download = filename;
                    link.href = canvas.toDataURL('image/png', 1.0);

                    // 触发下载
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);

                    button.textContent = '保存成功!';
                    setTimeout(() => {
                        button.innerHTML = originalHTML;
                        button.disabled = false;
                    }, 2000);

                } catch (error) {
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'visible';
                    if (screenshotState) { restoreAfterScreenshot(screenshotState); }
                    button.textContent = '保存失败';
                    setTimeout(() => {
                        button.innerHTML = originalHTML;
                        button.disabled = false;
                    }, 2000);
                }
            }

            async function saveAsMultipleImages(e) {
                const button = e.target.closest('.save-dropdown-item') || e.target;
                const originalHTML = button.innerHTML;
                const container = document.querySelector('.container');
                const scale = 1.5;
                const maxHeight = 5000 / scale;
                var screenshotState2 = null;

                try {
                    screenshotState2 = prepareForScreenshot();
                    button.textContent = '分析中...';
                    button.disabled = true;

                    // 获取所有可能的分割元素
                    const newsItems = Array.from(container.querySelectorAll('.news-item'));
                    const wordGroups = Array.from(container.querySelectorAll('.word-group'));
                    const newSection = container.querySelector('.new-section');
                    const errorSection = container.querySelector('.error-section');
                    const header = container.querySelector('.header');
                    const footer = container.querySelector('.footer');

                    // 计算元素位置和高度
                    const containerRect = container.getBoundingClientRect();
                    const elements = [];

                    // 添加header作为必须包含的元素
                    elements.push({
                        type: 'header',
                        element: header,
                        top: 0,
                        bottom: header.offsetHeight,
                        height: header.offsetHeight
                    });

                    // 添加错误信息（如果存在）
                    if (errorSection) {
                        const rect = errorSection.getBoundingClientRect();
                        elements.push({
                            type: 'error',
                            element: errorSection,
                            top: rect.top - containerRect.top,
                            bottom: rect.bottom - containerRect.top,
                            height: rect.height
                        });
                    }

                    // 按word-group分组处理news-item
                    wordGroups.forEach(group => {
                        const groupRect = group.getBoundingClientRect();
                        const groupNewsItems = group.querySelectorAll('.news-item');

                        // 添加word-group的header部分
                        const wordHeader = group.querySelector('.word-header');
                        if (wordHeader) {
                            const headerRect = wordHeader.getBoundingClientRect();
                            elements.push({
                                type: 'word-header',
                                element: wordHeader,
                                parent: group,
                                top: groupRect.top - containerRect.top,
                                bottom: headerRect.bottom - containerRect.top,
                                height: headerRect.height
                            });
                        }

                        // 添加每个news-item
                        groupNewsItems.forEach(item => {
                            const rect = item.getBoundingClientRect();
                            elements.push({
                                type: 'news-item',
                                element: item,
                                parent: group,
                                top: rect.top - containerRect.top,
                                bottom: rect.bottom - containerRect.top,
                                height: rect.height
                            });
                        });
                    });

                    // 添加新增新闻部分
                    if (newSection) {
                        const rect = newSection.getBoundingClientRect();
                        elements.push({
                            type: 'new-section',
                            element: newSection,
                            top: rect.top - containerRect.top,
                            bottom: rect.bottom - containerRect.top,
                            height: rect.height
                        });
                    }

                    // 添加footer
                    const footerRect = footer.getBoundingClientRect();
                    elements.push({
                        type: 'footer',
                        element: footer,
                        top: footerRect.top - containerRect.top,
                        bottom: footerRect.bottom - containerRect.top,
                        height: footer.offsetHeight
                    });

                    // 计算分割点
                    const segments = [];
                    let currentSegment = { start: 0, end: 0, height: 0, includeHeader: true };
                    let headerHeight = header.offsetHeight;
                    currentSegment.height = headerHeight;

                    for (let i = 1; i < elements.length; i++) {
                        const element = elements[i];
                        const potentialHeight = element.bottom - currentSegment.start;

                        // 检查是否需要创建新分段
                        if (potentialHeight > maxHeight && currentSegment.height > headerHeight) {
                            // 在前一个元素结束处分割
                            currentSegment.end = elements[i - 1].bottom;
                            segments.push(currentSegment);

                            // 开始新分段
                            currentSegment = {
                                start: currentSegment.end,
                                end: 0,
                                height: element.bottom - currentSegment.end,
                                includeHeader: false
                            };
                        } else {
                            currentSegment.height = potentialHeight;
                            currentSegment.end = element.bottom;
                        }
                    }

                    // 添加最后一个分段
                    if (currentSegment.height > 0) {
                        currentSegment.end = container.offsetHeight;
                        segments.push(currentSegment);
                    }

                    button.textContent = `生成中 (0/${segments.length})...`;

                    // 隐藏保存按钮
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'hidden';

                    // 为每个分段生成图片
                    const images = [];
                    for (let i = 0; i < segments.length; i++) {
                        const segment = segments[i];
                        button.textContent = `生成中 (${i + 1}/${segments.length})...`;

                        // 创建临时容器用于截图
                        const tempContainer = document.createElement('div');
                        tempContainer.style.cssText = `
                            position: absolute;
                            left: -9999px;
                            top: 0;
                            width: ${container.offsetWidth}px;
                            background: white;
                        `;
                        tempContainer.className = 'container';

                        // 克隆容器内容
                        const clonedContainer = container.cloneNode(true);

                        // 移除克隆内容中的保存按钮
                        const clonedButtons = clonedContainer.querySelector('.save-buttons');
                        if (clonedButtons) {
                            clonedButtons.style.display = 'none';
                        }

                        tempContainer.appendChild(clonedContainer);
                        document.body.appendChild(tempContainer);

                        // 等待DOM更新
                        await new Promise(resolve => setTimeout(resolve, 100));

                        // 使用html2canvas截取特定区域
                        const canvas = await html2canvas(clonedContainer, {
                            backgroundColor: '#ffffff',
                            scale: scale,
                            useCORS: true,
                            allowTaint: false,
                            imageTimeout: 10000,
                            logging: false,
                            width: container.offsetWidth,
                            height: segment.end - segment.start,
                            x: 0,
                            y: segment.start,
                            windowWidth: window.innerWidth,
                            windowHeight: window.innerHeight
                        });

                        images.push(canvas.toDataURL('image/png', 1.0));

                        // 清理临时容器
                        document.body.removeChild(tempContainer);
                    }

                    // 恢复按钮显示
                    buttons.style.visibility = 'visible';

                    // 下载所有图片
                    const now = new Date();
                    const baseFilename = `TrendRadar_热点新闻分析_${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`;

                    for (let i = 0; i < images.length; i++) {
                        const link = document.createElement('a');
                        link.download = `${baseFilename}_part${i + 1}.png`;
                        link.href = images[i];
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);

                        // 延迟一下避免浏览器阻止多个下载
                        await new Promise(resolve => setTimeout(resolve, 100));
                    }

                    button.textContent = `已保存 ${segments.length} 张图片!`;
                    restoreAfterScreenshot(screenshotState2);
                    setTimeout(() => {
                        button.innerHTML = originalHTML;
                        button.disabled = false;
                    }, 2000);

                } catch (error) {
                    console.error('分段保存失败:', error);
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'visible';
                    if (screenshotState2) { restoreAfterScreenshot(screenshotState2); }
                    button.textContent = '保存失败';
                    setTimeout(() => {
                        button.innerHTML = originalHTML;
                        button.disabled = false;
                    }, 2000);
                }
            }

            function saveAsMarkdown() {
                var lines = [];
                var now = new Date();
                var dateStr = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0');
                var timeStr = String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');

                // 标题
                var headerTitle = document.querySelector('.header-title');
                lines.push('# ' + (headerTitle ? headerTitle.textContent.trim() : 'TrendRadar'));
                lines.push('');

                // 报告元信息
                var infoItems = document.querySelectorAll('.header-info .info-item');
                if (infoItems.length) {
                    infoItems.forEach(function(item) {
                        var label = item.querySelector('.info-label');
                        var value = item.querySelector('.info-value');
                        if (label && value) {
                            lines.push('- **' + label.textContent.trim() + '**: ' + value.textContent.trim());
                        }
                    });
                    lines.push('');
                }

                // 提取 news-item 通用函数
                function extractItem(item, idx) {
                    var titleEl = item.querySelector('.news-title a');
                    var titleText = '';
                    var url = '';
                    if (titleEl) {
                        titleText = titleEl.textContent.trim();
                        url = titleEl.href || '';
                    } else {
                        var titleDiv = item.querySelector('.news-title') || item.querySelector('.new-item-title');
                        if (titleDiv) titleText = titleDiv.textContent.trim();
                    }
                    if (!titleText) return '';

                    var meta = [];
                    var rank = item.querySelector('.rank-num, .new-item-rank');
                    if (rank && rank.textContent.trim() && rank.textContent.trim() !== '?') meta.push('#' + rank.textContent.trim());
                    var source = item.querySelector('.source-name');
                    if (source) meta.push(source.textContent.trim());
                    var keyword = item.querySelector('.keyword-tag');
                    if (keyword) meta.push(keyword.textContent.trim());
                    var time = item.querySelector('.time-info');
                    if (time) meta.push(time.textContent.trim());
                    var count = item.querySelector('.count-info');
                    if (count) meta.push(count.textContent.trim());

                    var line = idx + '. ';
                    if (url) {
                        line += '[' + titleText.replace(/[[\\]]/g, '') + '](' + url + ')';
                    } else {
                        line += titleText;
                    }
                    if (meta.length) line += '  `' + meta.join(' | ') + '`';
                    return line;
                }

                // 热点关键词区
                var wordGroups = document.querySelectorAll('.hotlist-section > .word-group');
                if (wordGroups.length) {
                    lines.push('## 热点新闻');
                    lines.push('');
                    wordGroups.forEach(function(group) {
                        var wordName = group.querySelector('.word-name');
                        var wordCount = group.querySelector('.word-count');
                        if (wordName) {
                            lines.push('### ' + wordName.textContent.trim() + (wordCount ? ' (' + wordCount.textContent.trim() + ')' : ''));
                            lines.push('');
                        }
                        var items = group.querySelectorAll('.news-item');
                        items.forEach(function(item, i) {
                            var line = extractItem(item, i + 1);
                            if (line) lines.push(line);
                        });
                        lines.push('');
                    });
                }

                // 新增热点区
                var newSection = document.querySelector('.new-section');
                if (newSection) {
                    var newTitle = newSection.querySelector('.new-section-title');
                    lines.push('## ' + (newTitle ? newTitle.textContent.trim() : '本次新增热点'));
                    lines.push('');
                    var sourceGroups = newSection.querySelectorAll('.new-source-group');
                    sourceGroups.forEach(function(sg) {
                        var srcTitle = sg.querySelector('.new-source-title');
                        if (srcTitle) {
                            lines.push('### ' + srcTitle.textContent.trim());
                            lines.push('');
                        }
                        var items = sg.querySelectorAll('.new-item');
                        items.forEach(function(item, i) {
                            var line = extractItem(item, i + 1);
                            if (line) lines.push(line);
                        });
                        lines.push('');
                    });
                }

                // RSS 订阅区
                var rssSection = document.querySelector('.rss-section');
                if (rssSection) {
                    var rssSectionTitle = rssSection.querySelector('.rss-section-title');
                    lines.push('## ' + (rssSectionTitle ? rssSectionTitle.textContent.trim() : 'RSS 订阅'));
                    lines.push('');
                    var feedGroups = rssSection.querySelectorAll('.feed-group');
                    feedGroups.forEach(function(group) {
                        var feedName = group.querySelector('.feed-name');
                        var feedCount = group.querySelector('.feed-count');
                        if (feedName) {
                            lines.push('### ' + feedName.textContent.trim() + (feedCount ? ' (' + feedCount.textContent.trim() + ')' : ''));
                            lines.push('');
                        }
                        var items = group.querySelectorAll('.rss-item');
                        items.forEach(function(item, i) {
                            var titleEl = item.querySelector('.rss-title a');
                            var titleText = titleEl ? titleEl.textContent.trim() : '';
                            var url = titleEl ? (titleEl.href || '') : '';
                            if (!titleText) return;
                            var meta = [];
                            var time = item.querySelector('.rss-time');
                            if (time) meta.push(time.textContent.trim());
                            var author = item.querySelector('.rss-author');
                            if (author) meta.push(author.textContent.trim());
                            var line = (i + 1) + '. ';
                            if (url) { line += '[' + titleText.replace(/[\\[\\]]/g, '') + '](' + url + ')'; }
                            else { line += titleText; }
                            if (meta.length) line += '  `' + meta.join(' | ') + '`';
                            lines.push(line);
                        });
                        lines.push('');
                    });
                }

                // AI 热点分析区
                var aiSection = document.querySelector('.ai-section');
                if (aiSection) {
                    var aiError = aiSection.querySelector('.ai-error') || aiSection.querySelector('.ai-warning');
                    var aiInfo = aiSection.querySelector('.ai-info');
                    if (aiError) {
                        lines.push('## AI 分析');
                        lines.push('');
                        lines.push('> ' + aiError.textContent.trim());
                        lines.push('');
                    } else if (aiInfo) {
                        // 跳过 info 提示（如"跳过"）
                    } else {
                        var aiTitle = aiSection.querySelector('.ai-section-title');
                        lines.push('## ' + (aiTitle ? aiTitle.textContent.trim() : 'AI 热点分析'));
                        lines.push('');
                        var aiBlocks = aiSection.querySelectorAll('.ai-block');
                        aiBlocks.forEach(function(block) {
                            var blockTitle = block.querySelector('.ai-block-title');
                            var blockContent = block.querySelector('.ai-block-content');
                            if (blockTitle) {
                                lines.push('### ' + blockTitle.textContent.trim());
                                lines.push('');
                            }
                            if (blockContent) {
                                lines.push(blockContent.textContent.trim());
                                lines.push('');
                            }
                        });
                    }
                }

                // 独立展示区（热榜平台 + RSS）
                var standaloneSection = document.querySelector('.standalone-section');
                if (standaloneSection) {
                    var standaloneTitle = standaloneSection.querySelector('.standalone-section-title');
                    lines.push('## ' + (standaloneTitle ? standaloneTitle.textContent.trim() : '独立展示区'));
                    lines.push('');
                    var groups = standaloneSection.querySelectorAll('.standalone-group');
                    groups.forEach(function(group) {
                        var name = group.querySelector('.standalone-name');
                        var cnt = group.querySelector('.standalone-count');
                        if (name) {
                            lines.push('### ' + name.textContent.trim() + (cnt ? ' (' + cnt.textContent.trim() + ')' : ''));
                            lines.push('');
                        }
                        var items = group.querySelectorAll('.news-item');
                        items.forEach(function(item, i) {
                            var line = extractItem(item, i + 1);
                            if (line) lines.push(line);
                        });
                        lines.push('');
                    });
                }

                // 错误区
                var errorSection = document.querySelector('.error-section');
                if (errorSection) {
                    var errorItems = errorSection.querySelectorAll('.error-item');
                    if (errorItems.length) {
                        lines.push('## 抓取异常');
                        lines.push('');
                        errorItems.forEach(function(item) {
                            lines.push('- ' + item.textContent.trim());
                        });
                        lines.push('');
                    }
                }

                // 页脚
                lines.push('---');
                lines.push('*Generated by TrendRadar*');

                // 下载
                var md = lines.join('\\n');
                var blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
                var link = document.createElement('a');
                var filename = 'TrendRadar_' + dateStr + '_' + timeStr.replace(':', '') + '.md';
                link.download = filename;
                link.href = URL.createObjectURL(blob);
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                URL.revokeObjectURL(link.href);
            }

            document.addEventListener('DOMContentLoaded', function() {
                window.scrollTo(0, 0);

                // 自动检测宽屏模式
                var savedMode = null;
                try { savedMode = localStorage.getItem('trendradar-wide-mode'); } catch(e) {}
                if (savedMode === '1' || (savedMode === null && window.innerWidth > 768)) {
                    document.body.classList.add('wide-mode');
                    var btn = document.querySelector('.toggle-wide-btn');
                    if (btn) btn.textContent = '⊡';
                }

                // 暗色模式恢复
                var savedDark = null;
                try { savedDark = localStorage.getItem('trendradar-dark-mode'); } catch(e) {}
                if (savedDark === '1') {
                    document.body.classList.add('dark-mode');
                    var darkBtn = document.querySelector('.toggle-dark-btn');
                    if (darkBtn) darkBtn.textContent = '☀';
                }

                // 启用搜索栏
                var searchBar = document.querySelector('.search-bar');
                if (searchBar) searchBar.style.display = 'block';

                // 初始化增强功能
                initTabs();
                initBackToTop();
                initCollapse();
                initStandaloneTabs();

                // 键盘快捷键
                document.addEventListener('keydown', function(e) {
                    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
                    var helpBtn = document.querySelector('.fab-help');
                    switch(e.key) {
                        case '?':
                            if (helpBtn) {
                                helpBtn.classList.toggle('show-tip');
                                var fabBar = document.querySelector('.fab-bar');
                                if (fabBar) fabBar.classList.add('visible');
                            }
                            break;
                        case 'Escape':
                            if (helpBtn) helpBtn.classList.remove('show-tip');
                            break;
                        case 'w': case 'W': toggleWideMode(); break;
                        case 'd': case 'D': toggleDarkMode(); break;
                        case '/': e.preventDefault(); var si = document.querySelector('.search-input'); if (si) si.focus(); break;
                    }
                });

                // 阅读进度条
                var progressBar = document.querySelector('.reading-progress');
                if (progressBar) {
                    var progressTicking = false;
                    window.addEventListener('scroll', function() {
                        if (!progressTicking) {
                            requestAnimationFrame(function() {
                                var h = document.documentElement.scrollHeight - window.innerHeight;
                                progressBar.style.width = (h > 0 ? (window.scrollY / h * 100) : 0) + '%';
                                progressTicking = false;
                            });
                            progressTicking = true;
                        }
                    });
                }

                // 一键复制：hover 时数字变复制图标
                var copySvg = '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="5" y="5" width="9" height="9" rx="1.5"/><path d="M5 11H3.5A1.5 1.5 0 012 9.5v-7A1.5 1.5 0 013.5 1h7A1.5 1.5 0 0112 2.5V5"/></svg>';
                var checkSvg = '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="#22c55e" stroke-width="2"><path d="M3 8.5l3.5 3.5 7-7"/></svg>';
                document.querySelectorAll('.news-item .news-number').forEach(function(numEl) {
                    var item = numEl.closest('.news-item');
                    var titleEl = item ? item.querySelector('.news-title a') : null;
                    if (!titleEl) return;
                    var numText = numEl.textContent.trim();
                    numEl.innerHTML = '<span class="num-text">' + numText + '</span><span class="copy-icon">' + copySvg + '</span>';
                    numEl.title = '点击复制标题和链接';
                    numEl.addEventListener('click', function(e) {
                        e.stopPropagation();
                        var text = titleEl.textContent.trim() + ' ' + titleEl.href;
                        function onCopySuccess() {
                            numEl.classList.add('copied');
                            numEl.querySelector('.copy-icon').innerHTML = checkSvg;
                            setTimeout(function() {
                                numEl.classList.remove('copied');
                                numEl.querySelector('.copy-icon').innerHTML = copySvg;
                            }, 1500);
                        }
                        function fallbackCopy(str, cb) {
                            var ta = document.createElement('textarea');
                            ta.value = str; ta.style.position = 'fixed'; ta.style.opacity = '0';
                            document.body.appendChild(ta); ta.select();
                            try { document.execCommand('copy'); cb(); } catch(ex) {}
                            document.body.removeChild(ta);
                        }
                        if (navigator.clipboard && navigator.clipboard.writeText) {
                            navigator.clipboard.writeText(text).then(onCopySuccess).catch(function() {
                                fallbackCopy(text, onCopySuccess);
                            });
                        } else {
                            fallbackCopy(text, onCopySuccess);
                        }
                    });
                });



                // Header watermark 鼠标跟随揭示
                (function() {
                    var header = document.querySelector('.header');
                    var watermark = document.querySelector('.header-watermark');
                    if (!header || !watermark) return;

                    var radius = 100;

                    header.addEventListener('mousemove', function(e) {
                        var rect = watermark.getBoundingClientRect();
                        var x = e.clientX - rect.left;
                        var y = e.clientY - rect.top;
                        var maskVal = 'radial-gradient(circle ' + radius + 'px at ' + x + 'px ' + y + 'px, rgba(0,0,0,1) 0%, rgba(0,0,0,0.3) 50%, rgba(0,0,0,0) 100%)';
                        watermark.style.webkitMaskImage = maskVal;
                        watermark.style.maskImage = maskVal;
                        watermark.style.color = 'rgba(255, 255, 255, 0.25)';
                    });

                    header.addEventListener('mouseleave', function() {
                        watermark.style.webkitMaskImage = 'radial-gradient(circle 0px at 50% 50%, rgba(0,0,0,1) 0%, rgba(0,0,0,0) 100%)';
                        watermark.style.maskImage = 'radial-gradient(circle 0px at 50% 50%, rgba(0,0,0,1) 0%, rgba(0,0,0,0) 100%)';
                        watermark.style.color = 'rgba(255, 255, 255, 0.15)';
                    });
                })();
            });
        </script>
    </body>
    </html>
    """

    return html
