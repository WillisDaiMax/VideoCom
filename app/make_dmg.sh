#!/bin/bash
# 把 build/VideoCom.app 打成 dmg（含"拖到应用程序"快捷方式）
# 用法：cd app && ./make_dmg.sh [版本号]      → build/VideoCom-<版本>.dmg
set -euo pipefail
cd "$(dirname "$0")"
VERSION="${1:-0.2.0}"
STAGE="build/dmg"
rm -rf "$STAGE" && mkdir -p "$STAGE"
cp -R build/VideoCom.app "$STAGE/"
ln -s /Applications "$STAGE/Applications"
DMG="build/VideoCom-${VERSION}.dmg"
rm -f "$DMG"
hdiutil create -volname "VideoCom ${VERSION}" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
echo "完成：$(pwd)/$DMG"
