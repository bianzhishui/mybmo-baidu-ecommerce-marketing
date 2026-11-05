"""HTTP 传输：预览副作用、重试边界与响应契约。全部 mock，不访问网络。"""

import json
import urllib.error
from types import SimpleNamespace

import pytest

import transport
from errors import BaiduApiError, DryRunRequested


def credential():
    return SimpleNamespace(
        user_name="测试账户", access_token="expired-token", refresh_token="refresh"
    )


def test_dry_run_never_refreshes_or_calls_network(monkeypatch):
    client = transport.BaiduClient(credential(), dry_run=True)

    def forbidden(*args, **kwargs):
        raise AssertionError("预览不得刷新令牌或联网")

    monkeypatch.setattr(transport.auth, "ensure_valid", forbidden)
    monkeypatch.setattr(transport.urllib.request, "urlopen", forbidden)

    with pytest.raises(DryRunRequested) as exc:
        client.call("KRService", "getKRByQuery", {"query": "月季"})

    assert exc.value.to_dict()["payload"]["header"]["accessToken"] == "***"


def test_environment_refresh_stays_in_memory(monkeypatch):
    cred = credential()
    cred.persist_allowed = False
    seen = {}
    monkeypatch.setattr(
        transport.auth, "ensure_valid",
        lambda credential, persist=True: seen.setdefault("persist", persist),
    )
    client = transport.BaiduClient(cred)

    client._payload({})

    assert seen["persist"] is False


def test_write_network_error_is_not_retried(monkeypatch):
    calls = []

    def offline(*args, **kwargs):
        calls.append(args)
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(transport.urllib.request, "urlopen", offline)
    monkeypatch.setattr(transport.auth, "ensure_valid", lambda cred, persist=True: cred)

    with pytest.raises(BaiduApiError) as exc:
        transport.BaiduClient(credential()).call("KeywordService", "addWord", {})

    assert len(calls) == 1
    assert exc.value.outcome == "unknown"


def test_read_network_error_keeps_bounded_retry(monkeypatch):
    calls = []

    def offline(*args, **kwargs):
        calls.append(args)
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(transport.urllib.request, "urlopen", offline)
    monkeypatch.setattr(transport.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(transport.auth, "ensure_valid", lambda cred, persist=True: cred)

    with pytest.raises(BaiduApiError):
        transport.BaiduClient(credential()).call("KRService", "getKRByQuery", {})

    assert len(calls) == transport.MAX_RETRY + 1


@pytest.mark.parametrize("raw", ["null", "[]", '"text"', "not-json"])
def test_invalid_response_is_unknown_not_traceback(raw):
    client = transport.BaiduClient(credential())

    with pytest.raises(BaiduApiError) as exc:
        client._parse(raw, "KRService", "getKRByQuery")

    assert exc.value.outcome == "unknown"


def test_success_response_requires_object_body():
    client = transport.BaiduClient(credential())
    raw = json.dumps({"header": {"status": 0}, "body": []})

    with pytest.raises(BaiduApiError) as exc:
        client._parse(raw, "KRService", "getKRByQuery")

    assert exc.value.outcome == "unknown"


def test_explicit_api_rejection_is_failed():
    client = transport.BaiduClient(credential())
    raw = json.dumps({"header": {"status": 1, "failures": [{"code": 81020}]}})

    with pytest.raises(BaiduApiError) as exc:
        client._parse(raw, "KRService", "getKRByQuery")

    assert exc.value.outcome == "failed"
