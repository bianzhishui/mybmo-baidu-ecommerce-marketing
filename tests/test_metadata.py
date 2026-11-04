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


def test_skill_frontmatter_version_matches_plugin():
    """skill 单独分发时，SKILL.md 是唯一能标明版本的地方。

    官方 24 个自带 skill 里有 8 个写了 version，虽非必需，但不写就没法追溯。
    写了两处就必须一致，否则包内版本和产品版本会各说各话。
    """
    skill = (ROOT / "skills" / "baidu-marketing-api" / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"?([0-9][0-9.]*)"?\s*$', skill, re.MULTILINE)

    assert match, "SKILL.md frontmatter 缺少 version"
    assert match.group(1) == _plugin_version()


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


# ---------- 执行方式口径（uv run） ----------


FORBIDDEN_RUNNERS = (
    "python3 scripts/bmctl.py",
    "python3 <skill>/scripts/bmctl.py",
    "py -3 scripts",
    "py -3 <skill>",
)


def test_docs_only_use_uv_run():
    """命令半改不改最危险：同一会话混用 `python3` 与 `uv run` 会走不同解释器。"""
    offenders = []
    for path in _markdown_files():
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_RUNNERS:
            if token in text:
                offenders.append(f"{path.relative_to(ROOT)}: 仍出现 {token!r}")
        if "scripts/bmctl.py" in text and "uv run" not in text:
            offenders.append(f"{path.relative_to(ROOT)}: 提到 bmctl.py 却没有 uv run")

    assert offenders == [], "\n".join(offenders)


def test_skill_and_agent_document_uv_install():
    skill = (ROOT / "skills" / "baidu-marketing-api" / "SKILL.md").read_text(encoding="utf-8")
    agent = (ROOT / "agents" / "MyBMO.md").read_text(encoding="utf-8")

    assert "uv --version" in skill
    assert "astral.sh/uv" in skill, "必须给出官方安装地址，不能让用户自己搜"
    assert "uv run" in agent
    assert "astral.sh/uv" in agent


# ---------- 打包规则 ----------


def _rsync_block():
    """只取 rsync 命令行本身——注释里也提到 --include，全文搜索会误判。"""
    script = (ROOT / "tools" / "build-zip.sh").read_text(encoding="utf-8")
    start = script.index("rsync -a")
    end = script.index('"$ROOT/" "$TARGET/"', start)
    return script[start:end]


def test_build_zip_excludes_precede_includes():
    """rsync 首条匹配即定：exclude 放到第一个 --include 之后会全部失效。"""
    block = _rsync_block()
    first_include = block.index("--include")

    for token in ("'__pycache__/'", "'.venv/'", "'*.so'", "'*.pyd'", "'*.pyc'"):
        assert block.index(token) < first_include, f"{token} 必须在第一个 --include 之前"


def test_build_zip_ends_with_exclude_all():
    """白名单的最后一条必须是 --exclude '*'，且只能有一条。"""
    block = _rsync_block()

    assert block.count("--exclude '*'") == 1
    assert block.index("--exclude '*'") > block.index("--include '/README.md'")


# ---------- 依赖表述 ----------


ABSOLUTE_CLAIMS = ("零依赖", "零第三方依赖", "纯标准库", "不依赖任何外部库")


def test_no_absolute_dependency_claims():
    """这些说法加库当天就会变假。

    要表达「没依赖」，写「依赖声明在脚本头部」；要表达「用户不用装」，
    写「不需要 pip install」——这两句永远成立，不会随依赖增减失效。
    """
    targets = (
        _markdown_files()
        + sorted((ROOT / "skills").rglob("*.py"))
        + sorted((ROOT / "agents").rglob("*.md"))
    )

    offenders = []
    for path in targets:
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            for phrase in ABSOLUTE_CLAIMS:
                if phrase in line:
                    offenders.append(f"{path.relative_to(ROOT)}:{lineno} 含「{phrase}」")

    assert offenders == [], "\n".join(offenders)
