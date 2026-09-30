"""Keypair + signature helpers shared by HO (verify) and the device (sign).

Ed25519 is used: small keys, no padding/curve choices to get wrong, and a
single obvious signing/verification path. The device keeps the private PEM
(DPAPI-sealed on Windows); HO stores only the public PEM.
"""
from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def generate_keypair() -> tuple[str, str]:
    """Return (private_pem, public_pem) as str. Device-side helper (also used by
    tests); HO never calls this."""
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


def canonical_message(device_id: str, timestamp: str, nonce: str) -> bytes:
    """The exact bytes both sides sign/verify. Keep this stable — changing it
    invalidates in-flight signatures."""
    return f"{device_id}.{timestamp}.{nonce}".encode("utf-8")


def sign(private_pem: str, message: bytes) -> bytes:
    key = serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Not an Ed25519 private key")
    return key.sign(message)


def verify(public_pem: str, message: bytes, signature: bytes) -> bool:
    try:
        key = serialization.load_pem_public_key(public_pem.encode("utf-8"))
        if not isinstance(key, Ed25519PublicKey):
            return False
        key.verify(signature, message)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
