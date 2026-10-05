"""Nexora Stock Client Watchdog: Windows service (pywin32), Milestone 2.

A running "Axythic Supplier Stock" GUI cannot stop, replace, or relaunch itself,
and -- unlike the store agent -- it is not a Windows service, so once it is
closed there is nothing on the PC for HO to start again. This always-on SYSTEM
service is that missing piece. Every cycle it:

  1. Authenticates to HO with its device token (reusing modules.device_identity:
     sign <device_id>.<ts>.<nonce> -> /api/auth/device/token).
  2. Polls /api/agent/stock-client/state for the version AUTHORIZED for this
     machine's store (release != rollout; HO flips the target to PENDING only
     after an explicit AUTHORIZE in the HO UI -- see modules/stock_client_ops).
  3. If a new version is authorized: downloads the signed installer, verifies
     BOTH its sha256 AND an Ed25519 signature over `<version>|<sha256>|<size>`
     (public key shipped with the watchdog), closes the GUI by its EXACT install
     path, backs up the current installer, runs the new installer silently in the
     logged-on user's session, health-checks the result, and ROLLS BACK to the
     previous installer if the new one fails to come up.
  4. Heartbeats fleet status to /api/agent/stock-client/heartbeat, reporting the
     watchdog's own state AND the GUI's state separately (a SYSTEM service cannot
     be the GUI), plus live per-update progress.

Crash-loop guard: a version that fails to install/health-check is retried with
backoff and then parked, so a bad release cannot pin the machine in a reboot /
reinstall loop. State survives restarts via a marker file in ProgramData, so a
power loss mid-update is detected and reconciled on next start.

Runnable from source for development:
    python -m store_agent_setup.stock_client_watchdog_service install --startup auto
    python -m store_agent_setup.stock_client_watchdog_service start|stop|remove
    python -m store_agent_setup.stock_client_watchdog_service run-once   # one cycle, foreground
"""
import base64
import hashlib
import json
import os
import socket
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if _BACKEND.is_dir() and str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))  # resolve modules.device_identity in dev + onefile
_MEI = getattr(sys, "_MEIPASS", None)
if _MEI and _MEI not in sys.path:
    sys.path.insert(0, _MEI)

from . import (
    STOCK_CLIENT_PRODUCT_NAME,
    STOCK_CLIENT_WATCHDOG_DISPLAY_NAME,
    STOCK_CLIENT_WATCHDOG_SERVICE_NAME,
    STOCK_CLIENT_WATCHDOG_VERSION,
)
from . import stock_client_host as host

POLL_SECONDS = 60
# A health check that keeps the GUI alive this long after launch is treated as a
# successful start (no crash-on-launch). Kept short so a failed update is caught
# well within one poll cycle.
HEALTH_ALIVE_SECONDS = 20
# Give up auto-retrying a version after this many consecutive failures; park it
# and report FAILED so a bad release cannot reinstall-loop the machine.
MAX_UPDATE_ATTEMPTS = 3

# Machine-wide state dir, readable by the SYSTEM service AND writable regardless
# of which user is logged on (the GUI's own userData is per-user + DPAPI-sealed
# to that user, so SYSTEM cannot share it).
PROGRAMDATA = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
STATE_DIR = PROGRAMDATA / "Axythic" / "StockClient"
CONFIG_FILE = STATE_DIR / "watchdog.json"
PUBKEY_FILE = STATE_DIR / "stock_release_signing_key.pub.pem"
UPDATE_MARKER = STATE_DIR / "update_in_progress.json"
BACKUP_DIR = STATE_DIR / "backups"
STAGING_DIR = STATE_DIR / "staging"
LOG_FILE = STATE_DIR / "watchdog.log"
# Keep the log small on resource-constrained store PCs (see the 16GB-thrash
# incidents): rotate once over this size, keep a single .1 backup.
LOG_MAX_BYTES = 2 * 1024 * 1024


# --------------------------------------------------------------------------
# Logging (a service has no console)
# --------------------------------------------------------------------------

def _rotate_log():
    try:
        if LOG_FILE.is_file() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
            backup = LOG_FILE.with_suffix(".log.1")
            if backup.exists():
                backup.unlink()
            LOG_FILE.rename(backup)
    except OSError:
        pass


