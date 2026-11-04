"""skill 打包脚本：排除规则与 zip 内布局。

这里测的是「包里只有该有的东西」——官方 package_skill.py 用 rglob 全收，
我们另写了一份带排除规则的实现，得保证它真的排掉了。
"""

import importlib.util
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGER = ROOT / "tools" / "package_skill.py"


@pytest.fixture(scope="module")
def packager():
    spec = importlib.util.spec_from_file_location("package_skill_under_test", PACKAGER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_skill(base):
    """造一个最小可用 skill 目录，含故意混进来的垃圾文件。"""
    skill = base / "demo-skill"
    (skill / "scripts" / "__pycache__").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: 测试用\n---\n\n正文\n", encoding="utf-8"
    )
    (skill / "runtime.json").write_text("{}\n", encoding="utf-8")
    (skill / "scripts" / "bmctl.py").write_text("print(1)\n", encoding="utf-8")
    (skill / "scripts" / "__pycache__" / "bmctl.cpython-313.pyc").write_bytes(b"\x00\x01")
    (skill / "scripts" / "lib.so").write_bytes(b"\x00\x01")
    (skill / ".DS_Store").write_bytes(b"\x00\x01")
    return skill


def test_excludes_are_declared(packager):
    assert "__pycache__" in packager.EXCLUDED_DIRS
    assert ".venv" in packager.EXCLUDED_DIRS
    assert ".pyc" in packager.EXCLUDED_SUFFIXES
    assert ".so" in packager.EXCLUDED_SUFFIXES
    assert ".DS_Store" in packager.EXCLUDED_NAMES


def test_build_excludes_junk_and_keeps_prefix(packager, tmp_dir, monkeypatch):
    skill = _make_skill(tmp_dir)
    # 官方校验器需要 WorkBuddy 安装路径，测试里不依赖它
    monkeypatch.setattr(packager, "run_official_validate", lambda p: True)

    zip_path, files = packager.build(skill, tmp_dir / "dist", "1.0.0")

    assert zip_path.name == "demo-skill-1.0.0.zip", "文件名必须带版本"
    names = zipfile.ZipFile(zip_path).namelist()

    assert "demo-skill/SKILL.md" in names
    assert "demo-skill/scripts/bmctl.py" in names
    assert not [n for n in names if "__pycache__" in n or n.endswith((".pyc", ".so"))]
    assert ".DS_Store" not in " ".join(names)


def test_build_rejects_incomplete_skill(packager, tmp_dir):
    skill = tmp_dir / "broken-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: broken\n---\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        packager.build(skill, tmp_dir / "dist", "1.0.0")

    message = str(exc.value)
    assert "runtime.json" in message
    assert "scripts/bmctl.py" in message


def test_version_defaults_to_plugin_json(packager):
    expected = __import__("json").loads(
        (ROOT / ".codebuddy-plugin" / "plugin.json").read_text(encoding="utf-8")
    )["version"]

    assert packager.plugin_version() == expected


def test_package_stays_within_two_levels(packager):
    """开放平台上传校验：Skill 包只允许「根 / 二级目录 / 文件」。

    超限会被拒：「目录层级超限 — Skill 包仅支持两级目录结构」。
    用打包时的同一个过滤器检查，保证判的就是真正会进包的那批文件。
    """
    skill = ROOT / "skills" / "baidu-marketing-api"
    offenders = [str(rel) for _, rel in packager.iter_files(skill) if len(rel.parts) > 2]

    assert offenders == [], "以下文件超过两级目录：\n" + "\n".join(offenders)
