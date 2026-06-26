# coding=utf-8
"""staging 镜像 + 隔离测试（设计 §5 B1、§6 test_staging_mirror）。

校验 config.yaml 须把 timeline.yaml + frequency_words.txt 镜像进 staging，
否则 load_config(staging) 解析不到 sibling → oracle 失真。用完即删，并发隔离。
"""

import shutil
import threading
from pathlib import Path

from trendradar.admin.validators import _prepare_staging, validate_config_text


def test_staging_cleaned_after_success(real_config_dir):
    """校验成功后 staging 目录不留痕。"""
    # Arrange
    text = "report:\n  mode: daily\n"

    # Act
    validate_config_text("config.yaml", text, config_dir=str(real_config_dir))

    # Assert
    remain = list(real_config_dir.glob(".staging-*"))
    assert remain == [], f"staging 未清理: {remain}"


def test_staging_cleaned_after_failure(real_config_dir):
    """校验失败（语法错）后 staging 目录同样不留痕（finally 兜底）。"""
    # Arrange
    text = 'report:\n  mode: "unterminated\n'

    # Act
    validate_config_text("config.yaml", text, config_dir=str(real_config_dir))

    # Assert
    remain = list(real_config_dir.glob(".staging-*"))
    assert remain == []


def test_staging_mirrors_three_files(real_config_dir):
    """_prepare_staging 镜像三文件：config.yaml(目标) + timeline.yaml + frequency_words.txt。"""
    # Arrange
    text = "report:\n  mode: daily\n"

    # Act
    staging = _prepare_staging("config.yaml", text, str(real_config_dir))

    # Assert
    try:
        assert (staging / "config.yaml").exists()
        assert (staging / "timeline.yaml").exists()
        assert (staging / "frequency_words.txt").exists()
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def test_concurrent_validations_use_isolated_staging(real_config_dir):
    """并发两次校验互不踩踏：各自 ok，且 _prepare_staging 产出独立目录。"""
    # Arrange：mkdtemp race-free，同线程两次调用亦应产出不同目录
    s1 = _prepare_staging("config.yaml", "a: 1\n", str(real_config_dir))
    s2 = _prepare_staging("config.yaml", "a: 2\n", str(real_config_dir))
    try:
        assert s1 != s2
    finally:
        shutil.rmtree(s1, ignore_errors=True)
        shutil.rmtree(s2, ignore_errors=True)

    # Act：并发跑完整校验路径
    results: list = []
    errors: list = []

    def run():
        try:
            r = validate_config_text(
                "config.yaml", "report:\n  mode: daily\n", config_dir=str(real_config_dir)
            )
            results.append(r)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    # Assert
    assert errors == [], f"并发校验抛错: {errors}"
    assert len(results) == 4
    assert all(r.ok for r in results)
    remain = list(real_config_dir.glob(".staging-*"))
    assert remain == []
