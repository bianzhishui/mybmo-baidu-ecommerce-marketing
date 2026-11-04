"""凭据与账户管理：全部用 BM_HOME 重定向到临时目录，不碰真实账户。"""

import time

import pytest

from bmclient import config


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


def test_save_and_read_roundtrip(bm_home):
    cred = config.Credential(alias="wds02", user_name="某店铺", access_token="tok-1234567890abcdef")
    path = cred.save()

    assert path == bm_home / "accounts" / "wds02.json"
    assert path.stat().st_mode & 0o777 == 0o600, "凭据文件必须是 600"

    back = config.read_account("wds02")
    assert back is not None
    assert back.user_name == "某店铺"


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
