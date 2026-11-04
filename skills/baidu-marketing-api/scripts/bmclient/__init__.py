"""bmclient：百度营销 API 客户端核心库。

分层（依赖方向单向向下，不允许反向引用）：
    bmctl.py（CLI 薄壳）
        └── services/*        业务语义：拓词、账户、余额
              └── transport   HTTP + 鉴权 header + 重试 + 错误解析
                    ├── auth      令牌刷新 / 换取
                    ├── config    凭据来源解析
                    └── errors    错误码释义
运行时依赖（若有）由 bmctl.py 头部的 PEP 723 内联元数据声明。
"""

from .config import load_credential
from .transport import BaiduClient

__all__ = ["BaiduClient", "load_credential"]

# 这里刻意不放 __version__：版本号只在 .codebuddy-plugin/plugin.json 维护一处。
# 之前那个 "1.0.0" 早已和专家包版本脱节，留着只会误导排查。
