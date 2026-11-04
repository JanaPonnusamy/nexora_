"""Nexora Setup kit (client side): one sign-in, verified controller download,
controller enrollment for the chosen store, Store Agent identity + device-mode
config, and the HO install hand-off. No GUI, no real services."""
import hashlib
import json
from types import SimpleNamespace

import pytest
import requests

from store_agent_setup.setup_kit import engine, spec
from store_agent_setup.setup_kit.client import HoError, SetupClient, normalize_url

STORE = "96895c62-6034-43e0-a94c-ad08343161a5"


class Resp:
    def __init__(self, status=200, body=None, chunks=(), headers=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self._chunks = chunks
        self.headers = headers or {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def iter_content(self, chunk_size):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_normalize_url():
    assert normalize_url(" http://122.252.246.181:8444/   (SMS HO - internet)") == "http://122.252.246.181:8444"
    assert normalize_url("192.168.10.32:8000") == "http://192.168.10.32:8000"
    assert normalize_url("") == ""


def test_login_once_and_friendly_409(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "post", lambda url, **k: calls.append(url) or Resp(
        body={"token": "T", "user": {"username": "devadmin"}}))
    c = SetupClient("http://ho:8000")
    assert c.login("devadmin", "x")["username"] == "devadmin"
    c.login("devadmin", "x")                    # second click: no second login
    assert calls == ["http://ho:8000/api/auth/login"]

    monkeypatch.setattr(requests, "post", lambda url, **k: Resp(409, {"detail": "busy"}))
    with pytest.raises(HoError, match="already signed in"):
        SetupClient("http://ho:8000").login("smg", "x")


def test_download_controller_checks_sha(monkeypatch, tmp_path):
    body = b"controller-bytes"
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(chunks=[body]))
    c = SetupClient("http://ho:8000")
    c.token = "T"
    dest = tmp_path / "NexoraDeviceController.exe"
    with pytest.raises(HoError, match="checksum"):
        c.download_controller("1.0.6", dest, "0" * 64)
    assert not dest.exists() and not (tmp_path / "NexoraDeviceController.exe.part").exists()
    c.download_controller("1.0.6", dest, hashlib.sha256(body).hexdigest())
    assert dest.read_bytes() == body


@pytest.fixture
def ctl_dir(monkeypatch, tmp_path):
    state = tmp_path / "DeviceController"
    paths = {"PUBLIC_KEY_FILE": state / "device_public_key.pem",
             "FINGERPRINT_FILE": state / "device_fingerprint.txt",
             "INBOX_DIR": state / "inbox",
             "CONFIG_FILE": state / "private" / "controller.json"}
    for name, path in paths.items():
        monkeypatch.setattr(engine, name, path)
    return SimpleNamespace(**paths)


class FakeClient:
    base = "http://122.252.246.181:8444"
    token = "T"

    def __init__(self):
        self.registered = []
        self.installs = []
        self.polls = 0

    def download_controller(self, version, dest, sha256=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"exe")

    def register_device(self, payload):
        self.registered.append(payload)
        return {"device_id": "F5B70858-AAAA-BBBB-CCCC-000000000001"}

    def install(self, device_id, components, dirs):
        self.installs.append((device_id, list(components), dict(dirs)))
        return [{"app_key": k, "version": "2026.11.04.1", "command_id": "C-" + k} for k in components]

    def commands(self, ids):
        self.polls += 1
        status = "RUNNING" if self.polls == 1 else "SUCCEEDED"
        return [{"command_id": i, "app_key": i[2:], "status": status, "result_text": "ok"} for i in ids]


def _fake_install_service(ctl_dir):
    def run(cmd, **kwargs):
        assert cmd[1:] == ["install-service", "--ho", FakeClient.base]
        ctl_dir.PUBLIC_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        ctl_dir.PUBLIC_KEY_FILE.write_text("PUBKEY", encoding="utf-8")
        ctl_dir.FINGERPRINT_FILE.write_text("dc:guid\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="installed", stderr="")
    return run


def _controller_picks_up(ctl_dir):
    """Fake sleep: the running controller consumes the inbox file."""
    def sleep(_seconds):
        inbox = ctl_dir.INBOX_DIR / "enrollment.json"
        if inbox.is_file():
            data = json.loads(inbox.read_text(encoding="utf-8"))
            inbox.unlink()
            ctl_dir.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            ctl_dir.CONFIG_FILE.write_text(json.dumps({"device_id": data["device_id"]}), encoding="utf-8")
    return sleep


def test_install_controller_registers_store_and_enrolls(ctl_dir, tmp_path):
    fake = FakeClient()
    dropped = []
    real_sleep = _controller_picks_up(ctl_dir)

    def sleep(s):
        inbox = ctl_dir.INBOX_DIR / "enrollment.json"
        if inbox.is_file():
            dropped.append(json.loads(inbox.read_text(encoding="utf-8")))
        real_sleep(s)

    run = engine.SetupRun(fake, STORE, lambda m: None, run=_fake_install_service(ctl_dir),
                          sleep=sleep, work_dir=tmp_path / "work")
    assert run.install_controller({"version": "1.0.6", "file_name": "NexoraDeviceController.exe",
                                   "sha256": "x"}) == "F5B70858-AAAA-BBBB-CCCC-000000000001"
    reg = fake.registered[0]
    assert reg["app_type"] == "device_controller" and reg["store_id"] == STORE
    assert reg["public_key"] == "PUBKEY" and reg["device_fingerprint"] == "dc:guid"
    assert dropped == [{"device_id": "F5B70858-AAAA-BBBB-CCCC-000000000001",
                        "ho_urls": [FakeClient.base]}]


def test_already_enrolled_controller_is_not_re_enrolled(ctl_dir, tmp_path):
    ctl_dir.CONFIG_FILE.parent.mkdir(parents=True)
    ctl_dir.CONFIG_FILE.write_text(json.dumps({"device_id": "f5b70858-aaaa-bbbb-cccc-000000000001"}),
                                   encoding="utf-8")
    run = engine.SetupRun(FakeClient(), STORE, lambda m: None, run=_fake_install_service(ctl_dir),
                          sleep=lambda s: None, work_dir=tmp_path / "work")
    run.install_controller({"version": "1.0.6"})
    assert not (ctl_dir.INBOX_DIR / "enrollment.json").exists()


def test_failed_controller_setup_stops(ctl_dir, tmp_path):
    run = engine.SetupRun(FakeClient(), STORE, lambda m: None,
                          run=lambda cmd, **k: SimpleNamespace(returncode=1, stdout="", stderr="Access is denied"),
                          sleep=lambda s: None, work_dir=tmp_path / "work")
    with pytest.raises(engine.SetupError, match="Access is denied"):
        run.install_controller({"version": "1.0.6"})


def test_prepare_agent_seals_identity_and_writes_device_config(monkeypatch, tmp_path):
    import store_agent.device_client as dc

    sent = []
    monkeypatch.setattr(dc.requests, "post", lambda url, **k: sent.append((url, k["json"])) or Resp(
        body={"device_id": "1DA4A39E-0000-0000-0000-000000000002", "assigned_store_ids": [STORE]}))
    monkeypatch.setattr(dc, "dpapi_seal", lambda data: b"sealed:" + data)
    agent = tmp_path / "NexoraStoreAgent"
    engine.SetupRun(FakeClient(), STORE, lambda m: None).prepare_agent(
        {"version": "2026.11.04.1"}, agent)
    url, body = sent[0]
    assert url == FakeClient.base + "/api/auth/device/register"
    assert body["app_type"] == "store_agent" and body["store_id"] == STORE
    assert (agent / "config" / "device_key.bin").read_bytes().startswith(b"sealed:")
    assert (agent / "config" / "device_id.txt").read_text(encoding="utf-8") == "1DA4A39E-0000-0000-0000-000000000002"
    cfg = json.loads((agent / "agent_config.json").read_text(encoding="utf-8"))
    assert cfg["mode"] == "device" and cfg["ho_url"] == FakeClient.base
    assert cfg["install_path"] == str(agent)


def test_run_all_hands_installs_to_ho(ctl_dir, tmp_path, monkeypatch):
    fake = FakeClient()
    run = engine.SetupRun(fake, STORE, lambda m: None, run=_fake_install_service(ctl_dir),
                          sleep=_controller_picks_up(ctl_dir), work_dir=tmp_path / "work")
    prepared = []
    monkeypatch.setattr(run, "prepare_agent", lambda pkg, d, urls=(): prepared.append(d))
    plan = {"components": [{"app_key": "controller", "version": "1.0.6"},
                           {"app_key": "store_agent", "version": "2026.11.04.1"}]}
    dirs = {"store_agent": r"D:\NexoraStoreAgent"}
    spec_ = {"services": {"store_agent": "not-installed"}}
    res = run.run_all(plan, ["controller", "store_agent"], dirs, spec_)
    assert prepared == [r"D:\NexoraStoreAgent"]
    assert fake.installs == [("F5B70858-AAAA-BBBB-CCCC-000000000001", ["store_agent"], dirs)]
    assert res["failed"] == [] and res["statuses"] == {"C-store_agent": "SUCCEEDED"}

    # An agent that is already installed keeps its identity (the controller updates it).
    prepared.clear()
    run.run_all(plan, ["controller", "store_agent"], dirs, {"services": {"store_agent": "running"}})
    assert prepared == []


def test_spec_helpers():
    assert spec.default_agent_dir([{"drive": "C:"}, {"drive": "D:"}]) == r"D:\NexoraStoreAgent"
    assert spec.default_agent_dir([{"drive": "C:"}]) == r"C:\NexoraStoreAgent"
    got = spec.detect()
    assert got["machine_name"] and got["ram_mb"] > 0 and got["drives"]
    assert set(got["services"]) == {"controller", "store_agent", "ho_backend"}
    assert any("PC name" in line for line in spec.summary_lines(got))


# ---- unattended (prepare tonight, finish when HO answers) ---------------------

@pytest.fixture
def unattended_env(monkeypatch, tmp_path, ctl_dir):
    from store_agent_setup.setup_kit import unattended
    import store_agent.device_client as dc

    setup = tmp_path / "Setup"
    monkeypatch.setattr(unattended, "SETUP_DIR", setup)
    monkeypatch.setattr(unattended, "PENDING_FILE", setup / "pending.json")
    monkeypatch.setattr(unattended, "SECRET_FILE", setup / "pending.secret")
    monkeypatch.setattr(unattended, "LOG_FILE", setup / "finish.log")
    monkeypatch.setattr(dc, "dpapi_seal", lambda data: b"sealed:" + data)
    monkeypatch.setattr(dc, "dpapi_unseal", lambda blob: blob[len(b"sealed:"):])
    cmds = []

    def run(cmd, timeout=120):
        cmds.append(cmd)
        out = "STATE : 4 RUNNING" if cmd[:2] == ["sc", "query"] and any(c[:2] == ["sc", "create"] for c in cmds) \
            else ("FAILED 1060" if cmd[:2] == ["sc", "query"] else "")
        return SimpleNamespace(returncode=0, stdout=out, stderr="")

    monkeypatch.setattr(unattended, "run", run)
    return SimpleNamespace(mod=unattended, setup=setup, cmds=cmds, tmp=tmp_path)


def _prepare(env):
    agent_exe = env.tmp / "src" / "NexoraStoreAgent.exe"
    agent_exe.parent.mkdir()
    agent_exe.write_bytes(b"agent")
    kit = env.tmp / "src" / "NexoraSetup.exe"
    kit.write_bytes(b"kit")
    agent_dir = env.tmp / "NexoraStoreAgent"
    env.mod.prepare("122.252.246.181:8444", "smssma", STORE, agent_dir, agent_exe,
                    "2026.11.04.1", "pw", kit)
    return agent_dir


def test_prepare_stages_agent_and_schedules_finish(unattended_env):
    env = unattended_env
    agent_dir = _prepare(env)
    assert (agent_dir / "NexoraStoreAgent.exe").read_bytes() == b"agent"
    assert (agent_dir / "config" / "device_key.bin").read_bytes().startswith(b"sealed:")
    assert json.loads((agent_dir / "agent_config.json").read_text())["ho_url"] == "http://122.252.246.181:8444"
    assert env.mod.SECRET_FILE.read_bytes() == b"sealed:pw"
    pending = json.loads(env.mod.PENDING_FILE.read_text())
    assert pending["user"] == "smssma" and pending["store_id"] == STORE
    task = [c for c in env.cmds if c[0] == "schtasks"][0]
    assert task[task.index("/RU") + 1] == "SYSTEM" and task[task.index("/TR") + 1].endswith("--finish")
    with pytest.raises(engine.SetupError):
        env.mod.prepare("h", "u", STORE, agent_dir, agent_dir / "x", "v", "", "kit")


def test_finish_waits_for_ho_then_registers_and_cleans_up(unattended_env, monkeypatch, ctl_dir):
    env = unattended_env
    agent_dir = _prepare(env)
    ctl_dir.PUBLIC_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    ctl_dir.PUBLIC_KEY_FILE.write_text("PUBKEY", encoding="utf-8")
    ctl_dir.FINGERPRINT_FILE.write_text("dc:guid", encoding="utf-8")

    def down(*a, **k):
        raise requests.ConnectionError("refused")
    monkeypatch.setattr(requests, "request", down)
    assert env.mod.finish() == 0 and env.mod.PENDING_FILE.is_file()        # HO still off

    registered = []
    login_status = {"code": 401}

    def http(method, url, **k):
        if url.endswith("/health"):
            return Resp(body={"status": "healthy"})
        if url.endswith("/api/auth/device/register"):
            registered.append(k["json"])
            return Resp(body={"device_id": "DEV-" + k["json"]["app_type"]})
        return Resp(body={"ok": True})
    monkeypatch.setattr(requests, "request", http)
    def post(url, **k):
        if url.endswith("/api/auth/login"):
            ok = login_status["code"] == 200
            return Resp(login_status["code"], {"token": "T", "user": {}} if ok else {"detail": "bad"})
        return http("POST", url, **k)
    monkeypatch.setattr(requests, "post", post)
    assert env.mod.finish() == 0 and env.mod.PENDING_FILE.is_file()        # login not created yet

    login_status["code"] = 200
    assert env.mod.finish(sleep=_controller_picks_up(ctl_dir)) == 0
    assert [r["app_type"] for r in registered] == ["device_controller", "store_agent"]
    assert all(r["store_id"] == STORE for r in registered)
    assert any(c[:2] == ["sc", "create"] for c in env.cmds) and ["sc", "start", "NexoraStoreAgent"] in env.cmds
    assert not env.mod.PENDING_FILE.exists() and not env.mod.SECRET_FILE.exists()
    assert ["schtasks", "/Delete", "/TN", "NexoraSetupFinish", "/F"] in env.cmds
