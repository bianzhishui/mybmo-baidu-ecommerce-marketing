#!/usr/bin/env python3
"""百度营销 API 命令行入口（多账户）。

只做三件事：解析参数、调用 services、渲染输出。
不含任何业务逻辑与网络细节，保证这层足够薄。

账户模型：一个 alias = 一个推广账户 = 一份独立凭据，凭据自持，不依赖任何外部库。
    python3 bmctl.py auth exchange --code <authCode> --app-id <AppID> \
        --secret-key <SecretKey> --user-id <userId> --user-name "<账户中文名>" --alias wds02
    python3 bmctl.py accounts list
    python3 bmctl.py accounts use wds02
    python3 bmctl.py --account axd kr expand --seed "月季"

常用：
    python3 bmctl.py auth status
    python3 bmctl.py kr expand --seed "月季" --limit 30 --format md
    python3 bmctl.py kr multi --seeds "月季,花肥,缓释肥"
    python3 bmctl.py account balance
    python3 bmctl.py call --service CampaignService --method getCampaign --body '{}'
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bmclient import BaiduClient, auth, config, load_credential, oauthserver, render  # noqa: E402
from bmclient.errors import (  # noqa: E402
    BaiduApiError,
    CredentialError,
    DryRunRequested,
    WriteNotPermitted,
)
from bmclient.services import account, kr, transfer  # noqa: E402


def _common_parser():
    """让 --format / --dry-run / --timeout / --account 写在子命令后面也能生效。

    用 SUPPRESS 作默认值，子命令未显式传入时不会覆盖顶层已解析的值。
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS,
                        help="只打印将要请求的 URL 与报文，不发请求")
    common.add_argument("--format", choices=["json", "md"], default=argparse.SUPPRESS,
                        help="输出格式，默认 json")
    common.add_argument("--timeout", type=int, default=argparse.SUPPRESS,
                        help="单次请求超时秒数")
    common.add_argument("--account", default=argparse.SUPPRESS,
                        help="指定账户 alias，不填则用默认账户（BM_ACCOUNT）")
    return common


