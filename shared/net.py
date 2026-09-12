"""HTTPS for Fixelect: verify servers with the operating system's certificates.

Python frozen into a macOS app carries its own OpenSSL with no list of trusted
certificates, so a plain urlopen fails with CERTIFICATE_VERIFY_FAILED.
truststore verifies through the system instead (Keychain on macOS, the
certificate store on Windows), so company proxies and custom roots keep
working; certifi's bundle and macOS's /etc/ssl/cert.pem are fallbacks.
"""

import os
import ssl
import urllib.request

_context = None
_source = "default"


def ssl_context():
    global _context, _source
    if _context is None:
        try:
            import truststore
            _context, _source = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), "system certificates"
        except Exception:
            try:
                import certifi
                _context, _source = ssl.create_default_context(cafile=certifi.where()), "certifi"
            except Exception:
                cafile = "/etc/ssl/cert.pem" if os.path.isfile("/etc/ssl/cert.pem") else None
                _context, _source = ssl.create_default_context(cafile=cafile), cafile or "default"
    return _context


def urlopen(req, timeout=30):
    return urllib.request.urlopen(req, timeout=timeout, context=ssl_context())


def check(url):
    """(ok, detail) for one HEAD request - used by --check-https and the smoke tests."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Fixelect"})
        with urlopen(req, timeout=20) as resp:
            return True, f"HTTP {resp.status} using {_source}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e} (using {_source})"
