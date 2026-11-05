"""错误码释义与 dry-run 报文脱敏。"""

from errors import BaiduApiError, DryRunRequested


def test_hint_for_known_code():
    err = BaiduApiError("fail", code=89406)

    assert "权限" in err.hint


def test_hint_is_none_for_unknown_code():
    assert BaiduApiError("x", code=123).hint is None
    assert BaiduApiError("x").hint is None


def test_to_dict_shape():
    err = BaiduApiError(
        "boom", code=81020, position="_user", service="KRService", method="getKRByQuery"
    )

    payload = err.to_dict()

    assert set(payload) == {"error", "code", "position", "service", "method", "hint", "outcome"}
    assert payload["code"] == 81020
    assert "81020" not in payload["error"]


def test_dry_run_masks_access_token():
    payload = {
        "header": {"userName": "某店铺", "accessToken": "secret-token", "action": "getKRByQuery"},
        "body": {"query": "月季"},
    }

    rendered = str(DryRunRequested("https://api.baidu.com/x", payload).to_dict())

    assert "secret-token" not in rendered
    assert "某店铺" in rendered


def test_dry_run_keeps_body_for_inspection():
    payload = {
        "header": {"userName": "u", "accessToken": "t", "action": "a"},
        "body": {"query": "月季"},
    }

    assert DryRunRequested("url", payload).to_dict()["payload"]["body"] == {"query": "月季"}
