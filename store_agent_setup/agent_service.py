"""Nexora Store Agent Windows service wrapper (pywin32).

Built into the SELF-CONTAINED NexoraStoreAgent.exe (PyInstaller onedir). The
exe embeds its own Python interpreter and the entire store_agent runtime, so it
NEVER depends on a machine-installed Python and NEVER loads .py source files
deployed next to it.

Also runnable from source for development only:
    python -m store_agent_setup.agent_service install --startup auto
    python -m store_agent_setup.agent_service start|stop|remove|selftest

When the SCM starts the service it runs the existing agent loop
(store_agent.run_agent.main) in a worker thread. The sync runtime/engine is
NOT modified -- this only hosts it as a service.
"""
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

import servicemanager
import win32event
import win32service
import win32serviceutil

from . import SERVICE_DISPLAY_NAME, SERVICE_NAME


def _agent_install_path():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    env = os.environ.get("NEXORA_INSTALL_PATH")
    return Path(env) if env else Path.cwd()


def _redirect_logs(root):
    """Send the agent's stdout/stderr to <install>/logs/agent.log.

    A Windows service has no console, so without this any sync error printed by
    the runtime would be invisible (the failure mode behind PENDING tasks).
    """
    try:
        logs = root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        stream = open(logs / "agent.log", "a", buffering=1, encoding="utf-8")
        stream.write(f"\n==== agent start {datetime.now().isoformat()} ====\n")
        sys.stdout = stream
        sys.stderr = stream
    except OSError:
        pass


def _prepare_environment():
    """Point store_agent.config at the deployed agent_config.json.

    NOTE: we deliberately do NOT add any directory to sys.path. The store_agent
    runtime is imported from THIS executable's embedded bundle only.
    """
    root = _agent_install_path()
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


def _run_agent():
    # Imported lazily so environment is prepared before store_agent.config loads.
    from store_agent.run_agent import main
    main()


def _selftest():
    """Prove the executable is self-contained: import the full sync chain from
    the embedded bundle (no machine Python, no deployed source). Exit 0 if the
    whole task-execution path is present, non-zero otherwise."""
    modules = [
        "store_agent.run_agent",
        "store_agent.run_sync_runtime",
        "store_agent.services.sync_runtime_orchestrator",
        "store_agent.services.task_polling_service",
        "store_agent.services.data_extraction_service",
        "store_agent.services.hash_generation_service",
        "store_agent.services.chunk_builder_service",
        "store_agent.services.sync_sender_service",
        "store_agent.services.sqlite_cache_service",
        "store_agent.services.heartbeat_service",
        "store_agent.fernet_key_service",
        "pyodbc", "cryptography.fernet", "requests", "sqlite3",
    ]
    import importlib
    failed = []
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as ex:  # noqa: BLE001
            failed.append(f"{name}: {ex}")
    frozen = getattr(sys, "frozen", False)
    print(f"frozen={frozen} executable={sys.executable}")
    print(f"checked {len(modules)} modules, {len(failed)} failed")
    for f in failed:
        print("  MISSING:", f)
    if failed:
        print("SELFTEST: FAIL")
        return 1
    print("SELFTEST: PASS - executable is self-contained")
    return 0


class NexoraStoreAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = (
        "Nexora Store Agent: heartbeats to HO and runs delta sync tasks."
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
        _prepare_environment()
        self.worker = threading.Thread(target=self._guarded_run, daemon=True)
        self.worker.start()
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)

    def _guarded_run(self):
        try:
            _run_agent()
        except Exception as ex:  # pragma: no cover - service runtime
            servicemanager.LogErrorMsg(f"NexoraStoreAgent crashed: {ex}")
            import traceback
            print("AGENT CRASH:\n" + traceback.format_exc())


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) >= 2 and argv[1] == "selftest":
        sys.exit(_selftest())
    if len(argv) == 1:
        # Launched by the SCM (frozen exe with no args).
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(NexoraStoreAgentService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(NexoraStoreAgentService, argv=argv)


if __name__ == "__main__":
    main()
