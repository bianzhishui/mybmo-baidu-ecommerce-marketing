"""关键词规划师（KRService）。

对应接口：KRService/getKRByQuery
参数注意：body.query 是字符串，不是数组；空 body 报 901701。
返回字段不统一，这里统一归一化成扁平结构，上层不关心原始键名。
"""

from __future__ import annotations

# 原始字段 -> 归一化字段
_FIELD_MAP = {
    "word": "word",
    "pv": "pv",
    "show": "show",
    "click": "click",
    "competition": "competition",
    "recBid": "rec_bid",
    "pcPV": "pc_pv",
    "mobilePV": "mobile_pv",
    "groupName": "group",
    "wordPackage": "package",
    "recommendPricePc": "bid_pc",
    "recommendPriceMobile": "bid_mobile",
}


def _normalize(item):
    row = {}
    for src, dst in _FIELD_MAP.items():
        value = item.get(src)
        row[dst] = value
    row["reasons"] = item.get("showReasons") or []
    row["similar"] = item.get("similar") or []
    return row


def expand(client, seed, *, limit=0):
    """单个种子词拓词。limit>0 时按搜索量降序截断。"""
    if not seed or not str(seed).strip():
        raise ValueError("seed 不能为空")
    data = client.call("KRService", "getKRByQuery", {"query": str(seed).strip()})
    rows = [_normalize(it) for it in (data or [])]
    rows.sort(key=lambda r: (r.get("pv") or 0), reverse=True)
    if limit and limit > 0:
        rows = rows[:limit]
    return rows


def expand_many(client, seeds, *, limit_per_seed=0):
    """多种子词拓词并按 word 去重，保留首次出现的记录。"""
    merged = {}
    stats = []
    for seed in seeds:
        rows = expand(client, seed, limit=limit_per_seed)
        fresh = 0
        for row in rows:
            word = row.get("word")
            if word and word not in merged:
                merged[word] = row
                fresh += 1
        stats.append({"seed": seed, "returned": len(rows), "new": fresh})

    words = sorted(merged.values(), key=lambda r: (r.get("pv") or 0), reverse=True)
    return {"total": len(words), "words": words, "seeds": stats}


def summarize(words):
    """给策略判断用的聚合指标，避免 Agent 自己算。"""
    if not words:
        return {"total": 0}
    pv = sum(w.get("pv") or 0 for w in words)
    bids = [w.get("rec_bid") for w in words if w.get("rec_bid")]
    comps = [w.get("competition") for w in words if w.get("competition") is not None]
    return {
        "total": len(words),
        "pv_sum": pv,
        "pv_avg": round(pv / len(words), 1),
        "bid_avg": round(sum(bids) / len(bids), 2) if bids else None,
        "bid_min": min(bids) if bids else None,
        "bid_max": max(bids) if bids else None,
        "competition_avg": round(sum(comps) / len(comps), 1) if comps else None,
        "top": [
            {"word": w.get("word"), "pv": w.get("pv"), "rec_bid": w.get("rec_bid")}
            for w in words[:10]
        ],
    }
