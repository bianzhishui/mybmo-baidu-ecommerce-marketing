"""OAuth 一次性会话：让独立运行的 auth link / auth serve 安全共享 state。

会话和 state 都不是凭据，不存 SecretKey、token 或 authCode。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time

import config

SESSION_TTL = 900
STATE_MAX = 128
_BASE_RE = re.compile(r"^[A-Za-z0-9_-]{1,48}$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{22,64}$")


def _digest(nonce):
    return hashlib.sha256(nonce.encode("ascii")).hexdigest()


def sessions_dir():
    return config.home_dir() / "oauth-sessions"


def create(base, app_id, alias="", callback="", now=None):
    """创建一次性 nonce，返回完整 state。排他创建避免极小概率碰撞。"""
    if not _BASE_RE.fullmatch(base or ""):
        raise ValueError("state base 只允许 1-48 位字母、数字、下划线或连字符")
    if not app_id:
        raise ValueError("OAuth 会话缺少 app_id")
    directory = sessions_dir()
    directory.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        directory.chmod(0o700)
    nonce = secrets.token_urlsafe(24)
    state = f"{base}.v1.{alias or '_'}.{nonce}"
    if len(state) > STATE_MAX:
        raise ValueError("OAuth state 过长，请缩短账户 alias")
    key = _digest(nonce)
    now = time.time() if now is None else now
    record = {
        "version": 1, "base": base, "app_id": app_id, "alias": alias,
        "callback": callback, "nonce_hash": key,
        "created_at": now, "expires_at": now + SESSION_TTL,
    }
    path = directory / f"{key}.json"
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return create(base, app_id, alias, callback, now)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False)
    return state


def parse(state):
    """解析带版本的 state，不在这里信任其中的 alias。"""
    parts = (state or "").split(".")
    if len(parts) != 4 or parts[1] != "v1":
        raise ValueError("旧授权链接或 state 格式不受支持，请重新运行 auth link")
    base, _, alias, nonce = parts
    if not _BASE_RE.fullmatch(base) or not _NONCE_RE.fullmatch(nonce):
        raise ValueError("OAuth state 格式无效")
    if alias != "_":
        config.validate_alias(alias)
    return base, "" if alias == "_" else alias, nonce


def resolve(state, apps, now=None):
    """返回 (app, alias, session_key)；无效或过期 state 抛 ValueError。"""
    base, alias, nonce = parse(state)
    key = _digest(nonce)
    path = sessions_dir() / f"{key}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("OAuth 会话不存在或不可读，请重新生成授权链接") from exc
    if not isinstance(record, dict):
        raise ValueError("OAuth 会话格式无效")
    now = time.time() if now is None else now
    if now >= record.get("expires_at", 0):
        raise ValueError("OAuth 会话已过期，请重新生成授权链接")
    expected_alias = record.get("alias", "")
    if (record.get("base") != base or record.get("nonce_hash") != key
            or expected_alias != alias
            or not hmac.compare_digest(str(record.get("nonce_hash", "")), key)):
        raise ValueError("OAuth 会话与 state 不匹配")
    for app in apps or []:
        if app.get("base_state") == base and app.get("app_id") == record.get("app_id"):
            return app, expected_alias, key
    raise ValueError("OAuth 会话不属于当前回调服务")


def claim(session_key):
    """原子消费 nonce；成功后即使换令牌失败也不会再次开放。"""
    if not re.fullmatch(r"[0-9a-f]{64}", session_key or ""):
        return False
    claim_path = sessions_dir() / f"{session_key}.claimed"
    try:
        fd = os.open(str(claim_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError:
        return False
    os.close(fd)
    return True
