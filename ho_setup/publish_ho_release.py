"""Publish a built HO backend as an updatable release for the frozen-exe nodes.

Git-checkout HO nodes (the build box, NODE9-PC) update themselves with
deploy_ho_prod.bat. The frozen-exe nodes (installed from HO_Setup.exe, running
the UniNexHO service) have no git, so they instead PULL a signed bundle that this
script publishes on the build node:

    python -m ho_setup.publish_ho_release <version> [--notes "..."]

It zips dist/HO_Backend (HO_Backend.exe + _internal) together with the built SPA
(frontend/dist), records sha256 + size, Ed25519-signs the canonical manifest

    <version>|<sha256>|<file_size>

with the shared release-signing key (backend/config/stock_release_signing_key.pem,
the same key the stock client uses), and writes it under
backend/ho_backend_releases/<version>/ plus a latest.json pointer. The exe nodes
download it from the build node via /api/ho-ops/backend-release/* and verify the
signature AND hash (using the bundled public key) before swapping. NEVER commit
the release zips or the private key (.gitignore'd).
"""
import argparse
import base64
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from modules.device_identity import crypto  # noqa: E402

HO_DIST = REPO / "dist" / "HO_Backend"
FRONTEND_DIST = REPO / "frontend" / "dist"
RELEASES_DIR = BACKEND / "ho_backend_releases"
SIGNING_KEY = BACKEND / "config" / "stock_release_signing_key.pem"
PUBLIC_KEY = BACKEND / "config" / "stock_release_signing_key.pub.pem"
VERSION_MARKER = "HO_BACKEND_VERSION.txt"


def _sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_or_create_signing_key():
    if SIGNING_KEY.is_file():
        return SIGNING_KEY.read_text(encoding="utf-8")
    SIGNING_KEY.parent.mkdir(parents=True, exist_ok=True)
    private_pem, public_pem = crypto.generate_keypair()
    SIGNING_KEY.write_text(private_pem, encoding="utf-8")
    PUBLIC_KEY.write_text(public_pem, encoding="utf-8")
    print(f"generated release-signing key -> {SIGNING_KEY}")
    return private_pem


def _add_tree(zf, root: Path, arc_prefix: str):
    for p in sorted(root.rglob("*")):
        if p.is_file():
            zf.write(p, f"{arc_prefix}/{p.relative_to(root).as_posix()}")


def publish(version, notes=None):
    if not (HO_DIST / "HO_Backend.exe").is_file():
        raise SystemExit(
            f"{HO_DIST / 'HO_Backend.exe'} not found.\n"
            f"Build it first: python -m ho_setup.build backend"
        )
    if not FRONTEND_DIST.is_dir():
        raise SystemExit(
            f"{FRONTEND_DIST} not found. Build it first: (cd frontend && npm run build)"
        )

    dest_dir = RELEASES_DIR / version
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / f"HO_Backend-{version}.zip"

    print(f"packaging {zip_path} ...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Backend onedir at the zip root: HO_Backend.exe + _internal/...
        _add_tree(zf, HO_DIST, ".")
        # SPA under frontend/ (matches the install layout {app}\frontend).
        _add_tree(zf, FRONTEND_DIST, "frontend")
        zf.writestr(VERSION_MARKER, version)

    sha256 = _sha256_of(zip_path)
    size = zip_path.stat().st_size
    private_pem = _load_or_create_signing_key()
    manifest_bytes = f"{version}|{sha256}|{size}".encode("utf-8")
    signature = base64.b64encode(crypto.sign(private_pem, manifest_bytes)).decode("utf-8")

    manifest = {
        "version": version,
        "file_name": zip_path.name,
        "sha256": sha256,
        "file_size": size,
        "signature": signature,
        "notes": notes,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    (dest_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (RELEASES_DIR / "latest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"published HO backend release {version}")
    print(f"  zip:       {zip_path}")
    print(f"  sha256:    {sha256}")
    print(f"  size:      {size} bytes")
    print(f"  signature: {signature[:24]}...")
    print("  exe nodes can now pull it from the Backend Update page.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Publish an HO backend release for exe nodes.")
    parser.add_argument("version")
    parser.add_argument("--notes", default=None)
    args = parser.parse_args(argv)
    publish(args.version, args.notes)


if __name__ == "__main__":
    main(sys.argv[1:])
