"""
Which app is the user typing in (macOS)? Used for the per-app off switch and
to hand focus back after the Polish preview. Apps are identified by bundle ID.
"""

import os

try:
    from AppKit import NSWorkspace, NSRunningApplication, NSApplicationActivateIgnoringOtherApps
    _has_appkit = True
except Exception:  # pragma: no cover - not on macOS
    _has_appkit = False

# Off by default: terminals (text there is commands) and password managers.
DEFAULT_DISABLED = [
    "com.apple.Terminal", "com.googlecode.iterm2", "dev.warp.Warp-Stable", "net.kovidgoyal.kitty",
    "io.alacritty", "com.mitchellh.ghostty", "com.github.wez.wezterm",
    "com.1password.1password", "com.agilebits.onepassword7", "com.bitwarden.desktop",
    "org.keepassxc.keepassxc", "com.apple.keychainaccess", "com.apple.Passwords",
]

SUGGESTED = [
    "com.microsoft.VSCode", "com.todesktop.230313mzl4w4u92", "com.apple.dt.Xcode", "com.jetbrains.intellij",
    "com.jetbrains.pycharm", "com.sublimetext.4", "dev.zed.Zed",
] + DEFAULT_DISABLED

_NAMES = {
    "com.apple.Terminal": "Terminal", "com.googlecode.iterm2": "iTerm", "dev.warp.Warp-Stable": "Warp",
    "net.kovidgoyal.kitty": "kitty", "io.alacritty": "Alacritty", "com.mitchellh.ghostty": "Ghostty",
    "com.github.wez.wezterm": "WezTerm", "com.1password.1password": "1Password",
    "com.agilebits.onepassword7": "1Password 7", "com.bitwarden.desktop": "Bitwarden",
    "org.keepassxc.keepassxc": "KeePassXC", "com.apple.keychainaccess": "Keychain Access",
    "com.apple.Passwords": "Passwords", "com.microsoft.VSCode": "Visual Studio Code",
    "com.todesktop.230313mzl4w4u92": "Cursor", "com.apple.dt.Xcode": "Xcode",
    "com.jetbrains.intellij": "IntelliJ IDEA", "com.jetbrains.pycharm": "PyCharm",
    "com.sublimetext.4": "Sublime Text", "dev.zed.Zed": "Zed",
}

_IGNORED = {"com.fixelect.app", "com.apple.finder", "com.apple.dock", "com.apple.systemuiserver"}


def display_name(bundle_id):
    if bundle_id in _NAMES:
        return _NAMES[bundle_id]
    if _has_appkit:
        try:
            for app in NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id) or []:
                if app.localizedName():
                    return str(app.localizedName())
        except Exception:
            pass
    return (bundle_id or "Unknown app").split(".")[-1].replace("-", " ").title()


def foreground():
    """(NSRunningApplication or None, bundle id, pid) of the frontmost app."""
    if not _has_appkit:
        return None, "", 0
    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None, "", 0
        return app, str(app.bundleIdentifier() or ""), int(app.processIdentifier())
    except Exception:
        return None, "", 0


def activate(app):
    """Hand focus back to `app` (an NSRunningApplication)."""
    try:
        if app is not None:
            app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            return True
    except Exception:
        pass
    return False


def is_disabled(bundle_id, cfg, pid=None):
    if not bundle_id or bundle_id in _IGNORED or pid == os.getpid():
        return False
    return bundle_id in set(cfg.get("disabled_apps", DEFAULT_DISABLED))


def list_open_apps():
    if not _has_appkit:
        return []
    found = {}
    try:
        for app in NSWorkspace.sharedWorkspace().runningApplications() or []:
            if app.activationPolicy() != 0:  # NSApplicationActivationPolicyRegular
                continue
            bid = str(app.bundleIdentifier() or "")
            if bid and bid not in _IGNORED and app.processIdentifier() != os.getpid():
                found.setdefault(bid, str(app.localizedName() or display_name(bid)))
    except Exception:
        pass
    return sorted(found.items(), key=lambda kv: kv[1].lower())
