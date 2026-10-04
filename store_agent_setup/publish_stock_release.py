"""Publish a built Stock Client installer as a DRAFT release for HO approval.

    python -m store_agent_setup.publish_stock_release <version> \
        [--exe path\\to\\Axythic-Supplier-Stock-Setup-<v>.exe] [--notes "..."]

Mirrors store_agent_setup/publish_release.py but for the Electron Stock Client,
and (unlike the agent's single is_current flag) inserts a DRAFT release row in
dbo.stock_client_releases - approval + per-store deployment happen in the HO UI,
preserving the release != rollout + authorization split.

Integrity: copies the installer into backend/stock_client_releases/<version>/,
records its sha256 + size, and Ed25519-SIGNS the manifest

    <version>|<sha256>|<file_size>

with the HO release-signing key (backend/config/stock_release_signing_key.pem,
auto-generated on first run). The on-store watchdog (Milestone 2) ships the
matching PUBLIC key and verifies the signature AND the file hash before install.
NEVER commit the private key or the release binaries (.gitignore'd).
"""
import argparse
import base64
import hashlib
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))  # reuse the module's repo + crypto

from modules.device_identity import crypto  # noqa: E402
from modules.stock_client_ops import repository as repo  # noqa: E402

RELEASES_DIR = BACKEND / "stock_client_releases"
SIGNING_KEY = BACKEND / "config" / "stock_release_signing_key.pem"
PUBLIC_KEY = BACKEND / "config" / "stock_release_signing_key.pub.pem"
DEFAULT_EXE_DIR = REPO / "desktop" / "supplier-stock-client" / "release"


def _sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_or_create_signing_key():
    """Return the private PEM, generating a stable HO signing keypair the first
    time. The public key is written alongside for embedding into the watchdog."""
    if SIGNING_KEY.is_file():
        return SIGNING_KEY.read_text(encoding="utf-8")
    SIGNING_KEY.parent.mkdir(parents=True, exist_ok=True)
    private_pem, public_pem = crypto.generate_keypair()
    SIGNING_KEY.write_text(private_pem, encoding="utf-8")
    PUBLIC_KEY.write_text(public_pem, encoding="utf-8")
    print(f"generated HO release-signing key -> {SIGNING_KEY}")
    print(f"  public key (embed in watchdog) -> {PUBLIC_KEY}")
    return private_pem


def _manifest(version, sha256, file_size):
    """Canonical signed manifest. Keep this EXACT format in sync with the
    watchdog's verifier."""
    return f"{version}|{sha256}|{file_size}".encode("utf-8")


def _default_exe(version):
    cand = DEFAULT_EXE_DIR / f"Axythic-Supplier-Stock-Setup-{version}.exe"
    return cand if cand.is_file() else None


def publish(version, exe_path, notes=None, build=None, min_supported=None):
    exe_path = Path(exe_path) if exe_path else _default_exe(version)
    if not exe_path or not exe_path.is_file():
        raise SystemExit(
            f"installer not found: {exe_path}\n"
            f"build it first (cd desktop/supplier-stock-client && npm run dist), "
            f"or pass --exe."
        )

    dest_dir = RELEASES_DIR / version
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / exe_path.name
    shutil.copy2(exe_path, dest)

    sha256 = _sha256_of(dest)
    size = dest.stat().st_size
    private_pem = _load_or_create_signing_key()
    signature = base64.b64encode(crypto.sign(private_pem, _manifest(version, sha256, size))).decode("utf-8")

    release = repo.create_release(
        version=version,
        file_name=dest.name,
        package_path=str(dest),
        sha256=sha256,
        file_size=size,
        signature=signature,
        release_notes=notes,
        build=build,
        min_supported_version=min_supported,
        created_by="publish_cli",
    )

    print(f"published DRAFT release {version}  ({release['release_id']})")
    print(f"  file:      {dest}")
    print(f"  sha256:    {sha256}")
    print(f"  size:      {size} bytes")
    print(f"  signature: {signature[:24]}...")
    print("  next: approve + deploy it from the HO Store Client Monitor.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Publish a Stock Client DRAFT release.")
    parser.add_argument("version")
    parser.add_argument("--exe", default=None)
    parser.add_argument("--notes", default=None)
    parser.add_argument("--build", default=None)
    parser.add_argument("--min-supported", default=None)
    args = parser.parse_args(argv)
    publish(args.version, args.exe, args.notes, args.build, args.min_supported)


if __name__ == "__main__":
    main(sys.argv[1:])
