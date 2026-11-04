"""运行时契约：PEP 723 内联元数据、入口守卫、runtime.json 手册。

这里守两件事：
1. 用户拿到包时，环境不满足要能看懂发生了什么（守卫不能抛裸 Traceback）
2. 「Python 下限 / 依赖」这两个事实只有一个真源，不许漂

真源约定：**bmctl.py 头部的 PEP 723 块是权威**（uv 真正执行的就是它），
`MIN_PYTHON` 常量是守卫用的副本，两者必须相等。
"""

import importlib.util
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # 3.9 / 3.10
    tomllib = None

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "baidu-marketing-api"
BMCTL = SKILL_DIR / "scripts" / "bmctl.py"
RUNTIME_JSON = SKILL_DIR / "runtime.json"
PYPROJECT = ROOT / "pyproject.toml"

needs_tomllib = pytest.mark.skipif(tomllib is None, reason="需要 3.11+ 的 tomllib")


@pytest.fixture(scope="module")
def bmctl():
    spec = importlib.util.spec_from_file_location("bmctl_under_test", BMCTL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------- PEP 723 块解析 ----------


def parse_script_block():
    """返回 (起始行号, 块内容文本)。找不到或不合法直接断言失败。"""
    lines = BMCTL.read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if line == "# /// script"]

    assert len(starts) == 1, f"`# /// script` 必须且只能出现一次，实际 {len(starts)} 次"
    start = starts[0]

    body = []
    for line in lines[start + 1:]:
        if line == "# ///":
            return start, "\n".join(body)
        assert line.startswith("#"), f"块内出现非注释行：{line!r}"
        body.append(line[2:] if line.startswith("# ") else line[1:])

    raise AssertionError("PEP 723 块缺少结束行 `# ///`")


@needs_tomllib
def test_pep723_block_parses():
    _, content = parse_script_block()
    data = tomllib.loads(content)

    assert "requires-python" in data
    assert "dependencies" in data, "dependencies 必须存在，即使为空"


def test_pep723_block_is_single_and_at_top():
    start, _ = parse_script_block()

    assert start <= 1, "块必须紧跟 shebang（否则某些工具只扫文件头会看不到）"


def test_pep723_block_precedes_docstring():
    """块是注释，docstring 仍是第一条语句——顺序放对就不会破坏 __doc__。"""
    import ast

    tree = ast.parse(BMCTL.read_text(encoding="utf-8"))
    assert ast.get_docstring(tree), "模块 docstring 不能丢"


@needs_tomllib
def test_requires_python_matches_guard_constant(bmctl):
    _, content = parse_script_block()
    declared = tomllib.loads(content)["requires-python"]

    assert declared == f">={bmctl.MIN_PYTHON[0]}.{bmctl.MIN_PYTHON[1]}"


@needs_tomllib
def test_requires_python_matches_pyproject():
    _, content = parse_script_block()
    block = tomllib.loads(content)["requires-python"]
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]

    assert block == project["requires-python"], "开发环境与运行时下限必须一致"


@needs_tomllib
def test_dependencies_are_exact_pins():
    """PEP 723 没有 lock，只能靠精确 pin 保证可复现。"""
    import re

    _, content = parse_script_block()
    for dep in tomllib.loads(content)["dependencies"]:
        assert re.fullmatch(r"[A-Za-z0-9._-]+==[0-9][^<>=~!*,\s]*", dep), (
            f"依赖必须精确 pin（如 openpyxl==3.1.5），当前：{dep!r}"
        )


@needs_tomllib
def test_runtime_deps_are_mirrored_to_dev_group():
    """脚本环境与项目 venv 是两套环境。

    运行时依赖只写在 PEP 块里，仓库 .venv 就没有它——一旦测试跑到相关代码路径
    就会 ModuleNotFoundError，出现「用户能跑、我们测不了」的倒挂。
    所以运行时依赖必须同时出现在 dev group 里。
    """

    def name_of(spec):
        return spec.split("==")[0].split(">=")[0].strip().lower()

    _, content = parse_script_block()
    runtime = {name_of(d) for d in tomllib.loads(content)["dependencies"]}

    dev = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["dependency-groups"]["dev"]
    dev_names = {name_of(d) for d in dev}

    assert runtime <= dev_names, f"缺在 dev group 里：{sorted(runtime - dev_names)}"


