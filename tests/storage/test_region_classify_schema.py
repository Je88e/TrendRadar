# coding=utf-8
"""region_classify schema SQL 单元测试（in-memory sqlite）。"""

import sqlite3
from pathlib import Path

import pytest

SCHEMA_PATH = Path("trendradar/storage/region_classify_schema.sql")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return c


def test_tables_created(conn):
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "region_classify_results" in tables
    assert "region_classify_analyzed_news" in tables


def test_results_unique_per_news_source(conn):
    # 单地区/新闻：同 (news_item_id, source_type) 唯一
    conn.execute(
        "INSERT INTO region_classify_results(news_item_id,source_type,level,country,country_code,created_at) "
        "VALUES(1,'hotlist','country','中国','CN','t')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO region_classify_results(news_item_id,source_type,level,country,created_at) "
            "VALUES(1,'hotlist','country','美国','t')"
        )


def test_results_allows_same_news_different_source(conn):
    # 同 news 不同 source_type 允许（hotlist vs rss）
    conn.execute(
        "INSERT INTO region_classify_results(news_item_id,source_type,level,country,created_at) "
        "VALUES(1,'hotlist','country','中国','t')"
    )
    conn.execute(
        "INSERT INTO region_classify_results(news_item_id,source_type,level,country,created_at) "
        "VALUES(1,'rss','country','中国','t')"
    )
    n = conn.execute("SELECT COUNT(*) FROM region_classify_results").fetchone()[0]
    assert n == 2


def test_analyzed_news_pk_unique(conn):
    conn.execute(
        "INSERT INTO region_classify_analyzed_news(news_item_id,source_type,content_hash,level,created_at) "
        "VALUES(1,'hotlist','h1','city','t')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO region_classify_analyzed_news(news_item_id,source_type,content_hash,level,created_at) "
            "VALUES(1,'hotlist','h2','city','t')"
        )


def test_indexes_created(conn):
    idx = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    )}
    assert any("region_classify_results" in str(i) or i.startswith("idx_region") for i in idx)
