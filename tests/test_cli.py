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


# ---------- 写操作审批闸门（走真实 CLI，验证退出码与 JSON 契约） ----------


def seed_account(home, alias="demo"):
    accounts = home / "accounts"
    accounts.mkdir(parents=True, exist_ok=True)
    (accounts / f"{alias}.json").write_text(
        json.dumps(
            {
                "alias": alias,
                "user_name": "演示账户",
                "access_token": "tok",
                "expires_at": time.time() + 3600,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (home / "default").write_text(alias, encoding="utf-8")


def test_write_preview_returns_digest(tmp_dir):
    seed_account(tmp_dir)

    result = run_cli(
        ["write", "word-add", "--adgroup-id", "9", "--words", "月季", "--price", "2"],
        tmp_dir,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["dry_run"] is True
    assert len(data["approval"]["digest"]) == 16
    assert "keywordTypes" in data["payload"]["body"]


def test_write_preview_embeds_confirm_card(tmp_dir):
    seed_account(tmp_dir)

    result = run_cli(
        ["write", "word-add", "--adgroup-id", "9", "--words", "月季", "--price", "2"],
        tmp_dir,
    )

    card = json.loads(result.stdout)["approval"]["confirm_card"]
    assert card["type"] == "confirm"
    assert [f["label"] for f in card["fields"]] == ["账户", "动作", "条数", "回执"]
    assert [o["label"] for o in card["options"]] == ["确认执行", "取消"]


def test_write_execute_without_confirm_exits_4(tmp_dir):
    seed_account(tmp_dir)

    result = run_cli(
        ["write", "word-add", "--adgroup-id", "9", "--words", "月季", "--execute"],
        tmp_dir,
    )

    assert result.returncode == 4, "缺审批必须拒绝执行"
    data = json.loads(result.stdout)
    assert data["error"] == "需要用户审批"
    assert "--confirm" in data["how"]


def test_write_execute_with_bad_confirm_exits_4(tmp_dir):
    seed_account(tmp_dir)

    result = run_cli(
        [
            "write", "word-add", "--adgroup-id", "9", "--words", "月季",
            "--execute", "--confirm", "0000000000000000",
        ],
        tmp_dir,
    )

    assert result.returncode == 4


def test_write_execute_never_leaves_audit_when_refused(tmp_dir):
    seed_account(tmp_dir)

    run_cli(
        ["write", "word-add", "--adgroup-id", "9", "--words", "月季", "--execute"],
        tmp_dir,
    )

    audit_dir = tmp_dir / "audit"
    assert not audit_dir.exists() or not list(audit_dir.iterdir())


def test_call_write_method_is_gated(tmp_dir):
    """透传是最容易绕过审批的后门，必须同样拦住。"""
    seed_account(tmp_dir)

    result = run_cli(
        ["call", "--service", "KeywordService", "--method", "addWord",
         "--body", '{"keywordTypes":[]}'],
        tmp_dir,
    )

    assert result.returncode == 4
    assert json.loads(result.stdout)["error"] == "需要用户审批"


def test_call_read_method_not_gated(tmp_dir):
    seed_account(tmp_dir)

    result = run_cli(
        ["call", "--service", "AccountService", "--method", "getAccountInfo"], tmp_dir
    )

    assert result.returncode != 4, "读方法不该被审批拦住"


def test_call_write_preview_returns_digest(tmp_dir):
    seed_account(tmp_dir)

    result = run_cli(
        ["call", "--dry-run", "--service", "KeywordService", "--method", "addWord",
         "--body", '{"keywordTypes":[{"adgroupId":9,"word":"月季"}]}'],
        tmp_dir,
    )

    assert result.returncode == 0
    assert len(json.loads(result.stdout)["approval"]["digest"]) == 16

