"""跨账户投放方案复制（账户 A → 账户 B）。

场景：把账户 A 里某个商品/某一组计划的投放结构，在账户 B 里重建一遍。

核心思路是「中性方案 + 去 id 重放」：
    1. describe() 从源账户拉出四级结构（计划 → 单元 → 关键词 → 创意）
    2. 转成与账户无关的中性结构，所有 *Id 字段一律剔除
    3. apply() 在目标账户按新 id 逐级重建

为什么必须去 id：计划/单元/关键词的 id 是账户内唯一的，把 A 的 id 带到 B
会直接被拒或写到错误的物料上。strip_ids() 是这里唯一不能省的一步。

写操作（--execute）按 campaign → adgroup → keyword → creative 逐级创建，
**每级都要用上一级接口返回的新 id**。这不是可以批量拼完再一次性发出的请求，
必须串行——所以 apply() 在 execute 模式下是一棵依赖树，不是一串独立报文。

⚠️ 读接口（get_*）与写接口（add_*）都需要「投放管理」权限。
当前应用只有「工具」域时会返回 89406，错误会被翻译成 WriteNotPermitted。
本模块的字段以百度官方文档为准，首次使用前务必先 --dry-run 打印报文人工核对。
"""

from __future__ import annotations

import copy

import approval
import svc_write as write_ops
from errors import BaiduApiError, WriteFailed, WriteNotPermitted

# 跨账户时必须剔除的字段：任何以 Id 结尾的、以及账户/用户标识
ID_SUFFIXES = ("Id", "Ids", "ID", "IDs")
ACCOUNT_KEYS = {"userId", "userName", "accountId", "ucId", "openId", "mccId"}
PARENT_CAMPAIGN = "$parent_campaign_id"
PARENT_ADGROUP = "$parent_adgroup_id"
TEMPLATE_VERSION = 1
# 尚未取得四层物料的官方写 schema / 测试账户证据，绝不猜测暂停字段。
VERIFIED_PAUSE_FIELDS = {}


def pause_blockers(plan):
    """返回当前方案中尚未验证可强制暂停的层级。"""
    levels = set()
    for campaign in plan.get("campaigns") or []:
        levels.add("campaign")
        for group in campaign.get("adgroups") or []:
            levels.add("adgroup")
            if group.get("keywords"):
                levels.add("keyword")
            if group.get("creatives"):
                levels.add("creative")
    return sorted(level for level in levels if level not in VERIFIED_PAUSE_FIELDS)


def pause_blocked_error(blockers):
    return WriteNotPermitted(
        "跨账户复制要求新物料默认暂停，但以下层级的可写暂停字段尚未经官方协议或"
        f"测试账户验证：{', '.join(blockers)}。已拒绝执行，未发送任何请求；"
        "可先用 dry-run 核对模板，或提供脱敏协议证据后再启用。"
    )


def strip_ids(obj):
    """递归删除 id 类字段，保留纯业务配置。"""
    if isinstance(obj, dict):
        cleaned = {}
        for key, value in obj.items():
            if key in ACCOUNT_KEYS or key.endswith(ID_SUFFIXES):
                continue
            cleaned[key] = strip_ids(value)
        return cleaned
    if isinstance(obj, list):
        return [strip_ids(item) for item in obj]
    return obj


def _level(client, service, method, body, *, product_line="sms"):
    """统一读取一层物料，失败时补上足够的上下文便于排查。"""
    return client.call(service, method, body, product_line=product_line) or []


