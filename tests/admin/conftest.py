# coding=utf-8
"""tests/admin 共享 fixtures。

校验 config.yaml 需 staging 镜像真实 timeline.yaml + frequency_words.txt
（设计 §5 B1：否则 load_config(staging) 解析不到 sibling → oracle 失真），
故提供 real_config_dir fixture 把仓库 config/ 下的两个 sibling 拷进临时目录。
"""

import shutil
from pathlib import Path

import pytest

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture()
def real_config_dir(tmp_path: Path) -> Path:
    """临时 config_dir，含真实 timeline.yaml + frequency_words.txt 作为 sibling。

    被校验的 config.yaml 文本由测试自行写入；本 fixture 只提供 sibling 镜像源。
    """
    for sibling in ("timeline.yaml", "frequency_words.txt"):
        src = REPO_CONFIG / sibling
        if src.exists():
            shutil.copy2(src, tmp_path / sibling)
    return tmp_path


@pytest.fixture()
def config_dir_with_files(tmp_path: Path) -> Path:
    """临时 config_dir，三份真实配置文件齐备（PUT 端到端测试用）。

    与 real_config_dir 区别：本 fixture 额外拷入 config.yaml，使 PUT 既有合法
    起始文件（可取 If-Match ETag），又能在 staging 校验时镜像三 sibling。
    """
    for name in ("config.yaml", "timeline.yaml", "frequency_words.txt"):
        src = REPO_CONFIG / name
        if src.exists():
            shutil.copy2(src, tmp_path / name)
    return tmp_path
