"""写操作层：报文信封、批量保护、状态码映射、审计与权限错误翻译。

全部离线——用 FakeClient 代替真实传输层。
"""

from types import SimpleNamespace

import pytest

from bmclient.errors import BaiduApiError, WriteNotPermitted
from bmclient.services import write


class FakeClient:
    def __init__(self, responses=None, dry_run=False):
        self.cred = SimpleNamespace(alias="demo", user_name="演示账户")
        self.dry_run = dry_run
        self.calls = []
        self.responses = responses or {}

    def call(self, service, method, body=None, *, product_line="sms"):
        self.calls.append({"service": service, "method": method, "body": body})
        handler = self.responses.get(method)
        if isinstance(handler, Exception):
            raise handler
        return handler if handler is not None else []


@pytest.fixture
def bm_home(tmp_dir, monkeypatch):
    monkeypatch.setenv("BM_HOME", str(tmp_dir))
    return tmp_dir


# ---------- 报文构造 ----------


def test_add_words_builds_keyword_envelope(bm_home):
    client = FakeClient()

    write.add_words(client, 10086, "月季,玫瑰花", price=3.5, phrase_type=2)

    call = client.calls[0]
    assert call["service"] == "KeywordService"
    assert call["method"] == "addWord"
    assert call["body"]["keywordTypes"] == [
        {"adgroupId": 10086, "word": "月季", "price": 3.5, "phraseType": 2},
        {"adgroupId": 10086, "word": "玫瑰花", "price": 3.5, "phraseType": 2},
    ]


def test_add_words_accepts_chinese_comma_and_dedupes(bm_home):
    client = FakeClient()

    write.add_words(client, 9, "月季，玫瑰花,月季")

    words = [i["word"] for i in client.calls[0]["body"]["keywordTypes"]]
    assert words == ["月季", "玫瑰花"]


def test_add_words_merges_extra_fields(bm_home):
    client = FakeClient()

    write.add_words(client, 9, "月季", extra={"status": 1})

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
    client = FakeClient()

    write.delete_words(client, "11,22")

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


# ---------- 权限错误翻译 ----------


def test_permission_error_becomes_write_not_permitted(bm_home):
    client = FakeClient(responses={"addWord": BaiduApiError("bad", code=89406)})

    with pytest.raises(WriteNotPermitted) as exc:
        write.add_words(client, 9, "月季")

    assert "投放管理" in str(exc.value)


def test_other_api_errors_pass_through(bm_home):
    client = FakeClient(responses={"addWord": BaiduApiError("bad", code=81020)})

    with pytest.raises(BaiduApiError):
        write.add_words(client, 9, "月季")


# ---------- 审计 ----------


def test_audit_written_on_real_call(bm_home):
    client = FakeClient()

    write.add_words(client, 9, "月季", price=2.0)

    rows = write.read_audit()
    assert len(rows) == 1
    assert rows[0]["action"] == "keyword_write"
    assert rows[0]["alias"] == "demo"
    assert rows[0]["body"]["keywordTypes"][0]["word"] == "月季"


def test_audit_skipped_in_dry_run(bm_home):
    client = FakeClient(dry_run=True)

    write.add_words(client, 9, "月季")

    assert write.read_audit() == []


def test_audit_file_follows_bm_home(bm_home):
    assert str(write.audit_path()).startswith(str(bm_home))
