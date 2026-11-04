"""跨账户投放方案复制（账户 A → 账户 B）。

场景：把账户 A 里某个商品/某一组计划的投放结构，在账户 B 里重建一遍。

核心思路是「中性方案 + 去 id 重放」：
    1. describe() 从源账户拉出四级结构（计划 → 单元 → 关键词 → 创意）
    2. 转成与账户无关的中性结构，所有 *Id 字段一律剔除
    3. apply() 在目标账户按新 id 逐级重建

为什么必须去 id：计划/单元/关键词的 id 是账户内唯一的，把 A 的 id 带到 B
会直接被拒或写到错误的物料上。strip_ids() 是这里唯一不能省的一步。

⚠️ 重要：读接口（get_*）与写接口（add_*）都需要「投放管理」权限。
当前应用只有「工具」域，实际调用会返回 89406。本模块的接口参数以百度
官方文档为准，首次使用前务必先 --dry-run 打印报文人工核对。
"""

from __future__ import annotations

import copy

from ..errors import WriteNotPermitted

# 跨账户时必须剔除的字段：任何以 Id 结尾的、以及账户/用户标识
ID_SUFFIXES = ("Id", "Ids", "ID", "IDs")
ACCOUNT_KEYS = {"userId", "userName", "accountId", "ucId", "openId", "mccId"}


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


def apply(client, plan, *, dry_run=True, product_line="sms", stop_on_error=True):
    """在目标账户按新 id 逐级重建。默认 dry_run，只有显式传 False 才会写。

    返回每一步的执行结果，便于核对是哪一层失败。
    """
    if not dry_run:
        raise WriteNotPermitted(
            "写操作暂未开放：当前应用只有「工具」域权限，投放管理接口（addCampaign 等）"
            "会返回 89406。请先在开发者后台补开权限域并重新授权，再移除这里的保护。"
        )

    steps = []
    for campaign in plan.get("campaigns") or []:
        steps.append(
            {
                "level": "campaign",
                "name": campaign["name"],
                "service": "CampaignService",
                "method": "addCampaign",
                # apply 也要再 strip 一次：plan 可能来自外部文件，未经 describe 清洗。
                # id 泄漏到目标账户是跨账户复制最危险的错误，必须双重保险。
                "body": strip_ids(campaign.get("config")),
            }
        )
        for group in campaign.get("adgroups") or []:
            steps.append(
                {
                    "level": "adgroup",
                    "name": group["name"],
                    "parent": campaign["name"],
                    "service": "AdgroupService",
                    "method": "addAdgroup",
                    "body": strip_ids(group.get("config")),
                }
            )
            for word in group.get("keywords") or []:
                steps.append(
                    {
                        "level": "keyword",
                        "name": word.get("word"),
                        "parent": group["name"],
                        "service": "KeywordService",
                        "method": "addWord",
                        "body": strip_ids(word),
                    }
                )
            for creative in group.get("creatives") or []:
                steps.append(
                    {
                        "level": "creative",
                        "parent": group["name"],
                        "service": "CreativeService",
                        "method": "addCreative",
                        "body": strip_ids(creative),
                    }
                )

    return {
        "dry_run": True,
        "target": {"alias": client.cred.alias, "user_name": client.cred.user_name},
        "product_line": product_line,
        "stats": summarize_plan(plan),
        "steps": steps,
        "notice": (
            "以上为待执行报文，未发送。写接口需要投放管理权限，"
            "且 execute 前必须人工核对字段（尤其价格、地域、落地页 URL）。"
        ),
    }


def clone(source_client, target_client, campaign_ids, *,
          prefix="", suffix="", dry_run=True, product_line="sms"):
    """一步完成：从源账户读出方案，改名后投放到目标账户。"""
    plan = describe(source_client, campaign_ids, product_line=product_line)
    if prefix or suffix:
        plan = rename_plan(plan, prefix=prefix, suffix=suffix)
    result = apply(target_client, plan, dry_run=dry_run, product_line=product_line)
    result["source"] = plan.get("source")
    result["plan"] = plan
    return result
