# coding=utf-8
"""validators 单元测试 — 以 load_config 干跑为校验 oracle。

设计见 docs/online-config-design.md §5（校验细节）与 §6（测试计划）。
垂直切片：每个 test 固化一条可观察行为，按 RED→GREEN 推进。
"""

from trendradar.admin.validators import ValidationResult, validate_config_text


def test_valid_config_passes(real_config_dir):
    """合法 config.yaml 文本 → ok=True，无 errors。"""
    # Arrange：最小但合法的 config.yaml（load_config 各段均 .get 默认值）
    text = "report:\n  mode: daily\n"

    # Act
    result = validate_config_text("config.yaml", text, config_dir=str(real_config_dir))

    # Assert
    assert isinstance(result, ValidationResult)
    assert result.ok is True
    assert result.errors == []


def test_yaml_syntax_error_rejected(real_config_dir):
    """YAML 语法错误 → ok=False，errors 非空。"""
    # Arrange：未闭合的引号 → yaml.YAMLError
    text = 'report:\n  mode: "daily\n'

    # Act
    result = validate_config_text("config.yaml", text, config_dir=str(real_config_dir))

    # Assert
    assert result.ok is False
    assert len(result.errors) == 1


def test_loader_raises_rejected(real_config_dir):
    """YAML 合法但结构错误（loader 抛异常）→ ok=False。"""
    # Arrange：report 段为标量 → _load_report_config 调 .get 时 AttributeError
    text = "report: 5\n"

    # Act
    result = validate_config_text("config.yaml", text, config_dir=str(real_config_dir))

    # Assert
    assert result.ok is False
    assert len(result.errors) == 1


def test_silent_coerce_collected_as_warning(real_config_dir):
    """静默强转（负 max_age_days 纠正）→ ok=True 且 warnings 非空（非阻塞）。"""
    # Arrange
    text = "rss:\n  freshness_filter:\n    max_age_days: -5\n"

    # Act
    result = validate_config_text("config.yaml", text, config_dir=str(real_config_dir))

    # Assert
    assert result.ok is True
    assert result.errors == []
    assert len(result.warnings) >= 1
    assert any("max_age_days" in w for w in result.warnings)


# ── frequency_words.txt ──────────────────────────────────────────────
# load_frequency_words 解析极宽容（_parse_word 吞 re.error，仅 FileNotFoundError 会抛），
# 故 frequency 校验的拒绝路径用 oracle 抛异常的契约验证（与 config 段 loader-raises 同构）。


def test_valid_frequency_passes():
    """合法 frequency_words.txt → ok=True。"""
    # Arrange：一个普通词组
    text = "京东\n淘宝\n"

    # Act
    result = validate_config_text("frequency_words.txt", text)

    # Assert
    assert result.ok is True
    assert result.errors == []


def test_frequency_oracle_exception_rejected(monkeypatch):
    """load_frequency_words 抛异常（如文件缺失）→ ok=False。"""

    def boom(_path):
        raise FileNotFoundError("频率词文件不存在")

    monkeypatch.setattr(
        "trendradar.admin.validators.load_frequency_words", boom
    )

    # Act
    result = validate_config_text("frequency_words.txt", "京东\n")

    # Assert
    assert result.ok is False
    assert len(result.errors) == 1


# ── timeline.yaml ────────────────────────────────────────────────────
# 校验 = yaml.safe_load + Scheduler(preset="custom") 试构造，捕获 _validate_timeline
# 抛出的 ValueError（storage_backend 不参与构造期校验，传 None 即可）。


def test_valid_timeline_passes():
    """合法 timeline.yaml（仓库真文件内容）→ ok=True。"""
    # Arrange
    from pathlib import Path

    repo_timeline = Path(__file__).resolve().parents[2] / "config" / "timeline.yaml"
    text = repo_timeline.read_text(encoding="utf-8")

    # Act
    result = validate_config_text("timeline.yaml", text)

    # Assert
    assert result.ok is True
    assert result.errors == []


def test_invalid_timeline_rejected():
    """timeline 缺必须字段（空 custom）→ Scheduler 抛 ValueError → ok=False。"""
    # Arrange：custom 段缺 default/periods/day_plans/week_map
    text = "custom: {}\n"

    # Act
    result = validate_config_text("timeline.yaml", text)

    # Assert
    assert result.ok is False
    assert len(result.errors) == 1


def test_timeline_yaml_syntax_error_rejected():
    """timeline YAML 语法错 → ok=False。"""
    # Arrange
    text = 'custom: {[unterminated\n'

    # Act
    result = validate_config_text("timeline.yaml", text)

    # Assert
    assert result.ok is False
    assert len(result.errors) == 1
