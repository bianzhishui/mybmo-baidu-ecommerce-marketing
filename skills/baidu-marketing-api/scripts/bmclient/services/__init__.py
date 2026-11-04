"""services 层：按百度服务类划分的业务语义封装。

约定：
  - 每个模块只依赖 client.call()，互相不引用（低耦合）
  - 函数只做「参数整形 + 结果归一化」，不处理鉴权、重试、错误码
新增能力时照这个模式加一个模块即可，不需要动传输层。

模块：
  kr       关键词规划师（拓词）
  account  账户与资金（只读）
  transfer 跨账户投放方案复制（A → B）
"""

from . import account, kr, transfer

__all__ = ["account", "kr", "transfer"]
