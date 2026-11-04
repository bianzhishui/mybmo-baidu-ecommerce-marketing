"""写操作层：报文信封、批量保护、审批闸门、审计与权限错误翻译。

全部离线——用 FakeClient 代替真实传输层。
"""

from types import SimpleNamespace

import pytest

from bmclient import approval
from bmclient.errors import ApprovalRequired, BaiduApiError, DryRunRequested, WriteNotPermitted
from bmclient.services import write


class FakeClient:
    """和真实 client 保持同样的 dry_run 语义：dry_run 时抛 DryRunRequested。"""

    def __init__(self, responses=None, dry_run=False):
        self.cred = SimpleNamespace(alias="demo", user_name="演示账户")
        self.dry_run = dry_run
        self.calls = []
        self.responses = responses or {}

    def call(self, service, method, body=None, *, product_line="sms"):
        self.calls.append({"service": service, "method": method, "body": body})
        if self.dry_run:
            raise DryRunRequested(f"https://api.baidu.com/{service}/{method}",
                                  {"header": {"userName": "演示账户",
                                              "accessToken": "tok",
                                              "action": "API-PY-SDK"},
                                   "body": body})
        handler = self.responses.get(method)
        if isinstance(handler, Exception):
            raise handler
        return handler if handler is not None else []


def preview(fn, *args, **kwargs):
    """阶段一：预览，返回审批信息。"""
    probe = FakeClient(dry_run=True)
    with pytest.raises(DryRunRequested) as exc:
        fn(probe, *args, **kwargs)
    return exc.value.approval, exc.value.to_dict()


def approved(fn, *args, **kwargs):
    """走完两阶段：预览拿 digest，再带 digest 执行。返回执行用的 client。"""
    info, _ = preview(fn, *args, **kwargs)
    client = FakeClient()
    fn(client, *args, confirm=info["digest"], **kwargs)
    return client


@pytest.fixture
def bm_home(tmp_dir, monkeypatch):
    monkeypatch.setenv("BM_HOME", str(tmp_dir))
    return tmp_dir


# ---------- 报文构造 ----------


def test_add_words_builds_keyword_envelope(bm_home):
    client = approved(write.add_words, 10086, "月季,玫瑰花", price=3.5, phrase_type=2)

    call = client.calls[0]
    assert call["service"] == "KeywordService"
    assert call["method"] == "addWord"
    assert call["body"]["keywordTypes"] == [
        {"adgroupId": 10086, "word": "月季", "price": 3.5, "phraseType": 2},
        {"adgroupId": 10086, "word": "玫瑰花", "price": 3.5, "phraseType": 2},
    ]


def test_add_words_accepts_chinese_comma_and_dedupes(bm_home):
    client = approved(write.add_words, 9, "月季，玫瑰花,月季")

    words = [i["word"] for i in client.calls[0]["body"]["keywordTypes"]]
    assert words == ["月季", "玫瑰花"]


def test_add_words_merges_extra_fields(bm_home):
    client = approved(write.add_words, 9, "月季", extra={"status": 1})

    assert client.calls[0]["body"]["keywordTypes"][0]["status"] == 1


def test_add_words_rejects_too_many(bm_home):
    client = FakeClient()
    words = [f"词{i}" for i in range(write.MAX_ITEMS["keyword"] + 1)]

    with pytest.raises(ValueError) as exc:
        write.add_words(client, 9, words)

    assert "单次最多写入" in str(exc.value)
    assert not client.calls, "超限时不应该发出任何请求"


def test_add_words_rejects_empty(bm_home):
    with pytest.raises(ValueError):
        write.add_words(FakeClient(), 9, ",,,")


def test_update_words_requires_word_id(bm_home):
    with pytest.raises(ValueError) as exc:
        write.update_words(FakeClient(), [{"price": 2.0}])

    assert "wordId" in str(exc.value)


def test_delete_words_builds_word_ids(bm_home):
    client = approved(write.delete_words, "11,22")

    assert client.calls[0]["body"] == {"wordIds": [11, 22]}


