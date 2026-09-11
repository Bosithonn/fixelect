"""macOS smoke test - runs on the GitHub macOS runner (no model, no permissions).

Exercises every PyObjC code path that can run headless: pasteboard
snapshot/restore and rich text, RTF rewriting through NSAttributedString,
the status panel layout, the Polish preview alert (built, not shown),
front-app detection and the bundled engine lookup.
Run: python tests/mac_smoke.py [path/to/Fixelect.app]
"""

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "MacOS" / "tools"))
sys.path.insert(0, str(ROOT / "shared"))

results = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:  # a crash is a failure, not a runner abort
        ok, detail = False, f"{type(e).__name__}: {e}"
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


def t_imports():
    import apps_mac, check_guard, chunking, clipboard_mac, config_mac, diagnostics, downloader_mac  # noqa: F401
    import engine_mac, hardware_mac, hotkey_mac, hud_mac, richtext, status_bar, ui, ui_kit, updater  # noqa: F401
    return True, ""


def t_pasteboard():
    import clipboard_mac as clip
    snap = clip.snapshot()
    try:
        clip.set_text("teh cat", transient=True, html="<b>teh</b> cat")
        rich = clip.get_rich()
        ok = clip.get_text() == "teh cat" and "<b>" in rich.get("html", "")
        return ok, repr(rich.get("html", ""))[:60]
    finally:
        clip.restore(snap)


def t_rtf():
    import clipboard_mac as clip
    from AppKit import NSAttributedString, NSFont, NSFontAttributeName, NSMutableAttributedString
    s = NSMutableAttributedString.alloc().initWithString_("I recieved teh package")
    s.addAttribute_value_range_(NSFontAttributeName, NSFont.boldSystemFontOfSize_(14), (2, 8))
    rtf = s.RTFFromRange_documentAttributes_((0, s.length()), {})
    out = clip.rewrite_rich({"rtf": rtf}, "I recieved teh package", "I received the package")
    back, _ = NSAttributedString.alloc().initWithRTF_documentAttributes_(out["rtf"], None)
    font = back.attribute_atIndex_effectiveRange_(NSFontAttributeName, 3, None)[0]
    bold = "Bold" in str(font.fontName())
    return str(back.string()) == "I received the package" and bold, f"{back.string()} bold={bold}"


def t_hud():
    from AppKit import NSApplication
    import hud_mac
    from check_guard import POLISH_STYLES
    NSApplication.sharedApplication()
    hud = hud_mac.MacHud()
    hud._show("success", "Fixed 3 words", "Formatting kept.", [("Undo", lambda: None)], 1000, None)
    hud._show("working", "Fixing…  2 of 5", "Esc to cancel", [("Cancel", lambda: None)], None, 0.4)
    w = hud.panel.frame().size.width
    hud._hide(None)
    alert, popup, keys = hud_mac.make_alert(POLISH_STYLES, "friendly", "Could you send it?", "")
    return w >= 240 and popup.numberOfItems() == len(keys) and len(alert.buttons()) == 3, f"panel width {w:.0f}"


def t_apps():
    import apps_mac
    app, bid, pid = apps_mac.foreground()
    return isinstance(apps_mac.list_open_apps(), list), f"front={bid or 'none'}"


def t_engine_lookup(app_path=None):
    import engine_mac
    eng = engine_mac.MacEmbeddedEngine()
    found = eng._find_llama_server()
    if app_path:
        server = pathlib.Path(app_path) / "Contents" / "Frameworks" / "llama" / "llama-server"
        if not server.is_file():
            return False, f"not bundled at {server}"
        out = subprocess.run([str(server), "--version"], capture_output=True, text=True, timeout=30)
        return out.returncode == 0, (out.stdout or out.stderr).strip().splitlines()[-1:]
    return True, f"llama-server: {found or 'not installed (bundled in release builds)'}"


def t_frozen(app_path):
    exe = pathlib.Path(app_path) / "Contents" / "MacOS" / "Fixelect"
    out = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=120)
    return out.returncode == 0, out.stdout.strip() or out.stderr.strip()[-200:]


def main():
    app_path = sys.argv[1] if len(sys.argv) > 1 else None
    check("modules import", t_imports)
    check("pasteboard text + html round trip", t_pasteboard)
    check("RTF keeps bold after a fix", t_rtf)
    check("status panel and preview alert build", t_hud)
    check("front app detection", t_apps)
    check("engine lookup", lambda: t_engine_lookup(app_path))
    if app_path:
        check("frozen app starts (--version)", lambda: t_frozen(app_path))
    print(f"\n{sum(results)}/{len(results)} macOS smoke checks passed")
    return all(results)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
