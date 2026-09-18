"""
Win32 clipboard access for Fixelect with correct 64-bit ctypes signatures.

Why this module exists: calling kernel32/user32 through `ctypes.windll` without
argtypes/restype truncates every HANDLE and pointer to 32 bits. GlobalLock()
then returns a garbage address, the write faults, and the old code silently
fell back to pyperclip - so "keep Fixelect out of clipboard history" never
worked. It also could only save/restore plain text, wiping any image or rich
content the user had copied.
"""

import ctypes
import json
import time
from ctypes import wintypes as w

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_user32.OpenClipboard.argtypes = [w.HWND]
_user32.OpenClipboard.restype = w.BOOL
_user32.CloseClipboard.argtypes = []
_user32.CloseClipboard.restype = w.BOOL
_user32.EmptyClipboard.argtypes = []
_user32.EmptyClipboard.restype = w.BOOL
_user32.GetClipboardData.argtypes = [w.UINT]
_user32.GetClipboardData.restype = w.HANDLE
_user32.SetClipboardData.argtypes = [w.UINT, w.HANDLE]
_user32.SetClipboardData.restype = w.HANDLE
_user32.EnumClipboardFormats.argtypes = [w.UINT]
_user32.EnumClipboardFormats.restype = w.UINT
_user32.RegisterClipboardFormatW.argtypes = [w.LPCWSTR]
_user32.RegisterClipboardFormatW.restype = w.UINT
_user32.GetClipboardSequenceNumber.argtypes = []
_user32.GetClipboardSequenceNumber.restype = w.DWORD
_user32.IsClipboardFormatAvailable.argtypes = [w.UINT]
_user32.IsClipboardFormatAvailable.restype = w.BOOL

_kernel32.GlobalAlloc.argtypes = [w.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = w.HANDLE
_kernel32.GlobalLock.argtypes = [w.HANDLE]
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalUnlock.argtypes = [w.HANDLE]
_kernel32.GlobalUnlock.restype = w.BOOL
_kernel32.GlobalSize.argtypes = [w.HANDLE]
_kernel32.GlobalSize.restype = ctypes.c_size_t
_kernel32.GlobalFree.argtypes = [w.HANDLE]
_kernel32.GlobalFree.restype = w.HANDLE

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# Formats whose handle is a GDI object or owner-private, not an HGLOBAL. They
# cannot be copied byte-for-byte; CF_BITMAP is re-synthesised from CF_DIB anyway.
_NON_HGLOBAL = {2, 3, 9, 14, 0x0080, 0x0082, 0x0083, 0x008E}

_SNAPSHOT_BUDGET_S = 0.25
_SNAPSHOT_MAX_BYTES = 48 * 1024 * 1024

_fmt_cache = {}


def _fmt(name):
    if name not in _fmt_cache:
        _fmt_cache[name] = _user32.RegisterClipboardFormatW(name)
    return _fmt_cache[name]


def _open(retries=20, delay=0.01):
    """The clipboard is a global lock other apps hold briefly; retry instead of failing."""
    for _ in range(retries):
        if _user32.OpenClipboard(None):
            return True
        time.sleep(delay)
    return False


def _alloc(data: bytes):
    h = _kernel32.GlobalAlloc(GMEM_MOVEABLE, max(1, len(data)))
    if not h:
        return None
    p = _kernel32.GlobalLock(h)
    if not p:
        _kernel32.GlobalFree(h)
        return None
    ctypes.memmove(p, data, len(data))
    _kernel32.GlobalUnlock(h)
    return h


def _set(fmt, data: bytes):
    h = _alloc(data)
    if h and not _user32.SetClipboardData(fmt, h):
        _kernel32.GlobalFree(h)  # ownership only transfers on success
        return False
    return bool(h)


def _read_handle(h):
    size = _kernel32.GlobalSize(h)
    if not size:
        return None
    p = _kernel32.GlobalLock(h)
    if not p:
        return None
    try:
        return ctypes.string_at(p, size)
    finally:
        _kernel32.GlobalUnlock(h)


def _mark_private():
    """Keep our temporary clipboard writes out of Win+V history and cloud sync."""
    zero = (0).to_bytes(4, "little")
    for name in ("CanIncludeInClipboardHistory", "CanUploadToCloudClipboard"):
        f = _fmt(name)
        if f:
            _set(f, zero)
    f = _fmt("ExcludeClipboardContentFromMonitorProcessing")
    if f:
        _set(f, b"\0")


def sequence():
    return _user32.GetClipboardSequenceNumber()


def get_text():
    """Return the clipboard's Unicode text, or None if it holds no text."""
    if not _user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return None
    if not _open():
        return None
    try:
        h = _user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        raw = _read_handle(h)
        if raw is None:
            return None
        text = raw.decode("utf-16-le", errors="replace")
        nul = text.find("\0")
        return text if nul < 0 else text[:nul]
    finally:
        _user32.CloseClipboard()


def set_text(text, private=True, html=None):
    """Put `text` (and optionally CF_HTML bytes) on the clipboard."""
    if not _open():
        return False
    try:
        _user32.EmptyClipboard()
        if private:
            _mark_private()
        if html:
            f = _fmt("HTML Format")
            if f:
                _set(f, html)
        return _set(CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))
    finally:
        _user32.CloseClipboard()


