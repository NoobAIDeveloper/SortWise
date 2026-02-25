#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Activating virtual environment..."
source "$SCRIPT_DIR/venv/bin/activate"

echo "==> Installing backend dependencies..."
pip install -r "$SCRIPT_DIR/backend/requirements.txt" -q
pip install pyinstaller -q

echo "==> Building Python backend with PyInstaller..."
cd "$SCRIPT_DIR/backend"

pyinstaller \
  --name main \
  --onefile \
  --hidden-import=exifread \
  --hidden-import=PIL \
  --hidden-import=PIL.Image \
  --hidden-import=geopy \
  --hidden-import=geopy.geocoders \
  --hidden-import=geopy.geocoders.nominatim \
  main.py

echo "==> Copying binary to frontend/resources/..."
mkdir -p "$SCRIPT_DIR/frontend/resources"
cp dist/main "$SCRIPT_DIR/frontend/resources/main"
chmod +x "$SCRIPT_DIR/frontend/resources/main"

echo "==> Cleaning up PyInstaller build artifacts..."
rm -rf build dist main.spec

echo "==> Backend build complete → frontend/resources/main"
