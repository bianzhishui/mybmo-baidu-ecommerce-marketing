"""OAuth 传输与刷新边界：不访问真实 OAuth 服务。"""

import socket

import pytest

import auth
from errors import CredentialError


def test_oauth_timeout_is_credential_error(monkeypatch):
    def timeout(*args, **kwargs):
        raise socket.timeout("offline")

    monkeypatch.setattr(auth.urllib.request, "urlopen", timeout)
    with pytest.raises(CredentialError, match="网络失败"):
        auth._post("refreshToken", {})


def test_oauth_non_object_response_is_handled(monkeypatch):
    monkeypatch.setattr(auth, "_post", lambda path, payload: [])
    # _post 自身的 schema 校验由原始响应入口测试；这里验证凭据不会接受异常结构。
    with pytest.raises(CredentialError):
        auth.refresh(auth.Credential(
            refresh_token="r", app_id="a", secret_key="s"
        ))


def test_http_error_does_not_echo_response_secrets(monkeypatch):
    import io
    import urllib.error

    def rejected(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://u.baidu.com/oauth", 400, "bad", {},
            io.BytesIO(b'{"secretKey":"do-not-echo","authCode":"do-not-echo"}'),
        )

    monkeypatch.setattr(auth.urllib.request, "urlopen", rejected)
    with pytest.raises(CredentialError) as exc:
        auth._post("accessToken", {})
    assert "do-not-echo" not in str(exc.value)
