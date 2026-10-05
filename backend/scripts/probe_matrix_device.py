"""READ-ONLY identity probe of Matrix COSEC devices over HTTP (own hardware).

Fetches each device's web root (and a few well-known Matrix API paths) to identify
model/firmware and whether an event API is exposed. GET only -- no config change,
no writes, no door commands. This informs a direct-from-device integration plan.
"""
from __future__ import annotations
import ssl
import urllib.request
from pathlib import Path

OUT = Path(r"E:\nexora\matrix_device_probe.txt")
DEVICES = [
    ("NATHAN-S", "192.168.10.53"),
    ("NATHAN-C", "192.168.10.54"),
    ("NATHAN-A", "192.168.10.52"),
    ("NATHAN G", "192.168.10.55"),
]
# well-known Matrix COSEC device HTTP endpoints to test for existence (GET only)
PATHS = ["/", "/index.html", "/login.html", "/cosec/", "/api/", "/device.cgi", "/eventlog"]

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def head_get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
    r = urllib.request.urlopen(req, timeout=6, context=ctx)
    body = r.read(1500).decode("utf-8", "replace")
    server = r.headers.get("Server", "")
    www = r.headers.get("WWW-Authenticate", "")
    title = ""
    lo = body.lower()
    if "<title>" in lo:
        title = body[lo.find("<title>") + 7: lo.find("</title>")][:80]
    return r.status, server, www, title, body[:200]


def main() -> int:
    lines: list[str] = []
    add = lines.append
    add("MATRIX COSEC DEVICE HTTP IDENTITY PROBE -- READ-ONLY (GET only)")
    add("=" * 70)
    for name, ip in DEVICES:
        add(f"\n### {name}  {ip}")
        for scheme in ("http", "https"):
            base = f"{scheme}://{ip}"
            try:
                st, server, www, title, snip = head_get(base + "/")
                add(f"  {scheme}/ -> {st}  Server='{server}'  WWW-Auth='{www}'  Title='{title}'")
                add(f"       snippet: {snip!r}")
            except Exception as e:  # noqa: BLE001
                add(f"  {scheme}/ -> ERR {type(e).__name__}: {e}")
                continue
            # probe a few known paths on the scheme that answered
            for p in PATHS[1:]:
                try:
                    st, server, www, title, snip = head_get(base + p)
                    add(f"     {p} -> {st}  Title='{title}'")
                except Exception as e:  # noqa: BLE001
                    code = getattr(e, "code", type(e).__name__)
                    add(f"     {p} -> {code}")
            break  # one working scheme is enough for identity
    OUT.parent.mkdir(parents=True, exist_ok=True)
    report = "\n".join(lines) + "\n"
    OUT.write_text(report, encoding="utf-8")
    print(report)
    print(f"(report: {OUT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
