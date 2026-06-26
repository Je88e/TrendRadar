# coding=utf-8
"""atomic_write_with_backup 测试 — 校验→备份→原子写（设计 §4.1、§6 test_writer）。

ETag 失配抛 ETagMismatch（调用方映射 409）且不落盘；备份轮转保留近 5。
"""

import time

import pytest

from trendradar.admin.writer import ETagMismatch, atomic_write_with_backup, compute_etag


def test_atomic_write_writes_content(tmp_path):
    """ETag 匹配 → 原子写入新内容，读回一致（无半文件）。"""
    # Arrange
    f = tmp_path / "config.yaml"
    f.write_text("old\n", encoding="utf-8")
    etag = compute_etag(str(f))

    # Act
    atomic_write_with_backup(str(f), "new content\n", etag)

    # Assert
    assert f.read_text(encoding="utf-8") == "new content\n"


def test_etag_mismatch_raises_and_preserves_original(tmp_path):
    """ETag 失配 → 抛 ETagMismatch，原文件不变，不生成备份。"""
    # Arrange
    f = tmp_path / "config.yaml"
    f.write_text("original\n", encoding="utf-8")

    # Act / Assert
    with pytest.raises(ETagMismatch):
        atomic_write_with_backup(str(f), "clobber\n", etag="stale-etag")

    # 原文件未变
    assert f.read_text(encoding="utf-8") == "original\n"
    # 无备份产生
    backup_dir = tmp_path / ".backups"
    assert not backup_dir.exists() or list(backup_dir.glob("*")) == []


def test_backup_created_on_write(tmp_path):
    """成功写入 → 生成一份 .backups/<name>.<ts>.bak 备份。"""
    # Arrange
    f = tmp_path / "config.yaml"
    f.write_text("old\n", encoding="utf-8")
    etag = compute_etag(str(f))

    # Act
    atomic_write_with_backup(str(f), "new\n", etag)

    # Assert
    backups = list((tmp_path / ".backups").glob("config.yaml.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "old\n"


def test_backup_rotates_to_nearest_five(tmp_path):
    """连续写入 → 备份不超过 5 份（保留最近 5，旧的删除）。"""
    # Arrange
    f = tmp_path / "config.yaml"
    f.write_text("v0\n", encoding="utf-8")

    # Act：写 7 次（每次基于当前文件 ETag）
    for i in range(7):
        etag = compute_etag(str(f))
        atomic_write_with_backup(str(f), f"v{i + 1}\n", etag)
        time.sleep(0.002)  # 保证备份 ts 可区分

    # Assert
    backups = list((tmp_path / ".backups").glob("config.yaml.*.bak"))
    assert len(backups) == 5
