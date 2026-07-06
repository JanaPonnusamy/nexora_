"""UniNex HO backend Windows-service host (pywin32).

Built into the SELF-CONTAINED HO_Backend.exe (PyInstaller onedir). The exe
embeds its own Python and the entire backend, so the target needs NO machine
Python. When the SCM starts the service it loads the deployed production config
(<install>\\config\\ho.env) and runs the FastAPI app under uvicorn in a worker
thread, mirroring the Store Agent's agent_service host.

Also runnable from source for development:
    python -m ho_setup.ho_service install --startup auto
    python -m ho_setup.ho_service start|stop|remove|selftest
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

from . import (
    CONFIG_DIR_NAME,
    DEFAULT_HOST,
    DEFAULT_PORT,
    ENV_FILE_NAME,
    SERVICE_DESCRIPTION,
    SERVICE_DISPLAY_NAME,
    SERVICE_NAME,
)


def _install_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    env = os.environ.get("NEXORA_HO_INSTALL")
    return Path(env) if env else Path.cwd()


def _load_env_file(root):
    """Load <root>/config/ho.env into os.environ before the app imports."""
    env_path = root / CONFIG_DIR_NAME / ENV_FILE_NAME
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


def _redirect_logs(root):
    """A Windows service has no console; send backend output to a log file."""
    try:
        logs = Path(os.environ.get("UNINEX_LOG_PATH") or (root / "logs"))
        logs.mkdir(parents=True, exist_ok=True)
        stream = open(logs / "backend.log", "a", buffering=1, encoding="utf-8")
        stream.write(f"\n==== HO backend start {datetime.now().isoformat()} ====\n")
        sys.stdout = stream
        sys.stderr = stream
    except OSError:
        pass


def _prepare_environment():
    root = _install_root()
    os.environ["NEXORA_HO_INSTALL"] = str(root)
    _load_env_file(root)
    # Backend uses top-level imports (api.app, config.*, controllers.*). In
    # source mode the backend directory must be importable; the frozen bundle
    # already collects those packages.
    if not getattr(sys, "frozen", False):
        backend_dir = Path(__file__).resolve().parent.parent / "backend"
        if backend_dir.is_dir() and str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
    _redirect_logs(root)
    return root


class HoBackendService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = SERVICE_DESCRIPTION

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.server = None
        self.worker = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.server is not None:
            self.server.should_exit = True  # ask uvicorn to shut down
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
            self._serve()
        except Exception as ex:  # pragma: no cover - service runtime
            servicemanager.LogErrorMsg(f"UniNexHO backend crashed: {ex}")
            import traceback

            print("BACKEND CRASH:\n" + traceback.format_exc())

    def _serve(self):
        import uvicorn

        from api.app import app  # imported after env + sys.path are prepared

        host = os.environ.get("UNINEX_HOST", DEFAULT_HOST)
        port = int(os.environ.get("UNINEX_PORT", DEFAULT_PORT))
        config = uvicorn.Config(app, host=host, port=port, log_config=None)
        self.server = uvicorn.Server(config)
        print(f"[HO] uvicorn serving on {host}:{port}")
        self.server.run()  # uvicorn skips signal handlers off the main thread


def _selftest():
    """Prove the executable is self-contained: import the full backend app and
    its uvicorn host from the embedded bundle."""
    _prepare_environment()
    modules = ["uvicorn", "fastapi", "pyodbc", "api.app"]
    import importlib

    failed = []
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as ex:  # noqa: BLE001
            failed.append(f"{name}: {ex}")
    print(f"frozen={getattr(sys, 'frozen', False)} executable={sys.executable}")
    print(f"checked {len(modules)} modules, {len(failed)} failed")
    for f in failed:
        print("  MISSING:", f)
    if failed:
        print("SELFTEST: FAIL")
        return 1
    print("SELFTEST: PASS - HO backend executable is self-contained")
    return 0


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) >= 2 and argv[1] == "selftest":
        sys.exit(_selftest())
    if len(argv) == 1:
        # Launched by the SCM (frozen exe with no args).
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(HoBackendService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(HoBackendService, argv=argv)


if __name__ == "__main__":
    main()
