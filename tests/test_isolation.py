"""测试环境护栏自检。

这几条守的不是业务逻辑，而是「测试不许碰用户真实数据」。
起因：`test_transfer` 漏设 BM_HOME，50 条假记录写进了真实审计目录，把审计的可信度弄没了。

护栏有两层：
- conftest 的 autouse fixture：默认把 BM_HOME 指到临时目录（默认安全）
- conftest 的 session canary：跑完比对真实审计目录，被动过就当场失败（兜底）
"""

import os
from pathlib import Path

from bmclient import config
from bmclient.services import write

REAL_HOME = Path.home() / ".baidu-marketing"


def test_bm_home_is_isolated_by_default():
    home = Path(os.environ["BM_HOME"]).resolve()
    real = REAL_HOME.resolve()

    assert home != real, f"BM_HOME 指向了真实目录：{real}"
    assert real not in home.parents, f"BM_HOME 落在真实目录之内：{real}"


def test_audit_path_outside_real_home():
    path = write.audit_path().resolve()

    assert REAL_HOME.resolve() not in path.parents, f"审计会落到真实目录：{path}"


def test_config_home_dir_follows_isolation():
    assert config.home_dir().resolve() != REAL_HOME.resolve()
