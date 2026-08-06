"""Nexora Store Agent Watchdog: Windows service wrapper (pywin32).

A running NexoraStoreAgent.exe cannot safely stop, replace, or fully restart
itself, and once fully stopped there is nothing left on the store PC to
receive a "start" command from HO. This is a second, always-on, separately
installed service whose only job is to poll HO for the desired run-state and
version of THIS store's agent (see backend/modules/agent_ops) and reconcile
reality to match it every cycle - via the Windows Service Control Manager, the
same way a human would with ``sc stop``/``sc start``, plus a verified
download+swap when a new version is published.

Built into NexoraStoreAgentWatchdog.exe (PyInstaller onefile), same packaging
pattern as agent_service.py. Also runnable from source for development:
    python -m store_agent_setup.watchdog_service install --startup auto
    python -m store_agent_setup.watchdog_service start|stop|remove
"""
import hashlib
import os
import shutil
import sys
import time
import threading
import traceback
from datetime import datetime
from pathlib import Path

import servicemanager
import win32event
import win32service
import win32serviceutil

from . import WATCHDOG_DISPLAY_NAME, WATCHDOG_SERVICE_NAME, WATCHDOG_VERSION
from .service_manager import ServiceManager

POLL_SECONDS = 60
VERSION_MARKER_NAME = "agent_version_installed.txt"


def _install_path():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    env = os.environ.get("NEXORA_INSTALL_PATH")
    return Path(env) if env else Path.cwd()


def _redirect_logs(root):
    """Send stdout/stderr to <install>/logs/watchdog.log - a Windows service
    has no console, so without this every reconcile decision (and any crash)
    would be invisible, same failure mode the main agent had before it grew
    its own log redirection."""
    try:
        logs = root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        stream = open(logs / "watchdog.log", "a", buffering=1, encoding="utf-8")
        stream.write(f"\n==== watchdog start {datetime.now().isoformat()} ====\n")
        sys.stdout = stream
        sys.stderr = stream
    except OSError:
        pass


def _prepare_environment():
    """Point store_agent.config at the same agent_config.json the main agent
    uses, so the watchdog resolves the identical store_id / HO routes."""
    root = _install_path()
    os.environ["NEXORA_INSTALL_PATH"] = str(root)
    cfg = root / "agent_config.json"
    if cfg.is_file():
        os.environ["NEXORA_AGENT_CONFIG"] = str(cfg)
    try:
        os.chdir(str(root))
    except OSError:
        pass
    _redirect_logs(root)
    return root


def _read_installed_version(root):
    marker = root / VERSION_MARKER_NAME
    try:
        return marker.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _write_installed_version(root, version):
    (root / VERSION_MARKER_NAME).write_text(version, encoding="utf-8")


def _sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _replace_file_with_retries(staged, target, backup_path=None, timeout=30):
    """Windows services can report STOPPED slightly before the exe handle is
    fully released. Replace the target with bounded retries so one transient
    file lock does not trap the watchdog in a permanent update loop."""
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            if target.exists():
                try:
                    target.unlink()
                except FileNotFoundError:
                    pass
            shutil.move(str(staged), str(target))
            return
        except FileNotFoundError:
            shutil.move(str(staged), str(target))
            return
        except PermissionError as ex:
            last_error = ex
            time.sleep(1)
        except OSError as ex:
            last_error = ex
            if getattr(ex, "winerror", None) == 183 and target.exists():
                try:
                    target.unlink()
                except OSError:
                    time.sleep(1)
                else:
                    continue
            else:
                time.sleep(1)

    if backup_path and backup_path.is_file() and not target.exists():
        shutil.copy2(backup_path, target)
    if last_error:
        raise last_error
    raise TimeoutError(f"timed out replacing {target}")


