"""
"Copy diagnostics": a plain-text report the user can paste into a support
request. It never includes anything the user wrote - no selections, no
custom instruction text, no protected words - only settings and state.
"""

import platform
import sys
import time

from version import APP_VERSION

if sys.platform == "darwin":
    import config_mac as C
    import downloader_mac as D
    import hardware_mac as H
else:
    import config as C
    import downloader as D
    import hardware as H

_PRIVATE_KEYS = {"custom_instruction", "custom_fix", "custom_polish"}


def _hardware():
    try:
        return H.detect_hardware()
    except Exception as e:
        return {"error": str(e)}


def _log_tail(lines=60):
    try:
        path = C.get_logs_dir() / "fixelect.log"
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    except Exception:
        pass
    return []


def report(extra=None):
    cfg = C.load_config()
    out = [f"Fixelect {APP_VERSION} diagnostics - {time.strftime('%Y-%m-%d %H:%M:%S')}",
           f"OS: {platform.platform()}",
           f"Python: {platform.python_version()} ({'frozen app' if getattr(sys, 'frozen', False) else 'source'})",
           ""]
    hw = _hardware()
    out.append("Hardware: " + ", ".join(f"{k}={v}" for k, v in hw.items() if not isinstance(v, (list, dict))))

    profile = cfg.get("model_profile", "3b")
    path = D.resolve_model(profile)
    size = ""
    try:
        size = f" ({path.stat().st_size / 1048576:,.0f} MB)" if path else ""
    except Exception:
        pass
    out.append(f"Model: {profile} -> {path or 'not downloaded'}{size}")
    for k, v in (extra or {}).items():
        out.append(f"{k}: {v}")

    out.append("")
    out.append("Settings:")
    for k in sorted(cfg):
        v = cfg[k]
        if k in _PRIVATE_KEYS:
            v = f"<{len(str(v))} chars>" if v else "<empty>"
        elif k == "disabled_apps":
            v = f"{len(v)} apps"
        out.append(f"  {k} = {v}")
    try:
        from check_guard import get_user_words
        out.append(f"  protected words = {len(get_user_words())} (not listed)")
    except Exception:
        pass

    tail = _log_tail()
    out.append("")
    out.append(f"Log (last {len(tail)} lines):")
    out.extend("  " + line for line in tail)
    return "\n".join(out)
