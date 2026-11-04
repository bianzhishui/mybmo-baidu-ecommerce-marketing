"""元数据防漂移：版本号与文档口径只能有一个来源。

这几条不测业务，测的是「同一件事有没有被写了三份互相矛盾的说明」。
起因：Python 版本在四个文件里出现了 3.8 / 3.9 / 3.x 三种口径，
打包文件数在 README 里硬编码后立刻就和实际值对不上。
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_JSON = ROOT / ".codebuddy-plugin" / "plugin.json"


def _plugin_version():
    return json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))["version"]


def _pyproject_version():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml 里找不到 version"
    return match.group(1)


def _lock_version():
    text = (ROOT / "uv.lock").read_text(encoding="utf-8")
    match = re.search(
        r'name = "mybmo-baidu-ecommerce-marketing"\nversion = "([^"]+)"', text
    )
    return match.group(1) if match else None


def test_all_version_sources_agree():
    versions = {_plugin_version(), _pyproject_version(), _lock_version()}

    assert len(versions) == 1, f"版本源不一致：{versions}（uv.lock 记得跑 uv lock）"


def test_readme_badge_and_table_match_plugin_version():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    version = _plugin_version()

    assert f"badge/version-{version}-" in readme
    assert f"| 版本 | `{version}` |" in readme


def _markdown_files():
    files = list(ROOT.glob("*.md")) + list((ROOT / "agents").glob("*.md"))
    files += list((ROOT / "skills").rglob("*.md"))
    return sorted({p for p in files if "dist" not in p.parts})


def test_docs_do_not_promise_python_38():
    """口径统一到 3.9 之后，任何 md 都不该再写 3.8。"""
    offenders = []
    for path in _markdown_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "3.8" in line:
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}")

    assert offenders == [], "\n".join(offenders)


def test_readme_has_no_hardcoded_file_count():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert not re.search(r"\d+ 个文件", readme), "文件数会随打包变化，别写死"


def test_runtime_json_ships_with_the_package():
    """runtime.json 必须落在分发目录里，否则用户拆包看不到环境要求。"""
    assert (ROOT / "skills" / "baidu-marketing-api" / "runtime.json").is_file()
