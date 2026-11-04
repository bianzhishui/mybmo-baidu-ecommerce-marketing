#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""百度营销 API 命令行入口（多账户）。

只做三件事：解析参数、调用 services、渲染输出。
不含任何业务逻辑与网络细节，保证这层足够薄。

账户模型：一个 alias = 一个推广账户 = 一份独立凭据，凭据自持，不依赖外部服务。
    uv run bmctl.py auth exchange --code <authCode> --app-id <AppID> \
        --secret-key <SecretKey> --user-id <userId> --user-name "<账户中文名>" --alias wds02
    uv run bmctl.py accounts list
    uv run bmctl.py accounts use wds02
    uv run bmctl.py --account axd kr expand --seed "月季"

常用：
    uv run bmctl.py auth status
    uv run bmctl.py kr expand --seed "月季" --limit 30 --format md
    uv run bmctl.py kr multi --seeds "月季,花肥,缓释肥"
    uv run bmctl.py account balance
    uv run bmctl.py call --service CampaignService --method getCampaign --body '{}'

执行方式：
    推荐 `uv run bmctl.py <子命令>`。文件头的内联元数据（PEP 723）声明了依赖与
    Python 下限，uv 会据此准备一个隔离环境，不污染系统，也不需要 pip install。
    降级：机器上已有 Python 3.9+ 且 uv 不可用时，`python3 bmctl.py` 行为完全一致
    （dependencies 为空时，无需安装任何包即可直接运行）。