def get_html():
    """The clipboard's "HTML Format" (CF_HTML) payload as bytes, or None."""
    f = _fmt("HTML Format")
    if not f or not _user32.IsClipboardFormatAvailable(f):
        return None
    if not _open():
        return None
    try:
        h = _user32.GetClipboardData(f)
        return _read_handle(h) if h else None
    finally:
        _user32.CloseClipboard()


def snapshot():
    """Capture every copyable format currently on the clipboard.

    Returns a list of (format, bytes), [] for an empty clipboard, or None if
    the clipboard could not be opened. Bounded in time and size so a huge
    Excel selection with delay-rendered formats cannot stall the hotkey.
    """
    if not _open():
        return None
    items, total, started = [], 0, time.time()
    try:
        fmt = _user32.EnumClipboardFormats(0)
        while fmt:
            if fmt not in _NON_HGLOBAL and not (0x0200 <= fmt <= 0x03FF):
                h = _user32.GetClipboardData(fmt)
                if h:
                    data = _read_handle(h)
                    if data is not None:
                        items.append((fmt, data))
                        total += len(data)
            if total > _SNAPSHOT_MAX_BYTES or time.time() - started > _SNAPSHOT_BUDGET_S:
                break
            fmt = _user32.EnumClipboardFormats(fmt)
        return items
    finally:
        _user32.CloseClipboard()


def restore(items, private=True):
    """Put a snapshot() back. An empty snapshot empties the clipboard."""
    if items is None:
        return False
    if not _open():
        return False
    try:
        _user32.EmptyClipboard()
        if private:
            _mark_private()
        for fmt, data in items:
            _set(fmt, data)
        return True
    finally:
        _user32.CloseClipboard()


def copied_from_empty_selection():
    """True when the last copy was an editor's "copy the whole line" fallback.

    VS Code, Visual Studio and friends copy the entire current line when Ctrl+C
    is pressed with nothing selected. Fixing that and pasting it back would
    duplicate the line into the user's code, so treat it as "nothing selected".
    """
    import richtext
    if not _open():
        return False
    try:
        # VS Code and Cursor keep this metadata in Chromium's custom-data format.
        f = _fmt("Chromium Web Custom MIME Data Format")
        if f and _user32.IsClipboardFormatAvailable(f):
            h = _user32.GetClipboardData(f)
            if h and richtext.is_line_copy(_read_handle(h)):
                return True
        f = _fmt("vscode-editor-data")
        if f and _user32.IsClipboardFormatAvailable(f):
            h = _user32.GetClipboardData(f)
            raw = _read_handle(h) if h else None
            if raw:
                try:
                    meta = json.loads(raw.split(b"\0", 1)[0].decode("utf-8", errors="ignore"))
                    if meta.get("isFromEmptySelection"):
                        return True
                except Exception:
                    pass
        for name in ("VisualStudioEditorOperationsLineCutCopyClipboardTag", "MSDEVLineSelect"):
            f = _fmt(name)
            if f and _user32.IsClipboardFormatAvailable(f):
                return True
        return False
    finally:
        _user32.CloseClipboard()
