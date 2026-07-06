"""Validation for the Store Agent Setup Wizard (SYNC-029A).

Exercises the non-GUI logic: HO client (live when HO is up), config
read/write, installer file layout, and store_agent.config resolution from a
deployed agent_config.json.
"""
import json
import os

import pytest
import requests

from store_agent_setup.agent_config import (build_config, config_path,
                                            read_config, write_config)
from store_agent_setup.ho_client import HoClient, HoConnectionError
from store_agent_setup.installer import SUBDIRS, Installer
from store_agent_setup.paths import default_install_path

HO_URL = os.environ.get("NEXORA_HO_URL", "http://127.0.0.1:8000")


def _ho_up():
    try:
        return requests.get(f"{HO_URL}/health", timeout=3).ok
    except requests.RequestException:
        return False


live = pytest.mark.skipif(not _ho_up(), reason="HO not reachable")


# ---- config model ---------------------------------------------------------

def test_build_and_roundtrip_config(tmp_path):
    tenant = {"tenant_id": "T1", "tenant_name": "Nathan"}
    store = {"store_id": "S1", "store_name": "NMC Branch", "store_code": "NMC"}
    cfg = build_config(f"{HO_URL}/", tenant, store, tmp_path, log_level="DEBUG")

    assert cfg["ho_url"] == HO_URL  # trailing slash stripped
    assert cfg["store_id"] == "S1"
    assert cfg["tenant_name"] == "Nathan"
    assert cfg["log_level"] == "DEBUG"
    assert cfg["install_path"] == str(tmp_path)

    write_config(tmp_path, cfg)
    assert config_path(tmp_path).is_file()
    assert read_config(tmp_path) == cfg


# ---- installer ------------------------------------------------------------

def test_installer_creates_directory_layout(tmp_path):
    inst = Installer(tmp_path / "NexoraStoreAgent")
    inst.create_directories()
    for name in SUBDIRS:
        assert (tmp_path / "NexoraStoreAgent" / name).is_dir()


def test_installer_persists_configs(tmp_path):
    root = tmp_path / "NexoraStoreAgent"
    inst = Installer(root)
    inst.create_directories()
    agent_cfg = {"store_id": "S1", "ho_url": HO_URL}
    ho_cfg = {"store_id": "S1", "server_name": "X\\SQLEXPRESS"}
    inst.save_agent_config_json(agent_cfg)
    inst.save_ho_agent_config(ho_cfg)
    assert json.loads((root / "agent_config.json").read_text())["store_id"] == "S1"
    assert (root / "cache" / "ho_agent_config.json").is_file()


def _fake_agent_dist(tmp_path, with_source=False):
    """A stand-in for the prebuilt standalone agent onedir (exe + _internal)."""
    dist = tmp_path / "dist" / "NexoraStoreAgent"
    (dist / "_internal").mkdir(parents=True)
    (dist / "NexoraStoreAgent.exe").write_bytes(b"MZ")
    (dist / "_internal" / "python313.dll").write_bytes(b"DLL")
    (dist / "_internal" / "base_library.zip").write_bytes(b"PK")
    if with_source:
        (dist / "_internal" / "leaked.py").write_text("print('oops')")
    return dist


def test_standalone_deploy_has_no_python_source(tmp_path, monkeypatch):
    """SYNC-029B: deploy must drop exe + _internal only, never .py source and
    never a runtime/store_agent tree."""
    root = tmp_path / "NexoraStoreAgent"
    inst = Installer(root)
    inst.create_directories()
    dist = _fake_agent_dist(tmp_path)
    monkeypatch.setattr(inst, "_locate_agent_distribution", lambda: dist)
    inst.copy_runtime_files()

    assert (root / "NexoraStoreAgent.exe").is_file()
    assert (root / "_internal").is_dir()
    assert not (root / "runtime").exists()         # no source tree
    assert not list(root.rglob("*.py"))            # zero python source files