"""

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------- 解释器门槛
#
# 本文件**刻意不写** `from __future__ import annotations`：
# 那是 3.7 才有的 future 特性，在 3.6 上属编译期 SyntaxError，文件一个字节都不会执行，
# 守卫就永远兜不住。本文件没有任何类型注解，去掉它对运行期毫无影响。
# 新增代码不要再加回来，否则低版本又会变成裸 Traceback。

MIN_PYTHON = (3, 9)


def _write_line(stream, text):
    """写一行；编码不支持时退回纯 ASCII 提示，别让提示本身再抛异常。"""
    try:
        stream.write(text + "\n")
        stream.flush()
    except UnicodeEncodeError:
        ascii_text = text.encode("ascii", "replace").decode("ascii")
        stream.write(ascii_text + "\n")
        stream.flush()


def _check_python(version_info=None, *, out=None, err=None):
    """版本不足时给出可读提示并返回退出码 6；满足则返回 0。

    门槛只认 MIN_PYTHON 常量。曾经额外读 runtime.json 的 python_min，
    但那个值没有任何执行者——uv 读的是文件头的内联元数据——所以删掉了，
    避免同一个数字有三份拷贝。现在只有两处：内联元数据（uv 执行）与本常量（守卫执行），
    两者相等由测试锁死。
    """
    current = tuple(version_info or sys.version_info)[:2]
    required = MIN_PYTHON
    if current >= required:
        return 0

    required_text = ".".join(str(p) for p in required) + "+"
    current_text = ".".join(str(p) for p in current)
    payload = {
        "error": "运行环境不满足",
        "code": "PYTHON_VERSION",
        "required": required_text,
        "current": current_text,
        "executable": sys.executable,
        "platform": sys.platform,
        "hint": "建议改用 uv run <脚本路径> 执行，uv 会自动选一个 3.9+ 的解释器；"
                "若直接调用 python3，请先升级到 3.9+。",
    }
    # ensure_ascii=True：无论控制台是 cp936 还是被重定向到文件，都不会二次编码失败
    _write_line(out or sys.stdout, json.dumps(payload, ensure_ascii=True))
    _write_line(
        err or sys.stderr,
        f"[环境] 需要 Python {required_text}，当前是 {current_text}（{sys.executable}）。",
    )
    return 6


_min_python_status = _check_python()
if _min_python_status:
    raise SystemExit(_min_python_status)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bmclient import (  # noqa: E402
    BaiduClient,
    approval,
    auth,
    config,
    load_credential,
    oauthserver,
    render,
)
from bmclient.errors import (  # noqa: E402
    ApprovalRequired,
    BaiduApiError,
    CredentialError,
    DryRunRequested,
    WriteFailed,
    WriteNotPermitted,
)
from bmclient.services import account, kr, transfer, write  # noqa: E402


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
    # 注意 `%%`：argparse 会把 help 文案当 %-格式串处理，裸 % 在 3.14 上直接 ValueError
    p_link.add_argument("--callback", required=True, help="公网可达的回调地址，不能带 ? 或 %%")
    p_link.add_argument("--scope", default="", help="权限代码")
    p_link.add_argument("--state", default="", help="自定义 state，留空需配合 --developer-uid")
    p_link.add_argument("--developer-uid", default="", help="创建应用的开发者 uid")
    p_link.add_argument("--alias", default="", help="账户别名，会编进 state，供常驻服务区分账户")

    p_serve = leaf(auth_sub, "serve", "启动本地回调服务接收 authCode（仅监听本机）")
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
    p_clone.add_argument("--confirm", default=None,
                         help="预览输出里 approval.digest 的值；--execute 时必须带")

    # ---- write ----
    p_write = sub.add_parser(
        "write", help="写操作：关键词 / 计划 / 单元（默认 dry-run，加 --execute 才真正写入）"
    )
    wr = p_write.add_subparsers(dest="action", required=True)

    def execute_flag(p):
        p.add_argument("--execute", action="store_true",
                       help="真正写入账户（需投放管理权限，不加则只打印报文）")
        p.add_argument("--confirm", default=None,
                       help="预览输出里 approval.digest 的值；执行写操作必须带，防止跳过审批")
        return p

    p_wa = execute_flag(leaf(wr, "word-add", "向单元添加关键词"))
    p_wa.add_argument("--adgroup-id", type=int, required=True, dest="adgroup_id")
    p_wa.add_argument("--words", required=True, help="逗号分隔的词面，中英文逗号都行")
    p_wa.add_argument("--price", type=float,
                      help="每个词的出价（元）；多数接口要求必填，不填可能被拒")
    p_wa.add_argument("--phrase-type", type=int, dest="phrase_type",
                      help="1 精确 / 2 短语 / 3 广泛")
    p_wa.add_argument("--extra", default="", help="额外字段 JSON，合并进每个词")

    p_wu = execute_flag(leaf(wr, "word-update", "改关键词：出价 / 匹配模式 / 启停"))
    p_wu.add_argument("--items", help="keywordTypes 条目 JSON 数组")
    p_wu.add_argument("--items-file", dest="items_file", help="从文件读 JSON 数组")

    p_wd = execute_flag(leaf(wr, "word-delete", "按 id 删除关键词"))
    p_wd.add_argument("--word-ids", required=True, dest="word_ids", help="逗号分隔的 wordId")

    p_cu = execute_flag(leaf(wr, "campaign-update", "改计划：预算 / 启停"))
    p_cu.add_argument("--campaign-id", type=int, dest="campaign_id")
    p_cu.add_argument("--budget", type=float, help="日预算（元）")
    p_cu.add_argument("--status", help="enable / pause，或直接给数字状态码")
    p_cu.add_argument("--items", help="campaignTypes 条目 JSON 数组（批量时用）")
    p_cu.add_argument("--items-file", dest="items_file")

    p_au = execute_flag(leaf(wr, "adgroup-update", "改单元：出价 / 启停"))
    p_au.add_argument("--adgroup-id", type=int, dest="adgroup_id")
    p_au.add_argument("--price", type=float, help="单元出价（元）")
    p_au.add_argument("--status", help="enable / pause，或直接给数字状态码")
    p_au.add_argument("--items", help="adgroupTypes 条目 JSON 数组（批量时用）")
    p_au.add_argument("--items-file", dest="items_file")

    # ---- call ----
    p_call = leaf(sub, "call", "通用透传：调用任意百度接口")
    p_call.add_argument("--service", required=True, help="服务类名，如 CampaignService / KRService")
    p_call.add_argument("--method", required=True, help="方法名，支持 get_campaign 或 getCampaign")
    p_call.add_argument("--body", default="{}", help="JSON 字符串")
    p_call.add_argument("--body-file", help="从文件读 JSON 参数")
    p_call.add_argument("--line", choices=["sms", "feed"], default="sms", help="产品线，feed 走信息流网关")
    p_call.add_argument("--confirm", default=None,
                        help="方法名是写类（add/update/delete…）时的审批 digest，"
                             "由同一条命令加 --dry-run 预览得到")

    return parser


def _make_client_from(alias, args):
    cred = load_credential(alias)
    return BaiduClient(cred, timeout=getattr(args, "timeout", 45),
                       dry_run=getattr(args, "dry_run", False)), cred


def _make_client(args):
    return _make_client_from(getattr(args, "account", None), args)


def _configure_stdio():
    """把标准输出统一成 UTF-8。

    Windows 控制台默认 cp936，中文之外的符号（例如 emoji、箭头）会抛
    UnicodeEncodeError。errors="replace" 让它降级成问号而不是崩掉。

    pytest 的 capsys、被父进程替换的流可能没有 reconfigure，所以整段容错——
    这里失败不该影响任何业务。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            continue