def describe(client, campaign_ids, *, product_line="sms", with_creatives=True):
    """拉取源账户的投放结构，返回中性方案（不含任何 id）。

    campaign_ids 为空时尝试拉全量计划（部分账户需要显式传 id）。
    """
    body = {"campaignIds": list(campaign_ids)} if campaign_ids else {}
    campaigns = _level(client, "CampaignService", "getCampaign", body, product_line=product_line)

    plan = {
        "source": {
            "user_name": client.cred.user_name,
            "alias": client.cred.alias,
            "campaign_ids": list(campaign_ids or []),
        },
        "product_line": product_line,
        "campaigns": [],
    }

    for campaign in campaigns:
        cid = campaign.get("campaignId")
        node = {
            "name": campaign.get("campaignName") or f"campaign-{cid}",
            "config": strip_ids(campaign),
            "adgroups": [],
        }

        adgroups = _level(
            client, "AdgroupService", "getAdgroup",
            {"campaignIds": [cid]}, product_line=product_line,
        )
        for adgroup in adgroups:
            aid = adgroup.get("adgroupId")
            group_node = {
                "name": adgroup.get("adgroupName") or f"adgroup-{aid}",
                "config": strip_ids(adgroup),
                "keywords": [],
                "creatives": [],
            }

            words = _level(
                client, "KeywordService", "getWord",
                {"adgroupIds": [aid]}, product_line=product_line,
            )
            group_node["keywords"] = [strip_ids(w) for w in words]

            if with_creatives:
                creatives = _level(
                    client, "CreativeService", "getCreative",
                    {"adgroupIds": [aid]}, product_line=product_line,
                )
                group_node["creatives"] = [strip_ids(c) for c in creatives]

            node["adgroups"].append(group_node)

        plan["campaigns"].append(node)

    plan["stats"] = summarize_plan(plan)
    return plan


def summarize_plan(plan):
    campaigns = plan.get("campaigns") or []
    adgroups = sum(len(c.get("adgroups") or []) for c in campaigns)
    keywords = sum(
        len(g.get("keywords") or [])
        for c in campaigns
        for g in (c.get("adgroups") or [])
    )
    creatives = sum(
        len(g.get("creatives") or [])
        for c in campaigns
        for g in (c.get("adgroups") or [])
    )
    return {
        "campaigns": len(campaigns),
        "adgroups": adgroups,
        "keywords": keywords,
        "creatives": creatives,
    }


def rename_plan(plan, *, prefix="", suffix=""):
    """给所有名字加前后缀，避免在目标账户里重名难辨。

    同时同步 config 内的 *Name 字段——只改外层 name 会造成
    "步骤名带前缀、实际创建出来的物料不带前缀"的错位。
    """
    result = copy.deepcopy(plan)
    for campaign in result.get("campaigns") or []:
        campaign["name"] = f"{prefix}{campaign['name']}{suffix}"
        _apply_name(campaign.get("config"), "campaignName", campaign["name"])
        for group in campaign.get("adgroups") or []:
            group["name"] = f"{prefix}{group['name']}{suffix}"
            _apply_name(group.get("config"), "adgroupName", group["name"])
    return result


def _apply_name(config, key, name):
    if isinstance(config, dict) and key in config:
        config[key] = name


