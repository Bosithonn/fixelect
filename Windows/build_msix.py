"""
Build the Microsoft Store package (Fixelect.msix) from the PyInstaller output.

  python build_msix.py --name 12345Bositxon.Fixelect --publisher "CN=XXXXXXXX-..." \
                       --publisher-display "Bositxon Erkinxonov" [--dist dist/Fixelect] [--out dist/Fixelect.msix]

The three identity values come from Partner Center → your app → Product identity.
Upload the unsigned .msix there: the Store signs it. For a local or CI test
install, pass --sign-with test.pfx (a throwaway certificate whose subject
equals --publisher).
"""

import argparse
import pathlib
import re
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent


def sdk_tool(name):
    """makeappx.exe / signtool.exe from the newest installed Windows SDK."""
    found = sorted(pathlib.Path(r"C:\Program Files (x86)\Windows Kits\10\bin").glob(f"10.*/x64/{name}"))
    if not found:
        sys.exit(f"{name} not found: install the Windows 10/11 SDK.")
    return str(found[-1])


def app_version():
    text = (ROOT / "shared" / "version.py").read_text(encoding="utf-8")
    parts = re.search(r'APP_VERSION\s*=\s*"([\d.]+)"', text).group(1).split(".")
    return ".".join((parts + ["0", "0", "0"])[:3] + ["0"])   # the Store needs a.b.c.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="Package/Identity/Name from Partner Center")
    ap.add_argument("--publisher", required=True, help='Package/Identity/Publisher, e.g. "CN=..."')
    ap.add_argument("--publisher-display", required=True, help="Package/Properties/PublisherDisplayName")
    ap.add_argument("--dist", default=str(HERE / "dist" / "Fixelect"))
    ap.add_argument("--out", default=str(HERE / "dist" / "Fixelect.msix"))
    ap.add_argument("--sign-with", help="test only: .pfx to sign with (the Store signs uploads itself)")
    ap.add_argument("--pfx-password", default="")
    a = ap.parse_args()

    dist = pathlib.Path(a.dist)
    if not (dist / "Fixelect.exe").is_file():
        sys.exit(f"{dist}\\Fixelect.exe not found: build with PyInstaller first.")
    stage = HERE / "build" / "msix-stage"
    shutil.rmtree(stage, ignore_errors=True)
    shutil.copytree(dist, stage / "Fixelect")
    shutil.copytree(HERE / "msix" / "Assets", stage / "Assets")

    manifest = (HERE / "msix" / "AppxManifest.xml").read_text(encoding="utf-8")
    manifest = re.sub(r"<!--.*?-->\s*", "", manifest, count=1, flags=re.S)   # the template's header note
    from xml.sax.saxutils import escape
    for key, value in (("{NAME}", a.name), ("{PUBLISHER}", a.publisher),
                       ("{PUBLISHER_DISPLAY}", a.publisher_display), ("{VERSION}", app_version())):
        manifest = manifest.replace(key, escape(value, {'"': "&quot;"}))
    (stage / "AppxManifest.xml").write_text(manifest, encoding="utf-8")

    # resources.pri maps "Assets\StoreLogo.png" to the right scale-100/200/400 file
    makepri = sdk_tool("makepri.exe")
    priconfig = HERE / "build" / "priconfig.xml"
    subprocess.run([makepri, "createconfig", "/cf", str(priconfig), "/dq", "en-US", "/pv", "10.0.0", "/o"],
                   check=True, stdout=subprocess.DEVNULL)
    subprocess.run([makepri, "new", "/pr", str(stage), "/cf", str(priconfig),
                    "/of", str(stage / "resources.pri"), "/o"], check=True, stdout=subprocess.DEVNULL)

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sdk_tool("makeappx.exe"), "pack", "/o", "/h", "SHA256", "/d", str(stage), "/p", str(out)],
                   check=True)
    if a.sign_with:
        subprocess.run([sdk_tool("signtool.exe"), "sign", "/fd", "SHA256", "/f", a.sign_with,
                        "/p", a.pfx_password, str(out)], check=True)
    print(f"Built {out} (version {app_version()}, {out.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