def test_deploy_rejects_leaked_source(tmp_path, monkeypatch):
    """If the build accidentally bundles .py source, the install must fail."""
    root = tmp_path / "NexoraStoreAgent"
    inst = Installer(root)
    inst.create_directories()
    dist = _fake_agent_dist(tmp_path, with_source=True)
    monkeypatch.setattr(inst, "_locate_agent_distribution", lambda: dist)
    with pytest.raises(RuntimeError):
        inst.copy_runtime_files()


def test_deploy_requires_built_distribution(tmp_path, monkeypatch):
    """No prebuilt standalone distribution -> loud failure, not silent."""
    root = tmp_path / "NexoraStoreAgent"
    inst = Installer(root)
    inst.create_directories()
    monkeypatch.setattr(inst, "_locate_agent_distribution", lambda: None)
    with pytest.raises(FileNotFoundError):
        inst.copy_runtime_files()


def test_frozen_service_install_forces_auto_start(tmp_path):
    """Regression: frozen install must register the service with start= auto
    and reassert it, so it can never be left Disabled (error 1058)."""
    from store_agent_setup.service_manager import ServiceManager

    (tmp_path / "NexoraStoreAgent.exe").write_bytes(b"MZ")
    sm = ServiceManager(tmp_path)
    calls = []

    def fake_exec(cmd, check=True):
        calls.append(cmd)
        class P:
            returncode = 0
            stdout = ''
            stderr = ''
        return P()

    sm._exec = fake_exec
    sm.is_installed = lambda: False
    sm.status = lambda: 'running'
    sm.install()
    sm.start()

    create = next(c for c in calls if c[:2] == ['sc', 'create'])
    assert create[create.index('start=') + 1] == 'auto'
    assert 'binPath=' in create
    # start type reasserted via sc config at least once
    configs = [c for c in calls if c[:2] == ['sc', 'config']]
    assert configs and all(c[c.index('start=') + 1] == 'auto' for c in configs)
    assert any(c[:2] == ['sc', 'start'] for c in calls)


def test_default_install_path_is_drive_rooted():
    p = default_install_path()
    assert p.endswith("NexoraStoreAgent")
    assert p[0] in ("C", "D")


# ---- store_agent.config resolution ---------------------------------------

def test_agent_config_resolution_from_env(tmp_path, monkeypatch):
    cfg = {"store_id": "STORE-XYZ", "ho_url": "http://10.0.0.5:8000"}
    path = tmp_path / "agent_config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setenv("NEXORA_AGENT_CONFIG", str(path))

    import importlib

    import store_agent.config as agent_config
    importlib.reload(agent_config)
    try:
        assert agent_config.STORE_ID == "STORE-XYZ"
        assert agent_config.HO_API_URL == "http://10.0.0.5:8000"
    finally:
        monkeypatch.delenv("NEXORA_AGENT_CONFIG", raising=False)
        importlib.reload(agent_config)


# ---- HO client (live) -----------------------------------------------------

@live
def test_health():
    assert HoClient(HO_URL).test_connection()["status"].lower() == "healthy"


@live
def test_bad_url_raises():
    with pytest.raises(HoConnectionError):
        HoClient("http://127.0.0.1:59999").test_connection()


@live
def test_tenants_and_stores_and_agent_config():
    ho = HoClient(HO_URL)
    tenants = ho.get_tenants()
    assert tenants, "expected at least one active tenant"
    tenant_id = tenants[0]["tenant_id"]

    stores = ho.get_stores(tenant_id)
    assert stores, "expected stores for the tenant"
    # every returned store belongs to the requested tenant
    for s in stores:
        assert not s.get("tenant_id") or s["tenant_id"] == tenant_id
    assert "store_id" in stores[0] and "store_code" in stores[0]

    cfg = ho.get_agent_config(stores[0]["store_id"])
    assert cfg.get("store_id")
    assert "server_name" in cfg


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
