"""Nexora Mail Transfer Windows service wrapper (pywin32).

Phase 2 extraction: hosts store_agent.mail_transfer_main.main() (EMAIL
package delivery -- SMTP send + IMAP ACK poll) as its own always-on service,
separate from NexoraStoreAgent. Built the same way as agent_service.py: a
SELF-CONTAINED NexoraMailTransfer.exe (PyInstaller onefile) embedding its own
Python + the store_agent runtime, never depending on a machine Python.

Also runnable from source for development:
    python -m store_agent_setup.mail_transfer_service install --startup auto
    python -m store_agent_setup.mail_transfer_service start|stop|remove|selftest

Only meaningful for a store configured with file_transfer.transport.mode ==
EMAIL; store_agent.mail_transfer_main.run_cycle() logs (and no-ops) rather
than crashing the service if that is not the case, so installing this
service on a DIRECT_HTTP/FILE_DROP/SFTP store is harmless but pointless.
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

from . import MAIL_TRANSFER_DISPLAY_NAME, MAIL_TRANSFER_SERVICE_NAME


def _install_path():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    env = os.environ.get("NEXORA_INSTALL_PATH")
    return Path(env) if env else Path.cwd()


def _redirect_logs(root):
    """Send stdout/stderr to <install>/logs/mail_transfer.log -- a Windows
    service has no console."""
    try:
        logs = root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        stream = open(logs / "mail_transfer.log", "a", buffering=1, encoding="utf-8")
        stream.write(f"\n==== mail transfer start {datetime.now().isoformat()} ====\n")
        sys.stdout = stream
        sys.stderr = stream
    except OSError:
        pass


def _prepare_environment():
    """Point store_agent.config at the SAME agent_config.json the main agent
    uses -- this service must resolve the identical store_id / SQLite outbox
    the main agent wrote packages into."""
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


def _run_mail_transfer():
    # Imported lazily so environment is prepared before store_agent.config loads.
    from store_agent.mail_transfer_main import main
    main()


def _selftest():
    modules = [
        "store_agent.mail_transfer_main",
        "store_agent.file_transfer.email_transport",
        "store_agent.file_transfer.sync_dispatcher",
        "store_agent.file_transfer.outbox",
        "store_agent.file_transfer.transport_factory",
        "store_agent.services.sqlite_cache_service",
        "smtplib", "imaplib", "email",
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


class NexoraMailTransferService(win32serviceutil.ServiceFramework):
    _svc_name_ = MAIL_TRANSFER_SERVICE_NAME
    _svc_display_name_ = MAIL_TRANSFER_DISPLAY_NAME
    _svc_description_ = (
        "Nexora Mail Transfer: sends FILE_TRANSFER packages over SMTP and "
        "polls IMAP for HO acknowledgements, for stores configured with "
        "file_transfer.transport.mode = EMAIL."
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
            _run_mail_transfer()
        except Exception as ex:  # pragma: no cover - service runtime
            servicemanager.LogErrorMsg(f"NexoraMailTransfer crashed: {ex}")
            import traceback
            print("MAIL TRANSFER CRASH:\n" + traceback.format_exc())


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) >= 2 and argv[1] == "selftest":
        sys.exit(_selftest())
    if len(argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(NexoraMailTransferService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(NexoraMailTransferService, argv=argv)


if __name__ == "__main__":
    main()
