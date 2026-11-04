"""Nexora Setup (one kit) -- HO side, peer package mirror, store binding."""
import hashlib
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.device_controller import packages  # noqa: E402
from modules.device_identity import router as device_router  # noqa: E402
from modules.setup_kit import service  # noqa: E402

SUPER = {"sub": "u-super", "username": "devadmin", "role_names": ["SUPER_ADMIN"]}
STORE_USER = {"sub": "u-1", "username": "smg", "role_names": ["STORE_USER"],
              "store_id": "0c870c04-5b85-44e5-a2f7-51c40c764dfd", "tenant_id": "t-1"}


def _pkgs(monkeypatch, rows):
    monkeypatch.setattr(service.packages, "sync_local_packages", lambda *a, **k: 0)
    monkeypatch.setattr(service.dc_repo, "list_packages", lambda: rows)


def test_latest_version_is_numeric_not_text(monkeypatch):
    _pkgs(monkeypatch, [
        {"app_key": "controller", "version": "1.0.10", "sha256": "a", "file_name": "c", "file_size": 1},
        {"app_key": "controller", "version": "1.0.9", "sha256": "b", "file_name": "c", "file_size": 1},
        {"app_key": "store_agent", "version": "2026.11.04.1", "sha256": "c", "file_name": "a", "file_size": 1},
        {"app_key": "store_agent", "version": "2026.11.03.1", "sha256": "d", "file_name": "a", "file_size": 1},
    ])
    latest = service.latest_versions()
    assert latest["controller"]["version"] == "1.0.10"
    assert latest["store_agent"]["version"] == "2026.11.04.1"


def test_plan_rules(monkeypatch):
    _pkgs(monkeypatch, [
        {"app_key": k, "version": "1.0.0", "sha256": "x", "file_name": "f", "file_size": 1}
        for k in ("controller", "store_agent", "stock_client", "ho_backend")
    ])
    win7_32 = {"arch": "x86", "ram_mb": 1024, "odbc_drivers": []}
    out = {c["app_key"]: c for c in service.plan(win7_32, STORE_USER)["components"]}
    assert out["controller"]["required"] and out["controller"]["eligible"]
    assert not out["stock_client"]["eligible"]          # 32-bit
    assert out["store_agent"]["eligible"] and "ODBC" in out["store_agent"]["reason"]
    assert not out["ho_backend"]["eligible"]
    assert service.plan(win7_32, STORE_USER)["warnings"]  # low RAM
    ok = {c["app_key"]: c for c in service.plan(
        {"arch": "AMD64", "ram_mb": 8192, "odbc_drivers": ["ODBC Driver 17 for SQL Server"]},
        STORE_USER)["components"]}
    assert ok["stock_client"]["eligible"] and ok["store_agent"]["reason"] is None


def test_install_only_by_registering_user_or_super_admin(monkeypatch):
    monkeypatch.setattr(service.device_repo, "get_device", lambda d: {
        "device_id": d, "status": "active", "registered_by_user_id": "U-OTHER"})
    with pytest.raises(HTTPException) as e:
        service.queue_install("dev", ["store_agent"], {}, STORE_USER)
    assert e.value.status_code == 403

    _pkgs(monkeypatch, [{"app_key": "store_agent", "version": "2", "sha256": "x",
                         "file_name": "f", "file_size": 1}])
    made = []
    monkeypatch.setattr(service.dc_service, "create_command",
                        lambda dev, app, action, args, actor: made.append((app, action, args)) or
                        {"command_id": "C1"})
    res = service.queue_install("dev", ["controller", "store_agent", "ho_backend"],
                                {"store_agent": r"D:\NexoraStoreAgent"}, SUPER)
    assert made == [("store_agent", "install", {"version": "2", "install_dir": r"D:\NexoraStoreAgent"})]
    assert res["commands"][0]["command_id"] == "C1"


def test_peer_key_required_and_constant_time(monkeypatch):
    monkeypatch.delenv("NEXORA_PACKAGE_PEER_KEY", raising=False)
    assert not packages.peer_key_ok("anything")       # unset = off
    monkeypatch.setenv("NEXORA_PACKAGE_PEER_KEY", "s3cret")
    assert packages.peer_key_ok("s3cret")
    assert not packages.peer_key_ok("wrong") and not packages.peer_key_ok(None)


def test_ensure_local_rejects_hash_mismatch_and_keeps_good_copy(monkeypatch, tmp_path):
    body = b"controller-exe-bytes"
    monkeypatch.setenv("NEXORA_PACKAGE_PEER_KEY", "k")
    monkeypatch.setenv("NEXORA_PACKAGE_PEERS", "http://peer:8000")
    monkeypatch.setattr(packages, "self_base_url", lambda: "http://me:8000")
    monkeypatch.setitem(packages.RELEASE_ROOTS, "controller", tmp_path / "rel")
    upserts = []
    monkeypatch.setattr(packages.repository, "upsert_package", lambda *a: upserts.append(a))

    class Resp:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_content(self, chunk_size):
            yield body

    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp())

    monkeypatch.setattr(packages.repository, "get_package", lambda a, v: {
        "file_name": "NexoraDeviceController.exe", "sha256": "0" * 64, "file_size": len(body),
        "signature": None, "source_urls": "http://peer:8000"})
    assert packages.ensure_local("controller", "1.0.6") is None   # wrong hash -> discarded
    assert not (tmp_path / "rel" / "1.0.6").exists()

    good = hashlib.sha256(body).hexdigest()
    monkeypatch.setattr(packages.repository, "get_package", lambda a, v: {
        "file_name": "NexoraDeviceController.exe", "sha256": good, "file_size": len(body),
        "signature": None, "source_urls": "http://peer:8000"})
    path, name = packages.ensure_local("controller", "1.0.6")
    assert name == "NexoraDeviceController.exe" and path.read_bytes() == body
    assert (tmp_path / "rel" / "1.0.6" / "manifest.json").is_file()
    assert upserts and upserts[-1][2] == "http://me:8000"


def test_setup_store_binding_rules(monkeypatch):
    assert device_router._setup_store(None, STORE_USER) is None
    own = device_router._setup_store(STORE_USER["store_id"].upper(), STORE_USER)
    assert own == {"store_id": STORE_USER["store_id"], "tenant_id": "t-1"}
    with pytest.raises(HTTPException) as e:
        device_router._setup_store("someone-elses-store", STORE_USER)
    assert e.value.status_code == 403

    import services.store_service as ss
    monkeypatch.setattr(ss.StoreService, "get_by_id", lambda self, sid: ("x", "TEN-1"))
    assert device_router._setup_store("S-9", SUPER) == {"store_id": "S-9", "tenant_id": "TEN-1"}
