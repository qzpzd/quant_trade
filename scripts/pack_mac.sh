#!/bin/bash
# 在 macOS 上打包形迹 QuantTrade Web 便携包（含依赖与 data_cache）
# 用法：
#   cd quant_trade
#   chmod +x scripts/pack_mac.sh
#   ./scripts/pack_mac.sh
#   ./scripts/pack_mac.sh --no-data

set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "本脚本必须在 macOS 上运行（PyInstaller 不能交叉编译）。"
  exit 1
fi

PYTHON="${PYTHON:-python3}"
if [[ ! -d .venv ]]; then
  "$PYTHON" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt pyinstaller

python -m pack_desktop --zip "$@"
echo "完成: dist/QuantTrade-mac/ 与 dist/QuantTrade-mac.zip"