def test_campaign_item_requires_a_change(bm_home):
    with pytest.raises(ValueError) as exc:
        write.campaign_item(1)

    assert "--budget 或 --status" in str(exc.value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("enable", 1), ("pause", 2), ("PAUSE", 2), ("1", 1), (2, 2), (None, None)],
)
def test_resolve_status(value, expected):
    assert write.resolve_status(value) == expected


def test_resolve_status_rejects_garbage():
    with pytest.raises(ValueError):
        write.resolve_status("stop")


# ---------- 审批闸门 ----------


def test_preview_carries_digest(bm_home):
    info, rendered = preview(write.add_words, 9, "月季", price=2.0)

    assert len(info["digest"]) == approval.DIGEST_LEN
    assert info["items"] == 1
    assert rendered["approval"]["digest"] == info["digest"]
    assert rendered["dry_run"] is True


def test_execute_without_confirm_is_refused(bm_home):
    client = FakeClient()

    with pytest.raises(ApprovalRequired) as exc:
        write.add_words(client, 9, "月季")

    assert "先运行一次不带 --execute 的预览" in str(exc.value)
    assert client.calls == [], "没审批就一条都不许发"


def test_execute_with_wrong_digest_is_refused(bm_home):
    client = FakeClient()

    with pytest.raises(ApprovalRequired) as exc:
        write.add_words(client, 9, "月季", confirm="deadbeefdeadbeef")

    assert "审批不匹配" in str(exc.value)
    assert client.calls == []


def test_digest_changes_when_payload_changes(bm_home):
    before, _ = preview(write.add_words, 9, "月季", price=2.0)
    after, _ = preview(write.add_words, 9, "月季", price=2.1)

    assert before["digest"] != after["digest"], "改了出价就应该换一个 digest"


def test_stale_digest_is_rejected_with_new_payload(bm_home):
    stale, _ = preview(write.add_words, 9, "月季", price=2.0)
    client = FakeClient()

    with pytest.raises(ApprovalRequired):
        write.add_words(client, 9, "月季", price=9.9, confirm=stale["digest"])

    assert client.calls == []


def test_audit_records_approval_digest(bm_home):
    info, _ = preview(write.add_words, 9, "月季", price=2.0)
    client = FakeClient()

    write.add_words(client, 9, "月季", price=2.0, confirm=info["digest"])

    rows = write.read_audit()
    assert rows[0]["approval_digest"] == info["digest"]


def test_refused_write_leaves_no_audit(bm_home):
    client = FakeClient()

    with pytest.raises(ApprovalRequired):
        write.add_words(client, 9, "月季")

    assert write.read_audit() == [], "没发出去的请求不该进审计"


# ---------- 权限错误翻译 ----------


def test_permission_error_becomes_write_not_permitted(bm_home):
    info, _ = preview(write.add_words, 9, "月季", price=1.0)
    client = FakeClient(responses={"addWord": BaiduApiError("bad", code=89406)})

    with pytest.raises(WriteNotPermitted) as exc:
        write.add_words(client, 9, "月季", price=1.0, confirm=info["digest"])

    assert "投放管理" in str(exc.value)


def test_other_api_errors_pass_through(bm_home):
    info, _ = preview(write.add_words, 9, "月季", price=1.0)
    client = FakeClient(responses={"addWord": BaiduApiError("bad", code=81020)})

    with pytest.raises(BaiduApiError):
        write.add_words(client, 9, "月季", price=1.0, confirm=info["digest"])


# ---------- 审计 ----------


def test_audit_written_on_real_call(bm_home):
    approved(write.add_words, 9, "月季", price=2.0)

    rows = write.read_audit()
    assert len(rows) == 1
    assert rows[0]["action"] == "keyword_write"
    assert rows[0]["alias"] == "demo"
    assert rows[0]["body"]["keywordTypes"][0]["word"] == "月季"


def test_audit_skipped_in_dry_run(bm_home):
    preview(write.add_words, 9, "月季")

    assert write.read_audit() == []


def test_audit_file_follows_bm_home(bm_home):
    assert str(write.audit_path()).startswith(str(bm_home))
