"""写操作：把「建议」变成「真的改了账户」。

设计前提——写操作是不可逆的，别人账户里的钱会真的花掉。所以这个模块只做两件事：

  1. 把参数整形成百度 SMS 接口认识的信封（`keywordTypes` / `campaignTypes` / ...）
  2. 在发出去之前做本地拦截：空列表、超批量、缺关键字段、权限不足

真正的 dry-run 由传输层统一处理（`client.dry_run=True` 抛 `DryRunRequested`，
CLI 打印 URL 与完整报文）。所以这里的函数不需要 `dry_run` 参数——
CLI 决定 client 的 dry_run 属性，故意保持一致，避免两处开关打架。

**审批闸门**：执行必须带 `confirm=<digest>`，digest 来自同一条命令的预览输出。
没有 confirm 或 digest 对不上，一律拒绝执行且不落审计。详见 `bmclient/approval.py`。

⚠️ 字段名以百度营销 SMS 接口为准，当前环境无「投放管理」权限，**未经真实账户验证**。
首次使用务必先跑不带 `--execute` 的预览，逐字段核对后再放行。

审计：每次真实写入都会追加一行 JSON 到 `$BM_HOME/audit/YYYY-MM-DD.jsonl`，
记录谁、在哪个账户、对什么物料、改了什么。写失败也记，便于事后追查。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .. import approval, config
from ..errors import BaiduApiError, DryRunRequested, WriteNotPermitted

# ---------- 请求信封 ----------
# 百度 SMS 接口的 body 统一是 {信封名: [条目...]}。信封名写错会报 99912「JSON invalid」，
# 而不是参数错误——所以集中在这里定义，不要在各处手写字符串。
ENVELOPES = {
    "campaign": "campaignTypes",
    "adgroup": "adgroupTypes",
    "keyword": "keywordTypes",
    "creative": "creativeTypes",
}

# 单次调用的条数上限：一次改几千条，出错时无法人工核对，也容易触发网关限流。
MAX_ITEMS = {
    "keyword": 200,
    "campaign": 20,
    "adgroup": 50,
    "creative": 50,
}

PERMISSION_HINT = (
    "该接口需要「投放管理」权限域。当前应用可能只有「工具」域权限，"
    "请先在百度营销开发者后台补充权限并重新授权（旧令牌不会自动获得新权限）。"
)

# 百度 SMS 状态码：1 = 启用，2 = 暂停。
# 各接口对状态码的取值偶有差异，首次使用请在后台核对；
# 也可以直接传数字（如 --status 1），脚本会原样透传，不做猜测。
STATUS_MAP = {"enable": 1, "pause": 2}


def resolve_status(value):
    """把 enable / pause 或数字统一成接口要的整数。"""
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().lower()
    if text.lstrip("-").isdigit():
        return int(text)
    if text not in STATUS_MAP:
        raise ValueError(f"status 只接受 enable / pause 或数字：{value!r}")
    return STATUS_MAP[text]


# ---------- 对外接口 ----------


def add_words(client, adgroup_id, words, *, price=None, phrase_type=None, extra=None,
              confirm=None):
    """向单元添加关键词。words 是词面列表，price 会作为每个词的默认出价。"""
    adgroup_id = _require_id(adgroup_id, "adgroup_id")
    items = []
    for word in _clean_list(words, "words"):
        item = {"adgroupId": adgroup_id, "word": word}
        if price is not None:
            item["price"] = float(price)
        if phrase_type is not None:
            item["phraseType"] = int(phrase_type)
        if extra:
            item.update(extra)
        items.append(item)
    summary = f"向单元 {adgroup_id} 添加 {len(items)} 个关键词"
    if price is not None:
        summary += f"，出价 {price}"
    if phrase_type is not None:
        summary += f"，匹配模式 {phrase_type}"
    return _write(client, "keyword", "KeywordService", "addWord", items,
                  confirm=confirm, summary=summary)


def update_words(client, items, *, confirm=None):
    """批量修改关键词：出价、匹配模式、启停。items 是完整的 keywordTypes 条目。"""
    items = _require_items(items, "keyword", ("wordId",))
    return _write(client, "keyword", "KeywordService", "updateWord", items,
                  confirm=confirm, summary=f"修改 {len(items)} 个关键词（出价 / 匹配 / 状态）")


def delete_words(client, word_ids, *, confirm=None):
    """删除关键词，按 id。"""
    ids = [_require_id(i, "word_id") for i in _clean_list(word_ids, "word_ids")]
    _guard_count(len(ids), "keyword")
    return _dispatch(
        client, "keyword_delete", "KeywordService", "deleteWord",
        {"wordIds": ids}, len(ids), confirm,
        summary=f"删除 {len(ids)} 个关键词",
    )


def update_campaigns(client, items, *, confirm=None):
    """批量修改计划：预算、启停、地域等。items 是完整的 campaignTypes 条目。"""
    items = _require_items(items, "campaign", ("campaignId",))
    return _write(client, "campaign", "CampaignService", "updateCampaign", items,
                  confirm=confirm, summary=f"修改 {len(items)} 个计划（预算 / 状态）")


def update_adgroups(client, items, *, confirm=None):
    """批量修改单元：出价、启停等。items 是完整的 adgroupTypes 条目。"""
    items = _require_items(items, "adgroup", ("adgroupId",))
    return _write(client, "adgroup", "AdgroupService", "updateAdgroup", items,
                  confirm=confirm, summary=f"修改 {len(items)} 个单元（出价 / 状态）")


def call_raw(client, level, service, method, items, *, confirm=None, _preapproved=False):
    """逃生通道：按信封包装后直接发，供 CLI 的 --body 透传使用。

    `_preapproved` 只给 transfer 用：那边已经在整份方案上做过一次审批，
    逐级再要 digest 会让用户被问五次。除 transfer 外不要传这个参数。
    """
    items = _require_items(items, level)
    return _write(client, level, service, method, items,
                  confirm=confirm, _preapproved=_preapproved,
                  summary=f"透传调用 {service}/{method}")


def campaign_item(campaign_id, *, budget=None, status=None):
    """构造 campaignTypes 单条：只要改了预算或状态，其余字段走接口默认值。"""
    item = {"campaignId": _require_id(campaign_id, "campaign_id")}
    if budget is not None:
        item["budget"] = float(budget)
    state = resolve_status(status)
    if state is not None:
        item["status"] = state
    if len(item) == 1:
        raise ValueError("campaign update 至少要给 --budget 或 --status 之一")
    return item


def adgroup_item(adgroup_id, *, price=None, status=None):
    """构造 adgroupTypes 单条。"""
    item = {"adgroupId": _require_id(adgroup_id, "adgroup_id")}
    if price is not None:
        item["price"] = float(price)
    state = resolve_status(status)
    if state is not None:
        item["status"] = state
    if len(item) == 1:
        raise ValueError("adgroup update 至少要给 --price 或 --status 之一")
    return item


# ---------- 内部实现 ----------


def _write(client, level, service, method, items, *, confirm=None, _preapproved=False,
           summary=""):
    _guard_count(len(items), level)
    body = {ENVELOPES[level]: items}
    return _dispatch(client, f"{level}_write", service, method, body, len(items),
                     confirm, _preapproved=_preapproved, summary=summary)


def _dispatch(client, action, service, method, body, count, confirm=None, *,
              _preapproved=False, summary=""):
    """所有写操作的最后一道关卡：预览给 digest 与确认卡片，执行验 digest。

    顺序很重要——先算审批再落审计。审批没过就不该留下"尝试写入"的日志，
    否则审计里会混进一堆根本没发出去的记录。
    """
    alias = getattr(client.cred, "alias", "")
    steps = [{"service": service, "method": method, "body": body}]

    if getattr(client, "dry_run", False):
        try:
            return client.call(service, method, body)
        except DryRunRequested as exc:
            exc.approval = approval.describe(alias, steps, summary=summary)
            raise

    digest = None if _preapproved else approval.require(confirm, alias, steps)
    _record(client, action, service, method, body, count=count, digest=digest)
    try:
        return client.call(service, method, body)
    except BaiduApiError as exc:
        raise _translate(exc) from exc


def _translate(exc):
    """把「权限没开」翻译成能指导行动的错误，别让用户以为是令牌坏了。"""
    if exc.code == 89406:
        return WriteNotPermitted(f"{exc}｜{PERMISSION_HINT}")
    return exc


def _guard_count(count, level):
    if count <= 0:
        raise ValueError("没有要写入的条目")
    limit = MAX_ITEMS.get(level, 100)
    if count > limit:
        raise ValueError(
            f"单次最多写入 {limit} 条 {level}，本次 {count} 条。"
            "请拆成多批——一次改太多出错时无法人工核对。"
        )


def _require_items(items, level, required=()):
    if not isinstance(items, list) or not items:
        raise ValueError(f"{level} 至少要有一个条目，且必须是列表")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index + 1} 条不是对象：{item!r}")
        for key in required:
            if not item.get(key):
                raise ValueError(f"第 {index + 1} 条缺少必填字段 {key}")
    return items


def _require_id(value, name):
    if value in (None, "", 0):
        raise ValueError(f"缺少 {name}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是数字：{value!r}") from exc


def _clean_list(values, name):
    """支持列表或逗号分隔字符串，去空去重，保持原顺序。"""
    if isinstance(values, str):
        values = [v.strip() for v in values.replace("，", ",").split(",")]
    items, seen = [], set()
    for value in values or []:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    if not items:
        raise ValueError(f"{name} 不能为空")
    return items


# ---------- 审计 ----------


def audit_path(when=None):
    """当天审计文件路径，跟随 BM_HOME，便于测试隔离。"""
    stamp = time.strftime("%Y-%m-%d", time.localtime(when))
    return config.home_dir() / "audit" / f"{stamp}.jsonl"


def _record(client, action, service, method, body, *, count=None, digest=None):
    """真实写入前先落审计。dry-run 不记——预览不是动作。"""
    if getattr(client, "dry_run", False):
        return
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "action": action,
        "service": service,
        "method": method,
        "alias": getattr(client.cred, "alias", ""),
        "user_name": getattr(client.cred, "user_name", ""),
        "count": count,
        "approval_digest": digest,
        "body": body,
    }
    try:
        path = audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        # 审计失败不能阻断投放，但必须让人看见
        print(f"[audit] ! 审计日志写入失败（操作继续）：{exc}", file=sys.stderr)


def read_audit(when=None):
    """读回当天审计，供复盘与回滚参考。"""
    path = Path(audit_path(when))
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows
