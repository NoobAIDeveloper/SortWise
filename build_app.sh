#!/bin/bash
# Build SortWise into a distributable macOS .dmg
# Usage: ./build_app.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================"
echo " SortWise — Full Build"
echo "============================================"

echo ""
echo "[ 1 / 2 ]  Building Python backend..."
bash "$SCRIPT_DIR/build_backend.sh"

echo ""
echo "[ 2 / 2 ]  Building Electron app + DMG..."
cd "$SCRIPT_DIR/frontend"
npm run electron-pack

echo ""
echo "============================================"
echo " Build complete!"
echo " Output: frontend/dist/"
ls "$SCRIPT_DIR/frontend/dist/"*.dmg 2>/dev/null && echo " ↑ Share this DMG with users." || true
echo "============================================"
