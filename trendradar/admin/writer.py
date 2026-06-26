# coding=utf-8
"""
writer — 整文件原样写入：ETag 校验 + 备份 + 原子替换。

ETag = 文件字节 sha256 十六进制（非 mtime——同秒重写在 NTFS / WSL /mnt/d
粗粒度 mtime 下碰撞漏检，设计 §4.1）。If-Match 失配抛 ETagMismatch（调用方
映射 409）。备份到 <config_dir>/.backups/<name>.<ts>.bak，轮转保留近 5。
tempfile + os.replace 原子替换（同目录同文件系统保证原子性）。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import time
from pathlib import Path

KEEP_BACKUPS = 5


class ETagMismatch(Exception):
    """If-Match ETag 与当前文件不匹配（配置已被他人修改）。"""


def compute_etag(path: str) -> str:
    """返回文件字节的 sha256 十六进制（ETag / If-Match 用）。"""
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rotate_backups(backup_dir: Path, name: str, keep: int = KEEP_BACKUPS) -> None:
    """保留最近 keep 份 <name>.<ts>.bak，删除更旧的。按 ts 数值倒序。"""
    prefix = f"{name}."
    suffix = ".bak"

    def ts_of(p: Path) -> int:
        stem = p.name
        if stem.startswith(prefix) and stem.endswith(suffix):
            mid = stem[len(prefix) : len(stem) - len(suffix)]
            try:
                return int(mid)
            except ValueError:
                return 0
        return 0

    backups = sorted(backup_dir.glob(f"{prefix}*{suffix}"), key=ts_of, reverse=True)
    for old in backups[keep:]:
        old.unlink(missing_ok=True)


def atomic_write_with_backup(path: str, text: str, etag: str) -> None:
    """ETag 校验通过后：备份（轮转近 5）→ tempfile + os.replace 原子写入。

    Raises:
        ETagMismatch: etag 与当前文件 compute_etag 不一致（配置已被他人修改）。
    """
    target = Path(path)

    # 1. If-Match 校验（失配不落盘、不备份）
    if etag != compute_etag(path):
        raise ETagMismatch(
            f"ETag 失配: 文件 {target.name} 已被修改，请重新加载后再保存"
        )

    # 2. 备份原文件 + 轮转
    backup_dir = target.parent / ".backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = time.time_ns()
    bak = backup_dir / f"{target.name}.{ts}.bak"
    shutil.copy2(target, bak)
    _rotate_backups(backup_dir, target.name)

    # 3. 原子写入：tempfile 同目录 + os.replace
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_name, target)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise
