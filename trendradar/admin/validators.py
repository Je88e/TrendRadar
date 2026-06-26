# coding=utf-8
"""
validators — 以 load_config 干跑为校验 oracle。

写 staging 路径（镜像 sibling）→ 调 load_config(quiet=True, return_warnings=True)
→ 收集异常为 errors、静默强转为 warnings → 清 staging。
设计见 docs/online-config-design.md §5（B1：staging 须镜像三文件，否则 oracle 失真）。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import yaml

from trendradar.core.frequency import load_frequency_words
from trendradar.core.loader import load_config
from trendradar.core.scheduler import Scheduler


@dataclass(frozen=True)
class ValidationResult:
    """校验结果：ok 为阻断性结论；errors 阻断、warnings 非阻塞。"""

    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _prepare_staging(name: str, text: str, config_dir: str) -> Path:
    """在 config_dir 下建唯一 staging 目录，写入目标文件 + 镜像 sibling。

    mkdtemp 保证并发隔离（race-free）；timeline.yaml / frequency_words.txt
    作为 sibling 拷入，使 load_config(staging) 能解析相对路径（B1）。
    """
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=str(config_dir)))
    (staging / name).write_text(text, encoding="utf-8")
    for sibling in ("timeline.yaml", "frequency_words.txt"):
        if sibling == name:
            continue
        src = Path(config_dir) / sibling
        if src.exists():
            shutil.copy2(src, staging / sibling)
    return staging


def _validate_main_config(text: str, config_dir: str) -> ValidationResult:
    """config.yaml 校验：staging 干跑 load_config 作 oracle。"""
    staging = _prepare_staging("config.yaml", text, config_dir)
    try:
        staging_path = staging / "config.yaml"
        _config, warnings = load_config(
            str(staging_path), quiet=True, return_warnings=True
        )
        return ValidationResult(ok=True, errors=[], warnings=list(warnings))
    except Exception as e:  # noqa: BLE001 — oracle 抛任意异常均收为校验错误
        return ValidationResult(ok=False, errors=[str(e)], warnings=[])
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _validate_frequency(text: str) -> ValidationResult:
    """frequency_words.txt 校验：单文件干跑 load_frequency_words（无 sibling 依赖）。"""
    # load_frequency_words 解析极宽容（吞 re.error），仅文件缺失/IO 错才抛；
    # 仍包 try/except 以把未来解析异常收为校验错误，且与 config 段契约一致。
    fd, tmp_path = tempfile.mkstemp(prefix=".freq-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        load_frequency_words(tmp_path)
        return ValidationResult(ok=True, errors=[], warnings=[])
    except Exception as e:  # noqa: BLE001
        return ValidationResult(ok=False, errors=[str(e)], warnings=[])
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _validate_timeline(text: str) -> ValidationResult:
    """timeline.yaml 校验：yaml.safe_load + Scheduler(preset=custom) 试构造。

    _validate_timeline 在 __init__ 期跑且不触 storage_backend（仅校结构），
    故传 None。preset=custom 取 timeline_data["custom"] 干跑用户编辑面。
    """
    try:
        data = yaml.safe_load(text) or {}
        Scheduler(
            schedule_config={"enabled": True, "preset": "custom"},
            timeline_data=data,
            storage_backend=None,
            get_time_func=datetime.now,
        )
        return ValidationResult(ok=True, errors=[], warnings=[])
    except Exception as e:  # noqa: BLE001
        return ValidationResult(ok=False, errors=[str(e)], warnings=[])


def validate_config_text(
    name: str, text: str, *, config_dir: Optional[str] = None
) -> ValidationResult:
    """按文件名分发校验。name ∈ {config.yaml, frequency_words.txt, timeline.yaml}。

    config_dir 仅 config.yaml 需要（staging 镜像 sibling）；frequency/timeline 无依赖。
    """
    if name == "config.yaml":
        if config_dir is None:
            raise ValueError("config.yaml 校验需要 config_dir（staging 镜像 sibling）")
        return _validate_main_config(text, config_dir)
    if name == "frequency_words.txt":
        return _validate_frequency(text)
    if name == "timeline.yaml":
        return _validate_timeline(text)
    raise ValueError(f"未知配置文件名: {name}")