def log(msg):
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _rotate_log()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


# --------------------------------------------------------------------------
# Config + device identity
# --------------------------------------------------------------------------

def _load_config():
    """Watchdog config, part self-generated, part provisioned at enrollment:
        { ho_url, device_id, device_private_key_pem, device_public_key_pem,
          installation_id }

    The watchdog OWNS its Ed25519 keypair: it is generated here on first run and
    the PRIVATE key never leaves this SYSTEM-only file. Enrollment
    (provision_stock_watchdog.py, or the Stock Client's Device Setup) only reads
    the PUBLIC key + registers it with HO and writes back `ho_url` + `device_id`.
    installation_id is self-generated. Until `ho_url`+`device_id` are present the
    watchdog simply no-ops each cycle (nothing to poll)."""
    cfg = {}
    try:
        if CONFIG_FILE.is_file():
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        cfg = {}
    changed = False
    if not cfg.get("installation_id"):
        cfg["installation_id"] = "sc-" + uuid.uuid4().hex[:16]
        changed = True
    if not cfg.get("device_private_key_pem") or not cfg.get("device_public_key_pem"):
        try:
            from modules.device_identity import crypto

            private_pem, public_pem = crypto.generate_keypair()
            cfg["device_private_key_pem"] = private_pem
            cfg["device_public_key_pem"] = public_pem
            changed = True
        except Exception as ex:
            # Without crypto we cannot self-key; enrollment will have to supply it.
            log(f"[config] could not generate device keypair: {ex}")
    if changed:
        _save_config(cfg)
        _publish_public_key(cfg.get("device_public_key_pem"))
    return cfg


def _publish_public_key(public_pem):
    """Write the watchdog's device PUBLIC key where an enroller (the Stock Client
    / provisioning CLI) can read it to register this device with HO. Public key
    only -- the private half never leaves CONFIG_FILE."""
    if not public_pem:
        return
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / "device_public_key.pem").write_text(public_pem, encoding="utf-8")
    except OSError as ex:
        log(f"[config] could not publish device public key: {ex}")


def _save_config(cfg):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except OSError as ex:
        log(f"[config] could not persist watchdog.json: {ex}")


def _load_public_key():
    """The HO release-signing PUBLIC key, shipped next to the watchdog (bundled
    by build.py) and also honored from the state dir for field key-rotation."""
    for candidate in (PUBKEY_FILE, _bundled_path("stock_release_signing_key.pub.pem")):
        try:
            if candidate and candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        except OSError:
            continue
    return None


def _bundled_path(name):
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / name
    return Path(__file__).resolve().parent.parent / "backend" / "config" / name


# --------------------------------------------------------------------------
# HO client (device-token auth, reusing modules.device_identity semantics)
# --------------------------------------------------------------------------

class HoClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self.ho_url = (cfg.get("ho_url") or "").rstrip("/")
        self._token = None
        self._token_exp = 0

    def ready(self):
        return bool(self.ho_url and self.cfg.get("device_id")
                    and self.cfg.get("device_private_key_pem"))

    def _sign_token(self):
        import requests
        from modules.device_identity import crypto

        device_id = self.cfg["device_id"]
        ts = str(int(time.time()))
        nonce = uuid.uuid4().hex
        message = crypto.canonical_message(device_id, ts, nonce)
        signature = base64.b64encode(
            crypto.sign(self.cfg["device_private_key_pem"], message)
        ).decode("utf-8")
        resp = requests.post(
            f"{self.ho_url}/api/auth/device/token",
            json={"device_id": device_id, "timestamp": ts,
                  "nonce": nonce, "signature": signature},
            timeout=20,
        )
        resp.raise_for_status()
        self._token = resp.json()["token"]
        # Refresh a minute before the server's default 30-min expiry regardless of
        # exact TTL; cheap and avoids mid-cycle 401s.
        self._token_exp = time.time() + 20 * 60

    def _bearer(self):
        if not self._token or time.time() >= self._token_exp:
            self._sign_token()
        return {"Authorization": f"Bearer {self._token}"}

    def get_state(self, installation_id):
        import requests

        resp = requests.get(
            f"{self.ho_url}/api/agent/stock-client/state",
            params={"installation_id": installation_id},
            headers=self._bearer(), timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    def download(self, version, dest):
        import requests

        url = f"{self.ho_url}/api/agent/stock-client/download/{version}"
        with requests.get(url, headers=self._bearer(), stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)

    def heartbeat(self, payload):
        import requests

        try:
            requests.post(
                f"{self.ho_url}/api/agent/stock-client/heartbeat",
                json=payload, headers=self._bearer(), timeout=20,
            )
        except Exception as ex:
            # Heartbeat is best-effort; it must never break the reconcile loop.
            log(f"[heartbeat] failed: {ex}")


# --------------------------------------------------------------------------
# Integrity
# --------------------------------------------------------------------------

def _sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_package(path, target, public_pem):
    """Both checks must pass before anything is installed."""
    from modules.device_identity import crypto

    actual = _sha256_of(path)
    expected = (target.get("sha256") or "").strip().lower()
    if actual.lower() != expected:
        raise RuntimeError(f"sha256 mismatch: expected {expected}, got {actual}")
    if not public_pem:
        raise RuntimeError("no release-signing public key available to verify signature")
    size = os.path.getsize(path)
    manifest = f"{target['target_version']}|{actual}|{size}".encode("utf-8")
    signature = base64.b64decode(target.get("signature") or "")
    if not crypto.verify(public_pem, manifest, signature):
        raise RuntimeError("Ed25519 signature verification failed")


# --------------------------------------------------------------------------
# Install path resolution + health
# --------------------------------------------------------------------------

def _client_exe_path():
    """Full path to the installed GUI exe, resolved against the LOGGED-ON user's
    LOCALAPPDATA (not SYSTEM's). None if no user is logged on / not installed."""
    local = host.user_localappdata()
    if not local:
        return None
    exe = local / "Programs" / "axythic-supplier-stock" / f"{STOCK_CLIENT_PRODUCT_NAME}.exe"
    return exe


def _installed_client_version():
    """Best-effort: read the installed app's version from its package.json
    (electron-builder ships it inside resources/app or app.asar-adjacent). Falls
    back to the marker written after our own installs."""
    exe = _client_exe_path()
    if exe:
        root = exe.parent
        for rel in ("resources/app/package.json", "resources/app.asar.unpacked/package.json"):
            pj = root / rel
            try:
                if pj.is_file():
                    return json.loads(pj.read_text(encoding="utf-8")).get("version")
            except (OSError, ValueError):
                pass
    try:
        if (STATE_DIR / "installed_version.txt").is_file():
            return (STATE_DIR / "installed_version.txt").read_text(encoding="utf-8").strip() or None
    except OSError:
        pass
    return None


def _write_installed_version(version):
    try:
        (STATE_DIR / "installed_version.txt").write_text(version, encoding="utf-8")
    except OSError:
        pass


def _health_check(exe):
    """Start the GUI and confirm it stays up (no crash-on-launch). A localhost
    /health endpoint in the Electron main process can be layered on later; a
    stable live process is the honest minimum signal today."""
    host.launch_in_user_session(str(exe), log=log, show=True)
    deadline = time.time() + HEALTH_ALIVE_SECONDS
    while time.time() < deadline:
        time.sleep(2)
        if not host.is_running(exe):
            return False
    return host.is_running(exe)


# --------------------------------------------------------------------------
# The reconcile cycle
# --------------------------------------------------------------------------

class WatchdogCycle:
    def __init__(self):
        self.cfg = _load_config()
        self.installation_id = self.cfg["installation_id"]
        self.client = HoClient(self.cfg)
        self.public_pem = _load_public_key()
        self._attempts = {}  # version -> consecutive failure count

    # -- status gathering ---------------------------------------------------

    def _client_status(self, exe):
        if exe is None:
            return "UNKNOWN"
        return "RUNNING" if host.is_running(exe) else "STOPPED"

    def _local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            return None

    def _base_heartbeat(self, exe, last_update_status=None, last_error=None):
        return {
            "installation_id": self.installation_id,
            "watchdog_version": STOCK_CLIENT_WATCHDOG_VERSION,
            "watchdog_status": "RUNNING",
            "client_status": self._client_status(exe),
            "client_version": _installed_client_version(),
            "local_ip": self._local_ip(),
            "os_version": f"{sys.platform} {os.environ.get('OS', '')}".strip(),
            "last_update_status": last_update_status,
            "last_error": last_error,
        }

    # -- one pass -----------------------------------------------------------

    def run_once(self):
        exe = _client_exe_path()

        # Reconcile an update interrupted by a crash / power loss before polling.
        self._recover_interrupted(exe)

        if not self.client.ready():
            log("[cycle] not enrolled yet (missing ho_url/device identity); "
                "heartbeat skipped until the Stock Client binds this machine")
            return

        try:
            state = self.client.get_state(self.installation_id)
        except Exception as ex:
            log(f"[cycle] could not reach HO for state: {ex}")
            return

        target = (state or {}).get("target")
        last_status, last_error = "idle", None

        if target:
            try:
                last_status = self._apply_update(target, exe)
            except Exception:
                last_error = traceback.format_exc(limit=3)
                last_status = "update-failed"
                log("[cycle] update failed:\n" + last_error)

        exe = _client_exe_path()  # may have changed after install
        self.client.heartbeat(self._base_heartbeat(exe, last_status, last_error))

    # -- update -------------------------------------------------------------

    def _report_progress(self, target, status, progress, error=None, exe=None):
        hb = self._base_heartbeat(exe or _client_exe_path())
        hb.update({
            "target_version": target.get("target_version"),
            "target_status": status,
            "target_progress": progress,
            "target_error": error,
        })
        self.client.heartbeat(hb)

    def _apply_update(self, target, exe):
        version = target.get("target_version")
        installed = _installed_client_version()
        if installed and version and installed == version:
            return f"up-to-date:{version}"

        if self._attempts.get(version, 0) >= MAX_UPDATE_ATTEMPTS:
            self._report_progress(target, "FAILED", 100,
                                  error="max attempts reached; parked", exe=exe)
            return f"parked:{version}"

        STAGING_DIR.mkdir(parents=True, exist_ok=True)
        staged = STAGING_DIR / f"Axythic-Supplier-Stock-Setup-{version}.exe"

        # DOWNLOADING
        self._report_progress(target, "DOWNLOADING", 10, exe=exe)
        log(f"[update] downloading {version}")
        self.client.download(version, staged)

        # VERIFYING (sha256 + Ed25519)
        self._report_progress(target, "VERIFYING", 40, exe=exe)
        _verify_package(staged, target, self.public_pem)
        log(f"[update] verified {version}")

        # Mark intent BEFORE we touch the running app, so an interrupted install
        # is recoverable on next start.
        self._write_marker(version, staged, previous=_installed_backup_path())

        # INSTALLING
        self._report_progress(target, "INSTALLING", 60, exe=exe)
        if exe and host.is_running(exe):
            log("[update] closing running GUI before install")
            host.stop(exe, log=log)
        self._backup_current(staged)

        code = host.run_in_user_session_and_wait(
            str(staged), args="/S", log=log, timeout_seconds=600
        )
        if code not in (0, None):
            self._attempts[version] = self._attempts.get(version, 0) + 1
            raise RuntimeError(f"installer exited with code {code}")

        # RESTARTING + health
        self._report_progress(target, "RESTARTING", 85, exe=exe)
        new_exe = _client_exe_path()
        healthy = _health_check(new_exe) if new_exe else False
        if not healthy:
            log("[update] health check FAILED; rolling back")
            self._attempts[version] = self._attempts.get(version, 0) + 1
            self._rollback(new_exe)
            self._report_progress(target, "ROLLED_BACK", 100,
                                  error="post-update health check failed")
            self._clear_marker()
            return f"rolled-back:{version}"

        _write_installed_version(version)
        self._attempts.pop(version, None)
        self._clear_marker()
        self._report_progress(target, "SUCCESS", 100, exe=new_exe)
        log(f"[update] installed + healthy: {version}")
        return f"updated-to:{version}"

    # -- backup / rollback / recovery --------------------------------------

    def _backup_current(self, new_installer):
        """Keep a copy of the installer we are REPLACING so rollback can re-run
        it. We only retain the single most recent backup (disk hygiene -- old
        exes must not accumulate on store PCs)."""
        current = _installed_client_version()
        if not current:
            return
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        # The backup is the previously-staged installer, if we still have it.
        prev = STAGING_DIR / f"Axythic-Supplier-Stock-Setup-{current}.exe"
        dest = BACKUP_DIR / f"Axythic-Supplier-Stock-Setup-{current}.exe"
        try:
            if prev.is_file() and prev.resolve() != new_installer.resolve():
                import shutil
                shutil.copy2(prev, dest)
            # prune everything in backups except the one we just kept
            for old in BACKUP_DIR.glob("Axythic-Supplier-Stock-Setup-*.exe"):
                if old.name != dest.name:
                    old.unlink(missing_ok=True)
        except OSError as ex:
            log(f"[backup] could not snapshot current installer: {ex}")

    def _rollback(self, exe):
        backup = _installed_backup_path()
        if not backup or not backup.is_file():
            log("[rollback] no previous installer to restore")
            return
        if exe and host.is_running(exe):
            host.stop(exe, log=log)
        log(f"[rollback] re-running previous installer {backup.name}")
        host.run_in_user_session_and_wait(str(backup), args="/S", log=log,
                                          timeout_seconds=600)
        restored = _client_exe_path()
        if restored:
            host.launch_in_user_session(str(restored), log=log, show=True)

    def _write_marker(self, version, staged, previous):
        try:
            UPDATE_MARKER.write_text(json.dumps({
                "version": version,
                "staged": str(staged),
                "previous_backup": str(previous) if previous else None,
                "started_at": datetime.now().isoformat(timespec="seconds"),
            }, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _clear_marker(self):
        try:
            UPDATE_MARKER.unlink(missing_ok=True)
        except OSError:
            pass

    def _recover_interrupted(self, exe):
        """If a previous cycle died mid-install (crash / power loss), the marker
        survives. If the app is healthy now, just clear it; otherwise roll back
        to the backed-up installer so the machine is never left without a working
        client."""
        if not UPDATE_MARKER.is_file():
            return
        try:
            marker = json.loads(UPDATE_MARKER.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._clear_marker()
            return
        log(f"[recover] found interrupted update: {marker.get('version')}")
        if exe and host.is_running(exe):
            self._clear_marker()
            return
        if exe and exe.is_file():
            # Installed but not running -- try a plain launch before rolling back.
            if _health_check(exe):
                self._clear_marker()
                return
        self._rollback(exe)
        self._clear_marker()


def _installed_backup_path():
    try:
        backups = sorted(BACKUP_DIR.glob("Axythic-Supplier-Stock-Setup-*.exe"))
        return backups[-1] if backups else None
    except OSError:
        return None


# --------------------------------------------------------------------------
# Service loop + SCM shell
# --------------------------------------------------------------------------

def _watchdog_loop(stop_event):
    import win32event

    while True:
        try:
            WatchdogCycle().run_once()
        except Exception:
            log("[loop] cycle crashed:\n" + traceback.format_exc())
        if win32event.WaitForSingleObject(
            stop_event, POLL_SECONDS * 1000
        ) == win32event.WAIT_OBJECT_0:
            return


try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil

    class NexoraStockClientWatchdogService(win32serviceutil.ServiceFramework):
        _svc_name_ = STOCK_CLIENT_WATCHDOG_SERVICE_NAME
        _svc_display_name_ = STOCK_CLIENT_WATCHDOG_DISPLAY_NAME
        _svc_description_ = (
            "Keeps the Axythic Supplier Stock client on the version HO authorizes "
            "for this store, and relaunches it when needed."
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
            self.worker = threading.Thread(
                target=_watchdog_loop, args=(self.stop_event,), daemon=True
            )
            self.worker.start()
            win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)

    _HAVE_SERVICE = True
except ImportError:  # pragma: no cover - non-Windows / no pywin32
    _HAVE_SERVICE = False


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) >= 2 and argv[1] == "run-once":
        WatchdogCycle().run_once()
        return
    if not _HAVE_SERVICE:
        raise SystemExit("pywin32 is required to host the watchdog as a service")
    if len(argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(NexoraStockClientWatchdogService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(
            NexoraStockClientWatchdogService, argv=argv
        )


if __name__ == "__main__":
    main()
