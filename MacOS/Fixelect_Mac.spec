# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None
SHARED = os.path.join(os.path.dirname(os.path.abspath(SPECPATH)), 'shared')   # code shared with Windows
APP_VERSION = open(os.path.join(SHARED, 'version.py')).read().split('APP_VERSION = "')[1].split('"')[0]

a = Analysis(
    ['fixelect_mac.py'],
    pathex=['tools', SHARED],
    binaries=[],
    datas=[
        ('resources', 'resources'),
        (os.path.join(SHARED, 'data', 'dictionary.txt'), '.'),
        (os.path.join(SHARED, 'data', 'words.txt'), '.'),
        (os.path.join(SHARED, 'data', 'shorthand.txt'), '.'),
        ('resources/PRIVACY_POLICY.md', '.'),
        ('resources/LICENSE.txt', '.'),
    ],
    hiddenimports=[
        'tools',
        'tools.config_mac',
        'tools.hardware_mac',
        'tools.downloader_mac',
        'tools.engine_mac',
        'tools.clipboard_mac',
        'tools.hotkey_mac',
        'tools.status_bar',
        'tools.apps_mac',
        'tools.hud_mac',
        'apps_mac',
        'hud_mac',
        'check_guard',
        'languages',
        'chunking',
        'richtext',
        'updater',
        'diagnostics',
        'version',
        'ui',
        'ui_kit',
        'engine_mac',
        'status_bar',
        'pynput',
        'pynput.keyboard._darwin',
        'pynput.mouse._darwin',
        'Quartz',
        'ApplicationServices',
        'PIL',
        'tkinter',
        'rumps',
        'AppKit',
        'Cocoa',
        'PyObjCTools',
        'PyObjCTools.AppHelper',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'transformers', 'matplotlib', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Fixelect',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file='entitlements.plist',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Fixelect',
)

app = BUNDLE(
    coll,
    name='Fixelect.app',
    icon='resources/app_icon.icns',
    bundle_identifier='com.fixelect.app',
    info_plist={
        'CFBundleDisplayName': 'Fixelect',
        'CFBundleName': 'Fixelect',
        'CFBundleVersion': APP_VERSION,
        'CFBundleShortVersionString': APP_VERSION,
        'LSMinimumSystemVersion': '11.0',
        'LSUIElement': True,
        'NSRequiresAquaSystemAppearance': False,
        'NSHighResolutionCapable': True,
        'NSSupportsAutomaticGraphicsSwitching': True,
        'NSAppleEventsUsageDescription': 'Fixelect simulates Cmd+C and Cmd+V to replace your selected text with corrected grammar.',
        'NSSystemAdministrationUsageDescription': 'Fixelect requires Accessibility access to listen for global triggers (Double-tap Option, Double-tap Control, or custom hotkeys).',
    },
)