def build_parser():
    common = _common_parser()
    parser = argparse.ArgumentParser(
        prog="bmctl",
        description="百度营销开放平台命令行（多账户 / 关键词拓词 / 账户数据 / 通用透传）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印将要请求的 URL 与报文，不发请求")
    parser.add_argument("--format", choices=["json", "md"], default="json", help="输出格式，默认 json")
    parser.add_argument("--timeout", type=int, default=45, help="单次请求超时秒数")
    parser.add_argument("--account", help="指定账户 alias，不填则用默认账户")

    sub = parser.add_subparsers(dest="group", required=True)

    def leaf(parent, name, help_text):
        return parent.add_parser(name, help=help_text, parents=[common])

    # ---- accounts：多账户管理 ----
    p_accounts = sub.add_parser("accounts", help="多账户管理（列表 / 切换 / 导入 / 删除）")
    acc_ops = p_accounts.add_subparsers(dest="action", required=True)

    leaf(acc_ops, "list", "列出所有已授权账户")

    p_use = leaf(acc_ops, "use", "设置默认账户")
    p_use.add_argument("alias", help="账户别名")

    p_rm = leaf(acc_ops, "remove", "删除一个账户的本地凭据")
    p_rm.add_argument("alias")

    # ---- auth：当前账户的令牌 ----
    p_auth = sub.add_parser("auth", help="授权与令牌管理")
    auth_sub = p_auth.add_subparsers(dest="action", required=True)

    leaf(auth_sub, "status", "查看当前凭据状态（令牌已脱敏）")

    p_refresh = leaf(auth_sub, "refresh", "强制刷新 accessToken")
    p_refresh.add_argument("--no-save", action="store_true", help="不写回凭据文件")

    leaf(auth_sub, "whoami", "调用 getUserInfo 查账户名与权限范围")

    p_link = leaf(auth_sub, "link", "生成授权链接（发给推广账户持有人）")
    p_link.add_argument("--app-id", required=True)
    p_link.add_argument("--callback", required=True, help="公网可达的回调地址，不能带 ? 或 %")
    p_link.add_argument("--scope", default="", help="权限代码")
    p_link.add_argument("--state", default="", help="自定义 state，留空需配合 --developer-uid")
    p_link.add_argument("--developer-uid", default="", help="创建应用的开发者 uid")
    p_link.add_argument("--alias", default="", help="账户别名，会编进 state，供常驻服务区分账户")

    p_serve = leaf(auth_sub, "serve", "启动本地回调服务接收 authCode（零依赖，仅监听本机）")
    p_serve.add_argument("--port", type=int, default=8080)
    p_serve.add_argument("--host", default="127.0.0.1",
                         help="监听地址。默认只绑本机；容器内或反代在别的机器时才用 0.0.0.0")
    p_serve.add_argument("--path", default="/oauth/callback")
    p_serve.add_argument("--state", default="", help="state 的 base 部分；留空则用 --app-id + --developer-uid 推导")
    p_serve.add_argument("--developer-uid", default="")
    p_serve.add_argument("--wait", type=int, default=300, help="最长等待秒数，默认 300")
    p_serve.add_argument("--max", type=int, default=0,
                         help="接满 N 个账户后退出；0 表示不限制，只受 --wait 约束")
    p_serve.add_argument("--once", action="store_true", help="只接一个账户就退出（等价 --max 1）")
    p_serve.add_argument("--app-id", default="")
    p_serve.add_argument("--apps-file", default="",
                         help="应用清单 JSON，支持多个不同 AppID/密钥的应用共用一个服务")
    p_serve.add_argument("--callback", default="", help="公网回调地址，提供则顺带打印授权链接模板")
    p_serve.add_argument("--scope", default="")
    p_serve.add_argument("--secret-key", default="", help="提供则收到 authCode 后自动换令牌")
    p_serve.add_argument("--user-id", default="", help="回调未带 userId 时的兜底")
    p_serve.add_argument("--user-name", default="", help="不填则自动调 getUserInfo 取账户中文名")
    p_serve.add_argument("--alias", default="",
                         help="回调 state 未带别名时的默认账户名")
    p_serve.add_argument("--no-exchange", action="store_true", help="只接收 authCode，不自动换令牌")

    p_ex = leaf(auth_sub, "exchange", "用授权码换令牌（首次接入）")
    p_ex.add_argument("--code", required=True, help="回调拿到的 authCode，一次性")
    p_ex.add_argument("--app-id", required=True)
    p_ex.add_argument("--secret-key", required=True)
    p_ex.add_argument("--user-id", required=True, help="回调里的推广账户 userId")
    p_ex.add_argument("--user-name", default="", help="账户中文名，API 调用必填")
    p_ex.add_argument("--alias", default="", help="存为该 alias，不填则存为 default")

    # ---- kr ----
    p_kr = sub.add_parser("kr", help="关键词规划师")
    kr_sub = p_kr.add_subparsers(dest="action", required=True)

    p_expand = leaf(kr_sub, "expand", "单个种子词拓词")
    p_expand.add_argument("--seed", required=True)
    p_expand.add_argument("--limit", type=int, default=0, help="按搜索量降序截断条数，0 为全部")
    p_expand.add_argument("--summary", action="store_true", help="只输出聚合统计")

    p_multi = leaf(kr_sub, "multi", "多种子词拓词并去重合并")
    p_multi.add_argument("--seeds", required=True, help="逗号分隔的种子词")
    p_multi.add_argument("--limit-per-seed", type=int, default=0)

    # ---- account：账户业务数据 ----
    p_acc = sub.add_parser("account", help="账户与资金数据")
    acc_sub = p_acc.add_subparsers(dest="action", required=True)
    leaf(acc_sub, "info", "账户基本信息")
    leaf(acc_sub, "balance", "账户余额")
    p_pay = leaf(acc_sub, "payment", "付款记录")
    p_pay.add_argument("--body", default="{}", help="JSON 参数，默认 {}")

    # ---- transfer：跨账户复制 ----
    p_tr = sub.add_parser("transfer", help="跨账户复制投放方案（A 账户 → B 账户）")
    tr_sub = p_tr.add_subparsers(dest="action", required=True)

    p_desc = leaf(tr_sub, "describe", "从源账户导出投放结构为中性方案")
    p_desc.add_argument("--from-account", required=True, dest="from_account", help="源账户 alias")
    p_desc.add_argument("--campaign-ids", default="", help="逗号分隔的计划 id，留空尝试拉全量")
    p_desc.add_argument("--line", choices=["sms", "feed"], default="sms")
    p_desc.add_argument("--no-creatives", action="store_true", help="不拉创意，只导结构")
    p_desc.add_argument("--out", help="把方案写入 JSON 文件")

    p_clone = leaf(tr_sub, "clone", "把源账户方案投放到目标账户（默认 dry-run）")
    p_clone.add_argument("--from-account", dest="from_account", help="源账户 alias")
    p_clone.add_argument("--to-account", required=True, dest="to_account", help="目标账户 alias")
    p_clone.add_argument("--campaign-ids", default="", help="逗号分隔的计划 id")
    p_clone.add_argument("--plan-file", help="从 describe 导出的方案文件重放（与 --from-account 二选一）")
    p_clone.add_argument("--prefix", default="", help="给计划/单元名加前缀，便于区分来源")
    p_clone.add_argument("--suffix", default="", help="给计划/单元名加后缀")
    p_clone.add_argument("--line", choices=["sms", "feed"], default="sms")
    p_clone.add_argument("--execute", action="store_true",
                         help="真正写入目标账户（需投放管理权限，默认只 dry-run）")

    # ---- call ----
    p_call = leaf(sub, "call", "通用透传：调用任意百度接口")
    p_call.add_argument("--service", required=True, help="服务类名，如 CampaignService / KRService")
    p_call.add_argument("--method", required=True, help="方法名，支持 get_campaign 或 getCampaign")
    p_call.add_argument("--body", default="{}", help="JSON 字符串")
    p_call.add_argument("--body-file", help="从文件读 JSON 参数")
    p_call.add_argument("--line", choices=["sms", "feed"], default="sms", help="产品线，feed 走信息流网关")

    return parser


