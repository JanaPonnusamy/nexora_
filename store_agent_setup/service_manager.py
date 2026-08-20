"""Windows service lifecycle for NexoraStoreAgent (STEP 8 / 9 / settings).

Two registration paths:

* Frozen install (NexoraStoreAgent.exe present) -> drive the Service Control
  Manager directly with sc.exe. The exe self-hosts the pywin32 service when the
  SCM launches it with no arguments. Using sc.exe lets us force start= auto
  deterministically, so the service can never be left Disabled (error 1058).
* Source/dev (no exe) -> drive the pywin32 module (python -m ... install/start).

The start type is set AND reasserted, because a half-created or pre-existing
service is what produced "The service cannot be started ... because it is
disabled" on the NMG/NMS rollout.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

from . import AGENT_EXE_NAME, SERVICE_DISPLAY_NAME, SERVICE_NAME

try:
    import win32service
    import win32serviceutil
    _HAVE_PYWIN32 = True
except ImportError:  # pragma: no cover
    _HAVE_PYWIN32 = False

_DESCRIPTION = "Nexora Store Agent: heartbeats to HO and runs delta sync tasks."


class ServiceError(Exception):
    pass


class ServiceManager:
    def __init__(
        self,
        install_path,
        log=None,
        service_name=SERVICE_NAME,
        service_display_name=SERVICE_DISPLAY_NAME,
        exe_name=AGENT_EXE_NAME,
        module_name="store_agent_setup.agent_service",
        description=_DESCRIPTION,
    ):
        self.root = Path(install_path)
        self._log = log or (lambda msg: None)
        self.service_name = service_name
        self.service_display_name = service_display_name
        self.exe_name = exe_name
        self.module_name = module_name
        self.description = description

    def log(self, msg):
        self._log(msg)

    # ---- mode detection ---------------------------------------------------

    def _exe(self):
        exe = self.root / self.exe_name
        return exe if exe.is_file() else None

    def _agent_command(self):
        """Source/dev controller: the pywin32 service module via python."""
        return [sys.executable, "-m", self.module_name]

    # ---- subprocess helpers ----------------------------------------------

    def _env(self):
        env = dict(os.environ)
        env["NEXORA_INSTALL_PATH"] = str(self.root)
        cfg = self.root / "agent_config.json"
        if cfg.is_file():
            env["NEXORA_AGENT_CONFIG"] = str(cfg)
        runtime = self.root / "runtime"
        extra = [p for p in (str(runtime), str(Path(__file__).resolve().parent.parent))
                 if Path(p).exists()]
        if extra:
            env["PYTHONPATH"] = os.pathsep.join(
                extra + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
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

    # ---- STEP 8: register -------------------------------------------------

    def install(self):
        exe = self._exe()
        if exe is None:
            self._install_source()
        else:
            self._install_sc(exe)

    def _install_source(self):
        if self.is_installed():
            self.log(f"service {self.service_name} present; reconfiguring (source mode)")
            self._run("update", "--startup", "auto", check=False)
        else:
            self._run("--startup", "auto", "install")
        self.log(f"service {self.service_name} installed (startup=auto, source mode)")

    def _install_sc(self, exe):
        # Clean slate: a stale/disabled service is exactly what breaks start.
        if self.is_installed():
            self.log(f"service {self.service_name} present; recreating for a clean state")
            self._stop_quiet()
            self._sc("delete", self.service_name, check=False)
            self._wait_absent(timeout=15)

        bin_path = f'"{exe}"'  # SCM stores the command line; quote for spaces.
        self._sc(
            "create", self.service_name,
            "binPath=", bin_path,
            "start=", "auto",
            "DisplayName=", self.service_display_name,
            "obj=", "LocalSystem",
        )
        # Reassert start type so it can NEVER be left Disabled (error 1058).
        self._sc("config", self.service_name, "start=", "auto", check=False)
        self._sc("description", self.service_name, self.description, check=False)
        # Auto-restart on crash: 3 attempts, 60s apart, daily reset.
        self._sc("failure", self.service_name, "reset=", "86400",
                 "actions=", "restart/60000/restart/60000/restart/60000",
                 check=False)
        self.log(f"service {self.service_name} created (startup=auto)")

    # ---- STEP 9: start / stop / remove -----------------------------------

    def start(self):
        # Guarantee the start type before starting (defensive against 1058).
        if self._exe() is not None:
            self._sc("config", self.service_name, "start=", "auto", check=False)
            self._sc("start", self.service_name, check=False)
        else:
            self._run("start", check=False)
        if not self.wait_for_state("running", timeout=45):
            raise ServiceError(
                f"service {self.service_name} did not reach RUNNING (state="
                f"{self.status()}). Check {self.root / 'logs'} and the Windows "
                "Event Log (Application) for NexoraStoreAgent."
            )
        self.log(f"service {self.service_name} running")

    def stop(self):
        self._stop_quiet()
        self.wait_for_state("stopped", timeout=30)
        self.log(f"service {self.service_name} stopped")

    def _stop_quiet(self):
        if self._exe() is not None:
            self._sc("stop", self.service_name, check=False)
        else:
            self._run("stop", check=False)

    def remove(self):
        self._stop_quiet()
        self.wait_for_state("stopped", timeout=30)
        if self._exe() is not None:
            self._sc("delete", self.service_name, check=False)
        else:
            self._run("remove", check=False)
        self.log(f"service {self.service_name} removed")

    def restart(self):
        self.stop()
        self.start()

    # ---- state ------------------------------------------------------------

    def is_installed(self):
        if _HAVE_PYWIN32:
            try:
                win32serviceutil.QueryServiceStatus(self.service_name)
                return True
            except Exception:
                return False
        return self._sc_query() is not None

    def status(self):
        """Return 'running' | 'stopped' | 'pending' | 'not-installed' | 'unknown'."""
        if _HAVE_PYWIN32:
            try:
                state = win32serviceutil.QueryServiceStatus(self.service_name)[1]
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
            ["sc", "query", self.service_name], capture_output=True, text=True
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
