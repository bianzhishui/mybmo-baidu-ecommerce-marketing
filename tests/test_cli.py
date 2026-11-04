"""CLI 冒烟：验证 sys.path 注入可用、JSON 契约稳定，全程不联网、不碰真实账户。"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

BMCTL = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "baidu-marketing-api"
    / "scripts"
    / "bmctl.py"
)


def run_cli(args, home, **extra_env):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BAIDU_", "BM_"))}
    env.update({"BM_HOME": str(home), **extra_env})
    return subprocess.run(
        [sys.executable, str(BMCTL), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_help_lists_subcommands(tmp_dir):
    result = run_cli(["--help"], tmp_dir)

    assert result.returncode == 0
    assert "accounts" in result.stdout
    assert "kr" in result.stdout


def test_accounts_list_empty(tmp_dir):
    result = run_cli(["accounts", "list"], tmp_dir)

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["total"] == 0


def test_accounts_list_after_credential_written(tmp_dir):
    accounts = tmp_dir / "accounts"
    accounts.mkdir()
    (accounts / "demo.json").write_text(
        json.dumps(
            {
                "alias": "demo",
                "user_name": "演示账户",
                "access_token": "tok",
                "expires_at": time.time() + 3600,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_cli(["accounts", "list"], tmp_dir)

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["total"] == 1
    assert data["accounts"][0]["alias"] == "demo"
    assert data["accounts"][0]["usable"] is True
    assert data["accounts"][0]["access_token"] == "tok***", "令牌必须脱敏"


def test_accounts_use_unknown_account_fails(tmp_dir):
    result = run_cli(["accounts", "use", "ghost"], tmp_dir)

    assert result.returncode != 0