def _make_client_from(alias, args):
    cred = load_credential(alias)
    return BaiduClient(cred, timeout=getattr(args, "timeout", 45),
                       dry_run=getattr(args, "dry_run", False)), cred


def _make_client(args):
    return _make_client_from(getattr(args, "account", None), args)


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        if args.group == "accounts":
            return _run_accounts(args)
        if args.group == "auth":
            return _run_auth(args)
        if args.group == "kr":
            return _run_kr(args)
        if args.group == "account":
            return _run_account_data(args)
        if args.group == "transfer":
            return _run_transfer(args)
        if args.group == "call":
            return _run_call(args)
    except DryRunRequested as exc:
        render.emit(exc.to_dict(), args.format)
        return 0
    except WriteNotPermitted as exc:
        render.emit({"error": "写操作被拦截", "message": str(exc)}, args.format)
        return 3
    except CredentialError as exc:
        render.emit({"error": "凭据错误", "message": str(exc)})
        return 2
    except FileNotFoundError as exc:
        render.emit({"error": "账户不存在", "message": str(exc)})
        return 2
    except BaiduApiError as exc:
        render.emit(exc.to_dict(), args.format)
        return 1
    except ValueError as exc:
        render.emit({"error": "参数错误", "message": str(exc)})
        return 2
    return 0


# ---------- accounts ----------


def _run_accounts(args):
    if args.action == "list":
        rows = config.list_accounts()
        if not rows:
            render.emit(
                {
                    "total": 0,
                    "accounts": [],
                    "hint": "还没有任何账户。用 auth exchange --code <authCode> --app-id <AppID> "
                            "--secret-key <SecretKey> --user-id <userId> --user-name <账户中文名> "
                            "--alias <别名> 接入，完整步骤见 references/onboarding.md",
                },
                args.format,
            )
            return 0
        render.emit({"total": len(rows), "accounts": rows}, args.format, title="已授权账户")
        return 0

    if args.action == "use":
        alias = config.set_default_alias(args.alias)
        render.emit({"default_account": alias}, args.format)
        return 0

    if args.action == "remove":
        alias = config.validate_alias(args.alias)
        path = config.delete_account(alias)
        render.emit({"removed": alias, "path": str(path)}, args.format)
        return 0
    return 0


# ---------- auth ----------