def build_steps(plan, *, product_line="sms"):
    """把中性方案展开成待执行报文。

    预览与真实执行共用这一份，避免「预览看到的」和「实际发出的」不一致。
    """
    _require_writable_line(product_line)
    if not isinstance(plan, dict) or not isinstance(plan.get("campaigns"), list):
        raise ValueError("投放方案必须是含 campaigns 数组的 JSON 对象")
    steps = []
    for ci, campaign in enumerate(plan.get("campaigns") or []):
        if not isinstance(campaign, dict) or not campaign.get("name"):
            raise ValueError(f"第 {ci + 1} 个计划缺少 name")
        campaign_id = f"c{ci}"
        campaign_config = strip_ids(campaign.get("config"))
        if VERIFIED_PAUSE_FIELDS.get("campaign"):
            field, value = VERIFIED_PAUSE_FIELDS["campaign"]
            campaign_config[field] = value
        steps.append(
            {
                "level": "campaign",
                "step_id": campaign_id,
                "name": campaign["name"],
                "service": "CampaignService",
                "method": "addCampaign",
                # apply 也要再 strip 一次：plan 可能来自外部文件，未经 describe 清洗。
                # id 泄漏到目标账户是跨账户复制最危险的错误，必须双重保险。
                "body": {write_ops.ENVELOPES["campaign"]: [campaign_config]},
                "product_line": product_line,
            }
        )
        for gi, group in enumerate(campaign.get("adgroups") or []):
            if not isinstance(group, dict) or not group.get("name"):
                raise ValueError(f"计划 {campaign['name']} 的第 {gi + 1} 个单元缺少 name")
            group_id = f"{campaign_id}.g{gi}"
            group_config = strip_ids(group.get("config"))
            group_config["campaignId"] = PARENT_CAMPAIGN
            if VERIFIED_PAUSE_FIELDS.get("adgroup"):
                field, value = VERIFIED_PAUSE_FIELDS["adgroup"]
                group_config[field] = value
            steps.append(
                {
                    "level": "adgroup", "step_id": group_id, "parent_step": campaign_id,
                    "name": group["name"], "parent": campaign["name"],
                    "service": "AdgroupService", "method": "addAdgroup",
                    "body": {write_ops.ENVELOPES["adgroup"]: [group_config]},
                    "product_line": product_line,
                }
            )
            words = [strip_ids(w) for w in group.get("keywords") or []]
            if words:
                write_ops._guard_count(len(words), "keyword")
                for word in words:
                    word["adgroupId"] = PARENT_ADGROUP
                    if VERIFIED_PAUSE_FIELDS.get("keyword"):
                        field, value = VERIFIED_PAUSE_FIELDS["keyword"]
                        word[field] = value
                steps.append(
                    {
                        "level": "keyword", "step_id": f"{group_id}.k0",
                        "parent_step": group_id, "parent": group["name"],
                        "name": f"{group['name']} / 关键词", "count": len(words), "service": "KeywordService", "method": "addWord",
                        "body": {write_ops.ENVELOPES["keyword"]: words},
                        "product_line": product_line,
                    }
                )
            creatives = [strip_ids(c) for c in group.get("creatives") or []]
            if creatives:
                write_ops._guard_count(len(creatives), "creative")
                for creative in creatives:
                    creative["adgroupId"] = PARENT_ADGROUP
                    if VERIFIED_PAUSE_FIELDS.get("creative"):
                        field, value = VERIFIED_PAUSE_FIELDS["creative"]
                        creative[field] = value
                steps.append(
                    {
                        "level": "creative", "step_id": f"{group_id}.r0",
                        "parent_step": group_id, "parent": group["name"],
                        "name": f"{group['name']} / 创意", "count": len(creatives), "service": "CreativeService", "method": "addCreative",
                        "body": {write_ops.ENVELOPES["creative"]: creatives},
                        "product_line": product_line,
                    }
                )
    return steps


def apply(client, plan, *, dry_run=True, product_line="sms", stop_on_error=True,
          confirm=None):
    """在目标账户按新 id 逐级重建。默认 dry_run，只有显式传 False 才会写。

    dry_run=True：只返回待执行报文与审批 digest，不发请求。
    dry_run=False：先校验 confirm 与报文是否匹配，再串行写入。

    审批覆盖整棵步骤树，不是逐级审批——因为用户同意的是「把这套投放复制过去」这件事，
    不该在中间再被问三次。
    """
    _require_writable_line(product_line)
    if plan.get("product_line") and plan["product_line"] != product_line:
        raise ValueError("方案文件的产品线与 --line 不一致，请核对后重试")
    steps = build_steps(plan, product_line=product_line)
    alias = getattr(client.cred, "alias", "")
    stats = summarize_plan(plan)
    blockers = pause_blockers(plan)

    if dry_run:
        summary = (
            f"在账户 {alias or '默认账户'} 重建 {stats['campaigns']} 个计划 / "
            f"{stats['adgroups']} 个单元 / {stats['keywords']} 个关键词 / "
            f"{stats['creatives']} 个创意"
        )
        return {
            "dry_run": True,
            "target": {"alias": client.cred.alias, "user_name": client.cred.user_name},
            "product_line": product_line,
            "stats": stats,
            "steps": steps,
            "required_state": "pause",
            "executable": not blockers,
            "execution_blockers": blockers,
            "inherited_fields": ["budget", "URL", "定向及其他非 ID 配置"],
            "approval": approval.describe(alias, steps, summary=summary),
            "notice": (
                "以上为待执行报文，未发送。把 approval.confirm_card 弹给用户点选，"
                "点「确认执行」后再带 --execute --confirm <digest> 执行。"
            ),
        }

    digest = approval.require(confirm, alias, steps)
    if blockers:
        raise pause_blocked_error(blockers)
    return _execute(
        client, plan, steps=steps, stop_on_error=stop_on_error, approval_digest=digest,
        product_line=product_line,
    )


