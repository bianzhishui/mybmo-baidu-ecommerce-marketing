"""共享 fixture 与测试环境护栏。

两件事：
1. 用 tempfile.mkdtemp 而不是 pytest 内置的 tmp_path：本机沙箱对 `pytest-of-*`
   这类固定基目录的重复 mkdir 会抛 EEXIST，导致用例第二次运行时全部报错。
2. **强制隔离所有会落盘的副作用**（BM_HOME）。审计日志是按 BM_HOME 定位的，
   漏设一次就会把测试假数据写进用户真实目录——真踩过：50 条 alias=target 的假记录
   混进了真实审计目录，直接毁掉审计的可信度。
   所以隔离放在 conftest 里做 autouse，而不是靠每个测试文件自己记得。
"""

import shutil
import tempfile
from pathlib import Path

import pytest

# 真实数据目录。测试一旦漏隔离就会写到这里，必须守死。
REAL_BAIDU_HOME = Path.home() / ".baidu-marketing"


@pytest.fixture
def tmp_dir():
    path = Path(tempfile.mkdtemp(prefix="mybmo-test-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolate_bm_home(tmp_dir, monkeypatch):
    """每个测试都默认跑在临时 BM_HOME 下。

    需要真实目录的用例请显式 monkeypatch.delenv("BM_HOME") 并自担风险——
    那会同时被下面的 canary 抓到。
    """
    monkeypatch.setenv("BM_HOME", str(tmp_dir / "bm-home"))
    return tmp_dir / "bm-home"


def _snapshot_real_audit():
    """记录真实审计目录的文件指纹，用于会话前后比对。"""
    audit = REAL_BAIDU_HOME / "audit"
    if not audit.is_dir():
        return {}
    return {p.name: p.stat().st_size for p in sorted(audit.glob("*.jsonl"))}


@pytest.fixture(scope="session", autouse=True)
def guard_real_home():
    """兜底 canary：整个会话跑完，真实审计目录必须一字未动。

    isolate_bm_home 是「默认安全」，这一层是「万一漏了就当场炸」——
    静默污染比报错可怕得多，报错至少你知道发生过什么。
    """
    before = _snapshot_real_audit()
    yield
    after = _snapshot_real_audit()

    added = set(after) - set(before)
    changed = {k for k in before if k in after and after[k] != before[k]}

    if added or changed:
        raise AssertionError(
            "测试污染了真实审计目录！\n"
            f"  目录: {REAL_BAIDU_HOME / 'audit'}\n"
            f"  新增: {sorted(added)}\n"
            f"  变更: {sorted(changed)}\n"
            "某个测试没有隔离 BM_HOME，或显式删掉了它。"
            "请检查该用例为什么绕过了 conftest 的 autouse fixture。"
        )
