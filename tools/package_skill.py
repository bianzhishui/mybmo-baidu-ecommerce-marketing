#!/usr/bin/env python3
"""把单个 skill 目录打成可分发的 zip。

为什么不用官方 `skill-creator/scripts/package_skill.py`：
它用 `rglob('*')` 全收，只要跑过一次脚本，`scripts/__pycache__/` 就会跟着进包。
本脚本按排除规则过滤，包内只有该有的东西。

用法：
    python3 tools/package_skill.py <skill-dir> <out-dir> --version 1.9.2
    python3 tools/package_skill.py <skill-dir> <out-dir>          # 版本从 plugin.json 读

输出：<out-dir>/<skill 目录名>-<version>.zip，zip 内顶层目录为 <skill 目录名>。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_JSON = ROOT / ".codebuddy-plugin" / "plugin.json"

DEFAULT_SKILL_CREATOR = (
    "/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked"
    "/resources/plugins/workbuddy-builtin/skills/skill-creator/scripts"
)

# 目录名精确匹配
EXCLUDED_DIRS = {"__pycache__", ".venv", ".pytest_cache", ".ruff_cache", ".git", "node_modules"}
# 后缀匹配
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".so", ".pyd", ".dylib", ".py.lock"}
# 文件名精确匹配
EXCLUDED_NAMES = {".DS_Store", "Thumbs.db", ".gitkeep"}


def plugin_version():
    data = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
    return str(data["version"])


def iter_files(skill_dir):
    """产出 (绝对路径, zip 内相对路径)。顺序稳定，便于复现。"""
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(skill_dir)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if path.suffix in EXCLUDED_SUFFIXES:
            continue
        if path.name in EXCLUDED_NAMES:
            continue
        yield path, rel


def check_layout(skill_dir):
    """本项目的硬检查：缺了这些，包就算能解压也不能用。"""
    missing = []
    for rel in ("SKILL.md", "runtime.json", "scripts/bmctl.py"):
        if not (skill_dir / rel).is_file():
            missing.append(rel)
    return missing


def run_official_validate(skill_dir):
    """调官方 quick_validate.py；找不到就跳过（不阻断）。"""
    creator = Path(__import__("os").environ.get("SKILL_CREATOR_DIR", DEFAULT_SKILL_CREATOR))
    script = creator / "quick_validate.py"
    if not script.is_file():
        print(f"  [提示] 未找到官方校验器（{script}），跳过 frontmatter 校验")
        return True

    proc = subprocess.run(
        [sys.executable, str(script), str(skill_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        print(proc.stdout.strip())
        print(proc.stderr.strip())
    return proc.returncode == 0


def build(skill_dir, out_dir, version):
    skill_dir = skill_dir.resolve()
    if not skill_dir.is_dir():
        raise SystemExit(f"[失败] 目录不存在：{skill_dir}")

    name = skill_dir.name
    missing = check_layout(skill_dir)
    if missing:
        raise SystemExit(f"[失败] skill 目录缺少必需文件：{', '.join(missing)}")

    if not run_official_validate(skill_dir):
        raise SystemExit("[失败] 官方 frontmatter 校验未通过")

    files = list(iter_files(skill_dir))
    if not files:
        raise SystemExit("[失败] 没收集到任何文件")

    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{name}-{version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, rel in files:
            zf.write(path, str(Path(name) / rel))

    return zip_path, files


def main(argv=None):
    parser = argparse.ArgumentParser(description="打包单个 skill 为 zip")
    parser.add_argument("skill_dir", help="skill 目录，例如 skills/baidu-marketing-api")
    parser.add_argument("out_dir", help="输出目录，例如 dist")
    parser.add_argument("--version", default=None, help="版本号；缺省从 plugin.json 读")
    args = parser.parse_args(argv)

    version = args.version or plugin_version()
    zip_path, files = build(Path(args.skill_dir), Path(args.out_dir), version)
    size_kb = zip_path.stat().st_size / 1024
    print(f"[成功] {zip_path}（{len(files)} 个文件，{size_kb:.1f} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
