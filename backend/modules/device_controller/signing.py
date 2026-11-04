"""HO command-signing key.

The PRIVATE key never goes to git (see .gitignore); every HO node that should be
able to issue controller commands needs a copy:
  * git node:   backend/config/device_controller_command_key.pem
  * exe node:   <install dir>/config/device_controller_command_key.pem
  * or the path in env DEVICE_CONTROLLER_COMMAND_KEY.
The PUBLIC key (device_controller_command_key.pub.pem) is tracked in git and
bundled into NexoraDeviceController.exe, which verifies every message with it.

Generate a new pair (only once for the whole fleet -- rotating it means
re-shipping the controller):
    python -m modules.device_controller.signing generate
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import HTTPException

KEY_NAME = "device_controller_command_key.pem"
PUB_NAME = "device_controller_command_key.pub.pem"
_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def _candidates():
    env = os.getenv("DEVICE_CONTROLLER_COMMAND_KEY", "").strip()
    if env:
        yield Path(env)
    if getattr(sys, "frozen", False):
        yield Path(sys.executable).resolve().parent / "config" / KEY_NAME
    yield _CONFIG_DIR / KEY_NAME


def private_key_pem() -> str:
    for path in _candidates():
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8")
        except OSError:
            continue
    raise HTTPException(
        status_code=503,
        detail=("This HO node has no device-controller command key "
                f"({KEY_NAME}); copy it into the HO config folder to issue commands."),
    )


def has_private_key() -> bool:
    try:
        private_key_pem()
        return True
    except HTTPException:
        return False


def public_key_pem() -> str | None:
    for path in (_CONFIG_DIR / PUB_NAME,):
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8")
        except OSError:
            continue
    return None


def _generate():
    from modules.device_identity import crypto

    priv, pub = crypto.generate_keypair()
    key_path, pub_path = _CONFIG_DIR / KEY_NAME, _CONFIG_DIR / PUB_NAME
    if key_path.exists():
        raise SystemExit(f"{key_path} already exists; refusing to overwrite the fleet key.")
    key_path.write_text(priv, encoding="utf-8")
    pub_path.write_text(pub, encoding="utf-8")
    print(f"wrote {key_path}\nwrote {pub_path}")


if __name__ == "__main__":
    if sys.argv[1:] == ["generate"]:
        _generate()
    else:
        print(__doc__)
