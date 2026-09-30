"""Agent-side device identity: keypair, DPAPI-sealed private key, and the
signature-authenticated HO token flow.

Mirror of backend/modules/device_identity/crypto.py (same Ed25519 keys, same
canonical challenge string). The private key never leaves this machine: it is
sealed at rest with Windows DPAPI (LocalMachine scope, so the service account
can read it) and only held in memory long enough to sign a challenge.

Why DPAPI and not the shared fernet.key: the fernet.key is a single file shared
by every agent and was silently wiped from the onefile temp dir by Storage
Sense (see store_agent temp/fernet incident). A DPAPI blob is bound to THIS
machine, needs no shared secret, and lives in the persistent install dir.
"""
from __future__ import annotations

import base64
import os
import time
import uuid
from pathlib import Path

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


# ---- crypto (kept byte-for-byte compatible with the HO verifier) ----------

def generate_keypair() -> tuple[str, str]:
    key = Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def _canonical_message(device_id: str, timestamp: str, nonce: str) -> bytes:
    return f"{device_id}.{timestamp}.{nonce}".encode("utf-8")


def _sign(private_pem: str, message: bytes) -> bytes:
    key = serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)
    return key.sign(message)


# ---- DPAPI sealing (Windows) with a dev/non-Windows fallback --------------

def _dpapi_available() -> bool:
    return os.name == "nt"


def dpapi_seal(plaintext: bytes) -> bytes:
    """Encrypt with DPAPI LocalMachine scope so any account on this machine
    (incl. the LocalSystem service account) can later unseal it. Falls back to
    an obfuscated (NOT secure) form off-Windows so dev/tests still run."""
    if not _dpapi_available():
        return b"PLAIN:" + base64.b64encode(plaintext)
    return _dpapi(plaintext, encrypt=True)


def dpapi_unseal(blob: bytes) -> bytes:
    if blob.startswith(b"PLAIN:"):
        return base64.b64decode(blob[len(b"PLAIN:"):])
    return _dpapi(blob, encrypt=False)


def _dpapi(data: bytes, encrypt: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    def to_blob(raw):
        buf = ctypes.create_string_buffer(raw, len(raw))
        return DATA_BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    def from_blob(blob):
        out = ctypes.string_at(blob.pbData, blob.cbData)
        ctypes.windll.kernel32.LocalFree(blob.pbData)
        return out

    CRYPTPROTECT_LOCAL_MACHINE = 0x4
    in_blob = to_blob(data)
    out_blob = DATA_BLOB()
    fn = (ctypes.windll.crypt32.CryptProtectData if encrypt
          else ctypes.windll.crypt32.CryptUnprotectData)
    ok = fn(ctypes.byref(in_blob), None, None, None, None,
            CRYPTPROTECT_LOCAL_MACHINE, ctypes.byref(out_blob))
    if not ok:
        raise OSError("DPAPI " + ("seal" if encrypt else "unseal") + " failed")
    return from_blob(out_blob)


# ---- device identity store ------------------------------------------------

class DeviceIdentity:
    """Loads (or creates) this machine's device keypair + id, and performs the
    signed token exchange with HO. State lives under the install dir so it
    survives restarts and temp wipes."""

    def __init__(self, state_dir: Path, device_id: str | None = None):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._key_file = self.state_dir / "device_key.bin"
        self._id_file = self.state_dir / "device_id.txt"
        self._device_id = device_id
        self._private_pem: str | None = None
        self._token: str | None = None
        self._token_exp: float = 0.0

    # -- key/id lifecycle --

    def device_id(self) -> str | None:
        if self._device_id:
            return self._device_id
        try:
            if self._id_file.is_file():
                self._device_id = self._id_file.read_text(encoding="utf-8").strip() or None
        except OSError:
            pass
        return self._device_id

    def set_device_id(self, device_id: str) -> None:
        self._device_id = device_id
        self._id_file.write_text(device_id, encoding="utf-8")

    def ensure_keypair(self) -> str:
        """Return the public PEM, generating + sealing a new keypair on first
        use. Used at install/registration time."""
        if self._key_file.is_file():
            self._private_pem = dpapi_unseal(self._key_file.read_bytes()).decode("utf-8")
            key = serialization.load_pem_private_key(self._private_pem.encode(), password=None)
            return key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("utf-8")
        private_pem, public_pem = generate_keypair()
        self._key_file.write_bytes(dpapi_seal(private_pem.encode("utf-8")))
        self._private_pem = private_pem
        return public_pem

    def _load_private(self) -> str:
        if self._private_pem is None:
            self._private_pem = dpapi_unseal(self._key_file.read_bytes()).decode("utf-8")
        return self._private_pem

    def is_registered(self) -> bool:
        return bool(self.device_id()) and self._key_file.is_file()

    # -- HO exchange --

    def register(self, ho_url: str, user_token: str, fingerprint: str,
                 machine_name: str | None = None, app_type: str = "store_agent",
                 app_version: str | None = None, timeout: int = 15) -> dict:
        """Register this machine with HO using a signed-in store-user's bearer
        token. Persists the returned device_id. Called once at install time."""
        public_pem = self.ensure_keypair()
        resp = requests.post(
            f"{ho_url.rstrip('/')}/api/auth/device/register",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "device_fingerprint": fingerprint,
                "public_key": public_pem,
                "key_algo": "ED25519",
                "machine_name": machine_name,
                "app_type": app_type,
                "app_version": app_version,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        self.set_device_id(data["device_id"])
        return data

    def get_token(self, ho_url: str, timeout: int = 15, refresh_skew: int = 120) -> str:
        """Return a cached access token, minting a fresh one (signed challenge)
        when missing/near-expiry."""
        now = time.time()
        if self._token and now < self._token_exp - refresh_skew:
            return self._token
        device_id = self.device_id()
        if not device_id:
            raise RuntimeError("Device is not registered (no device_id)")
        ts = str(int(now))
        nonce = uuid.uuid4().hex
        signature = base64.b64encode(
            _sign(self._load_private(), _canonical_message(device_id, ts, nonce))
        ).decode()
        resp = requests.post(
            f"{ho_url.rstrip('/')}/api/auth/device/token",
            json={"device_id": device_id, "timestamp": ts, "nonce": nonce, "signature": signature},
            timeout=timeout,
        )
        resp.raise_for_status()
        self._token = resp.json()["token"]
        # Access tokens live 12h (UNINEX_JWT_EXPIRE_MINUTES); refresh well before.
        self._token_exp = now + 12 * 3600
        return self._token

    def fetch_assigned_stores(self, ho_url: str, timeout: int = 30) -> list[dict]:
        token = self.get_token(ho_url)
        resp = requests.get(
            f"{ho_url.rstrip('/')}/api/agent/stores",
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("stores", [])
