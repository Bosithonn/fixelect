"""
Which app is the user typing in? Used for the per-app off switch and to
restore focus after the Polish preview.

Apps are identified by their executable name (lower case), e.g. "code.exe".
"""

import ctypes
import os
from ctypes import wintypes as w

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_user32.GetForegroundWindow.restype = w.HWND
_user32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
_user32.GetWindowThreadProcessId.restype = w.DWORD
_user32.GetWindowTextLengthW.argtypes = [w.HWND]
_user32.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
_user32.IsWindowVisible.argtypes = [w.HWND]
_user32.GetAncestor.argtypes = [w.HWND, w.UINT]
_user32.GetAncestor.restype = w.HWND
_user32.GetWindow.argtypes = [w.HWND, w.UINT]
_user32.GetWindow.restype = w.HWND
_user32.GetWindowLongW.argtypes = [w.HWND, ctypes.c_int]
_user32.GetWindowLongW.restype = ctypes.c_long
_kernel32.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
_kernel32.OpenProcess.restype = w.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
_kernel32.CloseHandle.argtypes = [w.HANDLE]

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_EnumProc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)

# Off by default: terminals (text there is commands) and password managers.
DEFAULT_DISABLED = [
    "windowsterminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "mintty.exe", "putty.exe",
    "keepass.exe", "keepassxc.exe", "1password.exe", "bitwarden.exe",
]

# Offered in the picker as one-click additions.
SUGGESTED = [
    "code.exe", "cursor.exe", "devenv.exe", "idea64.exe", "pycharm64.exe", "webstorm64.exe",
    "rider64.exe", "sublime_text.exe", "notepad++.exe", "zed.exe",
    "wezterm-gui.exe", "alacritty.exe", "dashlane.exe", "enpass.exe",
] + DEFAULT_DISABLED

_NAMES = {
    "windowsterminal.exe": "Windows Terminal", "cmd.exe": "Command Prompt", "powershell.exe": "PowerShell",
    "pwsh.exe": "PowerShell 7", "conhost.exe": "Console", "openconsole.exe": "Console",
    "mintty.exe": "Git Bash", "putty.exe": "PuTTY", "wezterm-gui.exe": "WezTerm", "alacritty.exe": "Alacritty",
    "keepass.exe": "KeePass", "keepassxc.exe": "KeePassXC", "1password.exe": "1Password",
    "bitwarden.exe": "Bitwarden", "dashlane.exe": "Dashlane", "enpass.exe": "Enpass",
    "code.exe": "Visual Studio Code", "cursor.exe": "Cursor", "devenv.exe": "Visual Studio",
    "idea64.exe": "IntelliJ IDEA", "pycharm64.exe": "PyCharm", "webstorm64.exe": "WebStorm",
    "rider64.exe": "Rider", "sublime_text.exe": "Sublime Text", "notepad++.exe": "Notepad++", "zed.exe": "Zed",
    "winword.exe": "Word", "outlook.exe": "Outlook", "olk.exe": "Outlook", "excel.exe": "Excel",
    "powerpnt.exe": "PowerPoint", "chrome.exe": "Google Chrome", "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Firefox", "brave.exe": "Brave", "opera.exe": "Opera", "slack.exe": "Slack",
    "teams.exe": "Microsoft Teams", "ms-teams.exe": "Microsoft Teams", "discord.exe": "Discord",
    "telegram.exe": "Telegram", "notion.exe": "Notion", "obsidian.exe": "Obsidian", "notepad.exe": "Notepad",
    "whatsapp.exe": "WhatsApp", "thunderbird.exe": "Thunderbird", "explorer.exe": "File Explorer",
}

# Never listed or blocked: the shell and Fixelect itself.
_IGNORED = {"explorer.exe", "fixelect.exe", "applicationframehost.exe", "shellexperiencehost.exe",
            "searchhost.exe", "startmenuexperiencehost.exe", "textinputhost.exe", "systemsettings.exe",
            "lockapp.exe"}


def display_name(exe):
    exe = (exe or "").lower()
    if exe in _NAMES:
        return _NAMES[exe]
    stem = exe[:-4] if exe.endswith(".exe") else exe
    return stem.replace("_", " ").replace("-", " ").title() or "Unknown app"


def _process_exe(pid):
    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = w.DWORD(len(buf))
        if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        _kernel32.CloseHandle(h)


def window_exe(hwnd):
    pid = w.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return _process_exe(pid.value) if pid.value else "", pid.value


def foreground():
    """(hwnd, exe, pid) of the window the user is typing in."""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return None, "", 0
    exe, pid = window_exe(hwnd)
    return hwnd, exe, pid


def is_disabled(exe, cfg, pid=None):
    exe = (exe or "").lower()
    if not exe or exe in _IGNORED or pid == os.getpid():
        return False
    return exe in {a.lower() for a in cfg.get("disabled_apps", DEFAULT_DISABLED)}


def list_open_apps():
    """Apps with a visible top-level window, as [(exe, display name)], sorted by name."""
    found = {}
    own = os.getpid()

    def cb(hwnd, _lp):
        if not _user32.IsWindowVisible(hwnd) or _user32.GetWindow(hwnd, 4):  # skip owned popups
            return True
        if _user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        if _user32.GetWindowLongW(hwnd, -20) & 0x80:  # WS_EX_TOOLWINDOW
            return True
        exe, pid = window_exe(hwnd)
        if exe and pid != own and exe not in _IGNORED:
            found.setdefault(exe, display_name(exe))
        return True

    try:
        _user32.EnumWindows(_EnumProc(cb), 0)
    except Exception:
        pass
    return sorted(found.items(), key=lambda kv: kv[1].lower())
