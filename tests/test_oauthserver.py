"""OAuth 回调：本地回环 HTTP，不访问百度、不读取真实凭据。"""

import json
import threading
import urllib.error
import urllib.request
from urllib.parse import urlencode

import bmctl
import oauth_sessions

import oauthserver


def app():
    return {
        "label": "测试应用", "app_id": "app", "developer_uid": "dev",
        "secret_key": "secret", "base_state": oauthserver.default_state("app", "dev"),
    }


def local_request(port, query):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/oauth/callback?{query}", timeout=3) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def run_local_server(state, requests):
    ready = threading.Event()
    holder = {}

    def on_ready(port):
        holder["port"] = port
        ready.set()

    result = {}
    thread = threading.Thread(target=lambda: result.update({
        "value": oauthserver.serve(
            port=0, path="/oauth/callback", apps=[app()], timeout=5,
            max_callbacks=1, on_record=lambda record: None, ready=on_ready,
        )
    }), daemon=True)
    thread.start()
    assert ready.wait(3)
    responses = [local_request(holder["port"], query) for query in requests]
    thread.join(7)
    assert not thread.is_alive()
    return responses, result["value"]


def test_real_http_callback_consumes_nonce_and_rejects_replay(tmp_dir):
    state = oauth_sessions.create(app()["base_state"], "app", alias="shop")
    query = urlencode({"authCode": "one-time-code", "userId": "42", "state": state})

    responses, (records, rejected) = run_local_server(state, [query, query])

    assert [status for status, _ in responses] == [200, 409]
    assert len(records) == 1
    assert records[0].code == "one-time-code"


def test_real_http_callback_rejects_old_state(tmp_dir):
    state = app()["base_state"] + ".shop"

    responses, (records, rejected) = run_local_server(state, [
        urlencode({"authCode": "code", "userId": "42", "state": state})
    ])

    assert responses[0][0] == 400
    assert records == [] and rejected


def test_manual_callback_returns_auth_code_once(tmp_dir, capsys):
    state = oauth_sessions.create(app()["base_state"], "app", alias="shop")

    def respond(port, path, apps, timeout, max_callbacks, on_record, host):
        record = oauthserver.CallbackRecord("one-time-code", state, "42", "shop", apps[0])
        on_record(record)
        return [record], []

    original_serve = bmctl.oauthserver.serve
    bmctl.oauthserver.serve = respond
    try:
        code = bmctl.main([
            "auth", "serve", "--app-id", "app", "--developer-uid", "dev",
            "--no-exchange", "--once",
        ])
    finally:
        bmctl.oauthserver.serve = original_serve

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["accounts"][0]["auth_code"] == "one-time-code"
    assert payload["accounts"][0]["credential_saved"] is False
    assert "next_command" in payload["accounts"][0]


def test_failed_exchange_returns_nonzero(tmp_dir, capsys, monkeypatch):
    state = oauth_sessions.create(app()["base_state"], "app", alias="shop")
    monkeypatch.setattr(bmctl.auth, "exchange", lambda *args, **kwargs: (_ for _ in ()).throw(
        RuntimeError("模拟换码失败")
    ))

    def respond(port, path, apps, timeout, max_callbacks, on_record, host):
        record = oauthserver.CallbackRecord("one-time-code", state, "42", "shop", apps[0])
        on_record(record)
        return [record], []

    monkeypatch.setattr(bmctl.oauthserver, "serve", respond)
    code = bmctl.main([
        "auth", "serve", "--app-id", "app", "--developer-uid", "dev",
        "--secret-key", "secret", "--once",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["accounts"][0]["status"] == "exchange_failed"
    assert "auth_code" not in payload["accounts"][0]



def test_record_manual_output_contains_code_but_automatic_does_not():
    record = oauthserver.CallbackRecord("one-time-code", "state", "42", "shop", app())
    assert record.as_dict()["auth_code"] == "one-time-code"

    record.credential = {"alias": "shop", "access_token": "masked***"}
    assert "auth_code" not in record.as_dict()
