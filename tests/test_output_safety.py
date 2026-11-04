"""输出安全：Windows 控制台是 cp936，编码不了的字符会让程序崩在打印上。

两类防护各自有测试：
- 源码层面：可打印字符串（不含 docstring）必须都能用 cp936 编码
- 运行层面：_configure_stdio 把输出统一成 UTF-8，且遇到没有 reconfigure 的流不崩
"""

import ast
import importlib.util
import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "baidu-marketing-api" / "scripts"
BMCTL = SCRIPTS / "bmctl.py"


@pytest.fixture(scope="module")
def bmctl():
    spec = importlib.util.spec_from_file_location("bmctl_output_test", BMCTL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _docstring_node_ids(tree):
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def test_printable_strings_are_cp936_encodable():
    """docstring 不会被打印，允许出现 emoji；其余字符串必须能被 cp936 编码。"""
    offenders = []
    for path in sorted(SCRIPTS.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstring_node_ids(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if id(node) in skip:
                continue
            try:
                node.value.encode("cp936")
            except UnicodeEncodeError:
                rel = path.relative_to(ROOT)
                offenders.append(f"{rel}:{node.lineno} 无法用 cp936 编码")

    assert offenders == [], "\n".join(offenders)


def test_cli_uses_ascii_status_labels():
    src = BMCTL.read_text(encoding="utf-8")

    assert "✓" not in src
    assert "✗" not in src


def test_configure_stdio_tolerates_streams_without_reconfigure(bmctl, monkeypatch):
    """pytest 的 capsys 替换后的流没有 reconfigure，不能让整个进程炸掉。"""
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())

    bmctl._configure_stdio()


def test_configure_stdio_can_write_non_gbk_chars(bmctl, monkeypatch):
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp936", errors="strict", write_through=True)
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", io.StringIO())

    bmctl._configure_stdio()
    print("→ 测试箭头")
    stream.flush()

    assert "→ 测试箭头" in buffer.getvalue().decode("utf-8")