def _run_auth(args):
    if args.action == "status":
        cred = load_credential(getattr(args, "account", None))
        payload = cred.to_public_dict()
        if not cred.user_name:
            payload["warning"] = "缺少 user_name（账户中文名），API 调用会被拒，请配置 BAIDU_USER_NAME"
        render.emit(payload, args.format)
        return 0

    if args.action == "refresh":
        cred = load_credential(getattr(args, "account", None))
        auth.refresh(cred, persist=not args.no_save)
        render.emit(cred.to_public_dict(), args.format)
        return 0

    if args.action == "whoami":
        cred = load_credential(getattr(args, "account", None))
        auth.ensure_valid(cred)
        data = auth.user_info(cred)
        name = data.get("masterName") or data.get("userName")
        if name and name != cred.user_name:
            data["_hint"] = f"建议把 user_name 更新为 {name}"
        render.emit({"credential": cred.to_public_dict(), "user_info": data}, args.format)
        return 0

    if args.action == "link":
        base = args.state
        if not base and args.developer_uid:
            base = oauthserver.default_state(args.app_id, args.developer_uid)
        if not base:
            raise ValueError("需要 --state，或提供 --developer-uid 自动生成")

        # 别名编进 state：常驻服务据此把令牌落到对应账户
        alias = (args.alias or "").strip().lower()
        if alias:
            alias = config.validate_alias(alias)
        state = oauthserver.compose_state(base, alias)

        url = oauthserver.build_auth_url(
            args.app_id, callback=args.callback, scope=args.scope, state=state
        )
        payload = {
            "auth_url": url,
            "state": state,
            "alias": alias or "(未指定)",
            "callback": args.callback,
            "next": "先用 auth serve 起好回调服务，再把链接发给对应账户的持有人",
        }
        if alias:
            payload["hint"] = (
                f"该链接回调后会自动存为账户 {alias}。"
                "可以给不同账户生成不同 --alias 的链接，一次性丢给多个人。"
            )
        render.emit(payload, args.format)
        return 0

    if args.action == "serve":
        return _run_auth_serve(args)

    if args.action == "exchange":
        cred = auth.exchange(
            args.code,
            args.app_id,
            args.secret_key,
            args.user_id,
            user_name=args.user_name,
            alias=args.alias or config.default_alias() or "default",
        )
        render.emit(cred.to_public_dict(), args.format)
        return 0
    return 0


def _load_apps(args):
    """构造应用清单：一个服务可同时对接多个 AppID / 开发者uid / SecretKey。"""
    apps = []
    if getattr(args, "apps_file", ""):
        path = Path(args.apps_file).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"应用清单不存在：{path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data.get("apps") or []:
            app_id = str(item.get("app_id") or "").strip()
            dev = str(item.get("developer_uid") or "").strip()
            base = str(item.get("base_state") or "").strip()
            if not base and app_id and dev:
                base = oauthserver.default_state(app_id, dev)
            if not base:
                continue
            apps.append({
                "label": item.get("label") or (app_id[:10] if app_id else base[:8]),
                "app_id": app_id,
                "developer_uid": dev,
                "secret_key": str(item.get("secret_key") or "").strip(),
                "base_state": base,
            })
    if not apps:
        base = args.state or (
            oauthserver.default_state(args.app_id, args.developer_uid)
            if args.app_id and args.developer_uid else ""
        )
        if base:
            apps.append({
                "label": args.app_id[:10] if args.app_id else "default",
                "app_id": args.app_id,
                "developer_uid": args.developer_uid,
                "secret_key": args.secret_key,
                "base_state": base,
            })
    return apps


