"""一次性 OAuth 会话：跨实例、过期和原子消费。"""

import oauth_sessions
import pytest

import oauthserver


def app():
    return {"app_id": "app", "base_state": oauthserver.default_state("app", "dev")}


def test_state_resolves_across_store_instances(tmp_dir):
    state = oauth_sessions.create(app()["base_state"], "app", alias="shop")

    resolved_app, alias, key = oauth_sessions.resolve(state, [app()])

    assert resolved_app["app_id"] == "app"
    assert alias == "shop"
    assert oauth_sessions.claim(key) is True
    assert oauth_sessions.claim(key) is False


def test_old_state_is_rejected(tmp_dir):
    with pytest.raises(ValueError):
        oauth_sessions.resolve(f"{app()['base_state']}.shop", [app()])


def test_expired_session_is_rejected(tmp_dir):
    state = oauth_sessions.create(app()["base_state"], "app", alias="shop")
    with pytest.raises(ValueError, match="过期"):
        oauth_sessions.resolve(state, [app()], now=10**12)


def test_session_files_do_not_contain_credentials(tmp_dir):
    state = oauth_sessions.create(app()["base_state"], "app", alias="shop")
    oauth_sessions.resolve(state, [app()])
    text = "\n".join(p.read_text(encoding="utf-8") for p in tmp_dir.rglob("*.json"))

    assert "secret" not in text.lower()
    assert "token" not in text.lower()
    assert "authCode" not in text
    assert state not in text, "只保存 nonce 摘要，不保存可直接重放的完整 state"


def test_tampered_alias_is_rejected(tmp_dir):
    state = oauth_sessions.create(app()["base_state"], "app", alias="shop")
    base, version, _, nonce = state.split(".")

    with pytest.raises(ValueError):
        oauth_sessions.resolve(f"{base}.{version}.other.{nonce}", [app()])
