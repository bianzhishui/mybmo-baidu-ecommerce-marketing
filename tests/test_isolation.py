"""测试环境护栏自检。

这几条守的不是业务逻辑，而是「测试不许碰用户真实数据」。
起因：`test_transfer` 漏设 BM_HOME，50 条假记录写进了
`~/.workbuddy/baidu-marketing/audit/`，把审计的可信度弄没了。

护栏有两层：
- conftest 的 autouse fixture：默认把 BM_HOME 指到临时目录（默认安全）
- conftest 的 session canary：跑完比对真实审计目录，被动过就当场失败（兜底）
"""

import os
from pathlib import Path

from bmclient import config
from bmclient.services import write

REAL_HOME = Path.home() / ".workbuddy" / "baidu-marketing"


def test_bm_home_is_isolated_by_default():
    home = os.environ.get("BM_HOME")

    assert home, "conftest 的 autouse fixture 应该在每个测试里设好 BM_HOME"
    assert REAL_HOME not in Path(home).parents
    assert Path(home) != REAL_HOME


def test_audit_path_outside_real_home():
    path = write.audit_path().resolve()

    assert REAL_HOME.resolve() not in path.parents, f"审计会落到真实目录：{path}"


def test_config_home_dir_follows_isolation():
    assert config.home_dir().resolve() != REAL_HOME.resolve()
