"""Nexora Setup install steps (no UI, so they can be tested and re-run).

  1. Device Controller: download from HO -> verify sha256 -> `install-service`
     (creates its key pair + SYSTEM service) -> register its public key with
     the chosen store -> drop inbox\\enrollment.json, which the running
     controller picks up within ~30 s.
  2. Store Agent identity (when ticked): seal a key under <dir>\\config,
     register it with the store, write a device-mode agent_config.json.
  3. Ask HO to install the ticked apps: HO queues signed `install` commands
     and the controller downloads, verifies and installs each one.
"""
from __future__ import annotations

import json
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import requests

from store_agent_setup.device_controller import (CONFIG_FILE, FINGERPRINT_FILE, INBOX_DIR,
                                                 PUBLIC_KEY_FILE)
from store_agent_setup.setup_kit.client import HoError

CREATE_NO_WINDOW = 0x08000000
INSTALLED_BY_CONTROLLER = ("store_agent", "stock_client")
TERMINAL = {"SUCCEEDED", "FAILED", "EXPIRED", "CANCELLED"}
ENROLL_WAIT_SECONDS = 150
INSTALL_WAIT_SECONDS = 1200


class SetupError(Exception):
    pass


def _enrolled_device_id():
    try:
        return str((json.loads(CONFIG_FILE.read_text(encoding="utf-8")) or {}).get("device_id") or "")
    except (OSError, ValueError):
        return ""


class SetupRun:
    def __init__(self, client, store_id, log, run=subprocess.run, sleep=time.sleep, work_dir=None):
        self.client = client
        self.store_id = store_id
        self.log = log
        self.run = run
        self.sleep = sleep
        self.work_dir = Path(work_dir or Path(tempfile.gettempdir()) / "NexoraSetup")

    def _wait(self, check, seconds, interval=3):
        deadline = time.time() + seconds
        while True:
            if check():
                return True
            if time.time() >= deadline:
                return False
            self.sleep(interval)

    # ---- 1. Device Controller ---------------------------------------------

    def install_controller(self, pkg) -> str:
        if not pkg or not pkg.get("version"):
            raise SetupError("HO has no Device Controller package published")
        exe = self.work_dir / (pkg.get("file_name") or "NexoraDeviceController.exe")
        self.log(f"Downloading Device Controller {pkg['version']} from HO...")
        self.client.download_controller(pkg["version"], exe, pkg.get("sha256"))
        self.log("Installing the Device Controller service...")
        r = self.run([str(exe), "install-service", "--ho", self.client.base],
                     capture_output=True, text=True, timeout=300, creationflags=CREATE_NO_WINDOW)
        output = ((r.stdout or "") + (r.stderr or "")).strip()
        if r.returncode != 0:
            raise SetupError(f"Device Controller setup failed (exit {r.returncode}): {output[-400:]}")
        return self.enroll_controller(pkg["version"])

    def enroll_controller(self, version) -> str:
        """Register the installed controller's key for the store and hand it its
        device id through the inbox."""
        if not self._wait(lambda: PUBLIC_KEY_FILE.is_file() and FINGERPRINT_FILE.is_file(), 30):
            raise SetupError("The Device Controller did not create its device key")
        data = self.client.register_device({
            "device_fingerprint": FINGERPRINT_FILE.read_text(encoding="utf-8").strip(),
            "public_key": PUBLIC_KEY_FILE.read_text(encoding="utf-8"),
            "key_algo": "ED25519",
            "machine_name": socket.gethostname(),
            "app_type": "device_controller",
            "app_version": version,
            "store_id": self.store_id,
        })
        device_id = str(data["device_id"])
        self.log(f"Device Controller registered with HO as {device_id}")
        if _enrolled_device_id().lower() != device_id.lower():
            INBOX_DIR.mkdir(parents=True, exist_ok=True)
            (INBOX_DIR / "enrollment.json").write_text(
                json.dumps({"device_id": device_id, "ho_urls": [self.client.base]}), encoding="utf-8")
            self.log("Waiting for the Device Controller to connect to HO...")
            if self._wait(lambda: _enrolled_device_id().lower() == device_id.lower(), ENROLL_WAIT_SECONDS):
                self.log("Device Controller connected.")
            else:
                self.log("Device Controller has not confirmed yet; it keeps retrying, and HO's "
                         "install commands wait for it.")
        return device_id

    # ---- 2. Store Agent identity ------------------------------------------

    def prepare_agent(self, pkg, install_dir, fallback_urls=()):
        from store_agent.device_client import DeviceIdentity, machine_fingerprint
        from store_agent_setup.agent_config import build_device_config, write_config

        folder = Path(install_dir)
        self.log(f"Registering the Store Agent for {folder}...")
        try:
            data = DeviceIdentity(folder / "config").register(
                self.client.base, self.client.token, machine_fingerprint(),
                machine_name=socket.gethostname(), app_type="store_agent",
                app_version=(pkg or {}).get("version"), store_id=self.store_id)
        except requests.RequestException as ex:
            resp = getattr(ex, "response", None)
            raise SetupError(f"Store Agent registration failed: "
                             f"{resp.text[:200] if resp is not None else ex}") from ex
        write_config(folder, build_device_config(self.client.base, folder,
                                                 fallback_urls=list(fallback_urls)))
        self.log(f"Store Agent registered as {data.get('device_id')}")
        return data

    # ---- 3. HO installs the apps through the controller -------------------

    def queue(self, controller_device_id, components, install_dirs) -> list:
        cmds = self.client.install(controller_device_id, components, install_dirs)
        for c in cmds:
            self.log(f"HO queued: install {c['app_key']} {c['version']}")
        return cmds

    def wait(self, cmds, seconds=INSTALL_WAIT_SECONDS) -> dict:
        ids = [c["command_id"] for c in cmds]
        last = {}
        deadline = time.time() + seconds
        while ids:
            try:
                rows = self.client.commands(ids)
            except HoError as ex:
                self.log(f"  (status check failed, retrying: {ex})")
                rows = []
            for row in rows:
                status = row.get("status")
                if last.get(row["command_id"]) != status:
                    last[row["command_id"]] = status
                    note = f" - {row['result_text']}" if row.get("result_text") and status in TERMINAL else ""
                    self.log(f"  {row['app_key']}: {status}{note}")
            if all(last.get(i) in TERMINAL for i in ids) or time.time() >= deadline:
                break
            self.sleep(5)
        return last

    # ---- everything --------------------------------------------------------

    def run_all(self, plan, components, install_dirs, spec, fallback_urls=()) -> dict:
        by_key = {c["app_key"]: c for c in (plan or {}).get("components") or []}
        device_id = self.install_controller(by_key.get("controller"))
        wanted = [k for k in components if k in INSTALLED_BY_CONTROLLER]
        if "store_agent" in wanted:
            if (spec.get("services") or {}).get("store_agent") not in (None, "not-installed", "unknown"):
                self.log("Store Agent is already installed here: the controller updates it in place.")
            else:
                self.prepare_agent(by_key.get("store_agent"), install_dirs["store_agent"], fallback_urls)
        cmds = self.queue(device_id, wanted, install_dirs) if wanted else []
        statuses = self.wait(cmds) if cmds else {}
        failed = [c["app_key"] for c in cmds if statuses.get(c["command_id"]) != "SUCCEEDED"]
        return {"controller_device_id": device_id, "commands": cmds, "statuses": statuses,
                "failed": failed}
