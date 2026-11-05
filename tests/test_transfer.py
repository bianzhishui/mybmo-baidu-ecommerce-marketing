"""跨账户复制：共享模板、批量与产品线预检、暂停门禁和部分成功。"""

import copy
from types import SimpleNamespace

import pytest

import svc_transfer as transfer
import svc_write as write
from errors import ApprovalRequired, WriteFailed, WriteNotPermitted


class FakeClient:
    def __init__(self, responses=None):
        self.cred = SimpleNamespace(alias="target", user_name="目标账户")
        self.dry_run = False
        self.calls = []
        self.responses = responses or {}

    def call(self, service, method, body=None, *, product_line="sms"):
        self.calls.append({"service": service, "method": method, "body": body})
        handler = self.responses.get(method)
        if isinstance(handler, Exception):
            raise handler
        return handler if handler is not None else []


PLAN = {
    "source": {"user_name": "源账户", "alias": "src"}, "product_line": "sms",
    "campaigns": [{
        "name": "A-计划",
        "config": {"campaignName": "A-计划", "budget": 300, "campaignId": 111},
        "adgroups": [{
            "name": "A-单元",
            "config": {"adgroupName": "A-单元", "price": 2.5, "adgroupId": 222},
            "keywords": [{"word": "月季", "price": 3.0, "wordId": 333}],
            "creatives": [],
        }],
    }],
}
CREATED = {
    "addCampaign": [{"campaignId": 9001}],
    "addAdgroup": [{"adgroupId": 8001}],
    "addWord": [{"wordId": 7001}],
}


def digest_for(plan=PLAN):
    return transfer.apply(FakeClient(), plan, dry_run=True)["approval"]["digest"]


def test_shared_template_strips_ids_and_uses_parent_placeholders():
    steps = transfer.build_steps(PLAN)

    campaign = steps[0]["body"]["campaignTypes"][0]
    adgroup = steps[1]["body"]["adgroupTypes"][0]
    keyword = steps[2]["body"]["keywordTypes"][0]
    assert "campaignId" not in campaign
    assert adgroup["campaignId"] == transfer.PARENT_CAMPAIGN
    assert keyword["adgroupId"] == transfer.PARENT_ADGROUP
    assert steps[1]["parent_step"] == steps[0]["step_id"]


def test_preview_declares_pause_requirement_and_execution_blockers():
    result = transfer.apply(FakeClient(), PLAN, dry_run=True)

    assert result["required_state"] == "pause"
    assert result["executable"] is False
    assert result["execution_blockers"] == ["adgroup", "campaign", "keyword"]
    assert result["approval"]["digest"]
    assert result["approval"]["items"] == 3


def test_execute_is_refused_before_any_request_without_verified_pause_fields():
    client = FakeClient(CREATED)

    with pytest.raises(WriteNotPermitted, match="默认暂停"):
        transfer.apply(client, PLAN, dry_run=False, confirm=digest_for())

    assert client.calls == []


def test_execute_without_confirm_is_refused_before_pause_gate():
    client = FakeClient(CREATED)
    with pytest.raises(ApprovalRequired):
        transfer.apply(client, PLAN, dry_run=False)
    assert client.calls == []


@pytest.mark.parametrize(("level", "count"), [("keywords", 201), ("creatives", 51)])
def test_batch_limit_is_rejected_during_preview(level, count):
    plan = copy.deepcopy(PLAN)
    plan["campaigns"][0]["adgroups"][0][level] = [
        {"name": f"item-{i}"} for i in range(count)
    ]
    client = FakeClient()

    with pytest.raises(ValueError, match="单次最多写入"):
        transfer.apply(client, plan, dry_run=True)

    assert client.calls == []


def test_feed_plan_cannot_fall_back_to_sms():
    plan = copy.deepcopy(PLAN)
    plan["product_line"] = "feed"
    with pytest.raises(ValueError, match="产品线"):
        transfer.apply(FakeClient(), plan, dry_run=True)


def test_execute_rejects_stale_digest():
    plan = copy.deepcopy(PLAN)
    plan["campaigns"][0]["config"]["budget"] = 999
    with pytest.raises(ApprovalRequired):
        transfer.apply(FakeClient(), plan, dry_run=False, confirm=digest_for())


def test_local_executor_chains_ids_and_returns_actual_keyword_id(monkeypatch):
    """只验证本地执行器；不是百度暂停字段或响应协议的真实证据。"""
    steps = transfer.build_steps(PLAN)
    client = FakeClient(CREATED)
    monkeypatch.setattr(write, "_record", lambda *args, **kwargs: None)

    result = transfer._execute(client, PLAN, steps=steps, approval_digest="digest")

    adgroup = client.calls[1]["body"]["adgroupTypes"][0]
    keyword = client.calls[2]["body"]["keywordTypes"][0]
    assert adgroup["campaignId"] == 9001
    assert keyword["adgroupId"] == 8001
    assert result["created"]["keywords"] == [{"name": "A-单元 / 关键词", "wordId": 7001,
                                             "parent_step": "c0.g0"}]


def test_partial_failure_retains_created_context(monkeypatch):
    client = FakeClient({"addCampaign": CREATED["addCampaign"], "addAdgroup": []})
    monkeypatch.setattr(write, "_record", lambda *args, **kwargs: None)

    with pytest.raises(WriteFailed) as exc:
        transfer._execute(client, PLAN, steps=transfer.build_steps(PLAN))

    assert exc.value.created["campaigns"][0]["campaignId"] == 9001
    assert exc.value.current_step["level"] == "adgroup"


def test_incomplete_batch_ids_stop_without_claiming_full_success(monkeypatch):
    plan = copy.deepcopy(PLAN)
    plan["campaigns"][0]["adgroups"][0]["keywords"].append({"word": "玫瑰花"})
    client = FakeClient({**CREATED, "addWord": [{"wordId": 7001}]})
    monkeypatch.setattr(write, "_record", lambda *args, **kwargs: None)

    with pytest.raises(WriteFailed):
        transfer._execute(client, plan, steps=transfer.build_steps(plan))

    assert len(client.calls) == 3


def test_clone_helper_forwards_confirm(monkeypatch):
    seen = {}
    monkeypatch.setattr(transfer, "describe", lambda *args, **kwargs: copy.deepcopy(PLAN))

    def fake_apply(client, plan, **kwargs):
        seen.update(kwargs)
        return {"source": plan["source"]}

    monkeypatch.setattr(transfer, "apply", fake_apply)
    transfer.clone(FakeClient(), FakeClient(), [], confirm="digest")

    assert seen["confirm"] == "digest"


def test_audit_isolation_does_not_touch_real_home(tmp_dir):
    assert str(write.audit_path()).startswith(str(tmp_dir))
