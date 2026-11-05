"""内置 OAuth 回调服务。

支持**一次启动、连续接收多个账户**的授权回调：
    state = {base}.v1.{alias-or-_}.{nonce}
      base  = md5(appId_开发者uid)，仅用于应用路由
      nonce = 一次性随机会话标识，绑定应用、alias 与过期时间

百度是否原样回传自定义 state 尚未实证；缺失或不匹配时失败关闭。
默认只监听 127.0.0.1。nonce 原子消费，重放返回 409；会话不保存凭据。
手工收码才输出 authCode，自动换令牌失败时不回显授权码。
"""

from __future__ import annotations

import hashlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import oauth_sessions

PLATFORM_ID = "4960345965958561794"
AUTH_PAGE = "https://u.baidu.com/oauth/page/index"

def default_state(app_id, developer_uid):
    """百度约定的默认 state：md5(appId_开发者uid) 32 位小写。"""
    raw = f"{app_id}_{developer_uid}".encode()
    # usedforsecurity=False：这里只是生成百度约定的 state 值，不用于安全目的。
    # 不写这个参数，FIPS 模式的机器（部分企业 Windows / RHEL）会直接抛 ValueError。
    # 该关键字 3.9 起可用，与运行时门槛一致；md5 结果不变，已发出的授权链接照常有效。
    return hashlib.md5(raw, usedforsecurity=False).hexdigest()


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
        self.status = "code_received"
        self.exchange_attempted = False
        self.credential_saved = False
        self.credential = None
        self.next_command = ""

    def as_dict(self):
        result = {
            "alias": self.alias,
            "alias_source": self.alias_source,
            "app": self.app.get("label") or self.app.get("app_id", ""),
            "user_id": self.user_id,
            "ok": self.ok,
            "status": self.status,
            "exchange_attempted": self.exchange_attempted,
            "credential_saved": self.credential_saved,
            "detail": self.detail,
        }
        if self.credential is not None:
            result["credential"] = self.credential
        elif self.status == "code_received" and not self.exchange_attempted:
            # 仅在需要用户手工换令牌时交付一次性 code，不写持久日志。
            result["auth_code"] = self.code
        if self.next_command:
            result["next_command"] = self.next_command
        return result


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

            try:
                app, alias, session_key = oauth_sessions.resolve(state, apps)
            except ValueError as exc:
                collector.reject(str(exc))
                self._send({"code": 600011, "message": str(exc)}, 400)
                return
            if not code:
                collector.reject("回调里没有 authCode")
                self._send({"code": 600011, "message": "missing authCode"}, 400)
                return
            if not oauth_sessions.claim(session_key):
                collector.reject("OAuth 会话已消费或无法锁定，请重新生成授权链接")
                self._send({"code": 600011, "message": "session already used"}, 409)
                return

            collector.add(CallbackRecord(code, state, user_id, alias, app, self.client_address[0]))
            # 百度预期收到这个结构；不回传 token，减少泄露面
            self._send({"code": 0, "message": "success", "data": {"userId": user_id}})

        def log_message(self, *args):  # 静默，避免 authCode 落到 stderr
            return

    return Handler


def serve(*, port=8080, path="/oauth/callback", apps=None, timeout=300,
          max_callbacks=0, on_record=None, host="127.0.0.1", ready=None):
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
    actual_port = server.server_address[1]
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()

    deadline = time.time() + timeout
    if ready is not None:
        ready(actual_port)
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
