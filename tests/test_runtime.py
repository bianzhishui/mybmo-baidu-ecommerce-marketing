"""运行时契约：门槛声明与入口守卫。

这里守的是「用户拿到包，环境不满足时能不能看懂发生了什么」。
裸 Traceback 对非开发者等于没有信息量，所以守卫本身也要有测试。
"""

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "baidu-marketing-api"
BMCTL = SKILL_DIR / "scripts" / "bmctl.py"
RUNTIME_JSON = SKILL_DIR / "runtime.json"


@pytest.fixture(scope="module")
def bmctl():
    spec = importlib.util.spec_from_file_location("bmctl_under_test", BMCTL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_json_matches_code(bmctl):
    data = json.loads(RUNTIME_JSON.read_text(encoding="utf-8"))

    assert data["runtime"]["python_min"] == list(bmctl.MIN_PYTHON)
    assert data["runtime"]["dependencies"] == [], "运行时必须是零依赖"
    assert set(data["runtime"]["platforms"]) == {"macos", "linux", "windows"}
    assert (SKILL_DIR / data["entrypoint"]).is_file()


def test_runtime_json_declares_interpreter_per_platform():
    data = json.loads(RUNTIME_JSON.read_text(encoding="utf-8"))
    interpreter = data["runtime"]["interpreter"]

    assert interpreter["macos"] == "python3"
    assert interpreter["linux"] == "python3"
    assert interpreter["windows"] == "py -3", "Windows 没有 python3.exe，必须给 py -3"


def test_guard_accepts_supported_version(bmctl):
    assert bmctl._check_python((3, 9, 0), out=io.StringIO(), err=io.StringIO()) == 0


def test_guard_rejects_old_version(bmctl):
    out, err = io.StringIO(), io.StringIO()

    code = bmctl._check_python((3, 8, 10), out=out, err=err)

    assert code == 6
    payload = json.loads(out.getvalue())
    assert payload["code"] == "PYTHON_VERSION"
    assert payload["required"] == "3.9+"
    assert payload["current"] == "3.8"
    assert payload["executable"]
    assert "环境" in err.getvalue()


def test_guard_stdout_is_pure_ascii(bmctl):
    """无论控制台是 cp936 还是被重定向到文件，都不能二次编码失败。"""
    out = io.StringIO()

    bmctl._check_python((3, 7, 0), out=out, err=io.StringIO())

    assert out.getvalue().isascii()


def test_guard_end_to_end_exits_6_without_traceback(tmp_dir):
    script = (
        "import runpy, sys\n"
        "sys.version_info = (3, 8, 10, 'final', 0)\n"
        f"runpy.run_path({str(BMCTL)!r}, run_name='__main__')\n"
    )

    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )

    assert proc.returncode == 6
    assert json.loads(proc.stdout)["code"] == "PYTHON_VERSION"
    assert "Traceback" not in proc.stderr


def test_guard_runs_before_bmclient_import():
    src = BMCTL.read_text(encoding="utf-8")

    assert src.index("_check_python()") < src.index("from bmclient import")


def test_no_future_annotations_import():
    """`from __future__ import annotations` 是 3.7 特性，在 3.6 上是编译期 SyntaxError，
    留着它就等于守卫永远执行不到。本文件没有类型注解，不许加回来。

    用 AST 判断而不是子串匹配——文件里的注释正解释着这件事，子串会误判。
    """
    import ast

    tree = ast.parse(BMCTL.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            names = {alias.name for alias in node.names}
            assert "annotations" not in names


def test_source_parses_under_python_36():
    import ast

    ast.parse(BMCTL.read_text(encoding="utf-8"), feature_version=(3, 6))
