"""Unattended Nexora Setup for a PC prepared while its HO is offline.

  NexoraSetup.exe --prepare --ho URL --user NAME --store-id ID --agent-dir DIR
                  --agent-exe PATH --agent-version V
      Offline. Places the Store Agent exe, seals its device key, writes its
      device-mode agent_config.json, seals the store login's password (DPAPI,
      folder limited to SYSTEM + Administrators) and schedules --finish as
      SYSTEM every 5 minutes. The password comes in through the
      NEXORA_SETUP_LOGIN_PASSWORD environment variable, never the command line.
      The Device Controller service is installed beforehand by its own
      `install-service --ho URL`.

  NexoraSetup.exe --finish
      Exits quietly until HO answers. Then signs in once, registers the Device
      Controller and the Store Agent for the store, enrolls the controller,
      creates + starts the agent service, signs out, and deletes the sealed
      password and the task.
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
from pathlib import Path

from store_agent_setup.setup_kit import spec as spec_mod
from store_agent_setup.setup_kit.client import HoError, SetupClient, normalize_url
from store_agent_setup.setup_kit.engine import CREATE_NO_WINDOW, SetupError, SetupRun

SETUP_DIR = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Nexora" / "Setup"
PENDING_FILE = SETUP_DIR / "pending.json"
SECRET_FILE = SETUP_DIR / "pending.secret"
LOG_FILE = SETUP_DIR / "finish.log"
TASK_NAME = "NexoraSetupFinish"
AGENT_SERVICE = "NexoraStoreAgent"
AGENT_SUBDIRS = ("cache", "logs", "updates", "backups", "config")
PASSWORD_ENV = "NEXORA_SETUP_LOGIN_PASSWORD"


def log(msg):
    SETUP_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          creationflags=CREATE_NO_WINDOW)


def _seal(data: bytes) -> bytes:
    from store_agent.device_client import dpapi_seal

    return dpapi_seal(data)


def _unseal(blob: bytes) -> bytes:
    from store_agent.device_client import dpapi_unseal

    return dpapi_unseal(blob)


# ---- tonight ---------------------------------------------------------------

def prepare(ho, user, store_id, agent_dir, agent_exe, agent_version, password, kit_exe):
    from store_agent.device_client import DeviceIdentity
    from store_agent_setup.agent_config import build_device_config, write_config

    if not password:
        raise SetupError(f"{PASSWORD_ENV} is not set")
    if not kit_exe:
        raise SetupError("--prepare must run from NexoraSetup.exe (the task re-runs that exe)")
    ho = normalize_url(ho)
    folder = Path(agent_dir)
    for sub in AGENT_SUBDIRS:
        (folder / sub).mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(agent_exe), str(folder / "NexoraStoreAgent.exe"))
    (folder / "agent_version_installed.txt").write_text(agent_version, encoding="utf-8")
    DeviceIdentity(folder / "config").ensure_keypair()
    write_config(folder, build_device_config(ho, folder))
    log(f"agent {agent_version} placed in {folder} with its sealed key + device config ({ho})")

    SETUP_DIR.mkdir(parents=True, exist_ok=True)
    run(["icacls", str(SETUP_DIR), "/inheritance:r", "/grant:r",
         "*S-1-5-18:(OI)(CI)F", "/grant:r", "*S-1-5-32-544:(OI)(CI)F"])
    kit = SETUP_DIR / "NexoraSetup.exe"
    if Path(kit_exe).resolve() != kit.resolve():
        shutil.copy2(str(kit_exe), str(kit))
    SECRET_FILE.write_bytes(_seal(password.encode("utf-8")))
    PENDING_FILE.write_text(json.dumps({
        "ho": ho, "user": user, "store_id": store_id, "agent_dir": str(folder),
        "agent_version": agent_version, "prepared_at": datetime.datetime.now().isoformat(),
    }, indent=2), encoding="utf-8")
    r = run(["schtasks", "/Create", "/TN", TASK_NAME, "/TR", f'"{kit}" --finish',
             "/SC", "MINUTE", "/MO", "5", "/RU", "SYSTEM", "/RL", "HIGHEST", "/F"])
    if r.returncode != 0:
        raise SetupError(f"could not schedule {TASK_NAME}: {(r.stdout or '') + (r.stderr or '')}")
    log(f"scheduled {TASK_NAME} (SYSTEM, every 5 min): finishes as soon as {ho} answers")


# ---- morning -----------------------------------------------------------------

def _start_agent(folder):
    exe = Path(folder) / "NexoraStoreAgent.exe"
    if "1060" in (run(["sc", "query", AGENT_SERVICE]).stdout or ""):
        run(["sc", "create", AGENT_SERVICE, "binPath=", f'"{exe}"', "start=", "auto",
             "DisplayName=", "Nexora Store Agent", "obj=", "LocalSystem"])
        run(["sc", "description", AGENT_SERVICE,
             "Nexora Store Agent - syncs this PC's store databases to HO"])
        run(["sc", "failure", AGENT_SERVICE, "reset=", "86400",
             "actions=", "restart/60000/restart/60000/restart/60000"])
    run(["sc", "start", AGENT_SERVICE])
    state = run(["sc", "query", AGENT_SERVICE]).stdout or ""
    log("Store Agent service: " + next((ln.split()[-1] for ln in state.splitlines() if "STATE" in ln),
                                       "unknown"))


def _cleanup():
    for path in (SECRET_FILE, PENDING_FILE):
        try:
            path.unlink()
        except OSError:
            pass
    run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])


def finish(sleep=None) -> int:
    if not PENDING_FILE.is_file():
        _cleanup()
        return 0
    pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    client = SetupClient(pending["ho"])
    try:
        client.probe()
    except HoError as ex:
        log(f"waiting for HO: {ex}")
        return 0
    try:
        client.login(pending["user"], _unseal(SECRET_FILE.read_bytes()).decode("utf-8"))
    except HoError as ex:
        log(f"HO is up but sign-in is not possible yet: {ex}")
        return 0
    try:
        kwargs = {"sleep": sleep} if sleep else {}
        setup = SetupRun(client, pending.get("store_id"), log, **kwargs)
        setup.enroll_controller(spec_mod.controller_state().get("version") or "unknown")
        setup.prepare_agent({"version": pending.get("agent_version")}, pending["agent_dir"])
        _start_agent(pending["agent_dir"])
    except (HoError, SetupError) as ex:
        log(f"finish failed, retrying in 5 minutes: {ex}")
        return 1
    finally:
        client.logout()
    _cleanup()
    log("finished: Device Controller and Store Agent are registered with HO; setup task removed")
    return 0
