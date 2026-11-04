"""HTTP 传输层：唯一知道百度网关长什么样的地方。

职责边界（高内聚）：
  - 拼 URL、拼鉴权 header、发请求、解析 header.status、必要时重试
  - 不懂任何业务语义（不知道什么是关键词、什么是计划）
services 层只传 service + method + body，拿回 body.data。
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request

import auth
from errors import BaiduApiError, CredentialError, DryRunRequested

SMS_BASE = "https://api.baidu.com/json/sms/service"
FEED_BASE = "https://api.baidu.com/json/feed/v1"
DEFAULT_TIMEOUT = 45
MAX_RETRY = 2
MIN_INTERVAL = 0.2  # 相邻请求最小间隔，避免触发网关限流


class BaiduClient:
    def __init__(self, credential, *, timeout=DEFAULT_TIMEOUT, dry_run=False):
        self.cred = credential
        self.timeout = timeout
        self.dry_run = dry_run
        self._last_call = 0.0
        self.last_rquota = None

    # ---------- 对外唯一入口 ----------

    def call(self, service, method, body=None, *, product_line="sms"):
        """调用任意百度营销接口，返回 body.data。"""
        service = normalize_service(service)
        method = normalize_method(method)
        url = build_url(service, method, product_line)
        payload = self._payload(body or {})

        if self.dry_run:
            raise DryRunRequested(url, payload)

        self._throttle()
        data = self._send(url, payload, service, method)
        return data

    # ---------- 内部实现 ----------

    def _payload(self, body):
        try:
            auth.ensure_valid(self.cred)
        except CredentialError:
            raise
        return {
            # 鉴权必须在 JSON body 的 header 里；放 HTTP 头会报 8002
            "header": {
                "userName": self.cred.user_name,
                "accessToken": self.cred.access_token,
                "action": "API-PY-SDK",
            },
            "body": body,
        }

    def _throttle(self):
        delta = time.time() - self._last_call
        if delta < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - delta)
        self._last_call = time.time()

    def _send(self, url, payload, service, method):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_error = None
        for attempt in range(MAX_RETRY + 1):
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json;charset=utf-8")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8")
                return self._parse(raw, service, method)
            except urllib.error.HTTPError as exc:
                # HTTPError 是 URLError 的子类，必须排在 URLError 前面。
                # 顺序反了会让 4xx/5xx 被当成网络故障白白重试三次，
                # 下面那个分支也就永远走不到。
                raise BaiduApiError(
                    f"{service}/{method} HTTP {exc.code}",
                    service=service,
                    method=method,
                ) from exc
            except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
                # socket.timeout 在 3.10 才等于 TimeoutError，3.9 上它是 OSError 子类，
                # 不显式列出来，超时会被上层误判成"文件读写失败"。
                last_error = exc
                if attempt < MAX_RETRY:
                    time.sleep(2 ** attempt)
                    continue
                raise BaiduApiError(
                    f"{service}/{method} 网络失败：{exc}", service=service, method=method
                ) from exc
        raise BaiduApiError(str(last_error), service=service, method=method)

    def _parse(self, raw, service, method):
        try:
            result = json.loads(raw)
        except ValueError as exc:
            raise BaiduApiError(
                f"{service}/{method} 返回非 JSON：{raw[:200]}",
                service=service,
                method=method,
            ) from exc

        header = result.get("header") or {}
        self.last_rquota = header.get("rquota")
        status = header.get("status")

        if status != 0:
            failures = header.get("failures") or []
            first = failures[0] if failures else {}
            raise BaiduApiError(
                first.get("message") or header.get("desc") or f"status={status}",
                code=first.get("code"),
                position=first.get("position"),
                service=service,
                method=method,
            )

        body = result.get("body") or {}
        return body.get("data")


# ---------- 名称归一化（对接能力清单 CSV 里的小写蛇形写法）----------


def normalize_service(name):
    """accountService -> AccountService；krService -> KRService（KR 必须全大写）"""
    name = (name or "").strip()
    if not name:
        raise ValueError("service 不能为空")
    return (name[0].upper() + name[1:]).replace("Kr", "KR")


def normalize_method(name):
    """get_account_info / getAccountInfo -> getAccountInfo；KR 两个字母须大写。"""
    name = (name or "").strip()
    if not name:
        raise ValueError("method 不能为空")
    if "_" in name:
        parts = [p for p in name.split("_") if p]
        name = parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])
    else:
        name = name[0].lower() + name[1:]
    # KRService 的方法名要求 KR 全大写，否则报 87091
    return name.replace("Kr", "KR")


def build_url(service, method, product_line="sms"):
    base = FEED_BASE if product_line == "feed" else SMS_BASE
    return f"{base}/{service}/{method}"
