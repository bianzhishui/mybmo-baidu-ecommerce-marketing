"""凭据与账户管理：全部用 BM_HOME 重定向到临时目录，不碰真实账户。"""

import os
import time

import pytest

from bmclient import config
from bmclient.errors import CredentialError


@pytest.fixture
def bm_home(tmp_dir, monkeypatch):
    monkeypatch.setenv("BM_HOME", str(tmp_dir))
    return tmp_dir


def test_validate_alias_normalizes_case_and_space():
    assert config.validate_alias(" WDS02 ") == "wds02"
    assert config.validate_alias("acc-a_1") == "acc-a_1"


@pytest.mark.parametrize("bad", ["", "-x", "有中文", "A B", "a" * 33])
def test_validate_alias_rejects(bad):
    with pytest.raises(ValueError):
        config.validate_alias(bad)


@pytest.mark.skipif(os.name == "nt", reason="Windows 无 POSIX 权限位，chmod 只改只读标记")
def test_save_and_read_roundtrip(bm_home):
    cred = config.Credential(alias="wds02", user_name="某店铺", access_token="tok-1234567890abcdef")
    path = cred.save()

    assert path == bm_home / "accounts" / "wds02.json"
    assert path.stat().st_mode & 0o777 == 0o600, "凭据文件必须是 600"

    back = config.read_account("wds02")
    assert back is not None
    assert back.user_name == "某店铺"


def test_save_reports_locked_file(bm_home, monkeypatch):
    """Windows 上文件被占用时 os.replace 抛 PermissionError，不能裸崩。"""
    cred = config.Credential(alias="locked", user_name="某店铺")

    def locked_replace(src, dst):
        raise PermissionError(13, "被占用", str(dst))

    monkeypatch.setattr(os, "replace", locked_replace)

    with pytest.raises(CredentialError) as exc:
        cred.save()

    assert "被占用" in str(exc.value)
    assert not (bm_home / "accounts" / "locked.json").exists(), "不能留下半截凭据"
    assert not list((bm_home / "accounts").glob("*.json.tmp")), "临时文件必须清掉"


def test_list_accounts_puts_default_first(bm_home):
    config.Credential(alias="b1").save()
    config.Credential(alias="a1").save()
    config.set_default_alias("b1")

    rows = config.list_accounts()
    assert [r["alias"] for r in rows] == ["b1", "a1"]
    assert rows[0]["is_default"] is True
    assert rows[1]["is_default"] is False


def test_default_alias_ignores_missing_account(bm_home):
    (bm_home / "default").write_text("ghost", encoding="utf-8")
    assert config.default_alias() == ""


def test_delete_account_clears_default_marker(bm_home):
    config.Credential(alias="gone").save()
    config.set_default_alias("gone")

    config.delete_account("gone")

    assert not (bm_home / "accounts" / "gone.json").exists()
    assert not (bm_home / "default").exists()


def test_load_credential_without_any_account_raises(bm_home, monkeypatch):
    monkeypatch.delenv("BAIDU_ACCESS_TOKEN", raising=False)

    with pytest.raises(FileNotFoundError) as exc:
        config.load_credential()

    assert "还没有任何已授权账户" in str(exc.value)


def test_resolve_alias_priority(bm_home, monkeypatch):
    config.Credential(alias="dflt").save()
    config.set_default_alias("dflt")

    monkeypatch.setenv("BM_ACCOUNT", "envacc")
    assert config.resolve_alias("explicit") == "explicit"
    assert config.resolve_alias() == "envacc"

    monkeypatch.delenv("BM_ACCOUNT")
    assert config.resolve_alias() == "dflt"


def test_env_overrides_stored_credential(bm_home, monkeypatch):
    config.Credential(alias="wds02", user_name="旧名字", access_token="old").save()
    monkeypatch.setenv("BAIDU_ACCESS_TOKEN", "new-token")

    cred = config.load_credential("wds02")

    assert cred.access_token == "new-token"
    assert cred.user_name == "旧名字"


def test_access_expired_uses_skew():
    now = 1_000_000
    cred = config.Credential(
        access_token="t", expires_at=now + config.EXPIRY_SKEW + 1
    )
    assert cred.access_expired(now) is False

    cred.expires_at = now + config.EXPIRY_SKEW - 1
    assert cred.access_expired(now) is True


def test_is_usable_falls_back_to_refresh_token():
    now = time.time()
    cred = config.Credential(
        access_token="t",
        expires_at=now - 10,
        refresh_token="r",
        refresh_expires_at=now + 1000,
    )
    assert cred.is_usable() is True

    cred.refresh_token = ""
    assert cred.is_usable() is False


def test_public_dict_masks_tokens():
    cred = config.Credential(alias="a", access_token="0123456789abcdefxyz", refresh_token="short")

    view = cred.to_public_dict()

    assert view["access_token"] == "01234567...defxyz"
    assert view["refresh_token"] == "shor***"
    assert "0123456789abcdefxyz" not in str(view)


# ---------- 数据目录解析 ----------
#
# 技能要能被非 WorkBuddy 的 agent 加载，默认目录不再带平台品牌。
# 但老用户的凭据还在旧位置，不能让人升级后"账户凭空消失"。


def test_home_dir_prefers_env(monkeypatch, tmp_dir):
    monkeypatch.setenv("BM_HOME", str(tmp_dir / "custom"))

    assert config.home_dir() == tmp_dir / "custom"


def test_home_dir_uses_new_default_when_empty(monkeypatch, tmp_dir):
    monkeypatch.delenv("BM_HOME", raising=False)
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_dir / "new")
    monkeypatch.setattr(config, "LEGACY_HOME", tmp_dir / "legacy")

    assert config.home_dir() == tmp_dir / "new"


def test_home_dir_falls_back_to_legacy(monkeypatch, tmp_dir):
    """新目录没建过、旧目录有数据 → 沿用旧目录，否则老用户会以为凭据丢了。"""
    monkeypatch.delenv("BM_HOME", raising=False)
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_dir / "new")
    monkeypatch.setattr(config, "LEGACY_HOME", tmp_dir / "legacy")
    (tmp_dir / "legacy").mkdir()

    assert config.home_dir() == tmp_dir / "legacy"


def test_home_dir_keeps_new_default_when_both_exist(monkeypatch, tmp_dir):
    monkeypatch.delenv("BM_HOME", raising=False)
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_dir / "new")
    monkeypatch.setattr(config, "LEGACY_HOME", tmp_dir / "legacy")
    (tmp_dir / "new").mkdir()
    (tmp_dir / "legacy").mkdir()

    assert config.home_dir() == tmp_dir / "new"


def test_default_home_is_platform_neutral():
    """默认目录不能再带某个 agent 平台的品牌——技能要能被任意 agent 加载。"""
    assert ".workbuddy" not in str(config.DEFAULT_HOME)
    assert config.DEFAULT_HOME.name == ".baidu-marketing"
