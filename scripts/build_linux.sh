#!/bin/bash

# 获取脚本所在目录的上一级目录
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")

echo "Project Root: $PROJECT_ROOT"
cd "$PROJECT_ROOT"

if ! command -v pyinstaller &> /dev/null; then
    echo "Error: pyinstaller not found. Install with: pip install pyinstaller"
    exit 1
fi

echo "Cleaning build artifacts..."
rm -rf dist build *.spec


echo "Packaging with PyInstaller..."
pyinstaller ./main.py -F --name gis --clean

if [ ! -f "dist/gis" ]; then
    echo "Error: Build failed."
    exit 1
fi

echo "Organizing files..."
DIST_DIR="dist/gis_linux_pkg"
mkdir -p "$DIST_DIR/conf"

mv dist/gis "$DIST_DIR/"

echo "Generating default Linux config.json..."
CURRENT_USER_HOME=$HOME
cat > "$DIST_DIR/conf/config.json" <<EOF
{
    "lean": {
        "lean_remote_ip": "114.115.165.12",
        "lean_remote_user": "sia",
        "lean_remote_pwd": "Sia8soft",
        "lean_remote_path": "/home/sia/Documents/files/gits/base_lean",
        "lean_local_path": "${CURRENT_USER_HOME}/lean"
    },
    "base_url": "http://114.115.200.146:8082/"
}
EOF

echo "Installation:" > "$DIST_DIR/README.txt"
echo "1. Run: sudo ./gis install" >> "$DIST_DIR/README.txt"
echo "2. Run: source /etc/profile.d/gis_env.sh" >> "$DIST_DIR/README.txt"

echo "Compressing..."
cd dist
tar -czvf gis_linux_x64.tar.gz gis_linux_pkg/

echo "=========================================="
echo "Build Complete: dist/gis_linux_x64.tar.gz"
echo "=========================================="