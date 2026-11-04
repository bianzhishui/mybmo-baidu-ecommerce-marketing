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
# 开发用文件不进分发包：tests/、pyproject.toml、uv.lock、.venv、.git 等
# 注意 /tools 与 /dist 必须用前导斜杠锚定，否则会误伤
# skills/baidu-marketing-api/scripts 这类同名的嵌套目录。
rsync -a --delete \
  --exclude '.git' \
  --exclude '.gitignore' \
  --exclude '.workbuddy' \
  --exclude '.venv' \
  --exclude '/tests' \
  --exclude '/tools' \
  --exclude '/dist' \
  --exclude '/pyproject.toml' \
  --exclude '/uv.lock' \
  --exclude '/.python-version' \
  --exclude '__pycache__' \
  --exclude '.ruff_cache' \
  --exclude '.pytest_cache' \
  --exclude '.DS_Store' \
  "$ROOT/" "$TARGET/"

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
