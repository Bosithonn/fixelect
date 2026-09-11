# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from pathlib import Path

block_cipher = None
project_root = os.path.abspath(SPECPATH)
shared_root = os.path.join(os.path.dirname(project_root), 'shared')   # code shared with macOS

datas = [
    (os.path.join(shared_root, 'data', 'dictionary.txt'), '.'),
    (os.path.join(shared_root, 'data', 'shorthand.txt'), '.'),
    (os.path.join(shared_root, 'data', 'words.txt'), '.'),
    (os.path.join(shared_root, 'data', 'uz_words.txt'), '.'),
    (os.path.join(project_root, 'LICENSE.txt'), '.'),
    (os.path.join(project_root, 'PRIVACY_POLICY.md'), '.'),
    (os.path.join(project_root, 'resources'), 'resources'),
]

binaries = []

hidden_imports = [
    'pystray',
    'pystray._win32',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.IcoImagePlugin',
    'comtypes',
    'comtypes.client',
    'pyperclip',
    'psutil',
    'winreg',
    'tools',
    'tools.config',
    'tools.downloader',
    'tools.engine',
    'tools.hardware',
    'tools.tray',
    'tools.hotkey_win',
    'tools.clipboard_win',
    'clipboard_win',
    'apps_win',
    'hud_win',
    'check_guard',
    'languages',
    'chunking',
    'richtext',
    'updater',
    'diagnostics',
    'version',
    'ui_kit',
    'ui',
    'tray',
    'engine',
    'pynput',
    'pynput.keyboard._win32',
]

a = Analysis(
    ['fixelect.py'],
    pathex=[project_root, os.path.join(project_root, 'tools'), shared_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'transformers', 'sentencepiece', 'torchvision', 'torchaudio', 'matplotlib', 'scipy', 'numpy.testing'],
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
    entitlements_file=None,
    icon=os.path.join(project_root, 'resources', 'app_icon.ico'),
    version=os.path.join(project_root, 'file_version_info.txt'),
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
