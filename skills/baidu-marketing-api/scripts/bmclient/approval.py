"""写操作的审批闸门。

问题：写操作不可逆，但 CLI 是一条命令就能执行的。光靠「默认 dry-run + 记得加 --execute」
挡不住误操作——手一滑就写进去了，而且没人能证明「执行前用户看过报文」。

做法：把预览和执行绑成一个两阶段流程。

    阶段一  预览        打印完整报文，并给出一个 digest
    阶段二  执行        必须带 --confirm <digest>，且 digest 与当前报文严格对应

digest 是报文内容的指纹。它能做到两件现实里最要紧的事：

  1. **没预览就执行不了** —— digest 只从预览输出里能拿到
  2. **预览后改了报文就执行不了** —— 改一个出价，digest 就变

这不能加密学地证明「点确认的是真人」，但能保证「执行的那份报文，就是用户看过的那份」，
并把「预览 → 确认 → 执行」变成必须留下痕迹的三步，写进审计。

digest 不含令牌：只哈希 alias + service + method + body，避免把凭据写进日志或屏幕。
"""

from __future__ import annotations

import hashlib
import json

from .errors import ApprovalRequired

DIGEST_LEN = 16


def compute(alias, steps):
    """对一组待执行步骤算指纹。steps 是 [{service, method, body}, ...]。"""
    canonical = json.dumps(
        {"alias": alias or "", "steps": steps},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:DIGEST_LEN]


def describe(alias, steps, *, summary="", warning="", title="确认执行这次写入？"):
    """预览时返回给用户看的审批信息。

    除了 digest，还直接给出一份 `confirm_card`：标题、字段、选项都是现成的。
    这样「弹卡片」不再是需要临场发挥的环节——预览输出里有什么，就原样弹什么。
    少一次自行组织语言，就少一次漏掉关键数字的机会。
    """
    digest = compute(alias, steps)
    card = {
        "type": "confirm",
        "title": title,
        "fields": [
            {"label": "账户", "value": alias or "默认账户"},
            {"label": "动作", "value": summary or _service_label(steps)},
            {"label": "条数", "value": _count_items(steps)},
            {"label": "回执", "value": digest},
        ],
        "options": [
            {"label": "确认执行", "value": "confirm"},
            {"label": "取消", "value": "cancel"},
        ],
        "warning": warning or "写入后不可撤销，只能人工回滚。",
        "on_confirm": f"--execute --confirm {digest}",
    }
    return {
        "digest": digest,
        "target": alias or "默认账户",
        "items": _count_items(steps),
        "confirm_card": card,
        "next": (
            f"必须先把 confirm_card 弹给用户点选；用户点「确认执行」后，"
            f"再加 --execute --confirm {digest} 执行。"
        ),
        "notice": "未带 --confirm 的执行会被拒绝：写操作必须先给用户看过报文。",
    }


def require(confirm, alias, steps):
    """执行前校验审批。不通过就抛 ApprovalRequired，一条都不发。

    注意：两种拒绝都**不回显正确的 digest**。回显等于把钥匙一起递出去——
    执行被拒的一方可以直接抄下来再跑一次，审批就形同虚设。
    digest 只能从「显式预览」的输出里拿。
    """
    expected = compute(alias, steps)
    if not confirm:
        raise ApprovalRequired(
            "写操作需要用户审批：请先运行一次不带 --execute 的预览，把报文给用户核对；"
            "用户明确确认后，再用预览输出里的 approval.digest 作为 --confirm 重跑。"
            "（本命令不会把 digest 直接告诉你——它必须来自那次预览。）"
        )
    if confirm.strip() != expected:
        raise ApprovalRequired(
            "审批不匹配：--confirm 与当前报文不一致。常见原因是预览之后又改了参数，"
            "或者 digest 是手抄错的。请重新预览，用这次输出里的 digest 执行。"
        )
    return expected


def _count_items(steps):
    total = 0
    for step in steps:
        body = step.get("body") or {}
        for value in body.values():
            if isinstance(value, list):
                total += len(value)
    return total


def _service_label(steps):
    if not steps:
        return "写入"
    step = steps[0]
    return f"{step.get('service', '')}/{step.get('method', '')}".strip("/")


# 百度 SMS 的方法命名：get/query 之类是读，其余动词基本都是写。
# 通用透传 `call` 命令靠这个判断要不要走审批——否则一条 call 就能绕过所有闸门。
# 判断不了的一律当成写：多要一次审批的代价，远小于误改账户。
_READ_PREFIXES = ("get", "query", "list", "search", "describe", "download", "check")


def is_write_method(method):
    name = (method or "").strip().lower()
    if not name:
        return True
    return not name.startswith(_READ_PREFIXES)
