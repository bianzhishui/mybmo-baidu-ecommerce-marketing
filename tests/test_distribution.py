"""真实技能 ZIP：仓库外解压、无 uv、无凭据、禁网运行。"""

import importlib.util
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "baidu-marketing-api"


@pytest.fixture
def distribution(tmp_dir, monkeypatch):
    spec = importlib.util.spec_from_file_location("package_skill_distribution", ROOT / "tools" / "package_skill.py")
    package_skill = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package_skill)
    monkeypatch.setattr(package_skill, "run_official_validate", lambda path: True)
    archive, _ = package_skill.build(SKILL, tmp_dir / "dist", "test")
    target = tmp_dir / "仓库外 directory"
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(target)
    return target / "baidu-marketing-api", archive


def run_extracted(skill, tmp_dir, args):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("BAIDU_", "BM_"))}
    env.update({
        "BM_HOME": str(tmp_dir / "empty-home"),
        "PATH": str(tmp_dir / "empty-bin"),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    # 进程启动即禁止外部连接；保留 socket 类本身，避免破坏 SSL 初始化。
    script = (
        "import socket, runpy, sys\n"
        "socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('network disabled'))\n"
        "socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('network disabled'))\n"
        f"sys.argv = ['bmctl', *{args!r}]\n"
        f"runpy.run_path({str(skill / 'scripts' / 'bmctl.py')!r}, run_name='__main__')\n"
    )
    return subprocess.run(
        [sys.executable, "-I", "-B", "-c", script], cwd=tmp_dir,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, timeout=30,
    )


def test_real_zip_runs_outside_repository_without_uv_or_network(distribution, tmp_dir):
    skill, archive = distribution

    result = run_extracted(skill, tmp_dir, ["accounts", "list"])

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["total"] == 0
    assert not list(skill.rglob("__pycache__"))
    names = zipfile.ZipFile(archive).namelist()
    assert not any("oauth-sessions" in name or "/audit/" in name for name in names)


def test_real_zip_no_credential_query_fails_clearly(distribution, tmp_dir):
    skill, _ = distribution

    result = run_extracted(skill, tmp_dir, ["kr", "expand", "--seed", "月季"])

    assert result.returncode == 2
    assert "授权账户" in result.stdout
    assert "Traceback" not in result.stderr
