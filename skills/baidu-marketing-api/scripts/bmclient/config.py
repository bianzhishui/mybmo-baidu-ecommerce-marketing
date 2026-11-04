"""配置与凭据管理（多账户，独立运行）。

一个推广账户 = 一份凭据 = 一个 alias。目录布局：

    ~/.workbuddy/baidu-marketing/
    ├── accounts/
    │   ├── wds02.json        # alias=wds02 的完整凭据，权限 600
    │   └── axd.json
    └── default               # 纯文本，记录默认 alias

单个账户内的字段来源优先级（高 → 低）：
1. 环境变量（BAIDU_ACCESS_TOKEN / BAIDU_APP_ID / BAIDU_USER_NAME ...）
2. accounts/<alias>.json

环境变量是"临时覆盖"，适合 CI 或一次性调试；日常使用走 alias。
本模块不依赖任何外部项目的数据库，凭据完全自持。
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_HOME = Path.home() / ".workbuddy" / "baidu-marketing"
ACCOUNTS_DIRNAME = "accounts"
DEFAULT_ALIAS_FILE = "default"

# 提前 5 分钟视为过期，避免请求在路上失效
EXPIRY_SKEW = 300

_ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


@dataclass
class Credential:
    """一个推广账户的授权凭据。user_name 是账户中文名，不是数字 userId。"""

    alias: str = ""
    user_name: str = ""
    access_token: str = ""
    app_id: str = ""
    secret_key: str = ""
    user_id: int = 0
    open_id: str = ""
    refresh_token: str = ""
    expires_at: float = 0.0
    refresh_expires_at: float = 0.0
    scope: dict = field(default_factory=dict)
    note: str = ""

    def access_expired(self, now=None):
        now = now or time.time()
        if not self.expires_at:
            return False
        return now >= self.expires_at - EXPIRY_SKEW

    def refresh_expired(self, now=None):
        now = now or time.time()
        if not self.refresh_expires_at:
            return False
        return now >= self.refresh_expires_at

    def is_usable(self):
        """能立刻发请求：有令牌未过期，或能靠 refreshToken 续上。"""
        if self.access_token and not self.access_expired():
            return True
        return bool(self.refresh_token) and not self.refresh_expired()

    def to_public_dict(self):
        """给 CLI / Agent 看的视图，令牌只留首尾。"""
        return {
            "alias": self.alias,
            "user_name": self.user_name,
            "user_id": self.user_id,
            "app_id": self.app_id,
            "access_token": _mask(self.access_token),
            "refresh_token": _mask(self.refresh_token),
            "expires_at": _fmt_ts(self.expires_at),
            "refresh_expires_at": _fmt_ts(self.refresh_expires_at),
            "access_expired": self.access_expired(),
            "refresh_expired": self.refresh_expired(),
            "usable": self.is_usable(),
            "scope": self.scope,
            "note": self.note,
        }

    def save(self, path=None):
        target = Path(path) if path else account_path(self.alias or "default")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(_dumps(asdict(self)), encoding="utf-8")
        os.replace(tmp, target)  # 原子写，避免半截文件
        try:
            target.chmod(0o600)
        except OSError:
            pass
        return target


# ---------- 路径与 alias 管理 ----------


def home_dir():
    return Path(os.getenv("BM_HOME") or DEFAULT_HOME).expanduser()


def accounts_dir():
    return home_dir() / ACCOUNTS_DIRNAME


def account_path(alias):
    return accounts_dir() / f"{validate_alias(alias)}.json"


def validate_alias(alias):
    alias = (alias or "").strip().lower()
    if not _ALIAS_RE.match(alias):
        raise ValueError(
            f"alias 不合法：{alias!r}。只允许小写字母、数字、下划线、连字符，长度 1-32，"
            "且不能以符号开头（账户中文名请另存到 note 字段）"
        )
    return alias


def default_alias():
    """当前默认账户。没有设置或指向的账户已不存在时返回空串。"""
    marker = home_dir() / DEFAULT_ALIAS_FILE
    if not marker.exists():
        return ""
    value = marker.read_text(encoding="utf-8").strip()
    if value and account_path(value).exists():
        return value
    return ""


def set_default_alias(alias):
    alias = validate_alias(alias)
    if not account_path(alias).exists():
        raise ValueError(f"账户 {alias} 不存在，无法设为默认")
    target = home_dir() / DEFAULT_ALIAS_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(alias, encoding="utf-8")
    return alias


def list_accounts():
    """扫描 accounts/，返回账户摘要列表。"""
    items = []
    directory = accounts_dir()
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            cred = _read_json_credential(path)
            if cred is None:
                continue
            cred.alias = cred.alias or path.stem
            items.append(cred)

    current = default_alias()
    result = []
    for cred in items:
        row = cred.to_public_dict()
        row["is_default"] = cred.alias == current
        result.append(row)
    result.sort(key=lambda r: (not r["is_default"], r["alias"]))
    return result


def resolve_alias(explicit=None):
    """确定这次要用哪个账户：命令行 > 环境变量 > 默认账户。"""
    for candidate in (explicit, os.getenv("BM_ACCOUNT"), default_alias()):
        if candidate:
            return validate_alias(candidate)
    return ""


def delete_account(alias):
    alias = validate_alias(alias)
    path = account_path(alias)
    if not path.exists():
        raise ValueError(f"账户 {alias} 不存在")
    # 必须在 unlink 之前判断：删掉文件后 default_alias() 会因账户不存在而返回空串，
    # 导致默认指向永远不会被清理。
    was_default = default_alias() == alias
    path.unlink()
    if was_default:
        (home_dir() / DEFAULT_ALIAS_FILE).unlink(missing_ok=True)
    return path


def read_account(alias):
    """读取单个账户的凭据；不存在或损坏返回 None。"""
    path = account_path(alias)
    return _read_json_credential(path) if path.exists() else None


# ---------- 凭据加载 ----------


def load_credential(alias=None):
    """按 alias 加载一份凭据；未指定时用默认账户。

    完全没有账户时抛错，而不是返回空凭据——避免带着空令牌
    打出一串看不懂的认证失败。
    """
    resolved = resolve_alias(alias)

    if resolved:
        path = account_path(resolved)
        cred = _read_json_credential(path) if path.exists() else None
        if cred is None:
            raise FileNotFoundError(
                f"找不到账户 {resolved} 的凭据（{path}）。"
                "用 accounts list 查看已有账户，或用 auth exchange 接入新账户"
            )
        cred.alias = cred.alias or resolved
        return _merge_env(cred)

    if os.getenv("BAIDU_ACCESS_TOKEN"):
        # 纯环境变量模式：CI / 一次性调试，不落盘
        return _merge_env(Credential(alias="env"))

    raise FileNotFoundError(
        f"还没有任何已授权账户（{accounts_dir()}）。"
        "请先用 auth exchange 接入一个账户："
        "auth exchange --code <authCode> --app-id <AppID> --secret-key <SecretKey> "
        "--user-id <userId> --user-name <账户中文名> --alias <别名>"
    )


def _merge_env(cred):
    def pick(key, default=""):
        value = os.environ.get(key)
        return value if value not in (None, "") else default

    cred.user_name = pick("BAIDU_USER_NAME", cred.user_name)
    cred.access_token = pick("BAIDU_ACCESS_TOKEN", cred.access_token)
    cred.app_id = pick("BAIDU_APP_ID", cred.app_id)
    cred.secret_key = pick("BAIDU_SECRET_KEY", cred.secret_key)
    cred.open_id = pick("BAIDU_OPEN_ID", cred.open_id)
    cred.refresh_token = pick("BAIDU_REFRESH_TOKEN", cred.refresh_token)
    user_id = pick("BAIDU_USER_ID")
    if user_id:
        cred.user_id = int(user_id)
    expires_at = pick("BAIDU_EXPIRES_AT")
    if expires_at:
        cred.expires_at = float(expires_at)
    refresh_expires_at = pick("BAIDU_REFRESH_EXPIRES_AT")
    if refresh_expires_at:
        cred.refresh_expires_at = float(refresh_expires_at)
    return cred


def _read_json_credential(path):
    import json

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    known = {f for f in Credential.__dataclass_fields__}
    return Credential(**{k: v for k, v in data.items() if k in known})


def _dumps(data):
    import json

    return json.dumps(data, ensure_ascii=False, indent=2)


def _mask(value):
    if not value:
        return ""
    if len(value) <= 16:
        return value[:4] + "***"
    return value[:8] + "..." + value[-6:]


def _fmt_ts(ts):
    if not ts:
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