def test_no_third_party_toplevel_imports():
    """模块级 import 只允许标准库与 bmclient；第三方依赖必须惰性导入。

    这样在依赖没装的环境里，核心命令仍然可用，只有用到该功能的子命令才报错。
    """
    import ast

    stdlib = getattr(sys, "stdlib_module_names", None)
    if stdlib is None:
        pytest.skip("需要 3.10+ 的 sys.stdlib_module_names")

    allowed = set(stdlib) | {"bmclient"}
    offenders = []

    for path in [BMCTL, *sorted((SKILL_DIR / "scripts" / "bmclient").rglob("*.py"))]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root not in allowed:
                        offenders.append(f"{path.name}:{node.lineno} import {root}")
            elif isinstance(node, ast.ImportFrom):
                if node.level or not node.module:
                    continue
                root = node.module.split(".")[0]
                if root not in allowed:
                    offenders.append(f"{path.name}:{node.lineno} from {root}")

    assert offenders == [], "第三方导入请放进函数体内（惰性）：\n" + "\n".join(offenders)


# ---------- runtime.json（运行手册） ----------


def test_runtime_json_is_a_runbook_not_a_contract():
    data = json.loads(RUNTIME_JSON.read_text(encoding="utf-8"))

    assert (SKILL_DIR / data["entrypoint"]).is_file()
    assert data["runner"] == "uv run scripts/bmctl.py"
    assert set(data["platforms"]) == {"macos", "linux", "windows"}

    # 与 PEP 块重复的字段必须不存在，否则又变成多处声明
    for duplicated in ("python", "python_min", "dependencies"):
        assert duplicated not in data, f"{duplicated} 已由 PEP 723 块声明，不该重复"
        assert duplicated not in data.get("runtime", {})


def test_runtime_json_declares_interpreter_per_platform():
    data = json.loads(RUNTIME_JSON.read_text(encoding="utf-8"))
    interpreter = data["interpreter"]

    assert interpreter["macos"] == "python3"
    assert interpreter["linux"] == "python3"
    assert interpreter["windows"] == "py -3", "Windows 没有 python3.exe，必须给 py -3"
    assert data["interpreter_note"], "兜底解释器需要一句说明，避免被当成主路径"


def test_runtime_json_documents_uv_install():
    data = json.loads(RUNTIME_JSON.read_text(encoding="utf-8"))

    assert data["uv"]["check"] == "uv --version"
    install = data["uv"]["install"]
    assert set(install) == {"macos", "linux", "windows"}
    assert "astral.sh/uv" in install["macos"]
    assert "astral.sh/uv" in install["windows"]


def test_runtime_json_records_tested_versions():
    data = json.loads(RUNTIME_JSON.read_text(encoding="utf-8"))
    tested = data["python_tested"]

    assert tested, "应记录实测过的版本，避免声称支持却从未验证"
    assert tested[0].startswith("3.9"), "最低版本必须实测过"


# ---------- 入口守卫 ----------


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
    assert "uv run" in payload["hint"], "提示应引导改用 uv run，而不是让用户自己猜"
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


def test_argparse_help_has_no_bare_percent():
    """argparse 把 help 文案当 %-格式串处理。

    3.14 起在 add_argument 阶段就校验，裸 `%` 会抛 ValueError: incomplete format，
    整个 CLI 直接起不来——3.13 及以前不报错，所以这个坑只有跑过 3.14 才会发现。
    """
    import re

    src = BMCTL.read_text(encoding="utf-8")
    offenders = []
    for match in re.finditer(r'help=(?:"([^"]*)"|\'([^\']*)\')', src):
        text = match.group(1) or match.group(2) or ""
        if "%" in text.replace("%%", ""):
            lineno = src.count("\n", 0, match.start()) + 1
            offenders.append(f"bmctl.py:{lineno} help 文案含裸 %")

    assert offenders == [], "\n".join(offenders)


# ---------- 真实执行路径 ----------


@pytest.mark.skipif(shutil.which("uv") is None, reason="本机没有 uv")
def test_uv_run_smoke(tmp_dir):
    """唯一一条真的走 uv 的测试：验证内联元数据被识别、任意 cwd 都能跑。"""
    proc = subprocess.run(
        ["uv", "run", str(BMCTL), "--help"],
        cwd=tmp_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )

    assert proc.returncode == 0, proc.stderr
    assert "accounts" in proc.stdout
