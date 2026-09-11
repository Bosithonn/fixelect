#!/usr/bin/env bash
# ==============================================================================
# Fixelect macOS build: Fixelect.app (with its AI engine inside) -> Fixelect.dmg
#
#   ./build_dmg.sh
#
# Optional environment (set in CI from repository secrets):
#   DEVELOPER_ID          "Developer ID Application: Name (TEAMID)" - sign for Gatekeeper
#   APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD
#                         notarize the DMG and staple the ticket
# Without them the app is ad-hoc signed and the DMG includes a first-open helper.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="Fixelect"
DIST_DIR="$SCRIPT_DIR/dist"
BUILD_DIR="$SCRIPT_DIR/build"
APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
DMG_PATH="$DIST_DIR/$APP_NAME.dmg"
STAGING_DIR="$DIST_DIR/dmg_staging"
ENTITLEMENTS="$SCRIPT_DIR/entitlements.plist"

# Pinned llama.cpp Metal build shipped inside the app (the app never downloads
# code at runtime). Keep in sync with tools/downloader_mac.py.
ENGINE_URL="https://github.com/ggml-org/llama.cpp/releases/download/b4600/llama-b4600-bin-macos-arm64.zip"
ENGINE_SHA256="b1bfd80df6eca26ef304df47135069dfdf282fa4dcfba1a684e1ff857728973a"

echo "== Building $APP_NAME for macOS"

command -v pyinstaller >/dev/null || { echo "PyInstaller missing: pip3 install -r requirements.txt"; exit 1; }

# 1. App bundle
rm -rf "$APP_BUNDLE" "$DMG_PATH" "$STAGING_DIR"
pyinstaller --clean Fixelect_Mac.spec -y

# 2. The AI engine, verified against its pinned checksum
mkdir -p "$BUILD_DIR"
ENGINE_ZIP="$BUILD_DIR/llama-engine.zip"
if [ ! -f "$ENGINE_ZIP" ] || [ "$(shasum -a 256 "$ENGINE_ZIP" | cut -d ' ' -f 1)" != "$ENGINE_SHA256" ]; then
    echo ">> Downloading the llama.cpp engine"
    curl -fsSL -o "$ENGINE_ZIP" "$ENGINE_URL"
fi
if [ "$(shasum -a 256 "$ENGINE_ZIP" | cut -d ' ' -f 1)" != "$ENGINE_SHA256" ]; then
    echo "Error: engine checksum mismatch"; exit 1
fi
rm -rf "$BUILD_DIR/llama-engine"
unzip -q "$ENGINE_ZIP" -d "$BUILD_DIR/llama-engine"
ENGINE_DEST="$APP_BUNDLE/Contents/Frameworks/llama"
mkdir -p "$ENGINE_DEST"
cp "$BUILD_DIR/llama-engine/build/bin/llama-server" "$BUILD_DIR/llama-engine/build/bin/"*.dylib "$ENGINE_DEST/"
chmod 755 "$ENGINE_DEST"/*
echo ">> Engine bundled: $(ls "$ENGINE_DEST" | tr '\n' ' ')"

# 3. Code signing (inside-out: engine binaries, then the app)
if [ -n "${DEVELOPER_ID:-}" ]; then
    echo ">> Signing with $DEVELOPER_ID"
    SIGN=(codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$DEVELOPER_ID")
    for f in "$ENGINE_DEST"/*; do "${SIGN[@]}" "$f"; done
    "${SIGN[@]}" --deep "$APP_BUNDLE"
    codesign --verify --deep --strict --verbose=2 "$APP_BUNDLE"
else
    echo ">> No DEVELOPER_ID: ad-hoc signing (Gatekeeper will ask the user to confirm on first open)"
    for f in "$ENGINE_DEST"/*; do codesign --force --sign - "$f"; done
    codesign --force --deep --sign - --entitlements "$ENTITLEMENTS" "$APP_BUNDLE"
fi

# 4. DMG
mkdir -p "$STAGING_DIR"
cp -R "$APP_BUNDLE" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/Applications"
NOTARIZE=0
if [ -n "${DEVELOPER_ID:-}" ] && [ -n "${APPLE_ID:-}" ] && [ -n "${APPLE_TEAM_ID:-}" ] && [ -n "${APPLE_APP_PASSWORD:-}" ]; then
    NOTARIZE=1
fi
if [ "$NOTARIZE" = 0 ]; then
    # Unsigned builds only: macOS quarantines apps from unknown developers.
    cat << 'EOF' > "$STAGING_DIR/First_Time_Open_Helper.command"
#!/bin/bash
echo "Fixelect - first-open helper for builds that are not notarized"
if [ -d "/Applications/Fixelect.app" ]; then
    xattr -cr /Applications/Fixelect.app 2>/dev/null || true
    open /Applications/Fixelect.app
else
    echo "Drag Fixelect.app into Applications first."
fi
sleep 2
EOF
    chmod +x "$STAGING_DIR/First_Time_Open_Helper.command"
fi
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGING_DIR" -ov -format UDZO "$DMG_PATH"
rm -rf "$STAGING_DIR"

# 5. Notarization
if [ "$NOTARIZE" = 1 ]; then
    codesign --force --timestamp --sign "$DEVELOPER_ID" "$DMG_PATH"
    echo ">> Notarizing (this can take a few minutes)"
    xcrun notarytool submit "$DMG_PATH" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" \
        --password "$APPLE_APP_PASSWORD" --wait
    xcrun stapler staple "$DMG_PATH"
    spctl --assess --type open --context context:primary-signature -v "$DMG_PATH" || true
fi

shasum -a 256 "$DMG_PATH" | awk '{print $1}' > "$DMG_PATH.sha256"
echo "== Built $DMG_PATH"
echo "   SHA-256 $(cat "$DMG_PATH.sha256")   notarized: $([ "$NOTARIZE" = 1 ] && echo yes || echo no)"
