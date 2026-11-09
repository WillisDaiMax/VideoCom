#!/bin/bash
# 构建 VideoCom.app：编译 SwiftUI 壳，把 Python core、图标一起放进 .app。
# 用法：cd app && ./build_app.sh [版本号]      → 生成 app/build/VideoCom.app
set -euo pipefail
cd "$(dirname "$0")"
VERSION="${1:-0.2.0}"
swift build -c release
BIN="$(swift build -c release --show-bin-path)/VideoCom"
APP="build/VideoCom.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/core"
cp "$BIN" "$APP/Contents/MacOS/VideoCom"
rsync -a --exclude '__pycache__' ../core/videocom "$APP/Contents/Resources/core/"
cp Resources/Logo.png Resources/AppIcon.png "$APP/Contents/Resources/"

# 图标：AppIcon.png（1024）→ AppIcon.icns
ICONSET="build/AppIcon.iconset"
rm -rf "$ICONSET" && mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s Resources/AppIcon.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) Resources/AppIcon.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>VideoCom</string>
  <key>CFBundleDisplayName</key><string>VideoCom</string>
  <key>CFBundleIdentifier</key><string>io.github.videocom</string>
  <key>CFBundleExecutable</key><string>VideoCom</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>${VERSION}</string>
  <key>CFBundleVersion</key><string>${VERSION}</string>
  <key>CFBundleDevelopmentRegion</key><string>en</string>
  <key>CFBundleLocalizations</key><array><string>en</string><string>zh-Hans</string><string>zh-Hant</string><string>ja</string></array>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.video</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
codesign --force --deep -s - "$APP" >/dev/null 2>&1 || true   # 临时签名（ad-hoc），没有开发者证书
echo "完成：$(pwd)/$APP"
