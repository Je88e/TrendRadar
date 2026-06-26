# coding=utf-8
"""时间工具单元测试。

锁定 format_iso_time_friendly / is_within_days / calculate_days_old 的时区语义：

- aware ISO（带偏移或 Z）→ 按源时区正确换算到配置时区。
- naive ISO（无偏移）→ 视作已处于配置时区的墙钟时间，直接原样呈现，
  不再做 UTC→配置时区的 +8 换算。

历史 bug：旧实现把所有 naive 输入一律 `UTC.localize`，而真实 RSS 源
（如 foodmate）发布的裸日期 `2026-06-26 10:43:43` 是服务器本地（CST）墙钟，
并非 UTC → 显示被多加 8 小时，新鲜度过滤 / 天数计算同步偏 8 小时。

这三个函数是通知 / 分析器 / HTML 报告三条展示路径 + RSS 新鲜度过滤的
统一时区引擎，任何回归都会同时影响多条路径，故单独钉死。
"""

from trendradar.utils.time import (
    DEFAULT_TIMEZONE,
    format_iso_time_friendly,
    is_within_days,
    calculate_days_old,
)

SHANGHAI = "Asia/Shanghai"


# --- naive 输入（无偏移）→ 配置时区墙钟，原样呈现，不再 +8 ---


def test_naive_treated_as_configured_timezone_wallclock_with_date():
    # Arrange — naive 00:20 视作 Shanghai 墙钟，不应被换成 08:20
    iso = "2025-12-29T00:20:00"
    # Act
    out = format_iso_time_friendly(iso, SHANGHAI, include_date=True)
    # Assert
    assert out == "12-29 00:20"


def test_naive_treated_as_configured_timezone_wallclock_without_date():
    # Arrange
    iso = "2025-12-29T00:20:00"
    # Act
    out = format_iso_time_friendly(iso, SHANGHAI, include_date=False)
    # Assert
    assert out == "00:20"


def test_naive_foodmate_bare_wallclock_not_shifted():
    # Arrange — 模拟 foodmate 真实 pubDate（CST 墙钟，无偏移）经 parser 存为 naive ISO
    iso = "2026-06-26T10:43:43"
    # Act
    out = format_iso_time_friendly(iso, SHANGHAI, include_date=True)
    # Assert — 必须 10:43，旧实现会错误输出 18:43（+8 bug）
    assert out == "06-26 10:43"


# --- aware 输入（带偏移 / Z）→ 按源时区换算到配置时区 ---


def test_aware_explicit_offset_converts_correctly():
    # Arrange — UTC 00:20 -> Shanghai 08:20
    iso_aware = "2025-12-29T00:20:00+00:00"
    # Act
    out = format_iso_time_friendly(iso_aware, SHANGHAI, include_date=True)
    # Assert
    assert out == "12-29 08:20"


def test_aware_z_suffix_converts_correctly():
    # Arrange
    iso_z = "2025-12-29T00:20:00Z"
    # Act
    out = format_iso_time_friendly(iso_z, SHANGHAI, include_date=True)
    # Assert
    assert out == "12-29 08:20"


def test_aware_offset_date_rollover_when_offset_pushes_past_midnight():
    # Arrange — UTC 20:00 -> Shanghai 次日 04:00
    iso_aware = "2025-12-29T20:00:00+00:00"
    # Act
    out = format_iso_time_friendly(iso_aware, SHANGHAI, include_date=True)
    # Assert
    assert out == "12-30 04:00"


def test_aware_positive_offset_converts_correctly():
    # Arrange — +08:00 的 22:45 -> Shanghai 22:45（同墙钟，无偏移差）
    iso_aware = "2026-06-26T22:45:00+08:00"
    # Act
    out = format_iso_time_friendly(iso_aware, SHANGHAI, include_date=True)
    # Assert
    assert out == "06-26 22:45"


# --- 边界 / 容错 ---


def test_empty_string_returns_empty():
    # Act / Assert
    assert format_iso_time_friendly("", SHANGHAI) == ""


def test_unparseable_input_returns_simplified_fallback():
    # Arrange
    garbage = "not-a-real-time"
    # Act
    out = format_iso_time_friendly(garbage, SHANGHAI)
    # Assert — 容错分支原样回退，不抛异常
    assert out == garbage


def test_unknown_timezone_falls_back_to_default():
    # Arrange — naive 输入，未知时区 → 回退 DEFAULT_TIMEZONE=Shanghai 墙钟
    iso = "2025-12-29T00:20:00"
    # Act
    out = format_iso_time_friendly(iso, "Mars/Olympus_Mons")
    # Assert — naive 当墙钟原样输出；DEFAULT_TIMEZONE 仍是 Shanghai
    assert out == "12-29 00:20"
    assert DEFAULT_TIMEZONE == "Asia/Shanghai"


# --- is_within_days / calculate_days_old：naive 不再被当成 UTC ---


def test_is_within_days_naive_not_treated_as_utc():
    # Arrange — naive 输入等于 now 墙钟 → 差 0，必在 1 天内。
    #   旧实现把 naive 当 UTC → now_shanghai - utc_localize 会偏 +8h，
    #   极端情况下会把"刚刚发布"的文章误判为接近 8 小时前。
    from trendradar.utils.time import get_configured_time

    now_iso = get_configured_time(SHANGHAI).strftime("%Y-%m-%dT%H:%M:%S")
    # Act
    keep = is_within_days(now_iso, max_days=1, timezone=SHANGHAI)
    # Assert
    assert keep is True


def test_is_within_days_stale_naive_filtered_out():
    # Arrange — naive 墙钟比 now 早 10 天 → 应过滤
    from datetime import timedelta
    from trendradar.utils.time import get_configured_time

    old = (get_configured_time(SHANGHAI) - timedelta(days=10)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    # Act
    keep = is_within_days(old, max_days=3, timezone=SHANGHAI)
    # Assert
    assert keep is False


def test_calculate_days_old_naive_uses_configured_timezone():
    # Arrange — naive 墙钟等于 now → 距今 0 天
    from trendradar.utils.time import get_configured_time

    now_iso = get_configured_time(SHANGHAI).strftime("%Y-%m-%dT%H:%M:%S")
    # Act
    days = calculate_days_old(now_iso, timezone=SHANGHAI)
    # Assert — 容许小幅负值（执行耗时），但绝不应是 ~+0.33（旧 +8h bug 的指纹）
    assert days is not None
    assert abs(days) < 0.1