class WatchdogCycle:
    """One reconciliation pass: ask HO what should be true, make it true."""

    def __init__(self, root, log):
        self.root = root
        self.log = log
        self.svc = ServiceManager(str(root), log=log)

    def run_once(self):
        from store_agent import config as agent_config
        import requests

        store_id = agent_config.STORE_ID
        ho_url = agent_config.active_ho_url()
        try:
            resp = requests.get(
                f"{ho_url}/agent/watchdog/state/{store_id}", timeout=15
            )
            resp.raise_for_status()
            desired = resp.json()
        except Exception as ex:
            agent_config.mark_ho_failure()
            self.log(f"[WATCHDOG] could not reach HO: {ex}")
            return

        desired_state = (desired.get("desired_state") or "RUNNING").upper()
        last_action = "no-op"

        try:
            last_action = self._reconcile_version(desired.get("version"))
        except Exception:
            self.log("[WATCHDOG] update failed:\n" + traceback.format_exc())
            last_action = "update-failed"

        try:
            state_action = self._reconcile_state(desired_state)
            if state_action:
                last_action = f"{last_action}; {state_action}"
        except Exception:
            self.log("[WATCHDOG] state reconcile failed:\n" + traceback.format_exc())
            last_action = f"{last_action}; state-reconcile-failed"

        self._report(agent_config, last_action)

    def _reconcile_version(self, version_info):
        if not version_info:
            return "no-release-published"

        version = version_info["version"]
        previous_version = _read_installed_version(self.root)
        if previous_version == version:
            return "up-to-date:" + version

        from store_agent import config as agent_config
        import requests

        updates_dir = self.root / "updates"
        updates_dir.mkdir(parents=True, exist_ok=True)
        staged = updates_dir / f"NexoraStoreAgent-{version}.exe"

        self.log(f"[WATCHDOG] downloading agent version {version}")
        ho_url = agent_config.active_ho_url()
        with requests.get(
            ho_url + version_info["download_url"], stream=True, timeout=300
        ) as r:
            r.raise_for_status()
            with open(staged, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)

        actual = _sha256_of(staged)
        expected = version_info["sha256"]
        if actual.lower() != expected.lower():
            staged.unlink(missing_ok=True)
            raise RuntimeError(
                f"sha256 mismatch for {version}: expected {expected}, got {actual}"
            )

        was_running = self.svc.is_installed() and self.svc.status() == "running"
        if was_running:
            self.log("[WATCHDOG] stopping agent to apply update")
            self.svc.stop()

        target = self.root / "NexoraStoreAgent.exe"
        backups = self.root / "backups"
        backups.mkdir(parents=True, exist_ok=True)
        backup_path = None
        if target.is_file():
            suffix = previous_version or "unknown"
            backup_path = backups / f"NexoraStoreAgent-{suffix}.exe"
            shutil.copy2(target, backup_path)
        try:
            _replace_file_with_retries(staged, target, backup_path=backup_path)
            _write_installed_version(self.root, version)
            self.log(f"[WATCHDOG] installed agent version {version}")
            if was_running:
                self.svc.start()
        except Exception:
            if backup_path and backup_path.is_file():
                shutil.copy2(backup_path, target)
            if previous_version:
                _write_installed_version(self.root, previous_version)
            raise

        return f"updated-to:{version}"

    def _reconcile_state(self, desired_state):
        if not self.svc.is_installed():
            return None
        current = self.svc.status()
        if desired_state == "STOPPED" and current == "running":
            self.log("[WATCHDOG] stopping NexoraStoreAgent (desired=STOPPED)")
            self.svc.stop()
            return "stopped-agent"
        if desired_state == "RUNNING" and current == "stopped":
            self.log("[WATCHDOG] starting NexoraStoreAgent (desired=RUNNING)")
            self.svc.start()
            return "started-agent"
        return None

    def _report(self, agent_config, last_action):
        import requests
        try:
            requests.post(
                agent_config.active_ho_url() + "/agent/watchdog/heartbeat",
                json={
                    "store_id": agent_config.STORE_ID,
                    "watchdog_version": WATCHDOG_VERSION,
                    "installed_agent_version": _read_installed_version(self.root),
                    "service_state": (
                        self.svc.status() if self.svc.is_installed() else "not-installed"
                    ),
                    "last_action": last_action,
                },
                timeout=15,
            )
        except Exception:
            pass  # heartbeat is best-effort, must never break the reconcile loop


def _watchdog_loop(stop_event, root):
    log = lambda msg: print(msg, flush=True)  # noqa: E731
    cycle = WatchdogCycle(root, log)
    while True:
        try:
            cycle.run_once()
        except Exception:
            print("[WATCHDOG] cycle crashed:\n" + traceback.format_exc(), flush=True)
        if win32event.WaitForSingleObject(
            stop_event, POLL_SECONDS * 1000
        ) == win32event.WAIT_OBJECT_0:
            return


class NexoraStoreAgentWatchdogService(win32serviceutil.ServiceFramework):
    _svc_name_ = WATCHDOG_SERVICE_NAME
    _svc_display_name_ = WATCHDOG_DISPLAY_NAME
    _svc_description_ = (
        "Keeps NexoraStoreAgent on the version and run-state HO wants, "
        "so it can be updated/started/stopped remotely."
    )

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.worker = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        root = _prepare_environment()
        self.worker = threading.Thread(
            target=_watchdog_loop, args=(self.stop_event, root), daemon=True
        )
        self.worker.start()
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) == 1:
        # Launched by the SCM (frozen exe with no args).
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(NexoraStoreAgentWatchdogService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(NexoraStoreAgentWatchdogService, argv=argv)


if __name__ == "__main__":
    main()
