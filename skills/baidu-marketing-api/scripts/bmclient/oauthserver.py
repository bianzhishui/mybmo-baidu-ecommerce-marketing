"""内置 OAuth 回调服务（零依赖，仅标准库）。

支持**一次启动、连续接收多个账户**的授权回调：
    state = {base}.{alias}
      base  = md5(appId_开发者uid)，32 位小写，用于校验回调确实属于本次授权
      alias = 账户别名，服务据此把令牌落到对应的 accounts/<alias>.json

百度会把 state 原样带回，所以 alias 不需要额外通道传。

安全边界（重要）：
  - 只监听 127.0.0.1，绝不绑 0.0.0.0。公网暴露交给隧道（cloudflared / frp）。
  - **不做 AES 验签**：验签需要第三方 AES 实现，会破坏零依赖特性。
  - 改为强制校验 state 的 base 部分 —— 伪造者即便打通回调，也换不出令牌：
    换令牌还要服务端持有的 secretKey，且 authCode 是一次性的。
  - 日志不落盘，authCode 只在终端显示一次。
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

PLATFORM_ID = "4960345965958561794"
AUTH_PAGE = "https://u.baidu.com/oauth/page/index"

# state 用 "." 分隔 base 与 alias：base 是纯 hex 不含点，alias 也不允许点，解析无歧义
ALIAS_SEP = "."
_ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def default_state(app_id, developer_uid):
    """百度约定的默认 state：md5(appId_开发者uid) 32 位小写。"""
    raw = f"{app_id}_{developer_uid}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def compose_state(base_state, alias=""):
    """把 alias 编进 state，让常驻服务能区分不同账户的回调。"""
    if not alias:
        return base_state
    return f"{base_state}{ALIAS_SEP}{alias}"


def parse_alias(state, base_state):
    """从回调的 state 解析出 alias。

    返回 (matched, alias)：
      matched=False —— state 不属于本次服务（伪造，或复用了过期的授权链接）
    """
    if not base_state:
        return True, state
    if state == base_state:
        return True, ""
    prefix = base_state + ALIAS_SEP
    if state.startswith(prefix):
        alias = state[len(prefix):]
        return (True, alias) if _ALIAS_RE.match(alias) else (False, "")
    return False, ""


def resolve_app(state, apps):
    """按 state 前缀找到它属于哪个应用。

    apps 是 [{label, app_id, developer_uid, secret_key, base_state}] 的列表。
    多应用共用一个服务时，靠这一步区分：不同 AppID/开发者uid 的 base 不同。

    返回 (app, alias)；app 为 None 表示没有任何应用匹配（伪造或过期链接）。
    """
    for app in apps or []:
        matched, alias = parse_alias(state, app.get("base_state", ""))
        if matched:
            return app, alias
    return None, ""


def build_auth_url(app_id, *, callback, scope="", state="", platform_id=PLATFORM_ID):
    """生成授权链接。callback 不能带 ? 或 %，百度侧不允许。"""
    if not callback:
        raise ValueError("缺少 callback（公网可达的回调地址）")
    if "?" in callback or "%" in callback:
        raise ValueError("callback 不能包含 ? 或 %，需要额外参数请用 state 传递")
    query = {
        "platformId": platform_id,
        "appId": app_id,
        "scope": scope,
        "state": state,
        "callback": callback,
    }
    return f"{AUTH_PAGE}?{urlencode({k: v for k, v in query.items() if v})}"


class CallbackRecord:
    """一次成功回调的处理记录。"""

    def __init__(self, code, state, user_id, alias, app=None, client_ip=""):
        self.code = code
        self.state = state
        self.user_id = user_id
        self.alias = alias
        self.alias_source = "state" if alias else ""
        self.app = app or {}
        self.client_ip = client_ip
        self.ok = None
        self.detail = ""

    def as_dict(self):
        return {
            "alias": self.alias,
            "alias_source": self.alias_source,
            "app": self.app.get("label") or self.app.get("app_id", ""),
            "user_id": self.user_id,
            "ok": self.ok,
            "detail": self.detail,
        }


class _Collector:
    """线程安全地累积回调，支持多次。"""

    def __init__(self, max_callbacks=0):
        self.records = []
        self.rejected = []
        self._lock = threading.Lock()
        self._done = threading.Event()
        self.max_callbacks = max_callbacks

    def add(self, record):
        with self._lock:
            self.records.append(record)
            count = len(self.records)
        if self.max_callbacks and count >= self.max_callbacks:
            self._done.set()

    def reject(self, message):
        with self._lock:
            self.rejected.append(message)

    def snapshot(self):
        with self._lock:
            return list(self.records), list(self.rejected)

    @property
    def done(self):
        return self._done


def _make_handler(collector, apps, path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BaiduOAuthCallback/1.2"

        def _send(self, payload, status=200):
            import json

            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json;charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/healthz":
                count = len(collector.snapshot()[0])
                self._send({"status": "ok", "received": count})
                return
            if parsed.path != path:
                self._send({"code": 600011, "message": "unknown path"}, 404)
                return

            qs = parse_qs(parsed.query)
            code = (qs.get("authCode") or qs.get("code") or [""])[0]
            state = (qs.get("state") or [""])[0]
            user_id = (qs.get("userId") or [""])[0]

            app, alias = resolve_app(state, apps)
            if apps and app is None:
                collector.reject(f"state 不属于任何已配置应用：{state[:48]}")
                self._send({"code": 600011, "message": "state mismatch"}, 400)
                return
            if not code:
                collector.reject("回调里没有 authCode")
                self._send({"code": 600011, "message": "missing authCode"}, 400)
                return

            collector.add(CallbackRecord(code, state, user_id, alias, app, self.client_address[0]))
            # 百度预期收到这个结构；不回传 token，减少泄露面
            self._send({"code": 0, "message": "success", "data": {"userId": user_id}})

        def log_message(self, *args):  # 静默，避免 authCode 落到 stderr
            return

    return Handler


def serve(*, port=8080, path="/oauth/callback", apps=None, timeout=300,
          max_callbacks=0, on_record=None, host="127.0.0.1"):
    """循环接收回调，直到超时、或收满 max_callbacks（0 表示只受超时限制）。

    apps: [{label, app_id, developer_uid, secret_key, base_state}]。
          支持多个应用（不同 AppID / 开发者uid / SecretKey）共用一个服务：
          收到回调后按 state 的 base 找到对应应用，再用它的 SecretKey 换令牌。

    on_record(record) 在主线程被调用，可安全地换令牌、写凭据文件。
    返回 (records, rejected)。
    """
    apps = apps or []
    collector = _Collector(max_callbacks=max_callbacks)
    server = ThreadingHTTPServer((host, port), _make_handler(collector, apps, path))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()

    deadline = time.time() + timeout
    processed = 0

    def drain():
        nonlocal processed
        records, _ = collector.snapshot()
        while processed < len(records):
            record = records[processed]
            processed += 1
            if on_record:
                try:
                    on_record(record)
                except Exception as exc:  # 单个失败不能让服务停摆
                    record.ok = False
                    record.detail = f"处理异常：{exc}"

    try:
        while time.time() < deadline:
            drain()
            if collector.done.is_set():
                break
            time.sleep(0.2)
    finally:
        drain()  # 收尾：把最后一批也处理掉
        try:
            server.shutdown()
        except Exception:
            pass
        server.server_close()

    records, rejected = collector.snapshot()
    return records, rejected
