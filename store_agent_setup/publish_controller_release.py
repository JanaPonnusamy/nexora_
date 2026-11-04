"""Publish a built NexoraDeviceController.exe so HO can push it to PCs.

    python -m store_agent_setup.publish_controller_release [--exe dist\\NexoraDeviceController.exe]

The version is the CONTROLLER_VERSION compiled into the exe (bump it in
store_agent_setup/device_controller/__init__.py before building). Copies the exe
to backend/device_controller_releases/<version>/ with a manifest signed by the
HO release key (same key and manifest convention as the Stock Client / HO
backend releases). Every HO node registers what it holds in dbo.dc_packages on
its next catalog refresh, so the version then shows up in Device Control.
"""
import argparse
import base64
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from modules.device_identity import crypto  # noqa: E402

from store_agent_setup.device_controller import CONTROLLER_VERSION, EXE_NAME  # noqa: E402
from store_agent_setup.publish_stock_release import _load_or_create_signing_key, _sha256_of  # noqa: E402

RELEASES_DIR = BACKEND / "device_controller_releases"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", default=str(REPO / "dist" / EXE_NAME))
    parser.add_argument("--version", default=CONTROLLER_VERSION)
    parser.add_argument("--notes", default="")
    args = parser.parse_args(argv)

    exe = Path(args.exe)
    if not exe.is_file():
        raise SystemExit(f"{exe} not found -- build it first: python -m store_agent_setup.build device_controller")
    folder = RELEASES_DIR / args.version
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / EXE_NAME
    shutil.copy2(str(exe), str(target))

    sha = _sha256_of(target)
    size = target.stat().st_size
    signature = base64.b64encode(
        crypto.sign(_load_or_create_signing_key(), f"{args.version}|{sha}|{size}".encode("utf-8"))
    ).decode("ascii")
    manifest = {
        "version": args.version,
        "file_name": EXE_NAME,
        "sha256": sha,
        "file_size": size,
        "signature": signature,
        "notes": args.notes,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"published controller {args.version} -> {target}\n  sha256 {sha}  size {size}")


if __name__ == "__main__":
    main()
