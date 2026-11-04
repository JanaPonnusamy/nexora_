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


def test_enrollment_is_proven_against_the_new_ho(monkeypatch, tmp_path):
    """Moving an enrolled PC to another HO: the inbox enrollment must be proven
    against the HO that issued the new id, not the previously active URL."""
    import json as _json

    from store_agent_setup.device_controller import ho as ctl_ho
    from store_agent_setup.device_controller import service as ctl

    monkeypatch.setattr(ctl, "INBOX_DIR", tmp_path)
    monkeypatch.setattr(ctl, "save_config", lambda cfg: None)
    monkeypatch.setattr(ctl, "log", lambda *a, **k: None)   # never touch the real controller.log
    (tmp_path / "enrollment.json").write_text(
        _json.dumps({"device_id": "NEW-ID", "ho_urls": ["http://new-ho:8444"]}), encoding="utf-8")
    c = ctl.Controller.__new__(ctl.Controller)
    c.cfg = {"device_id": "OLD-ID", "ho_urls": ["http://old-ho:8000"], "device_private_key_pem": "k"}
    c.ho = ctl_ho.HoClient(c.cfg)
    c.ho._active = "http://old-ho:8000"
    asked = []

    def token(base, force=False):
        asked.append(base)
        if base != "http://new-ho:8444":
            raise ctl_ho.NotEnrolled("unknown device")
        return "T"

    monkeypatch.setattr(c.ho, "_token", token)
    c.pick_up_enrollment()
    assert asked == ["http://new-ho:8444"]
    assert c.cfg["device_id"] == "NEW-ID"
    assert c.cfg["ho_urls"][0] == "http://new-ho:8444"


class _Resp:
    def __init__(self, code):
        self.status_code = code
        self.text = "{}"


def _ho_client(monkeypatch, answers, enrolled_at=None):
    """HoClient whose URLs answer from `answers` {url: status}; `enrolled_at`
    limits which HOs know the device (others reject its token)."""
    import requests

    from store_agent_setup.device_controller import ho as ctl_ho

    urls = list(answers)
    client = ctl_ho.HoClient({"ho_urls": urls, "device_id": "D", "device_private_key_pem": "k"})

    def token(base, force=False):
        if enrolled_at is not None and base not in enrolled_at:
            raise ctl_ho.NotEnrolled("unknown device")
        return "T"

    def request(method, url, **kwargs):
        for base, code in answers.items():
            if url.startswith(base):
                if code is None:
                    raise requests.ConnectionError("down")
                return _Resp(code)
        raise AssertionError(url)

    monkeypatch.setattr(client, "_token", token)
    monkeypatch.setattr(requests, "request", request)
    return client


def test_controller_skips_an_ho_without_the_controller_api(monkeypatch):
    """The 2026-11-04 outage: after its HO restarted, every controller failed
    over to an older HO that answers 404/405 and stayed there for good."""
    c = _ho_client(monkeypatch, {"http://old-build:8000": 404, "http://ho:8000": 200})
    c._active = "http://old-build:8000"
    assert c.request("GET", "/api/agent/controller/poll").status_code == 200
    assert c._active == "http://ho:8000"


def test_controller_skips_another_hos_url_that_does_not_know_it(monkeypatch):
    c = _ho_client(monkeypatch, {"http://ho:8000": None, "http://127.0.0.1:8000": 200,
                                 "http://ho-public:8443": 200},
                   enrolled_at={"http://ho:8000", "http://ho-public:8443"})
    assert c.request("POST", "/api/agent/controller/heartbeat").status_code == 200
    assert c._active == "http://ho-public:8443"


def test_controller_failover_keeps_old_answers_when_nothing_serves(monkeypatch):
    from store_agent_setup.device_controller import ho as ctl_ho

    c = _ho_client(monkeypatch, {"http://a:8000": 404, "http://b:8000": None})
    c._active = "http://a:8000"
    assert c.request("GET", "/api/agent/controller/poll").status_code == 404   # as before
    c = _ho_client(monkeypatch, {"http://a:8000": 200, "http://b:8000": 200}, enrolled_at=set())
    with pytest.raises(ctl_ho.NotEnrolled):
        c.request("GET", "/api/agent/controller/poll")
