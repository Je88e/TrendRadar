# coding=utf-8
"""时间工具单元测试。

锁定 format_iso_time_friendly 行为：naive-UTC ISO → 配置时区墙钟时间。
该函数是通知 / 分析器 / HTML 报告三个展示路径的统一时区转换引擎，
任何回归都会同时影响三条路径，故单独钉死。
"""

from trendradar.utils.time import DEFAULT_TIMEZONE, format_iso_time_friendly

SHANGHAI = "Asia/Shanghai"


# --- naive-UTC 输入（parser._parse_date 主路径产物，无时区后缀） ---


def test_naive_utc_with_date_converts_to_configured_timezone():
    # Arrange
    iso_utc = "2025-12-29T00:20:00"  # UTC 00:20 -> Shanghai 08:20
    # Act
    out = format_iso_time_friendly(iso_utc, SHANGHAI, include_date=True)
    # Assert
    assert out == "12-29 08:20"


def test_naive_utc_without_date_returns_time_only():
    # Arrange
    iso_utc = "2025-12-29T00:20:00"
    # Act
    out = format_iso_time_friendly(iso_utc, SHANGHAI, include_date=False)
    # Assert
    assert out == "08:20"


def test_naive_utc_date_rollover_when_offset_pushes_past_midnight():
    # Arrange
    iso_utc = "2025-12-29T20:00:00"  # UTC 20:00 -> Shanghai 次日 04:00
    # Act
    out = format_iso_time_friendly(iso_utc, SHANGHAI, include_date=True)
    # Assert
    assert out == "12-30 04:00"


# --- aware 输入（parser._parse_date 回退路径 parsedate_to_datetime 产物） ---


def test_aware_explicit_offset_converts_correctly():
    # Arrange
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
    # Arrange
    iso_utc = "2025-12-29T00:20:00"
    # Act
    out = format_iso_time_friendly(iso_utc, "Mars/Olympus_Mons")
    # Assert — 回退到 DEFAULT_TIMEZONE（Asia/Shanghai）
    assert out == "12-29 08:20"
    assert DEFAULT_TIMEZONE == "Asia/Shanghai"