def main(argv=None):
    _configure_stdio()
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
        if args.group == "write":
            return _run_write(args)
        if args.group == "call":
            return _run_call(args)
    except DryRunRequested as exc:
        render.emit(exc.to_dict(), args.format)
        return 0
    except WriteNotPermitted as exc:
        render.emit({"error": "写操作被拦截", "message": str(exc)}, args.format)
        return 3
    except ApprovalRequired as exc:
        render.emit(
            {
                "error": "需要用户审批",
                "message": str(exc),
                "how": "先不带 --execute 跑一次预览，把报文给用户确认，"
                       "再用预览里的 approval.digest 作为 --confirm 重跑。",
            },
            args.format,
        )
        return 4
    except WriteFailed as exc:
        render.emit(
            {
                "error": "写入中断",
                "message": str(exc),
                "hint": "已创建的物料需要到百度后台手工清理，不能假装没发生。",
            },
            args.format,
        )
        return 5
    except CredentialError as exc:
        render.emit({"error": "凭据错误", "message": str(exc)})
        return 2
    except FileNotFoundError as exc:
        render.emit({"error": "账户不存在", "message": str(exc)})
        return 2
    except OSError as exc:
        # Windows 上文件被占用/无权限是高频路径（凭据写入、审计落盘、--out 导出）。
        # FileNotFoundError 是 OSError 子类，必须排在它前面。
        # 注意：网络超时不能落进这里——transport 已把 socket.timeout 收进 BaiduApiError。
        render.emit(
            {
                "error": "本地文件读写失败",
                "message": str(exc),
                "hint": "常见原因是文件被其他程序占用或目录无写权限；关闭占用程序后重试。",
            },
            args.format,
        )
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
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        # 默认只绑回环；容器/反代确实需要对外监听，那是用户的显式选择，
        # 但必须留一条痕迹，避免"以为只在本机"。
        print(
            f"[serve] [警告] 已绑定非回环地址 {args.host}，授权回调可被同网络访问。"
            "仅在容器/反向代理场景使用，用完请关闭。",
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
            print(f"[serve] [失败] {record.detail}", file=sys.stderr, flush=True)
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
            print(f"[serve] [失败] {record.detail}", file=sys.stderr, flush=True)
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
        print(f"[serve] [成功] {record.detail}", file=sys.stderr, flush=True)

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
        # 与 write 保持一致：显式 --dry-run 优先，其次才看 --execute。
        # 否则 `--execute --dry-run` 两条自相矛盾的参数会走到半截怪异行为。
        result = transfer.apply(
            target_client, plan,
            dry_run=bool(getattr(args, "dry_run", False)) or not args.execute,
            product_line=args.line,
            confirm=args.confirm,
        )
        result["source"] = plan.get("source")
        render.emit(result, args.format, title="跨账户复制")
        return 0
    return 0


def _run_write(args):
    """写操作统一入口。dry-run 由 client 的 dry_run 开关控制，命中时抛 DryRunRequested。"""
    client, _ = _make_client_from(getattr(args, "account", None), args)
    # 默认预览：只有显式 --execute 才写；同时给了 --dry-run 则以 --dry-run 为准
    client.dry_run = bool(getattr(args, "dry_run", False)) or not args.execute

    if args.action == "word-add":
        extra = _parse_body(args.extra) if args.extra else None
        data = write.add_words(
            client, args.adgroup_id, args.words,
            price=args.price, phrase_type=args.phrase_type, extra=extra,
            confirm=args.confirm,
        )
        title = "添加关键词"
    elif args.action == "word-update":
        data = write.update_words(client, _load_items(args), confirm=args.confirm)
        title = "修改关键词"
    elif args.action == "word-delete":
        data = write.delete_words(client, args.word_ids, confirm=args.confirm)
        title = "删除关键词"
    elif args.action == "campaign-update":
        items = _load_items(args)
        if items is None:
            items = [write.campaign_item(args.campaign_id, budget=args.budget, status=args.status)]
        data = write.update_campaigns(client, items, confirm=args.confirm)
        title = "修改计划"
    elif args.action == "adgroup-update":
        items = _load_items(args)
        if items is None:
            items = [write.adgroup_item(args.adgroup_id, price=args.price, status=args.status)]
        data = write.update_adgroups(client, items, confirm=args.confirm)
        title = "修改单元"
    else:
        raise ValueError(f"未知写操作：{args.action}")

    render.emit(
        {"result": data, "written": not client.dry_run, "audit": str(write.audit_path())},
        args.format,
        title=title,
    )
    return 0


def _load_items(args):
    """--items / --items-file 二选一；都没给返回 None，由调用方走便捷参数。"""
    raw = getattr(args, "items", None)
    path = getattr(args, "items_file", None)
    if path:
        raw = Path(path).read_text(encoding="utf-8")
    if not raw:
        return None
    data = _parse_body(raw)
    if not isinstance(data, list) or not data:
        raise ValueError("--items 必须是非空 JSON 数组")
    return data


def _run_call(args):
    client, _ = _make_client(args)
    if args.body_file:
        body = json.loads(Path(args.body_file).read_text(encoding="utf-8"))
    else:
        body = _parse_body(args.body)

    # 透传是最大的后门：一条 call 就能调 addWord 改账户。
    # 所以方法名一像写操作，就必须走和其他写命令同一套审批，并同样落审计。
    if approval.is_write_method(args.method):
        steps = [{"service": args.service, "method": args.method, "body": body}]
        alias = getattr(client.cred, "alias", "")
        if client.dry_run:
            try:
                client.call(args.service, args.method, body, product_line=args.line)
            except DryRunRequested as exc:
                exc.approval = approval.describe(
                    alias, steps, summary=f"透传调用 {args.service}/{args.method}"
                )
                raise
        digest = approval.require(getattr(args, "confirm", None), alias, steps)
        write.audit_external(client, args.service, args.method, body, digest=digest)

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
