"""测试环境护栏自检。

这几条守的不是业务逻辑，而是「测试不许碰用户真实数据」。
起因：`test_transfer` 漏设 BM_HOME，50 条假记录写进了真实审计目录，把审计的可信度弄没了。

护栏有两层：
- conftest 的 autouse fixture：默认把 BM_HOME 指到临时目录（默认安全）
- conftest 的 session canary：跑完比对真实审计目录，被动过就当场失败（兜底）

真实目录有两个：当前默认 `~/.baidu-marketing` 与历史位置 `~/.workbuddy/baidu-marketing`。
两边都要守——老用户可能还落在后者。
"""

import os
from pathlib import Path

from bmclient import config
from bmclient.services import write

REAL_HOMES = (
    Path.home() / ".baidu-marketing",
    Path.home() / ".workbuddy" / "baidu-marketing",
)


def test_bm_home_is_isolated_by_default():
    home = Path(os.environ["BM_HOME"]).resolve()

    for real in REAL_HOMES:
        resolved = real.resolve()
        assert home != resolved, f"BM_HOME 指向了真实目录：{resolved}"
        assert resolved not in home.parents, f"BM_HOME 落在真实目录之内：{resolved}"


def test_audit_path_outside_real_home():
    path = write.audit_path().resolve()

    for real in REAL_HOMES:
        assert real.resolve() not in path.parents, f"审计会落到真实目录：{path}"


def test_config_home_dir_follows_isolation():
    resolved = config.home_dir().resolve()

    for real in REAL_HOMES:
        assert resolved != real.resolve(), f"home_dir 返回了真实目录：{resolved}"
