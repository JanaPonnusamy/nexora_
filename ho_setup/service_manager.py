"""Windows-service lifecycle for the UniNex HO backend.

Adapted directly from the proven Store Agent ServiceManager (store_agent_setup):
same dual-mode design and the same hardening that fixed the "service cannot be
started because it is disabled" (error 1058) rollout problem.

Two registration paths:
* Frozen install (HO_Backend.exe present) -> drive the Service Control Manager
  with sc.exe. The exe self-hosts the pywin32 service when launched with no
  arguments. sc.exe lets us force start= auto deterministically.
* Source/dev (no exe) -> drive the pywin32 module (python -m ho_setup.ho_service).

Supports install / uninstall / start / stop / restart, automatic startup and
restart-on-failure.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

from . import (
    BACKEND_EXE_NAME,
    SERVICE_DESCRIPTION,
    SERVICE_DISPLAY_NAME,
    SERVICE_NAME,
)

try:
    import win32service
    import win32serviceutil

    _HAVE_PYWIN32 = True
except ImportError:  # pragma: no cover
    _HAVE_PYWIN32 = False


class ServiceError(Exception):
    pass


class ServiceManager:
    def __init__(self, install_path, log=None):
        self.root = Path(install_path)
        self._log = log or (lambda msg: None)

    def log(self, msg):
        self._log(msg)

    # ---- mode detection ---------------------------------------------------

    def _exe(self):
        exe = self.root / BACKEND_EXE_NAME
        return exe if exe.is_file() else None

    def _agent_command(self):
        """Source/dev controller: the pywin32 service module via python."""
        return [sys.executable, "-m", "ho_setup.ho_service"]

    # ---- subprocess helpers ----------------------------------------------

    def _env(self):
        env = dict(os.environ)
        env["NEXORA_HO_INSTALL"] = str(self.root)
        runtime = Path(__file__).resolve().parent.parent
        env["PYTHONPATH"] = os.pathsep.join(
            [str(runtime)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
        )
        return env

    def _exec(self, cmd, check=True):
        self.log("run: " + subprocess.list2cmdline(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True, env=self._env())
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if out:
            self.log(out)
        if err:
            self.log(err)
        if check and proc.returncode != 0:
            raise ServiceError(
                f"command failed ({proc.returncode}): "
                f"{subprocess.list2cmdline(cmd)}\n{err or out}"
            )
        return proc

    def _sc(self, *args, check=True):
        return self._exec(["sc", *args], check=check)

    def _run(self, *args, check=True):
        return self._exec(self._agent_command() + list(args), check=check)

    # ---- install ----------------------------------------------------------

    def install(self):
        exe = self._exe()
        if exe is None:
            self._install_source()
        else:
            self._install_sc(exe)

    def _install_source(self):
        if self.is_installed():
            self.log(f"service {SERVICE_NAME} present; reconfiguring (source mode)")
            self._run("update", "--startup", "auto", check=False)
        else:
            self._run("--startup", "auto", "install")
        self.log(f"service {SERVICE_NAME} installed (startup=auto, source mode)")

    def _install_sc(self, exe):
        # Clean slate: a stale/disabled service is exactly what breaks start.
        if self.is_installed():
            self.log(f"service {SERVICE_NAME} present; recreating for a clean state")
            self._stop_quiet()
            self._sc("delete", SERVICE_NAME, check=False)
            self._wait_absent(timeout=15)

        bin_path = f'"{exe}"'  # SCM stores the command line; quote for spaces.
        self._sc(
            "create", SERVICE_NAME,
            "binPath=", bin_path,
            "start=", "auto",
            "DisplayName=", SERVICE_DISPLAY_NAME,
            "obj=", "LocalSystem",
        )
        # Reassert start type so it can NEVER be left Disabled (error 1058).
        self._sc("config", SERVICE_NAME, "start=", "auto", check=False)
        self._sc("description", SERVICE_NAME, SERVICE_DESCRIPTION, check=False)
        # Auto-restart on crash: 3 attempts, 60s apart, daily reset.
        self._sc("failure", SERVICE_NAME, "reset=", "86400",
                 "actions=", "restart/60000/restart/60000/restart/60000",
                 check=False)
        self.log(f"service {SERVICE_NAME} created (startup=auto)")

    # ---- start / stop / remove -------------------------------------------

    def start(self):
        if self._exe() is not None:
            self._sc("config", SERVICE_NAME, "start=", "auto", check=False)
            self._sc("start", SERVICE_NAME, check=False)
        else:
            self._run("start", check=False)
        if not self.wait_for_state("running", timeout=60):
            raise ServiceError(
                f"service {SERVICE_NAME} did not reach RUNNING (state="
                f"{self.status()}). Check {self.root / 'logs'} and the Windows "
                "Event Log (Application) for UniNexHO."
            )
        self.log(f"service {SERVICE_NAME} running")

    def stop(self):
        self._stop_quiet()
        self.wait_for_state("stopped", timeout=30)
        self.log(f"service {SERVICE_NAME} stopped")

    def _stop_quiet(self):
        if self._exe() is not None:
            self._sc("stop", SERVICE_NAME, check=False)
        else:
            self._run("stop", check=False)

    def remove(self):
        self._stop_quiet()
        self.wait_for_state("stopped", timeout=30)
        if self._exe() is not None:
            self._sc("delete", SERVICE_NAME, check=False)
        else:
            self._run("remove", check=False)
        self.log(f"service {SERVICE_NAME} removed")

    def restart(self):
        self.stop()
        self.start()

    # ---- state ------------------------------------------------------------

    def is_installed(self):
        if _HAVE_PYWIN32:
            try:
                win32serviceutil.QueryServiceStatus(SERVICE_NAME)
                return True
            except Exception:
                return False
        return self._sc_query() is not None

    def status(self):
        """'running' | 'stopped' | 'pending' | 'not-installed' | 'unknown'."""
        if _HAVE_PYWIN32:
            try:
                state = win32serviceutil.QueryServiceStatus(SERVICE_NAME)[1]
            except Exception:
                return "not-installed"
            return {
                win32service.SERVICE_RUNNING: "running",
                win32service.SERVICE_STOPPED: "stopped",
                win32service.SERVICE_START_PENDING: "pending",
                win32service.SERVICE_STOP_PENDING: "pending",
            }.get(state, "unknown")
        return self._sc_query() or "not-installed"

    def wait_for_state(self, target, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.status() == target:
                return True
            time.sleep(1)
        return self.status() == target

    def _wait_absent(self, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.is_installed():
                return True
            time.sleep(1)
        return not self.is_installed()

    def _sc_query(self):
        proc = subprocess.run(
            ["sc", "query", SERVICE_NAME], capture_output=True, text=True
        )
        if proc.returncode != 0:
            return None
        out = proc.stdout.upper()
        if "RUNNING" in out:
            return "running"
        if "STOPPED" in out:
            return "stopped"
        if "PENDING" in out:
            return "pending"
        return "unknown"
