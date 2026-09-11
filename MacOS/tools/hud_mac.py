"""
On-screen feedback for macOS, drawn natively in the menu-bar daemon:

  * MacHud  - a small non-activating panel near the pointer ("Fixing…",
              "Fixed 3 words · Undo", progress with Cancel). It never takes
              focus from the app you are typing in.
  * ask_polish() - the Polish preview: a native alert showing the rewrite,
              with a style picker, Replace (Return), Try again and Cancel (Esc).

Everything that touches AppKit runs on the main thread via AppHelper.callAfter;
the worker thread only calls these functions. Every failure degrades to a
notification instead of breaking the fix itself.
"""

import threading

try:
    import objc
    from AppKit import (
        NSAlert, NSApp, NSButton, NSColor, NSEvent, NSFont, NSMakeRect, NSPanel, NSPopUpButton,
        NSProgressIndicator, NSScreen, NSTextField, NSView,
    )
    from Foundation import NSObject
    from PyObjCTools import AppHelper
    _OK = True
except Exception:  # pragma: no cover - not on macOS / PyObjC missing
    _OK = False

_BORDERLESS, _NONACTIVATING = 0, 1 << 7
_BUFFERED = 2
_STATUS_LEVEL = 25
_ALL_SPACES, _FULLSCREEN_AUX = 1 << 0, 1 << 8

_COLORS = {
    "working": (0.24, 0.48, 1.0),
    "success": (0.20, 0.83, 0.60),
    "polish": (1.0, 0.35, 0.43),
    "info": (0.98, 0.75, 0.14),
    "error": (0.97, 0.44, 0.44),
}
_GLYPH = {"working": "…", "success": "✓", "polish": "✓", "info": "!", "error": "×"}


if _OK:
    class _Target(NSObject):
        """Bridges an NSButton click to a Python callable."""

        def initWithCallback_(self, cb):
            self = objc.super(_Target, self).init()
            if self is None:
                return None
            self._cb = cb
            return self

        def fire_(self, _sender):
            try:
                self._cb()
            except Exception as e:  # never let a button crash the app
                print(f"  (hud action failed: {e})")


def _rgb(c, a=1.0):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(c[0], c[1], c[2], a)


def _label(text, size, bold=False, color=(0.93, 0.93, 0.95), width=None):
    f = NSTextField.labelWithString_(text)
    f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
    f.setTextColor_(_rgb(color))
    f.sizeToFit()
    if width and f.frame().size.width > width:
        f.setLineBreakMode_(4)  # truncate the tail on one line
        f.setFrameSize_((width, f.frame().size.height))
    return f


