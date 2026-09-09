"""
py2app setup script for Fixelect on macOS.
Builds standalone Fixelect.app bundle:
    python3 setup.py py2app
"""

from setuptools import setup
import pathlib

APP = ["fixelect_mac.py"]

DATA_FILES = [
    ("resources", [
        "resources/app_icon.icns",
        "resources/app_icon.png",
        "resources/status_bar_template.png",
        "resources/status_bar_template@2x.png",
        "resources/brand_logo.png",
        "resources/brand_logo_dashboard.png",
        "resources/brand_logo_setup.png",
        "resources/PRIVACY_POLICY.md",
        "resources/LICENSE.txt",
    ]),
    ("", [
        "dictionary.txt",
        "freq.txt",
        "words.txt",
        "shorthand.txt",
    ]),
]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "resources/app_icon.icns",
    "plist": "Info.plist",
    "packages": ["tools", "PIL", "pynput"],
    "includes": ["tkinter"],
}

setup(
    app=APP,
    name="Fixelect",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
