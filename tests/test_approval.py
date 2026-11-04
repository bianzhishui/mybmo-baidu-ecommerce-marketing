"""审批指纹：稳定性、不泄露、写方法识别。"""

import pytest

import approval
from errors import ApprovalRequired

STEPS = [{"service": "KeywordService", "method": "addWord",
          "body": {"keywordTypes": [{"adgroupId": 9, "word": "月季"}]}}]


def test_digest_is_stable_and_short():
    first = approval.compute("demo", STEPS)
    second = approval.compute("demo", STEPS)

    assert first == second
    assert len(first) == approval.DIGEST_LEN


def test_digest_depends_on_account():
    assert approval.compute("a", STEPS) != approval.compute("b", STEPS)


def test_digest_depends_on_body():
    other = [{"service": "KeywordService", "method": "addWord",
              "body": {"keywordTypes": [{"adgroupId": 9, "word": "玫瑰花"}]}}]

    assert approval.compute("demo", STEPS) != approval.compute("demo", other)


def test_digest_ignores_key_order():
    reordered = [{"body": {"keywordTypes": [{"word": "月季", "adgroupId": 9}]},
                  "method": "addWord",
                  "service": "KeywordService"}]

    assert approval.compute("demo", STEPS) == approval.compute("demo", reordered)


def test_require_accepts_matching_digest():
    digest = approval.compute("demo", STEPS)

    assert approval.require(digest, "demo", STEPS) == digest


def test_require_rejects_missing_digest_without_leaking_expected():
    with pytest.raises(ApprovalRequired) as exc:
        approval.require(None, "demo", STEPS)

    message = str(exc.value)
    assert approval.compute("demo", STEPS) not in message, "不能把答案写在错误里"
    assert "预览" in message


def test_require_rejects_wrong_digest_without_leaking_expected():
    with pytest.raises(ApprovalRequired) as exc:
        approval.require("0000000000000000", "demo", STEPS)

    assert approval.compute("demo", STEPS) not in str(exc.value)


def test_describe_counts_items():
    info = approval.describe("demo", STEPS)

    assert info["items"] == 1
    assert info["digest"] == approval.compute("demo", STEPS)


@pytest.mark.parametrize(
    ("method", "is_write"),
    [
        ("addWord", True),
        ("updateCampaign", True),
        ("deleteWord", True),
        ("bindAtpFeed", True),
        ("getCampaign", False),
        ("get_account_info", False),
        ("queryRecommendReasons", False),
        ("somethingUnknown", True),
        ("", True),
    ],
)
def test_is_write_method(method, is_write):
    assert approval.is_write_method(method) is is_write
