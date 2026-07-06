"""Installer logging and rollback support.

``InstallLogger`` writes a timestamped log file AND forwards every line to an
optional UI callback so the wizard can show live progress. ``Rollback`` records
undo actions as the install proceeds; on failure the orchestrator unwinds them
in reverse order so a failed install leaves the machine clean.
"""
import os
import tempfile
import traceback
from datetime import datetime
from pathlib import Path


def default_log_path():
    """A log location that is writable before the install folder exists."""
    base = Path(os.getenv("TEMP", tempfile.gettempdir())) / "UniNex"
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return base / f"HO_Setup_{stamp}.log"


class InstallLogger:
    def __init__(self, log_file=None, ui_callback=None):
        self.log_file = Path(log_file) if log_file else default_log_path()
        self.ui_callback = ui_callback
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.log_file, "a", encoding="utf-8", buffering=1)
        self.info(f"==== HO_Setup log started {datetime.now().isoformat()} ====")

    def _write(self, level, msg):
        line = f"{datetime.now().strftime('%H:%M:%S')} [{level}] {msg}"
        try:
            self._fh.write(line + "\n")
        except Exception:
            pass
        if self.ui_callback:
            try:
                self.ui_callback(msg)
            except Exception:
                pass

    def info(self, msg):
        self._write("INFO", msg)

    def warn(self, msg):
        self._write("WARN", msg)

    def error(self, msg):
        self._write("ERROR", msg)

    def exception(self, msg):
        self._write("ERROR", msg)
        self._write("ERROR", traceback.format_exc())

    # Allow the logger to be used as a plain ``log(msg)`` callable, matching the
    # Store Agent convention used by ServiceManager / Installer.
    def __call__(self, msg):
        self.info(msg)

    def close(self):
        try:
            self._fh.close()
        except Exception:
            pass


class Rollback:
    """A LIFO stack of undo actions executed if the install fails."""

    def __init__(self, log=None):
        self._actions = []
        self._log = log or (lambda msg: None)

    def push(self, description, action):
        self._actions.append((description, action))

    def commit(self):
        """Install succeeded: discard the undo stack."""
        self._actions.clear()

    def unwind(self):
        """Install failed: run every undo action in reverse order."""
        while self._actions:
            description, action = self._actions.pop()
            try:
                self._log(f"rollback: {description}")
                action()
            except Exception as ex:  # never let cleanup raise
                self._log(f"rollback step failed ({description}): {ex}")
