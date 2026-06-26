# coding=utf-8
"""ETag 测试 — ETag = 文件字节 sha256 十六进制（设计 §4.1、§6 test_etag）。

非 mtime：同秒不同内容写须产出不同 ETag（NTFS / WSL /mnt/d 粗粒度 mtime 碰撞漏检）。
"""

import hashlib

from trendradar.admin.writer import compute_etag


def test_etag_is_sha256_of_bytes(tmp_path):
    """ETag = sha256(文件字节) 的十六进制。"""
    # Arrange
    f = tmp_path / "config.yaml"
    f.write_bytes(b"hello world\n")

    # Act
    etag = compute_etag(str(f))

    # Assert
    assert etag == hashlib.sha256(b"hello world\n").hexdigest()


def test_different_content_yields_different_etag(tmp_path):
    """不同字节内容 → 不同 ETag（内容寻址，非 mtime）。"""
    # Arrange
    f = tmp_path / "config.yaml"
    f.write_text("version-1\n", encoding="utf-8")
    e1 = compute_etag(str(f))

    # Act：同秒覆盖不同内容
    f.write_text("version-2\n", encoding="utf-8")
    e2 = compute_etag(str(f))

    # Assert
    assert e1 != e2