def _run_auth_serve(args):
    """起本地回调服务：一次启动可连续接收多个应用、多个账户的授权回调。"""
    apps = _load_apps(args)
    if not apps:
        raise ValueError(
            "需要 --state、或 --app-id + --developer-uid，或用 --apps-file 提供应用清单"
        )

    max_callbacks = 1 if args.once else max(0, args.max)
    default_alias = (args.alias or "").strip().lower()
    if default_alias:
        default_alias = config.validate_alias(default_alias)

    local = f"http://{args.host}:{args.port}{args.path}" if args.host != "0.0.0.0" \
        else f"http://0.0.0.0:{args.port}{args.path}（已绑定所有网卡）"
    limit_text = f"最多 {max_callbacks} 个账户" if max_callbacks else "不限账户数"
    print(
        f"[serve] 监听 {local}（{limit_text}，最长 {args.wait} 秒）",
        file=sys.stderr, flush=True,
    )
    print(f"[serve] 已加载 {len(apps)} 个应用：", file=sys.stderr, flush=True)
    for a in apps:
        can = "可自动换令牌" if (a["app_id"] and a["secret_key"]) else "缺 app_id/secret_key，只收码"
        print(
            f"[serve]   · {a['label']} · appId {a['app_id'] or '(未填)'} · {can}",
            file=sys.stderr, flush=True,
        )

    if args.callback:
        print("[serve] 各应用授权链接示例：", file=sys.stderr, flush=True)
        for a in apps:
            if not a["app_id"]:
                continue
            sample = oauthserver.compose_state(a["base_state"], default_alias or "<alias>")
            print(
                f"  {a['label']}: "
                + oauthserver.build_auth_url(
                    a["app_id"], callback=args.callback, scope=args.scope, state=sample
                ),
                file=sys.stderr, flush=True,
            )
        print(
            "\n[serve] 建议用 auth link --app-id ... --alias 账户A 逐个生成，避免手改 alias\n",
            file=sys.stderr, flush=True,
        )

    print("[serve] 等待回调…（可连续接收多个账户，Ctrl+C 结束）", file=sys.stderr, flush=True)

    def handle(record):
        app = record.app or {}
        app_label = app.get("label") or app.get("app_id") or "未知应用"

        # 账户名优先取 state 里带的别名。若百度没有回传自定义 state
        # （把 state 覆盖成自己的值），就退化为按 userId 命名，
        # 避免多个账户全部落到同一个 default 上互相覆盖。
        alias = record.alias
        if alias:
            record.alias_source = "state"
        elif record.user_id:
            alias = f"acct_{record.user_id}"
            record.alias_source = "user_id"
        else:
            alias = default_alias or "default"
            record.alias_source = "fallback"
        record.alias = alias

        print(
            f"[serve] ← 回调：应用 {app_label} · 账户 {alias}（来自 {record.alias_source}）"
            f" · userId {record.user_id or '未知'}",
            file=sys.stderr, flush=True,
        )

        app_id = app.get("app_id") or args.app_id
        secret = app.get("secret_key") or args.secret_key

        if args.no_exchange:
            record.ok = True
            record.detail = "按 --no-exchange 只收码，未换令牌"
            return
        if not (app_id and secret):
            record.ok = True
            record.detail = "该应用缺 app_id 或 secret_key，只收码"
            return

        user_id = record.user_id or args.user_id
        if not user_id:
            record.ok = False
            record.detail = "回调未带 userId，无法换令牌"
            print(f"[serve] ✗ {record.detail}", file=sys.stderr, flush=True)
            return

        existing = config.read_account(alias)
        if existing and existing.app_id and app_id and existing.app_id != app_id:
            print(
                f"[serve] ! 账户 {alias} 原本属于应用 {existing.app_id[:10]}，"
                f"本次被 {app_id[:10]} 覆盖",
                file=sys.stderr, flush=True,
            )

        try:
            cred = auth.exchange(
                record.code, app_id, secret, user_id,
                user_name=args.user_name, alias=alias,
            )
        except Exception as exc:  # 单个账户失败不拖垮整个服务
            record.ok = False
            record.detail = f"换令牌失败：{exc}"
            print(f"[serve] ✗ {record.detail}", file=sys.stderr, flush=True)
            return

        if not args.user_name:
            try:
                info = auth.user_info(cred)
                name = info.get("masterName") or info.get("userName")
                if name:
                    cred.user_name = name
                    cred.save()
            except Exception as exc:
                print(f"[serve] ! 取账户名失败（令牌已保存）：{exc}", file=sys.stderr, flush=True)

        record.ok = True
        record.detail = f"已保存为账户 {cred.alias}（{cred.user_name or '未取到中文名'}）"
        print(f"[serve] ✓ {record.detail}", file=sys.stderr, flush=True)

    try:
        records, rejected = oauthserver.serve(
            port=args.port, path=args.path, apps=apps, timeout=args.wait,
            max_callbacks=max_callbacks, on_record=handle, host=args.host,
        )
    except OSError as exc:
        render.emit(
            {
                "received": 0,
                "reason": f"端口 {args.port} 无法监听：{exc}",
                "hint": "换个 --port，或先关掉占用该端口的进程",
            },
            args.format,
        )
        return 1

    payload = {
        "received": len(records),
        "apps": [a["label"] for a in apps],
        "accounts": [r.as_dict() for r in records],
        "rejected": rejected,
    }
    if not records:
        payload["reason"] = rejected[0] if rejected else "等待超时，未收到有效回调"
        payload["hint"] = "确认回调地址已填到对应应用的管理页，且公网隧道指向本机这个端口"
        render.emit(payload, args.format)
        return 1

    payload["next"] = "用 accounts list 查看已接入账户；多账户用 --account <alias> 指定操作对象"
    render.emit(payload, args.format)
    return 0


