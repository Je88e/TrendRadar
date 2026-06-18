-- 地区分类相关表结构
-- 在 news 库中创建，与 news_items / rss_items 同库
-- 详见 docs/region-classify-design.md、ADR-0001、ADR-0002

-- ============================================
-- 地区分类结果表
-- 每条新闻 = 一行（单一主地区路径，区别于 ai_filter 的 per-tag 多行）
-- 引用 news_items.id 或 rss_items.id（通过 source_type 区分）
-- ============================================
CREATE TABLE IF NOT EXISTS region_classify_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_item_id INTEGER NOT NULL,       -- 引用 news_items.id 或 rss_items.id
    source_type TEXT NOT NULL DEFAULT 'hotlist',  -- hotlist / rss
    level TEXT NOT NULL,                 -- unknown / country / province / city
    country TEXT,                        -- 规范中文全称：中国 / 美国
    country_code TEXT,                   -- ISO alpha-2：CN / US（归一化失败 NULL）
    province TEXT,                       -- 广东省 / 加利福尼亚州（海外仅名）
    province_adcode TEXT,                -- 仅中国：440000
    city TEXT,                           -- 广州市 / 旧金山（海外仅名）
    city_adcode TEXT,                    -- 仅中国：440100
    confidence REAL DEFAULT 0,
    status TEXT DEFAULT 'active',        -- active / deprecated
    deprecated_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(news_item_id, source_type)    -- 单地区 → 每条新闻唯一
);

-- ============================================
-- 已分析去重表（内容绑定缓存）
-- 跨运行去重，避免重复发给 AI；标题变更（content_hash 变）触发重分类
-- ============================================
CREATE TABLE IF NOT EXISTS region_classify_analyzed_news (
    news_item_id INTEGER NOT NULL,       -- 引用 news_items.id 或 rss_items.id
    source_type TEXT NOT NULL DEFAULT 'hotlist',  -- hotlist / rss
    content_hash TEXT NOT NULL,          -- title 维度 hash；标题变 → 重分类
    level TEXT NOT NULL,                 -- 最近一次 level（含 unknown）
    created_at TEXT NOT NULL,
    PRIMARY KEY (news_item_id, source_type)
);

-- ============================================
-- 索引
-- ============================================
CREATE INDEX IF NOT EXISTS idx_region_classify_results_status
    ON region_classify_results(status);
CREATE INDEX IF NOT EXISTS idx_region_classify_results_news
    ON region_classify_results(news_item_id, source_type);
CREATE INDEX IF NOT EXISTS idx_region_classify_analyzed_news_lookup
    ON region_classify_analyzed_news(source_type);
