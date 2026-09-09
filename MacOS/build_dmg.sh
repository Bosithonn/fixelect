#!/usr/bin/env bash
# ==============================================================================
# Fixelect macOS DMG Packaging Script
# Packages Fixelect.app into a standalone drag-and-drop Fixelect.dmg installer
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="Fixelect"
VOLUME_NAME="Fixelect"
DMG_NAME="Fixelect.dmg"
DIST_DIR="$SCRIPT_DIR/dist"
STAGING_DIR="$DIST_DIR/dmg_staging"
APP_BUNDLE="$DIST_DIR/$APP_NAME.app"

echo "======================================================="
echo " Building $APP_NAME for macOS (Phase 5 DMG Packaging)"
echo "======================================================="

# 1. Check if Fixelect.app is built, or build it via PyInstaller
if [ ! -d "$APP_BUNDLE" ]; then
    echo ">> $APP_BUNDLE not found. Building via PyInstaller..."
    if command -v pyinstaller &> /dev/null; then
        pyinstaller --clean Fixelect_Mac.spec -y
    else
        echo ">> PyInstaller not found. Attempting py2app build..."
        python3 setup.py py2app
    fi
fi

if [ ! -d "$APP_BUNDLE" ]; then
    echo "Error: Failed to create $APP_BUNDLE"
    exit 1
fi

# 2. Code sign bundle
echo ">> Code signing $APP_BUNDLE..."
if [ -n "$DEVELOPER_ID" ]; then
    echo "   Signing with Developer ID: $DEVELOPER_ID"
    codesign --force --deep --options runtime --entitlements "$SCRIPT_DIR/entitlements.plist" --sign "$DEVELOPER_ID" "$APP_BUNDLE"
else
    echo "   Ad-hoc signing with entitlements (hardened runtime)..."
    codesign --force --deep --sign - --entitlements "$SCRIPT_DIR/entitlements.plist" "$APP_BUNDLE" || true
fi

echo ">> Preparing DMG staging folder..."
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

# 3. Copy .app bundle into staging
cp -R "$APP_BUNDLE" "$STAGING_DIR/"

# 4. Create Applications symlink for drag-and-drop installation
echo ">> Creating /Applications symlink..."
ln -s /Applications "$STAGING_DIR/Applications"

# 5. Add 1-Click Gatekeeper Helper for macOS Sequoia & Sonoma
cat << 'EOF' > "$STAGING_DIR/First_Time_Open_Helper.command"
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
echo "======================================================="
echo " Fixelect — macOS Gatekeeper Setup Helper"
echo "======================================================="
if [ -d "/Applications/Fixelect.app" ]; then
    echo ">> Clearing Gatekeeper quarantine on /Applications/Fixelect.app..."
    xattr -cr /Applications/Fixelect.app 2>/dev/null || true
    echo ">> Launching Fixelect..."
    open /Applications/Fixelect.app
else
    echo ">> Please drag Fixelect.app into Applications first!"
fi
echo "Done."
sleep 2
EOF
chmod +x "$STAGING_DIR/First_Time_Open_Helper.command"

# 4. Create DMG via native macOS hdiutil
echo ">> Building compressed DMG ($DMG_NAME)..."
rm -f "$DIST_DIR/$DMG_NAME"
hdiutil create \
    -volname "$VOLUME_NAME" \
    -srcfolder "$STAGING_DIR" \
    -ov \
    -format UDZO \
    "$DIST_DIR/$DMG_NAME"

# 5. Cleanup
rm -rf "$STAGING_DIR"

echo "======================================================="
echo " ✓ Build complete: $DIST_DIR/$DMG_NAME"
echo " SHA-256: $(shasum -a 256 "$DIST_DIR/$DMG_NAME" | cut -d ' ' -f 1)"
echo "======================================================="
