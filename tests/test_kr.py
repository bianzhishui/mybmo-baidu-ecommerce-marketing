"""关键词规划师：响应契约、排序、去重与统计口径。"""

import pytest

import svc_kr as kr
from errors import BaiduApiError


class FakeClient:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def call(self, service, method, body):
        self.calls.append((service, method, body))
        return self.data


def test_expand_uses_canonical_method_and_sorts_by_pv():
    client = FakeClient([{"word": "窄词", "pv": 3}, {"word": "宽词", "pv": 100}])

    rows = kr.expand(client, "月季", limit=1)

    assert client.calls == [("KRService", "getKRByQuery", {"query": "月季"})]
    assert rows[0]["word"] == "宽词"


def test_expand_rejects_unexpected_data_shape():
    with pytest.raises(BaiduApiError):
        kr.expand(FakeClient({"items": []}), "月季")


def test_summary_keeps_zero_and_declares_simple_average():
    summary = kr.summarize([
        {"word": "a", "pv": 10, "rec_bid": 0, "competition": 0},
        {"word": "b", "pv": 0, "rec_bid": 2, "competition": 4},
    ])

    assert summary["bid_min"] == 0
    assert summary["competition_avg"] == 2
    assert "简单算术平均" in summary["basis"]
