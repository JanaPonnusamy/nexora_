"""UniNex HO Mail Receiver Windows-service host (pywin32).

Phase 2 extraction: hosts modules.sync.file_transfer_scheduler.run_forever()
(EMAIL package receiving -- IMAP poll + validate/import via the EXISTING
staging/MERGE pipeline + ACK send) as its own always-on service, separate
from UniNexHO (which keeps serving the API). Built the same way as
ho_service.py: a SELF-CONTAINED NexoraHOMailReceiver.exe (PyInstaller
onedir) embedding its own Python + the backend, so the target needs no
machine Python.

Also runnable from source for development:
    python -m ho_setup.mail_receiver_service install --startup auto
    python -m ho_setup.mail_receiver_service start|stop|remove|selftest

Requires NEXORA_FILE_TRANSFER_ENABLED=true and
NEXORA_FILE_TRANSFER_MODE=EMAIL in <install>\\config\\ho.env -- refuses to
serve otherwise (see backend/mail_receiver_main.py), so installing this
service on a deployment not using EMAIL FILE_TRANSFER is harmless but
pointless.
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
    ENV_FILE_NAME,
    MAIL_RECEIVER_DISPLAY_NAME,
    MAIL_RECEIVER_SERVICE_DESCRIPTION,
    MAIL_RECEIVER_SERVICE_NAME,
)


def _install_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    env = os.environ.get("NEXORA_HO_INSTALL")
    return Path(env) if env else Path.cwd()


def _load_env_file(root):
    """Same convention as ho_service.py: load <root>/config/ho.env before the
    backend imports, so this service reads the identical mail/DB settings the
    main HO backend service does."""
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
    try:
        logs = Path(os.environ.get("UNINEX_LOG_PATH") or (root / "logs"))
        logs.mkdir(parents=True, exist_ok=True)
        stream = open(logs / "mail_receiver.log", "a", buffering=1, encoding="utf-8")
        stream.write(f"\n==== HO mail receiver start {datetime.now().isoformat()} ====\n")
        sys.stdout = stream
        sys.stderr = stream
    except OSError:
        pass


def _prepare_environment():
    root = _install_root()
    os.environ["NEXORA_HO_INSTALL"] = str(root)
    _load_env_file(root)
    if not getattr(sys, "frozen", False):
        backend_dir = Path(__file__).resolve().parent.parent / "backend"
        if backend_dir.is_dir() and str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
    _redirect_logs(root)
    return root


def _run_mail_receiver():
    from mail_receiver_main import main
    main()


def _selftest():
    _prepare_environment()
    modules = [
        "mail_receiver_main",
        "modules.sync.file_transfer_scheduler",
        "modules.sync.file_transfer_receiver_service",
        "modules.sync.file_transfer_transport.email",
        "modules.sync.file_transfer_repository",
        "smtplib", "imaplib", "email",
    ]
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
    print("SELFTEST: PASS - HO mail receiver executable is self-contained")
    return 0


class NexoraHOMailReceiverService(win32serviceutil.ServiceFramework):
    _svc_name_ = MAIL_RECEIVER_SERVICE_NAME
    _svc_display_name_ = MAIL_RECEIVER_DISPLAY_NAME
    _svc_description_ = MAIL_RECEIVER_SERVICE_DESCRIPTION

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
            _run_mail_receiver()
        except Exception as ex:  # pragma: no cover - service runtime
            servicemanager.LogErrorMsg(f"NexoraHOMailReceiver crashed: {ex}")
            import traceback
            print("HO MAIL RECEIVER CRASH:\n" + traceback.format_exc())


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) >= 2 and argv[1] == "selftest":
        sys.exit(_selftest())
    if len(argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(NexoraHOMailReceiverService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(NexoraHOMailReceiverService, argv=argv)


if __name__ == "__main__":
    main()
