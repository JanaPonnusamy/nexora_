"""Device Controller: signing protocol, command validation, and the controller's
message verification (forgery / wrong device / expiry / replay)."""
import sys
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

from modules.device_controller import protocol, service
from modules.device_identity import crypto

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture
def keypair():
    return crypto.generate_keypair()


def test_sign_verify_roundtrip_and_tamper(keypair):
    priv, pub = keypair
    payload = {"v": 1, "kind": "command", "id": "x", "device_id": "d", "args": {"a": 1}}
    sig = protocol.sign(priv, payload)
    assert protocol.verify(pub, payload, sig)
    assert not protocol.verify(pub, {**payload, "args": {"a": 2}}, sig)
    assert not protocol.verify(pub, payload, "not-base64!!")


def test_canonical_is_key_order_independent():
    assert protocol.canonical({"b": 1, "a": 2}) == protocol.canonical({"a": 2, "b": 1})


@pytest.fixture
def fake_backend(monkeypatch, keypair):
    priv, _ = keypair
    stored = {}
    monkeypatch.setattr(service.signing, "private_key_pem", lambda: priv)
    monkeypatch.setattr(service.repository, "get_device",
                        lambda d: {"device_id": d, "registration_status": "active"})
    monkeypatch.setattr(service.repository, "insert_command",
                        lambda cid, dev, app, action, args, payload, sig, actor, exp:
                        stored.update(payload=payload, signature=sig) or {"command_id": cid})
    monkeypatch.setattr(service.repository, "set_desired",
                        lambda *a: stored.setdefault("desired", []).append(a))
    monkeypatch.setattr(service.packages, "sync_local_packages", lambda *a, **k: 0)
    monkeypatch.setattr(service.repository, "get_package", lambda app, v: {
        "version": v, "file_name": "x.exe", "sha256": "AB" * 32, "file_size": 10,
        "signature": None, "source_urls": "http://a:8000,http://b:8000"})
    return stored


def test_command_is_signed_and_sets_desired(fake_backend, keypair):
    _, pub = keypair
    service.create_command("DEV-1", "store_agent", "pause", {"minutes": 5}, "admin")
    payload, sig = fake_backend["payload"], fake_backend["signature"]
    assert protocol.verify(pub, payload, sig)
    assert payload["device_id"] == "dev-1" and payload["args"] == {"minutes": 5}
    assert fake_backend["desired"][0][2:4] == ("PAUSED", 5)


def test_update_embeds_package_metadata(fake_backend):
    service.create_command("d", "ho_backend", "update", {"version": "1.2.0"}, "admin")
    pkg = fake_backend["payload"]["args"]["package"]
    assert pkg["sha256"] == "ab" * 32
    assert pkg["sources"] == ["http://a:8000", "http://b:8000"]


@pytest.mark.parametrize("app,action,args", [
    ("store_agent", "explode", {}),
    ("nope", "start", {}),
    ("mail_transfer", "update", {"version": "1"}),
    ("store_agent", "set_ho_urls", {"urls": ["ftp://x"]}),
    ("store_agent", "set_ho_urls", {"urls": []}),
    ("ho_backend", "update", {}),
])
def test_invalid_commands_rejected(fake_backend, app, action, args):
    with pytest.raises(HTTPException):
        service.create_command("d", app, action, args, "admin")


def test_controller_verify_rejects_forgery_wrong_device_and_expiry(keypair, monkeypatch):
    from store_agent_setup.device_controller import service as ctl

    priv, pub = keypair
    c = ctl.Controller.__new__(ctl.Controller)
    c.hq_public_key = pub
    c.cfg = {"device_id": "DEV-1"}
    now = int(time.time())
    good = {"v": 1, "kind": "command", "id": "1", "device_id": "dev-1",
            "issued_at": now, "expires_at": now + 60}
    assert c.verify({"payload": good, "signature": protocol.sign(priv, good)}) is None

    other_priv, _ = crypto.generate_keypair()
    assert c.verify({"payload": good, "signature": protocol.sign(other_priv, good)}) == "bad signature"

    other_dev = {**good, "device_id": "dev-2"}
    assert "another device" in c.verify({"payload": other_dev, "signature": protocol.sign(priv, other_dev)})

    expired = {**good, "expires_at": now - 3600}
    assert c.verify({"payload": expired, "signature": protocol.sign(priv, expired)}) == "message expired"
