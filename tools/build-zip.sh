#!/usr/bin/env bash
# 从本仓库生成可上传到 WorkBuddy 开发平台的专家包 zip。
#
# 流程与 expert-manager 技能一致：同步 → 校验 → 注册 → 打包。
# 之所以要多一步「同步到专家目录」，是因为 validate_expert.py 会强制检查
# 专家必须在 $WORKBUDDY_CONFIG_DIR/plugins/marketplaces/my-experts/plugins 下，
# 在仓库目录里直接打包会被判为「专家不在专家目录下」。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="mybmo-baidu-ecommerce-marketing"

CONFIG_DIR="${WORKBUDDY_CONFIG_DIR:-$HOME/.workbuddy}"
MARKETPLACE="$CONFIG_DIR/plugins/marketplaces/my-experts"
TARGET="$MARKETPLACE/plugins/$NAME"

EXPERT_MANAGER_DIR="${EXPERT_MANAGER_DIR:-/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/skills/expert-manager/scripts}"

if [ ! -f "$EXPERT_MANAGER_DIR/package_expert.py" ]; then
  echo "❌ 找不到 expert-manager 脚本：$EXPERT_MANAGER_DIR" >&2
  echo "   用 EXPERT_MANAGER_DIR=/path/to/skills/expert-manager/scripts 指定" >&2
  exit 1
fi

echo "① 同步源码到专家目录"
echo "   $ROOT  ->  $TARGET"
mkdir -p "$TARGET"
# 用**白名单**同步：只把分发包该有的东西拷过去。
#
# 之前用黑名单（--exclude 一堆），结果是仓库根目录出现任何没预料到的文件
# （编辑器备份、临时探测文件、别人的 .bak）都会被悄悄打进 zip——
# 实际就发生过：一个 4 字节的沙箱探测文件 c_i_vpl4 混进了 1.8.1 的包。
# 白名单的失效方式是「少打一个文件，validate 会报错」，比「多打垃圾」安全得多。
# --delete-excluded：光有 --delete 不会删掉被 --exclude 规则挡下的文件，
# 而白名单的最后一条就是 `--exclude '*'`，所以必须加它才能清走目标目录里的残留。
#
# 下面这批 exclude 必须排在第一个 --include 之前：rsync 是**首条匹配即定**，
# 放到 --include '/skills/**' 后面就全部失效，一个几百 MB 的 .venv 会被打进包。
# 也不能加前导斜杠——要匹配 skills/ 下任意层级的同名项。
rsync -a --delete --delete-excluded \
  --exclude '__pycache__/' \
  --exclude '.venv/' \
  --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' \
  --exclude '*.pyc' \
  --exclude '*.pyo' \
  --exclude '*.so' \
  --exclude '*.pyd' \
  --exclude '*.dylib' \
  --exclude '*.py.lock' \
  --include '/.codebuddy-plugin/' \
  --include '/.codebuddy-plugin/**' \
  --include '/agents/' \
  --include '/agents/**' \
  --include '/avatars/' \
  --include '/avatars/**' \
  --include '/skills/' \
  --include '/skills/**' \
  --include '/README.md' \
  --exclude '*' \
  "$ROOT/" "$TARGET/"

# 兜底检查：分发包根目录除了 README.md 不该有别的文件。
# 目录结构是「根目录只放 README + 几个约定目录」，多出文件一定是混进来的。
STRAY="$(find "$TARGET" -maxdepth 1 -type f ! -name 'README.md' -print)"
if [ -n "$STRAY" ]; then
  echo "❌ 分发包根目录出现意外文件：" >&2
  echo "$STRAY" >&2
  echo "   打包已中止。请确认这些文件是否该随包分发。" >&2
  exit 1
fi

echo
echo "② 校验专家包规范"
python3 "$EXPERT_MANAGER_DIR/validate_expert.py" "$TARGET"

echo
echo "③ 注册到 marketplace.json"
python3 "$EXPERT_MANAGER_DIR/register_expert.py" "$TARGET"

echo
echo "④ 打包"
python3 "$EXPERT_MANAGER_DIR/package_expert.py" "$TARGET" "$ROOT/dist"

echo
echo "✅ 可上传的包：$ROOT/dist/$NAME.zip"
