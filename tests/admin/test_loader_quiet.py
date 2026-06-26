# coding=utf-8
"""load_config(quiet=) / return_warnings 改造测试。

见 docs/online-config-design.md §4.2(1) 与 §5。loader 的 print 透传 quiet，
不用 redirect_stdout（后者会吞第三方库正常 stdout，且测试难断言）。
"""

from trendradar.core.loader import load_config


def test_load_config_quiet_suppresses_stdout(tmp_path, capsys, monkeypatch):
    """quiet=True 抑制 loader 全部 print（配置加载/timeline/通知来源）。"""
    # Arrange：最小 config，无 timeline.yaml、无通知渠道 → 触发多条 print
    (tmp_path / "config.yaml").write_text(
        "platforms:\n  enabled: true\n", encoding="utf-8"
    )
    monkeypatch.delenv("CONFIG_PATH", raising=False)

    # Act
    load_config(str(tmp_path / "config.yaml"), quiet=True)
    captured = capsys.readouterr()

    # Assert
    assert captured.out == ""


def test_load_config_default_keeps_stdout(tmp_path, capsys, monkeypatch):
    """quiet 默认 False 保持现行输出（回归，向后兼容）。"""
    # Arrange
    (tmp_path / "config.yaml").write_text(
        "platforms:\n  enabled: true\n", encoding="utf-8"
    )
    monkeypatch.delenv("CONFIG_PATH", raising=False)

    # Act
    load_config(str(tmp_path / "config.yaml"))
    captured = capsys.readouterr()

    # Assert
    assert "配置文件加载成功" in captured.out


def test_load_config_return_warnings_captures_silent_coercion(tmp_path, monkeypatch):
    """return_warnings=True 暴露静默强转（负 max_age_days 纠正为 3，收为非阻塞 warning）。"""
    # Arrange：rss freshness_filter.max_age_days 为负数 → 现行静默纠正为 3
    (tmp_path / "config.yaml").write_text(
        "rss:\n"
        "  enabled: false\n"
        "  freshness_filter:\n"
        "    max_age_days: -5\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("CONFIG_PATH", raising=False)

    # Act
    config, warnings = load_config(
        str(tmp_path / "config.yaml"), quiet=True, return_warnings=True
    )

    # Assert
    assert config["RSS"]["FRESHNESS_FILTER"]["MAX_AGE_DAYS"] == 3  # 被纠正
    assert len(warnings) >= 1
    assert any("max_age_days" in w for w in warnings)


def test_load_config_applies_storage_retention_env(tmp_path, monkeypatch):
    """STORAGE_RETENTION_DAYS env 在 loader 归一化层生效（reload 安全，不再依赖 __main__ mutate）。

    见 ADR-0004 §52：原就地 mutate 破坏不可变性且 reload 后丢失。
    """
    # Arrange
    (tmp_path / "config.yaml").write_text(
        "platforms:\n  enabled: true\n", encoding="utf-8"
    )
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.setenv("STORAGE_RETENTION_DAYS", "30")

    # Act
    config = load_config(str(tmp_path / "config.yaml"), quiet=True)

    # Assert
    assert config["STORAGE"]["RETENTION_DAYS"] == 30
