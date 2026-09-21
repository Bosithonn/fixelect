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
ENGINE_TAG="b10917"   # supports Gemma 4 and Qwen 3 (the old b4600 did not)
ENGINE_URL="https://github.com/ggml-org/llama.cpp/releases/download/$ENGINE_TAG/llama-$ENGINE_TAG-bin-macos-arm64.tar.gz"
ENGINE_SHA256="3deb6ddac52ae7afa5768a10a26288214f2d635a4f7b13ceb96ddbb60ade993a"

echo "== Building $APP_NAME for macOS"

command -v pyinstaller >/dev/null || { echo "PyInstaller missing: pip3 install -r requirements.txt"; exit 1; }

# 1. App bundle
rm -rf "$APP_BUNDLE" "$DMG_PATH" "$STAGING_DIR"
pyinstaller --clean Fixelect_Mac.spec -y

# 2. The AI engine, verified against its pinned checksum
mkdir -p "$BUILD_DIR"
ENGINE_TGZ="$BUILD_DIR/llama-engine-$ENGINE_TAG.tar.gz"
if [ ! -f "$ENGINE_TGZ" ] || [ "$(shasum -a 256 "$ENGINE_TGZ" | cut -d ' ' -f 1)" != "$ENGINE_SHA256" ]; then
    echo ">> Downloading the llama.cpp engine ($ENGINE_TAG)"
    curl -fsSL --retry 5 --retry-delay 5 --retry-all-errors -o "$ENGINE_TGZ" "$ENGINE_URL"
fi
if [ "$(shasum -a 256 "$ENGINE_TGZ" | cut -d ' ' -f 1)" != "$ENGINE_SHA256" ]; then
    echo "Error: engine checksum mismatch"; exit 1
fi
rm -rf "$BUILD_DIR/llama-engine"
mkdir -p "$BUILD_DIR/llama-engine"
tar -xzf "$ENGINE_TGZ" -C "$BUILD_DIR/llama-engine"
ENGINE_DEST="$APP_BUNDLE/Contents/Frameworks/llama"
mkdir -p "$ENGINE_DEST"
# cp -R keeps the dylib version symlinks (libllama.dylib -> libllama.0.dylib) intact.
cp -R "$BUILD_DIR/llama-engine/llama-$ENGINE_TAG/." "$ENGINE_DEST/"
[ -x "$ENGINE_DEST/llama-server" ] || { echo "Error: llama-server missing from the engine archive"; exit 1; }
echo ">> Engine bundled: $(ls "$ENGINE_DEST" | wc -l | tr -d ' ') files, $(du -sh "$ENGINE_DEST" | cut -f1)"
# Mach-O files to sign (symlinks are signed through their targets).
ENGINE_BINARIES=$(find "$ENGINE_DEST" -type f \( -name "*.dylib" -o -perm -u+x \))

# 3. Code signing (inside-out: engine binaries, then the app)
if [ -n "${DEVELOPER_ID:-}" ]; then
    echo ">> Signing with $DEVELOPER_ID"
    SIGN=(codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$DEVELOPER_ID")
    for f in $ENGINE_BINARIES; do "${SIGN[@]}" "$f"; done
    "${SIGN[@]}" --deep "$APP_BUNDLE"
    codesign --verify --deep --strict --verbose=2 "$APP_BUNDLE"
else
    echo ">> No DEVELOPER_ID: ad-hoc signing (Gatekeeper will ask the user to confirm on first open)"
    for f in $ENGINE_BINARIES; do codesign --force --sign - "$f"; done
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
    # Builds that are not notarized: Gatekeeper blocks the first open (a helper
    # script would be blocked too), so explain the steps in plain text.
    cat << 'EOF' > "$STAGING_DIR/How to open Fixelect.txt"
How to open Fixelect
====================

1. Drag Fixelect onto the Applications folder in this window.

2. Open Fixelect from Applications. macOS says it can't verify the app,
   because it is not notarized by Apple yet. Click Done.

3. Open System Settings > Privacy & Security, scroll down and click
   "Open Anyway" next to Fixelect. Enter your Mac password.

4. Open Fixelect again. Setup downloads the AI model (about 2 GB).

5. Allow Accessibility when asked, so Fixelect can fix the text you select.


Instead of steps 2 and 3, you can paste this into Terminal:

    xattr -dr com.apple.quarantine /Applications/Fixelect.app && open /Applications/Fixelect.app


Fixelect lives in the menu bar at the top right, not in the Dock.
Select text in any app, then double-tap Option to fix it
or double-tap Shift to polish it.

Help: https://github.com/Bosithonn/fixelect/issues
EOF
fi
# hdiutil fails now and then on CI machines ("Resource busy"): try a few times
for attempt in 1 2 3 4; do
    if hdiutil create -volname "$APP_NAME" -srcfolder "$STAGING_DIR" -ov -format UDZO "$DMG_PATH"; then
        break
    fi
    if [ "$attempt" = 4 ]; then echo "Error: hdiutil could not create the DMG"; exit 1; fi
    echo ">> hdiutil failed (attempt $attempt), retrying"
    sleep $((attempt * 10))
done
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