# ---------- 业务 ----------


def _run_kr(args):
    client, _ = _make_client(args)
    if args.action == "expand":
        words = kr.expand(client, args.seed, limit=args.limit)
        if args.summary:
            render.emit(kr.summarize(words), args.format)
        else:
            render.emit(
                {"seed": args.seed, "total": len(words), "words": words},
                args.format,
                title=f"关键词拓词 · {args.seed}",
            )
        return 0

    if args.action == "multi":
        # 中文逗号和顿号也接受：手工输入时几乎不会用英文逗号
        raw = args.seeds.replace("，", ",").replace("、", ",")
        seeds = [s.strip() for s in raw.split(",") if s.strip()]
        if not seeds:
            raise ValueError("--seeds 里没有有效种子词")
        data = kr.expand_many(client, seeds, limit_per_seed=args.limit_per_seed)
        data["summary"] = kr.summarize(data["words"])
        render.emit(data, args.format, title="多种子词拓词")
        return 0
    return 0


def _run_account_data(args):
    client, _ = _make_client(args)
    if args.action == "info":
        render.emit(account.info(client), args.format)
        return 0
    if args.action == "balance":
        render.emit(account.balance(client), args.format)
        return 0
    if args.action == "payment":
        render.emit(account.payment_record(client, _parse_body(args.body)), args.format)
        return 0
    return 0


def _parse_ids(raw):
    values = []
    for piece in (raw or "").split(","):
        piece = piece.strip()
        if not piece:
            continue
        if not piece.isdigit():
            raise ValueError(f"计划 id 必须是数字：{piece!r}")
        values.append(int(piece))
    return values


def _run_transfer(args):
    if args.action == "describe":
        client, _ = _make_client_from(args.from_account, args)
        plan = transfer.describe(
            client,
            _parse_ids(args.campaign_ids),
            product_line=args.line,
            with_creatives=not args.no_creatives,
        )
        if args.out:
            Path(args.out).write_text(
                json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            plan = {
                "written_to": str(Path(args.out).resolve()),
                "source": plan.get("source"),
                "stats": plan.get("stats"),
                "hint": f"已导出。投放前先核对，再执行 transfer clone --plan-file {args.out} --to-account <alias>",
            }
        render.emit(plan, args.format, title="投放方案导出")
        return 0

    if args.action == "clone":
        if args.plan_file:
            plan = json.loads(Path(args.plan_file).read_text(encoding="utf-8"))
        else:
            if not args.from_account:
                raise ValueError("需要 --from-account（读源账户）或 --plan-file（从文件重放）")
            source_client, _ = _make_client_from(args.from_account, args)
            plan = transfer.describe(
                source_client,
                _parse_ids(args.campaign_ids),
                product_line=args.line,
            )
        if args.prefix or args.suffix:
            plan = transfer.rename_plan(plan, prefix=args.prefix, suffix=args.suffix)

        target_client, _ = _make_client_from(args.to_account, args)
        result = transfer.apply(
            target_client, plan, dry_run=not args.execute, product_line=args.line
        )
        result["source"] = plan.get("source")
        render.emit(result, args.format, title="跨账户复制")
        return 0
    return 0


def _run_call(args):
    client, _ = _make_client(args)
    if args.body_file:
        body = json.loads(Path(args.body_file).read_text(encoding="utf-8"))
    else:
        body = _parse_body(args.body)
    data = client.call(args.service, args.method, body, product_line=args.line)
    render.emit(data, args.format)
    return 0


def _parse_body(raw):
    try:
        return json.loads(raw) if raw else {}
    except ValueError as exc:
        raise ValueError(f"--body 不是合法 JSON：{exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
