"""配置与凭据管理（多账户，独立运行）。

一个推广账户 = 一份凭据 = 一个 alias。目录布局：

    ~/.baidu-marketing/
    ├── accounts/
    │   ├── wds02.json        # alias=wds02 的完整凭据，权限 600
    │   └── axd.json
    └── default               # 纯文本，记录默认 alias

目录位置解析顺序（高 → 低）：
1. 环境变量 `BM_HOME`（显式指定，最高优先级）
2. `~/.baidu-marketing`（默认）

本模块不依赖任何特定 agent 平台，也不依赖外部项目的数据库，凭据完全自持。

单个账户内的字段来源优先级（高 → 低）：
1. 环境变量（BAIDU_ACCESS_TOKEN / BAIDU_APP_ID / BAIDU_USER_NAME ...）
2. accounts/<alias>.json

环境变量是"临时覆盖"，适合 CI 或一次性调试；日常使用走 alias。
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from errors import CredentialError

DEFAULT_HOME = Path.home() / ".baidu-marketing"
ACCOUNTS_DIRNAME = "accounts"
DEFAULT_ALIAS_FILE = "default"

# 提前 5 分钟视为过期，避免请求在路上失效
EXPIRY_SKEW = 300

_ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
STORED_FIELDS = {
    "alias", "user_name", "access_token", "app_id", "secret_key", "user_id",
    "open_id", "refresh_token", "expires_at", "refresh_expires_at", "scope", "note",
}
ENV_CREDENTIAL_KEYS = (
    "BAIDU_USER_NAME", "BAIDU_ACCESS_TOKEN", "BAIDU_APP_ID", "BAIDU_SECRET_KEY",
    "BAIDU_OPEN_ID", "BAIDU_REFRESH_TOKEN", "BAIDU_USER_ID", "BAIDU_EXPIRES_AT",
    "BAIDU_REFRESH_EXPIRES_AT",
)


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
    # 运行期元数据，不序列化：决定凭据能否写回以及写回哪个账户。
    source: str = "file"
    persist_allowed: bool = True
    env_overrides: list = field(default_factory=list)

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
        if not self.persist_allowed:
            raise CredentialError(
                "环境变量凭据只允许临时使用，不能写回账户文件。"
                "需要持久化时请通过 auth exchange 重新授权。"
            )
        target = Path(path) if path else account_path(self.alias or "default")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        stored = {key: value for key, value in asdict(self).items()
                  if key in STORED_FIELDS}
        tmp.write_text(_dumps(stored), encoding="utf-8")
        try:
            os.replace(tmp, target)  # 原子写，避免半截文件
        except PermissionError as exc:
            # Windows 上目标文件被其他程序/杀软占用时 replace 会失败。
            # 必须清掉临时文件，否则下次写入会撞上一个过期的 .json.tmp。
            try:
                tmp.unlink()
            except OSError:
                pass
            raise CredentialError(
                f"凭据写入失败：{target} 被占用或没有写权限。"
                "关闭占用该文件的程序后重试。"
            ) from exc
        if os.name != "nt":
            # Windows 没有 POSIX 权限位，chmod 只能改只读标记，设 600 是无效的；
            # 那边的保护来自 %USERPROFILE% 的用户目录 ACL，不是这里。
            try:
                target.chmod(0o600)
            except OSError:
                pass
        return target


# ---------- 路径与 alias 管理 ----------


def home_dir():
    """数据目录：BM_HOME 优先，否则 ~/.baidu-marketing。"""
    env = os.getenv("BM_HOME")
    return Path(env).expanduser() if env else DEFAULT_HOME


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
    if alias == "env" and not account_path(alias).exists():
        raise ValueError("env 是环境变量临时凭据，不能设为默认账户")
    if not account_path(alias).exists():
        raise ValueError(f"账户 {alias} 不存在，无法设为默认")
    target = home_dir() / DEFAULT_ALIAS_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(alias, encoding="utf-8")
    return alias


def list_accounts():
    """扫描 accounts/，返回账户摘要列表。损坏文件必须显式暴露。"""
    items = []
    directory = accounts_dir()
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            cred = _read_json_credential(path)
            cred.alias = path.stem
            items.append(cred)

    if not items and os.getenv("BAIDU_ACCESS_TOKEN"):
        items.append(_merge_env(Credential(
            alias="env", source="environment", persist_allowed=False
        )))

    current = default_alias()
    result = []
    for cred in items:
        row = cred.to_public_dict()
        row["is_default"] = cred.alias == current
        row["source"] = cred.source
        row["temporary"] = not cred.persist_allowed
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
    """读取单个账户的凭据；不存在返回 None，损坏则明确报错。"""
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
        # 文件名是持久化身份的唯一依据，不能由手编 JSON 重定向到另一账户。
        cred.alias = resolved
        return _merge_env(cred)

    if os.getenv("BAIDU_ACCESS_TOKEN"):
        # 纯环境变量模式：CI / 一次性调试，不落盘
        return _merge_env(Credential(
            alias="env", source="environment", persist_allowed=False
        ))

    existing = list(accounts_dir().glob("*.json")) if accounts_dir().is_dir() else []
    if existing:
        raise FileNotFoundError(
            f"已有 {len(existing)} 个本地账户，但尚未选择默认账户。"
            "请用 --account <alias> 指定本次账户，或执行 accounts use <alias>。"
        )
    raise FileNotFoundError(
        f"还没有任何已授权账户（{accounts_dir()}）。"
        "请先按 references/onboarding.md 接入一个账户。"
    )


def _merge_env(cred):
    cred.env_overrides = [key for key in ENV_CREDENTIAL_KEYS if os.environ.get(key)]
    if cred.env_overrides:
        cred.persist_allowed = False
        if cred.source == "file":
            cred.source = "file+environment"

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
    except (OSError, ValueError) as exc:
        raise CredentialError(f"凭据文件不可读或 JSON 损坏：{path}（{exc}）") from exc
    if not isinstance(data, dict):
        raise CredentialError(f"凭据文件顶层必须是 JSON 对象：{path}")
    known = STORED_FIELDS
    cred = Credential(**{k: v for k, v in data.items() if k in known})
    for key in ("expires_at", "refresh_expires_at"):
        value = getattr(cred, key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise CredentialError(f"凭据字段 {key} 必须是 Unix 数字时间戳：{path}")
    return cred


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