def _execute(client, plan, *, steps, stop_on_error=True, approval_digest=None,
             product_line="sms"):
    """只执行共享模板；除父 ID 占位符外，不允许改变审批后的报文。"""
    created = {"campaigns": [], "adgroups": [], "keywords": [], "creatives": []}
    errors = []
    ids = {}
    id_keys = {"campaign": "campaignId", "adgroup": "adgroupId",
               "keyword": "wordId", "creative": "creativeId"}
    current = None
    try:
        for step in steps:
            current = step
            if step.get("parent_step") and step["parent_step"] not in ids:
                raise WriteFailed(f"父级 {step['parent_step']} 尚未创建，停止后代写入")
            body = copy.deepcopy(step["body"])
            parent_id = ids.get(step.get("parent_step"))
            for item in body[write_ops.ENVELOPES[step["level"]]]:
                if step["level"] == "adgroup":
                    item["campaignId"] = _resolve_placeholder(item["campaignId"], parent_id)
                elif step["level"] in ("keyword", "creative"):
                    item["adgroupId"] = _resolve_placeholder(item["adgroupId"], parent_id)
            data = write_ops.call_raw(
                client, step["level"], step["service"], step["method"],
                body[write_ops.ENVELOPES[step["level"]]], _preapproved=True,
                _approval_digest=approval_digest, product_line=product_line,
            )
            new_ids = _pick_ids(
                data, id_keys[step["level"]], step["name"],
                expected=1 if step["level"] in ("campaign", "adgroup") else None,
                requested=len(body[write_ops.ENVELOPES[step["level"]]]),
            )
            ids[step["step_id"]] = new_ids[0]
            for new_id in new_ids:
                row = {"name": step["name"], id_keys[step["level"]]: new_id}
                if step.get("parent_step"):
                    row["parent_step"] = step["parent_step"]
                created[f"{step['level']}s"].append(row)
    except (BaiduApiError, WriteNotPermitted, WriteFailed, ValueError) as exc:
        errors.append({
            "step_id": current.get("step_id") if current else None,
            "level": current.get("level") if current else None,
            "name": current.get("name") if current else None,
            "error": str(exc),
        })
        failure = WriteFailed(
            f"跨账户复制在 {current.get('step_id') if current else '未知步骤'} 中断：{exc}"
        )
        failure.created = created
        failure.errors = errors
        failure.current_step = current
        failure.audit = str(write_ops.audit_path())
        raise failure from exc
    return {
        "dry_run": False,
        "target": {"alias": client.cred.alias, "user_name": client.cred.user_name},
        "created": created, "errors": errors, "audit": str(write_ops.audit_path()),
    }


def _resolve_placeholder(value, parent_id):
    if value not in (PARENT_CAMPAIGN, PARENT_ADGROUP):
        raise WriteFailed("复制模板含未声明的父 ID 字段，拒绝执行")
    if parent_id is None:
        raise WriteFailed("父级 ID 尚未解析，拒绝继续")
    return parent_id


def _pick_ids(data, key, label, *, expected=None, requested=None):
    """返回实际响应 ID；无法确认完整结果时停止，不能按请求数冒充已创建。"""
    candidates = data if isinstance(data, list) else [data]
    ids = [item[key] for item in candidates if isinstance(item, dict) and item.get(key)]
    if (not ids or len(ids) != len(candidates)
            or (expected is not None and len(ids) != expected)
            or (requested is not None and len(ids) != requested)):
        raise WriteFailed(
            f"{label} 创建后接口未返回完整 {key}，无法继续。"
            f"已创建的物料需要在后台手工清理。原始返回：{str(data)[:300]}"
        )
    return ids


def _pick_id(data, key, label):
    return _pick_ids(data, key, label, expected=1)[0]


def _require_writable_line(product_line):
    if product_line != "sms":
        raise WriteNotPermitted(
            "信息流（feed）写操作暂未支持：信封名与 SMS 不同（campaignFeedTypes 等），"
            "需要单独适配后再开放。当前请用 sms 产品线，或用 call 接口自行透传。"
        )


def clone(source_client, target_client, campaign_ids, *,
          prefix="", suffix="", dry_run=True, product_line="sms", confirm=None):
    """一步完成：从源账户读出方案，改名后投放到目标账户。"""
    plan = describe(source_client, campaign_ids, product_line=product_line)
    if prefix or suffix:
        plan = rename_plan(plan, prefix=prefix, suffix=suffix)
    result = apply(
        target_client, plan, dry_run=dry_run, product_line=product_line, confirm=confirm
    )
    result["source"] = plan.get("source")
    result["plan"] = plan
    return result
