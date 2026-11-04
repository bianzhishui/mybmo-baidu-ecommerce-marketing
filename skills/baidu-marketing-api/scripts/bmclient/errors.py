"""百度营销 API 错误类型与错误码释义。

只做一件事：把百度返回的 code / message / position 翻译成人能看懂的修复建议。
调用方（services 层）不需要知道错误码细节，统一抛 BaiduApiError。
"""

from __future__ import annotations

# code -> (现象, 修复建议)
ERROR_HINTS = {
    8002: (
        "The Json message you provided is invalid",
        "鉴权信息放错了位置。userName / accessToken / action 必须放在请求体 JSON 的 "
        "header 字段里，不能放 HTTP 头。",
    ),
    81012: (
        "Username is not set in request header",
        "header 里的键名必须是大写 N 的 userName。写成 username 会报此错。",
    ),
    81020: (
        "The username information in the request is incorrect",
        "userName 与 accessToken 不是同一个账户 —— 多账户场景下的典型错误。"
        "token 属于 A 账户，却填了 B 账户的中文名。用 --account <alias> 指定账户，"
        "不要手动混用凭据。",
    ),
    84261: (
        "The token is invalid in encrypt",
        "accessToken 不能放在 token 字段。token 字段属于旧的加密通道，"
        "OAuth 令牌必须放 accessToken。",
    ),
    87091: (
        "request url is invalid",
        "服务名或方法名大小写错误。KRService 的 KR 两个字母都必须大写，"
        "方法名是驼峰 getKRByQuery 而非 getKrbyQuery。",
    ),
    901701: (
        "Seed Word is null",
        "body.query 为空。关键词规划师必须传种子词。",
    ),
    99912: (
        "JSON invalid",
        "参数类型不对。例如 getKRByQuery 的 query 是字符串而不是数组。",
    ),
    89406: (
        "The access token you provided is invalidate",
        "字面意思是令牌失效，但同一个令牌能调通别的接口时，真实原因是该接口所属权限未开通。"
        "先用 kr 命令验证令牌本身是否可用，再确认应用是否申请了对应能力域的权限。",
    ),
}


class BaiduApiError(RuntimeError):
    """百度 API 返回 status != 0，或网络层失败。"""

    def __init__(self, message, *, code=None, position=None, service=None, method=None):
        super().__init__(message)
        self.code = code
        self.position = position
        self.service = service
        self.method = method

    @property
    def hint(self):
        entry = ERROR_HINTS.get(self.code)
        return entry[1] if entry else None

    def to_dict(self):
        return {
            "error": str(self),
            "code": self.code,
            "position": self.position,
            "service": self.service,
            "method": self.method,
            "hint": self.hint,
        }


class CredentialError(RuntimeError):
    """凭据缺失、过期且无法刷新、或刷新被拒绝。"""


class WriteNotPermitted(RuntimeError):
    """写操作被本地策略拦住（权限域未开通时的保护性拦截）。

    这不是网络或权限报错，而是脚本主动拒绝执行——避免在无权限的情况下
    反复调用写接口，或误以为写成功。
    """


class ApprovalRequired(RuntimeError):
    """写操作缺少用户审批，或审批凭据与当前报文不符。

    写操作不可逆，必须走「预览 → 用户确认 → 凭预览里的 digest 执行」两步。
    缺少 digest 说明没预览过；digest 不匹配说明预览之后报文被改过——
    两种情况都必须重新来过，不能放行。
    """


class WriteFailed(RuntimeError):
    """写入已经开始但中途失败（例如建了计划却拿不到 campaignId）。

    与 WriteNotPermitted 的区别：那个是「一条都没发」，这个是「发了一半」。
    必须在错误信息里说清已在账户里留下了什么，否则用户不知道要去清理。
    """


class DryRunRequested(Exception):
    """dry-run 模式下的短路信号。

    用异常而不是返回特殊字典，是为了不污染 services 层的返回类型——
    业务函数始终可以假定自己拿到的是真实 data 或正常异常。
    """

    def __init__(self, url, payload, *, approval=None):
        super().__init__("dry-run")
        self.url = url
        self.payload = payload
        self.approval = approval

    def to_dict(self):
        safe = {
            "header": {
                "userName": self.payload["header"]["userName"],
                "accessToken": "***",
                "action": self.payload["header"]["action"],
            },
            "body": self.payload.get("body"),
        }
        result = {"dry_run": True, "url": self.url, "payload": safe}
        if self.approval:
            result["approval"] = self.approval
        return result
