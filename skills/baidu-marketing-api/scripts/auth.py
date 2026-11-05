"""OAuth 令牌生命周期：刷新、授权码换取、有效性保障。

百度令牌接口（全部 POST + JSON）：
  换令牌  https://u.baidu.com/oauth/accessToken
  刷新    https://u.baidu.com/oauth/refreshToken
  用户信息 https://u.baidu.com/oauth/getUserInfo

accessToken 有效期 24 小时，refreshToken 30 天。refreshToken 一旦过期只能重新授权。
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request

from config import Credential
from errors import CredentialError

OAUTH_BASE = "https://u.baidu.com/oauth"
TIMEOUT = 15


def _post(path, payload):
    url = f"{OAUTH_BASE}/{path}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json;charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise CredentialError(f"{path} HTTP {exc.code}，请核对授权参数或稍后重试") from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise CredentialError(f"{path} 网络失败：{exc}") from exc

    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise CredentialError(f"{path} 返回非 JSON，未披露响应内容") from exc

    if not isinstance(data, dict):
        raise CredentialError(f"{path} 返回的 JSON 顶层不是对象")
    if data.get("code") != 0:
        raise CredentialError(
            f"{path} 失败 code={data.get('code')} message={data.get('message')}"
        )
    payload = data.get("data") or {}
    if not isinstance(payload, dict):
        raise CredentialError(f"{path} 返回的 data 不是对象")
    return payload


def _apply(cred, data):
    if not isinstance(data, dict):
        raise CredentialError("OAuth 凭据响应必须是对象")
    now = time.time()
    cred.access_token = data.get("accessToken") or cred.access_token
    if data.get("refreshToken"):
        cred.refresh_token = data["refreshToken"]
    if data.get("openId"):
        cred.open_id = str(data["openId"])
    if data.get("userId"):
        cred.user_id = int(data["userId"])
    if data.get("expiresIn"):
        cred.expires_at = now + int(data["expiresIn"])
    if data.get("refreshExpiresIn"):
        cred.refresh_expires_at = now + int(data["refreshExpiresIn"])
    if isinstance(data.get("scope"), dict):
        cred.scope = data["scope"]
    return cred


def refresh(cred, persist=True):
    """用 refreshToken 换一对新令牌。"""
    if not cred.refresh_token:
        raise CredentialError("没有 refreshToken，无法刷新，需要重新走一次授权")
    if not (cred.app_id and cred.secret_key):
        raise CredentialError("缺少 app_id / secret_key，无法刷新令牌")
    if cred.refresh_expired():
        raise CredentialError("refreshToken 已过期（30 天），必须重新授权")

    data = _post(
        "refreshToken",
        {
            "appId": cred.app_id,
            "refreshToken": cred.refresh_token,
            "secretKey": cred.secret_key,
            "userId": int(cred.user_id or 0),
        },
    )
    _apply(cred, data)
    if persist:
        cred.save()
    return cred


def exchange(auth_code, app_id, secret_key, user_id, persist=True, user_name="", alias=""):
    """首次接入：用回调拿到的授权码换令牌。grantType 必须是 auth_code。"""
    data = _post(
        "accessToken",
        {
            "appId": app_id,
            "authCode": auth_code,
            "secretKey": secret_key,
            "grantType": "auth_code",
            "userId": int(user_id),
        },
    )
    cred = Credential(alias=alias, app_id=app_id, secret_key=secret_key, user_name=user_name)
    cred.user_id = int(user_id)
    _apply(cred, data)
    if persist:
        cred.save()
    return cred


def user_info(cred):
    """查账户信息，masterName 就是 API 调用要用的 userName。"""
    data = _post(
        "getUserInfo",
        {
            "openId": cred.open_id,
            "accessToken": cred.access_token,
            "userId": int(cred.user_id or 0),
            "needSubList": False,
        },
    )
    return data


def ensure_valid(cred, persist=True):
    """拿令牌前统一走这里：过期就自动刷新。"""
    if cred.access_token and not cred.access_expired():
        return cred
    if cred.refresh_token and not cred.refresh_expired():
        return refresh(cred, persist=persist)
    raise CredentialError(
        "accessToken 已过期且无法刷新（refreshToken 缺失或已过期），需要重新授权"
    )
