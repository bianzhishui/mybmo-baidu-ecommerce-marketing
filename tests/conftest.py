"""共享 fixture。

用 tempfile.mkdtemp 而不是 pytest 内置的 tmp_path：本机沙箱对
`pytest-of-*` 这类固定基目录的重复 mkdir 会抛 EEXIST，导致用例在
第二次运行时全部报错。mkdtemp 每次生成唯一目录，天然规避。
"""

import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir():
    path = Path(tempfile.mkdtemp(prefix="mybmo-test-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