class MacHud:
    WIDTH_MAX = 420

    def __init__(self):
        self.panel = None
        self._targets = []
        self._token = 0

    @property
    def available(self):
        return _OK

    def show(self, kind, title, detail="", actions=(), timeout=None, progress=None, anchor=None):
        if not _OK:
            return False
        AppHelper.callAfter(self._show, kind, title, detail, list(actions), timeout, progress)
        return True

    def hide(self):
        if _OK:
            AppHelper.callAfter(self._hide, None)

    # -- main thread -----------------------------------------------------------

    def _build(self):
        p = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 300, 48), _BORDERLESS | _NONACTIVATING, _BUFFERED, False)
        p.setLevel_(_STATUS_LEVEL)
        p.setOpaque_(False)
        p.setBackgroundColor_(NSColor.clearColor())
        p.setHasShadow_(True)
        p.setHidesOnDeactivate_(False)
        p.setFloatingPanel_(True)
        p.setBecomesKeyOnlyIfNeeded_(True)
        p.setCollectionBehavior_(_ALL_SPACES | _FULLSCREEN_AUX)
        self.panel = p

    def _show(self, kind, title, detail, actions, timeout, progress):
        try:
            self._token += 1
            token = self._token
            if self.panel is None:
                self._build()
            color = _COLORS.get(kind, _COLORS["info"])
            title_l = _label(title, 13, bold=True)
            detail_l = _label(detail, 11.5, color=(0.64, 0.67, 0.72), width=self.WIDTH_MAX - 130) if detail else None
            glyph = _label(_GLYPH.get(kind, "!"), 14, bold=True, color=color)

            self._targets = []
            buttons = []
            for text, cb in actions:
                target = _Target.alloc().initWithCallback_(lambda c=cb: (self._hide(None), c()))
                self._targets.append(target)
                b = NSButton.buttonWithTitle_target_action_(text, target, "fire:")
                b.setBezelStyle_(1)
                b.setControlSize_(1)  # small
                b.sizeToFit()
                buttons.append(b)

            text_w = max(title_l.frame().size.width, detail_l.frame().size.width if detail_l else 0)
            if progress is not None:
                text_w = max(text_w, 200)
            btn_w = sum(b.frame().size.width for b in buttons) + 6 * max(0, len(buttons) - 1)
            w = min(self.WIDTH_MAX, max(240, 16 + 22 + 8 + text_w + (14 + btn_w if buttons else 0) + 16))
            h = 22 + title_l.frame().size.height + (detail_l.frame().size.height + 2 if detail_l else 0) \
                + (10 if progress is not None else 0)

            view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
            view.setWantsLayer_(True)
            layer = view.layer()
            layer.setBackgroundColor_(_rgb((0.07, 0.08, 0.11), 0.97).CGColor())
            layer.setCornerRadius_(12)
            layer.setBorderWidth_(1)
            layer.setBorderColor_(_rgb((0.19, 0.22, 0.29)).CGColor())

            y = h - 11 - title_l.frame().size.height
            glyph.setFrameOrigin_((16, y - 1))
            view.addSubview_(glyph)
            title_l.setFrameOrigin_((16 + 22 + 8, y))
            view.addSubview_(title_l)
            if detail_l:
                y -= detail_l.frame().size.height + 2
                detail_l.setFrameOrigin_((16 + 22 + 8, y))
                view.addSubview_(detail_l)
            if progress is not None:
                bar = NSProgressIndicator.alloc().initWithFrame_(NSMakeRect(46, 8, text_w, 6))
                bar.setIndeterminate_(False)
                bar.setMinValue_(0.0)
                bar.setMaxValue_(1.0)
                bar.setDoubleValue_(float(progress))
                view.addSubview_(bar)
            x = w - 16
            for b in reversed(buttons):
                bw, bh = b.frame().size.width, b.frame().size.height
                x -= bw
                b.setFrameOrigin_((x, (h - bh) / 2))
                view.addSubview_(b)
                x -= 6

            self.panel.setContentView_(view)
            mouse = NSEvent.mouseLocation()
            screen = NSScreen.mainScreen()
            for s in NSScreen.screens() or []:
                f = s.frame()
                if f.origin.x <= mouse.x < f.origin.x + f.size.width and f.origin.y <= mouse.y < f.origin.y + f.size.height:
                    screen = s
            vis = screen.visibleFrame()
            px_ = min(max(vis.origin.x + 8, mouse.x - 20), vis.origin.x + vis.size.width - w - 8)
            py_ = mouse.y - h - 24
            if py_ < vis.origin.y + 8:
                py_ = mouse.y + 24
            self.panel.setFrame_display_(NSMakeRect(px_, py_, w, h), True)
            self.panel.orderFrontRegardless()
            if timeout:
                AppHelper.callLater(timeout / 1000.0, self._hide, token)
        except Exception as e:
            print(f"  (hud failed: {e})")

    def _hide(self, token):
        if self.panel is not None and (token is None or token == self._token):
            self.panel.orderOut_(None)


# ---------------------------------------------------------------------------
# Polish preview
# ---------------------------------------------------------------------------

def make_alert(styles, style, after, note=""):
    """The preview alert: rewrite text, a style picker, Replace / Cancel / Try again."""
    alert = NSAlert.alloc().init()
    label = styles.get(style, {}).get("label", "Polish")
    alert.setMessageText_(f"Polish · {label}")
    shown = after if len(after) <= 1800 else after[:1800] + "…"
    alert.setInformativeText_(shown + (f"\n\n{note}" if note else ""))
    alert.addButtonWithTitle_("Replace")    # Return
    alert.addButtonWithTitle_("Cancel")     # Esc (NSAlert maps a "Cancel" button to Escape)
    alert.addButtonWithTitle_("Try again")
    keys = list(styles)
    popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, 240, 26), False)
    popup.addItemsWithTitles_([styles[k]["label"] for k in keys])
    popup.selectItemAtIndex_(keys.index(style) if style in keys else 0)
    alert.setAccessoryView_(popup)
    return alert, popup, keys


def ask_polish(styles, style, before, after, note=""):
    """Blocking (call from the worker). Returns ("accept", text) | ("cancel", None) | ("retry", style)."""
    if not _OK:
        return ("accept", after)
    done = threading.Event()
    box = {}

    def run():
        try:
            NSApp.activateIgnoringOtherApps_(True)
            alert, popup, keys = make_alert(styles, style, after, note)
            resp = int(alert.runModal())
            chosen = keys[int(popup.indexOfSelectedItem())]
            if resp == 1000:
                box["r"] = ("retry", chosen) if chosen != style else ("accept", after)
            elif resp == 1002:
                box["r"] = ("retry", chosen)
            else:
                box["r"] = ("cancel", None)
        except Exception as e:
            print(f"  (preview failed: {e})")
            box["r"] = ("accept", after)
        finally:
            done.set()

    AppHelper.callAfter(run)
    done.wait()
    return box["r"]
