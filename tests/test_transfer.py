"""跨账户复制：报文信封、id 剔除、审批闸门、写入链路串联。

重点验证两件事：
  1. 每级用上一级返回的新 id —— 这是跨账户复制最容易写错的地方
  2. 没有审批 digest 就不许写
"""

from types import SimpleNamespace

import pytest

from bmclient.errors import ApprovalRequired, WriteFailed, WriteNotPermitted
from bmclient.services import transfer, write


@pytest.fixture(autouse=True)
def _isolate_bm_home(tmp_dir, monkeypatch):
    """审计会真的落盘。不隔离就会把测试假数据写进用户真实审计目录——
    这个坑真踩过：50 条 alias=target 的假记录混进了 ~/.workbuddy/baidu-marketing/audit。"""
    monkeypatch.setenv("BM_HOME", str(tmp_dir))


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
    "source": {"user_name": "源账户", "alias": "src"},
    "product_line": "sms",
    "campaigns": [
        {
            "name": "A-计划",
            "config": {"campaignName": "A-计划", "budget": 300, "campaignId": 111},
            "adgroups": [
                {
                    "name": "A-单元",
                    "config": {"adgroupName": "A-单元", "price": 2.5, "adgroupId": 222},
                    "keywords": [
                        {"word": "月季", "price": 3.0, "wordId": 333},
                        {"word": "玫瑰花", "price": 2.0, "wordId": 334},
                    ],
                    "creatives": [],
                }
            ],
        }
    ],
}

CREATED = {
    "addCampaign": [{"campaignId": 9001}],
    "addAdgroup": [{"adgroupId": 8001}],
    "addWord": [{"wordId": 7001}],
}


def digest_for(plan=PLAN):
    return transfer.apply(FakeClient(), plan, dry_run=True)["approval"]["digest"]


# ---------- 报文构造 ----------


def test_build_steps_uses_envelopes_and_strips_ids():
    steps = transfer.build_steps(PLAN)

    campaign = steps[0]
    assert campaign["method"] == "addCampaign"
    assert "campaignTypes" in campaign["body"]
    assert "campaignId" not in campaign["body"]["campaignTypes"][0]

    keyword = [s for s in steps if s["level"] == "keyword"][0]
    assert "keywordTypes" in keyword["body"]
    assert all("wordId" not in w for w in keyword["body"]["keywordTypes"])


def test_build_steps_rejects_feed_line():
    with pytest.raises(WriteNotPermitted) as exc:
        transfer.build_steps(PLAN, product_line="feed")

    assert "信息流" in str(exc.value)


# ---------- 审批闸门 ----------


def test_preview_carries_digest():
    client = FakeClient()

    result = transfer.apply(client, PLAN, dry_run=True)

    assert result["dry_run"] is True
    assert len(result["approval"]["digest"]) == 16
    assert result["approval"]["items"] == 2 + 2  # 计划+单元 + 2 个词
    assert client.calls == [], "预览不该发请求"


def test_preview_carries_confirm_card():
    result = transfer.apply(FakeClient(), PLAN, dry_run=True)

    card = result["approval"]["confirm_card"]
    assert card["type"] == "confirm"
    action = [f["value"] for f in card["fields"] if f["label"] == "动作"][0]
    assert "1 个计划" in action
    assert "2 个关键词" in action
    assert [o["value"] for o in card["options"]] == ["confirm", "cancel"]


def test_execute_without_confirm_is_refused():
    client = FakeClient(responses=CREATED)

    with pytest.raises(ApprovalRequired) as exc:
        transfer.apply(client, PLAN, dry_run=False)

    assert "先运行一次不带 --execute 的预览" in str(exc.value)
    assert client.calls == [], "没审批就一条都不许发"


def test_execute_rejects_stale_digest():
    client = FakeClient(responses=CREATED)
    plan = {
        **PLAN,
        "campaigns": [{**PLAN["campaigns"][0], "name": "被改过的计划"}],
    }

    with pytest.raises(ApprovalRequired):
        transfer.apply(client, plan, dry_run=False, confirm=digest_for())

    assert client.calls == []


# ---------- 真实写入链路 ----------


def test_execute_chains_parent_ids():
    client = FakeClient(responses=CREATED)

    result = transfer.apply(client, PLAN, dry_run=False, confirm=digest_for())

    assert result["dry_run"] is False
    assert result["created"]["campaigns"][0]["campaignId"] == 9001
    assert result["created"]["adgroups"][0]["adgroupId"] == 8001
    assert result["created"]["keywords"] == 2

    assert [c["method"] for c in client.calls] == ["addCampaign", "addAdgroup", "addWord"]

    adgroup_body = client.calls[1]["body"]["adgroupTypes"][0]
    assert adgroup_body["campaignId"] == 9001, "单元必须挂到新建的计划下"

    keyword_items = client.calls[2]["body"]["keywordTypes"]
    assert all(w["adgroupId"] == 8001 for w in keyword_items), "关键词必须挂到新建的单元下"


def test_execute_refuses_to_guess_missing_id():
    client = FakeClient(responses={"addCampaign": []})

    with pytest.raises(WriteFailed) as exc:
        transfer.apply(client, PLAN, dry_run=False, confirm=digest_for())

    assert "未返回 campaignId" in str(exc.value)


def test_execute_stops_before_children_when_campaign_fails():
    client = FakeClient(responses={"addCampaign": WriteNotPermitted("权限不足")})

    with pytest.raises(WriteNotPermitted):
        transfer.apply(client, PLAN, dry_run=False, confirm=digest_for())

    assert [c["method"] for c in client.calls] == ["addCampaign"]


def test_execute_audits_every_level_with_plan_digest():
    """整份方案只在开头审批一次，但每级写入都要能追回到那次审批。"""
    client = FakeClient(responses=CREATED)
    digest = digest_for()

    transfer.apply(client, PLAN, dry_run=False, confirm=digest)

    rows = write.read_audit()
    assert len(rows) == 3, "计划、单元、关键词各一条"
    assert {r["approval_digest"] for r in rows} == {digest}
    assert {r["action"] for r in rows} == {"campaign_write", "adgroup_write", "keyword_write"}


def test_audit_isolation_does_not_touch_real_home(tmp_dir):
    assert str(write.audit_path()).startswith(str(tmp_dir))
