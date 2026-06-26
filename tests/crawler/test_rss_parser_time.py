# coding=utf-8
"""RSS 解析器发布时间回归测试。

钉死 `_parse_date` 的关键契约：
- 源带时区偏移（RFC822 / ISO / Z）→ 存储为 aware ISO，**保留偏移**。
- 源为裸墙钟（foodmate `2026-06-26 10:43:43`，无偏移）→ 存储为 naive ISO，
  由下游 utils.time 按配置时区墙钟处理。

回归对象：历史上 `_parse_date` 优先取 feedparser `published_parsed`
（time.struct_time 不携带 tz 信号），把 foodmate 的 CST 裸墙钟当成 UTC 存储，
下游再 +8 → 显示多 8 小时。
"""

import time as _time

from trendradar.crawler.rss.parser import RSSParser


def _make_feed(pubdate: str) -> str:
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>'
        f"<item><title>t</title><link>http://a/b</link>"
        f"<pubDate>{pubdate}</pubDate></item></channel></rss>"
    )


def _published_at(pubdate: str) -> str:
    items = RSSParser().parse(_make_feed(pubdate))
    assert items, f"解析失败: {pubdate!r}"
    return items[0].published_at


# --- 源带偏移：aware ISO，偏移必须保留（不得降级为 naive 或被二次换算） ---


def test_rfc822_positive_offset_preserved():
    # Arrange / Act
    out = _published_at("Thu, 26 Jun 2026 10:43:43 +0800")
    # Assert — +08:00 原样保留
    assert out == "2026-06-26T10:43:43+08:00"


def test_rfc822_utc_preserved():
    # Arrange / Act
    out = _published_at("Thu, 26 Jun 2026 02:43:43 GMT")
    # Assert — GMT → +00:00
    assert out == "2026-06-26T02:43:43+00:00"


def test_iso_aware_offset_preserved():
    # Arrange / Act
    out = _published_at("2025-12-29T00:20:00+00:00")
    # Assert
    assert out == "2025-12-29T00:20:00+00:00"


def test_iso_z_suffix_preserved():
    # Arrange / Act
    out = _published_at("2025-12-29T00:20:00Z")
    # Assert — Z 归一为 +00:00
    assert out == "2025-12-29T00:20:00+00:00"


# --- 源无偏移：naive ISO，交下游处理（不得当 UTC localize） ---


def test_foodmate_bare_wallclock_stored_naive():
    # Arrange — foodmate 真实 pubDate 格式（CST 裸墙钟，无偏移）
    # Act
    out = _published_at("2026-06-26 10:43:43")
    # Assert — naive 存储，无 +00:00 / +08:00 后缀
    assert out == "2026-06-26T10:43:43"
    assert "+" not in out


def test_iso_naive_stored_naive():
    # Arrange / Act
    out = _published_at("2025-12-29T00:20:00")
    # Assert
    assert out == "2025-12-29T00:20:00"
    assert "+" not in out


# --- 容错 ---


def test_missing_pubdate_returns_none():
    # Arrange — 无 pubDate 字段
    xml = (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>'
        "<item><title>t</title><link>http://a/b</link></item></channel></rss>"
    )
    # Act
    items = RSSParser().parse(xml)
    # Assert
    assert items[0].published_at is None


def test_unparseable_pubdate_returns_none():
    # Arrange / Act
    out = _published_at("not-a-date")
    # Assert — 容错返回 None（不抛异常）
    assert out is None


# --- struct_time 兜底路径：仅当原始字符串不可用时走，按 UTC aware ---


def test_struct_time_fallback_when_raw_string_absent():
    """构造伪 entry，仅有 published_parsed、无 published 字符串，验证兜底按 UTC aware。"""
    parser = RSSParser()

    class _FakeEntry(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    entry = _FakeEntry()
    # struct_time(2026-06-26 10:43:43 UTC)
    entry["published_parsed"] = _time.struct_time(
        (2026, 6, 26, 10, 43, 43, 0, 0, 0)
    )
    # Act
    out = parser._parse_date(entry)
    # Assert — 兜底标记 UTC aware
    assert out == "2026-06-26T10:43:43+00:00"
