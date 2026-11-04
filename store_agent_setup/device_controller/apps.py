"""What the controller can manage on a PC, one adapter per app.

Every adapter reports status()/version and implements the actions HO may send
(start/stop/restart/update/...). Pause and resume are plain stop/start here --
the "auto-resume after N minutes" part lives in the desired state HO keeps.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import time
import zipfile
from pathlib import Path

from .. import stock_client_host as host
from . import (
    BACKUP_DIR,
    CONTROLLER_VERSION,
    EXE_NAME,
    HO_MAINTENANCE_FLAG,
    INSTALL_DIR,
    LEGACY_WATCHDOG_SERVICES,
    LEGACY_WATCHDOG_TASKS,
    SERVICE_NAME,
    STAGING_DIR,
    STATE_DIR,
)
from .util import bundled_path, log, run, sha256_of, spawn_detached, wait_until

try:
    import win32service
    import win32serviceutil
    _HAVE_WIN32 = True
except ImportError:  # pragma: no cover
    _HAVE_WIN32 = False


class ActionError(Exception):
    pass


# ---------------------------------------------------------------------------
# Windows service + process helpers
# ---------------------------------------------------------------------------

def service_state(name):
    """'running' | 'stopped' | 'pending' | 'not-installed' | 'unknown'."""
    if not _HAVE_WIN32:
        return "unknown"
    try:
        state = win32serviceutil.QueryServiceStatus(name)[1]
    except Exception:
        return "not-installed"
    return {
        win32service.SERVICE_RUNNING: "running",
        win32service.SERVICE_STOPPED: "stopped",
        win32service.SERVICE_START_PENDING: "pending",
        win32service.SERVICE_STOP_PENDING: "pending",
    }.get(state, "unknown")


def service_binary(name):
    """Path of the service's exe (from its ImagePath), or None."""
    if not _HAVE_WIN32:
        return None
    try:
        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        try:
            svc = win32service.OpenService(scm, name, win32service.SERVICE_QUERY_CONFIG)
            try:
                cmd = win32service.QueryServiceConfig(svc)[3]
            finally:
                win32service.CloseServiceHandle(svc)
        finally:
            win32service.CloseServiceHandle(scm)
    except Exception:
        return None
    cmd = (cmd or "").strip()
    if cmd.startswith('"'):
        exe = cmd[1:].split('"', 1)[0]
    else:
        exe = cmd.split(" ", 1)[0]
    return Path(exe) if exe else None


def processes_under(folder):
    """(pid, path) of every process whose exe lives under `folder`."""
    prefix = str(folder).rstrip("\\").lower() + "\\"
    found = []
    try:
        import win32com.client

        wmi = win32com.client.GetObject("winmgmts:")
        for proc in wmi.ExecQuery("SELECT ProcessId, ExecutablePath FROM Win32_Process"):
            path = (proc.ExecutablePath or "").lower()
            if path.startswith(prefix):
                found.append((int(proc.ProcessId), proc.ExecutablePath))
    except Exception:
        pass
    return found


def kill_processes_under(folder):
    killed = []
    for pid, path in processes_under(folder):
        if pid == os.getpid():
            continue
        code, _ = run(["taskkill", "/F", "/T", "/PID", str(pid)], timeout=30)
        if code == 0:
            killed.append(f"{pid} {path}")
    if killed:
        log(f"[kill] {folder}: " + "; ".join(killed))
    return killed


def sc_start(name, timeout=60):
    run(["sc", "config", name, "start=", "auto"])
    run(["sc", "start", name])
    if not wait_until(lambda: service_state(name) == "running", timeout):
        raise ActionError(f"{name} did not reach RUNNING (state={service_state(name)})")


def sc_stop(name, timeout=45):
    if service_state(name) in ("stopped", "not-installed"):
        return
    run(["sc", "stop", name])
    if not wait_until(lambda: service_state(name) == "stopped", timeout):
        raise ActionError(f"{name} did not stop (state={service_state(name)})")


def replace_file(src, dst, timeout=60):
    """Copy src over dst, retrying while a lingering handle holds dst."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            return
        except PermissionError as ex:
            last = ex
            time.sleep(1)
        except OSError as ex:
            last = ex
            time.sleep(1)
    raise ActionError(f"could not replace {dst}: {last}")


def verify_package(path, pkg, require_signature=False):
    actual = sha256_of(path)
    if actual.lower() != (pkg.get("sha256") or "").lower():
        raise ActionError(f"sha256 mismatch: expected {pkg.get('sha256')}, got {actual}")
    if os.path.getsize(path) != int(pkg.get("file_size") or 0):
        raise ActionError("size mismatch")
    sig = pkg.get("signature")
    if not sig:
        if require_signature:
            raise ActionError("package is not release-signed")
        return
    from modules.device_identity import crypto

    pub = release_public_key()
    if not pub:
        raise ActionError("no release-signing public key available")
    manifest = f"{pkg['version']}|{actual}|{os.path.getsize(path)}".encode("utf-8")
    if not crypto.verify(pub, manifest, base64.b64decode(sig)):
        raise ActionError("release signature verification failed")


def release_public_key():
    path = bundled_path("stock_release_signing_key.pub.pem")
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else None
    except OSError:
        return None


def fetch_package(ctx, app_key, pkg):
    """Download + verify a package into staging; returns its path."""
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    dest = STAGING_DIR / f"{app_key}-{pkg['version']}-{pkg['file_name']}"
    if not (dest.is_file() and sha256_of(dest).lower() == pkg["sha256"].lower()):
        ctx.progress(f"downloading {pkg['file_name']}")
        ctx.ho.download(pkg.get("sources"), f"/api/agent/controller/packages/{app_key}/{pkg['version']}", dest)
    ctx.progress("verifying package")
    verify_package(dest, pkg, require_signature=app_key in ("ho_backend", "stock_client", "controller"))
    return dest


# ---------------------------------------------------------------------------
# Base adapters
# ---------------------------------------------------------------------------

class App:
    key = ""
    label = ""
    enforce_running = True   # restart it automatically when desired RUNNING

    def installed(self):
        return False

    def status(self):
        return "unknown"

    def version(self):
        return None

    def details(self):
        return {}

    def snapshot(self):
        installed = self.installed()
        return {
            "app_key": self.key,
            "installed": installed,
            "status": self.status() if installed else "not-installed",
            "version": self.version() if installed else None,
            "details": self.details() if installed else {},
        }

    def start(self, ctx):
        raise ActionError("start not supported")

    def stop(self, ctx):
        raise ActionError("stop not supported")

    def restart(self, ctx):
        self.stop(ctx)
        self.start(ctx)

    def pause(self, ctx, minutes=None):
        self.stop(ctx)

    def resume(self, ctx):
        self.start(ctx)

    def is_running(self):
        return self.status() == "running"


class ServiceApp(App):
    service = ""

    def installed(self):
        return service_state(self.service) != "not-installed"

    def status(self):
        return service_state(self.service)

    def install_dir(self):
        exe = service_binary(self.service)
        return exe.parent if exe else None

    def _require_installed(self):
        if not self.installed():
            raise ActionError(f"{self.label} ({self.service}) is not installed on this PC")

    def start(self, ctx):
        self._require_installed()
        sc_start(self.service)

    def stop(self, ctx):
        self._require_installed()
        sc_stop(self.service)
        exe = service_binary(self.service)
        if exe:  # a service that "stopped" but left its exe running (seen on .73)
            for pid in host.processes_by_path(exe):
                run(["taskkill", "/F", "/T", "/PID", str(pid)])


# ---------------------------------------------------------------------------
# Store Agent (+ HO links)
# ---------------------------------------------------------------------------

class StoreAgentApp(ServiceApp):
    key = "store_agent"
    label = "Store Agent"
    service = "NexoraStoreAgent"

    def _config_path(self):
        d = self.install_dir()
        return d / "agent_config.json" if d else None

    def _read_config(self):
        p = self._config_path()
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p and p.is_file() else {}
        except (OSError, ValueError):
            return {}

    def version(self):
        d = self.install_dir()
        try:
            marker = d / "agent_version_installed.txt" if d else None
            if marker and marker.is_file():
                return marker.read_text(encoding="utf-8").strip() or None
        except OSError:
            pass
        return None

    def _override_file(self):
        return Path(r"C:\ProgramData\Nexora\ho_override.txt")

    def details(self):
        cfg = self._read_config()
        urls = cfg.get("ho_urls") or ([cfg["ho_url"]] if cfg.get("ho_url") else [])
        override = None
        try:
            if self._override_file().is_file():
                override = self._override_file().read_text(encoding="utf-8").strip()
        except OSError:
            pass
        return {
            "install_dir": str(self.install_dir() or ""),
            "store_id": cfg.get("store_id"),
            "agent_mode": cfg.get("agent_mode"),
            "ho_urls": urls,
            "ho_override": override,
        }

    def set_ho_urls(self, ctx, urls, restart=True):
        path = self._config_path()
        if not path or not path.is_file():
            raise ActionError("agent_config.json not found next to the Store Agent")
        cfg = self._read_config()
        backup = path.with_name(f"agent_config.backup-{int(time.time())}.json")
        shutil.copy2(str(path), str(backup))
        cfg["ho_urls"] = list(urls)
        cfg["ho_url"] = urls[0]
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(path))
        # The disaster-recovery override file beats agent_config.json; keep it
        # in line so the new links actually take effect.
        if self._override_file().is_file():
            self._override_file().write_text("\n".join(urls), encoding="utf-8")
        ctx.progress(f"HO links set to {', '.join(urls)} (backup {backup.name})")
        if restart and self.installed():
            self.restart(ctx)
        return f"HO links updated: {', '.join(urls)}"

    def update(self, ctx, pkg):
        staged = fetch_package(ctx, self.key, pkg)
        d = self.install_dir()
        if not d:
            raise ActionError("Store Agent service is not installed")
        target = d / "NexoraStoreAgent.exe"
        previous = self.version() or "unknown"
        backup = BACKUP_DIR / "store_agent" / f"NexoraStoreAgent-{previous}.exe"
        backup.parent.mkdir(parents=True, exist_ok=True)
        was_running = self.is_running()
        with ctx.maintenance(self.key):
            self.stop(ctx)
            if target.is_file():
                shutil.copy2(str(target), str(backup))
            try:
                replace_file(staged, target)
                (d / "agent_version_installed.txt").write_text(pkg["version"], encoding="utf-8")
                if was_running:
                    self.start(ctx)
                    time.sleep(15)
                    if not self.is_running():
                        raise ActionError("agent did not stay running after update")
            except Exception:
                ctx.progress("update failed -- rolling back")
                if backup.is_file():
                    sc_stop(self.service)
                    replace_file(backup, target)
                    (d / "agent_version_installed.txt").write_text(previous, encoding="utf-8")
                    if was_running:
                        sc_start(self.service)
                raise
        return f"Store Agent updated {previous} -> {pkg['version']}"

    def install(self, ctx, pkg, install_dir=None):
        """Fresh install for Nexora Setup. The setup kit has already registered
        this PC's agent identity (config\\device_key.bin) and written a device-
        mode agent_config.json into the folder; this places the exe and
        registers the service exactly as the old setup wizard did."""
        if self.installed():
            return self.update(ctx, pkg)
        d = Path(install_dir) if install_dir else default_agent_dir()
        if not ((d / "agent_config.json").is_file() and (d / "config" / "device_key.bin").is_file()):
            raise ActionError(f"no Store Agent identity in {d}: run Nexora Setup and select Store Agent")
        staged = fetch_package(ctx, self.key, pkg)
        exe = d / "NexoraStoreAgent.exe"
        ctx.progress(f"installing {pkg['version']} into {d}")
        (d / "logs").mkdir(parents=True, exist_ok=True)
        replace_file(staged, exe)
        (d / "agent_version_installed.txt").write_text(pkg["version"], encoding="utf-8")
        run(["sc", "create", self.service, "binPath=", f'"{exe}"', "start=", "auto",
             "DisplayName=", "Nexora Store Agent", "obj=", "LocalSystem"])
        run(["sc", "description", self.service,
             "Nexora Store Agent - syncs this PC's store databases to HO"])
        run(["sc", "failure", self.service, "reset=", "86400",
             "actions=", "restart/60000/restart/60000/restart/60000"])
        if not self.installed():
            raise ActionError("the NexoraStoreAgent service could not be created")
        sc_start(self.service)
        if not wait_until(self.is_running, 45, interval=3):
            raise ActionError(f"Store Agent installed but not running (state={self.status()})")
        return f"Store Agent {pkg['version']} installed in {d}"


def default_agent_dir():
    """Same place the old wizard used: D:\\NexoraStoreAgent when the PC has a
    fixed D: drive, else C:\\NexoraStoreAgent."""
    try:
        import ctypes

        if ctypes.windll.kernel32.GetDriveTypeW("D:\\") == 3:  # DRIVE_FIXED
            return Path(r"D:\NexoraStoreAgent")
    except (AttributeError, OSError):
        pass
    return Path(r"C:\NexoraStoreAgent")


class MailTransferApp(ServiceApp):
    key = "mail_transfer"
    label = "Mail Transfer"
    service = "NexoraMailTransfer"


# ---------------------------------------------------------------------------
# HO Backend (exe nodes: UniNexHO)
# ---------------------------------------------------------------------------

class HoBackendApp(ServiceApp):
    key = "ho_backend"
    label = "HO Backend"
    service = "UniNexHO"
    KEEP = {"config", "logs", "uploads", "backups", "updates"}

    def version(self):
        d = self.install_dir()
        try:
            marker = d / "HO_BACKEND_VERSION.txt" if d else None
            if marker and marker.is_file():
                return marker.read_text(encoding="utf-8").strip() or None
        except OSError:
            pass
        return None

    def _port(self):
        d = self.install_dir()
        try:
            env = d / "config" / "ho.env" if d else None
            if env and env.is_file():
                for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.strip().startswith("UNINEX_PORT="):
                        return int(line.split("=", 1)[1].strip())
        except (OSError, ValueError):
            pass
        return 8000

    def healthy(self):
        import requests

        try:
            return requests.get(f"http://127.0.0.1:{self._port()}/health", timeout=4).status_code == 200
        except Exception:
            return False

    def details(self):
        return {"install_dir": str(self.install_dir() or ""), "port": self._port(),
                "healthy": self.healthy() if self.status() == "running" else False}

    def stop(self, ctx):
        sc_stop(self.service, timeout=60)
        d = self.install_dir()
        if d:
            kill_processes_under(d)

    def _set_maintenance(self, on):
        try:
            if on:
                HO_MAINTENANCE_FLAG.parent.mkdir(parents=True, exist_ok=True)
                HO_MAINTENANCE_FLAG.write_text(str(time.time()), encoding="utf-8")
            elif HO_MAINTENANCE_FLAG.is_file():
                HO_MAINTENANCE_FLAG.unlink()
        except OSError:
            pass

    def _copy_tree(self, src_root, dst_root, skip_top):
        """Copy every file under src_root to dst_root (skipping top-level
        runtime dirs), retrying files that are briefly locked."""
        failed = []
        for src in Path(src_root).rglob("*"):
            rel = src.relative_to(src_root)
            if rel.parts and rel.parts[0].lower() in skip_top:
                continue
            if src.is_dir():
                continue
            dst = Path(dst_root) / rel
            try:
                if dst.is_file() and dst.stat().st_size == src.stat().st_size \
                        and sha256_of(dst) == sha256_of(src):
                    continue  # identical (e.g. a DLL some other process holds open)
                replace_file(src, dst, timeout=20)
            except Exception as ex:
                failed.append(f"{rel}: {ex}")
        return failed

    def update(self, ctx, pkg):
        staged = fetch_package(ctx, self.key, pkg)
        d = self.install_dir()
        if not d:
            raise ActionError("UniNexHO service is not installed on this PC")
        previous = self.version() or "unknown"
        extract = STAGING_DIR / f"ho_backend-{pkg['version']}"
        if extract.exists():
            shutil.rmtree(str(extract), ignore_errors=True)
        ctx.progress("extracting bundle")
        with zipfile.ZipFile(str(staged)) as z:
            z.extractall(str(extract))
        backup = BACKUP_DIR / "ho_backend" / previous
        with ctx.maintenance(self.key):
            self._set_maintenance(True)
            try:
                ctx.progress("stopping UniNexHO")
                run(["sc", "config", self.service, "start=", "disabled"])
                self.stop(ctx)
                ctx.progress(f"backing up {previous}")
                if backup.exists():
                    shutil.rmtree(str(backup), ignore_errors=True)
                self._copy_tree(d, backup, self.KEEP)
                ctx.progress(f"installing {pkg['version']}")
                failed = self._copy_tree(extract, d, self.KEEP)
                if failed:
                    raise ActionError("files could not be replaced: " + "; ".join(failed[:5]))
                ctx.progress("starting UniNexHO")
                sc_start(self.service, timeout=90)
                if not wait_until(self.healthy, 150, interval=3):
                    raise ActionError("HO backend did not become healthy after update")
            except Exception as ex:
                ctx.progress(f"update failed ({ex}) -- rolling back to {previous}")
                try:
                    run(["sc", "config", self.service, "start=", "disabled"])
                    self.stop(ctx)
                    self._copy_tree(backup, d, self.KEEP)
                finally:
                    sc_start(self.service, timeout=90)
                raise
            finally:
                run(["sc", "config", self.service, "start=", "auto"])
                self._set_maintenance(False)
                shutil.rmtree(str(extract), ignore_errors=True)
        return f"HO backend updated {previous} -> {pkg['version']}"


class HoBackendGitApp(App):
    """HO backend on a GIT node (the build PC, .80): no UniNexHO service -- the
    `NexoraBackend` scheduled task runs uvicorn from the checkout. There is no
    package to install: the code on disk IS the version, so "update" means
    restart to load whatever is checked out now."""
    key = "ho_backend"
    label = "HO Backend (git)"
    TASK = "NexoraBackend"
    PORT = 8000
    # A backend can be HUNG: still holding :8000 but never answering /health
    # (2026-10-24: three store syncs + 300s searches starved it). The task's
    # start-prod-8000.bat then skips ("already running"), so a plain start can
    # never recover it. The enforce loop kills the hung listener only after it
    # has been silent this long; an explicit HO Start/Restart kills at once.
    HUNG_GRACE = 300

    def __init__(self):
        self._unhealthy_since = None

    def _task_command(self):
        code, out = run(["schtasks", "/Query", "/TN", self.TASK, "/XML"])
        if code != 0:
            return None
        import re

        m = re.search(r"<Command>(.*?)</Command>", out, re.S)
        return Path(m.group(1).strip().strip('"')) if m else None

    def installed(self):
        return self._task_command() is not None

    def _repo(self):
        cmd = self._task_command()
        return cmd.parent.parent if cmd else None   # <repo>\backend\start-prod-8000.bat

    def healthy(self):
        import requests

        try:
            return requests.get(f"http://127.0.0.1:{self.PORT}/health", timeout=4).status_code == 200
        except Exception:
            return False

    def status(self):
        if self.healthy():
            self._unhealthy_since = None
            return "running"
        if self._unhealthy_since is None:
            self._unhealthy_since = time.time()
        return "stopped"

    def version(self):
        repo = self._repo()
        if not repo:
            return None
        code, head = run(["git", "-c", "safe.directory=*", "-C", str(repo), "rev-parse", "--short", "HEAD"], timeout=20)
        return f"git {head.strip()}" if code == 0 and head.strip() else None

    def details(self):
        repo = self._repo()
        info = {"kind": "git", "repo": str(repo or ""), "port": self.PORT, "healthy": self.healthy()}
        if repo:
            code, subject = run(["git", "-c", "safe.directory=*", "-C", str(repo), "log", "-1", "--pretty=%s (%cr)"], timeout=20)
            if code == 0:
                info["commit"] = subject.strip()[:200]
        return info

    def _listener_pids(self):
        code, out = run(["netstat", "-ano", "-p", "TCP"], timeout=20)
        pids = set()
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].endswith(f":{self.PORT}") and parts[3].upper() == "LISTENING":
                pids.add(parts[4])
        return pids

    def start(self, ctx):
        if self.healthy():
            self._unhealthy_since = None
            return
        hung = self._listener_pids()
        if hung:
            silent = time.time() - (self._unhealthy_since or time.time())
            if ctx is None and silent < self.HUNG_GRACE:
                log(f"[enforce] {self.key}: :{self.PORT} held but /health silent {int(silent)}s -- "
                    f"waiting {self.HUNG_GRACE}s before killing it")
                return
            log(f"[{self.key}] :{self.PORT} held by unresponsive pid(s) {', '.join(sorted(hung))} -- killing")
            self.stop(ctx)
        run(["schtasks", "/Run", "/TN", self.TASK])
        if not wait_until(self.healthy, 120, interval=3):
            raise ActionError("backend did not answer /health within 2 minutes")
        self._unhealthy_since = None

    def stop(self, ctx):
        run(["schtasks", "/End", "/TN", self.TASK])
        for pid in self._listener_pids():
            run(["taskkill", "/F", "/T", "/PID", pid])
        if not wait_until(lambda: not self.healthy(), 30):
            raise ActionError("backend is still answering after stop")

    def update(self, ctx, pkg):
        raise ActionError("this is a git node -- use Restart to load the code currently checked out")


# ---------------------------------------------------------------------------
# Stock Client (Electron GUI, not a service)
# ---------------------------------------------------------------------------

PRODUCT_NAME = "Axythic Supplier Stock"


def _uninstall_key_dirs(winreg, sub):
    """Install dir from an uninstall key: InstallLocation, else the folder of
    DisplayIcon / UninstallString (both point at files inside the install dir)."""
    dirs = []
    for value in ("InstallLocation", "DisplayIcon", "UninstallString"):
        try:
            raw = str(winreg.QueryValueEx(sub, value)[0] or "").strip()
        except OSError:
            continue
        if not raw:
            continue
        if value == "InstallLocation":
            dirs.append(Path(raw.strip('"')))
            continue
        if raw.startswith('"'):
            raw = raw[1:].split('"', 1)[0]
        else:
            raw = raw.split(",", 1)[0]
            lower = raw.lower()
            if ".exe" in lower:
                raw = raw[:lower.index(".exe") + 4]
        if raw:
            dirs.append(Path(raw).parent)
    return dirs


class StockClientApp(App):
    key = "stock_client"
    label = "Stock Client"
    enforce_running = False   # a GUI the user may close; only explicit start

    def exe(self):
        for root in self._candidate_dirs():
            exe = root / f"{PRODUCT_NAME}.exe"
            if exe.is_file():
                return exe
        return None

    def _candidate_dirs(self):
        dirs = []
        try:
            import winreg

            for hive, view in ((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
                               (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY)):
                base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
                try:
                    with winreg.OpenKey(hive, base, 0, winreg.KEY_READ | view) as root:
                        for i in range(winreg.QueryInfoKey(root)[0]):
                            try:
                                with winreg.OpenKey(root, winreg.EnumKey(root, i)) as sub:
                                    name = winreg.QueryValueEx(sub, "DisplayName")[0]
                                    # electron-builder writes "Axythic Supplier Stock 0.1.48"
                                    # and may leave InstallLocation empty (custom install dir)
                                    if name == PRODUCT_NAME or name.startswith(PRODUCT_NAME + " "):
                                        dirs += _uninstall_key_dirs(winreg, sub)
                            except OSError:
                                continue
                except OSError:
                    continue
        except ImportError:
            pass
        pf = Path(os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles") or r"C:\Program Files")
        dirs.append(pf / PRODUCT_NAME)
        # older installs used a custom dir with no matching uninstall key (NMS .32)
        dirs.append(pf / "Nexora Supplier Stock" / PRODUCT_NAME)
        local = host.user_localappdata()
        if local:
            dirs += [local / "Programs" / PRODUCT_NAME, local / "Programs" / "axythic-supplier-stock"]
        return dirs

    def installed(self):
        return self.exe() is not None

    def status(self):
        exe = self.exe()
        return "running" if exe and host.is_running(exe) else "stopped"

    def version(self):
        exe = self.exe()
        if not exe:
            return None
        for rel in ("resources/app/package.json", "resources/app.asar.unpacked/package.json"):
            pj = exe.parent / rel
            try:
                if pj.is_file():
                    return json.loads(pj.read_text(encoding="utf-8")).get("version")
            except (OSError, ValueError):
                pass
        return None

    def details(self):
        exe = self.exe()
        return {"install_dir": str(exe.parent) if exe else "",
                "user_session": host.active_session_username()}

    def start(self, ctx):
        exe = self.exe()
        if not exe:
            raise ActionError("Stock Client is not installed")
        if host.is_running(exe):
            return
        if not host.launch_in_user_session(str(exe), log=log, show=True):
            raise ActionError("no logged-on user to start the Stock Client for")

    def stop(self, ctx):
        exe = self.exe()
        if exe and not host.stop(exe, log=log):
            raise ActionError("Stock Client did not close")

    def update(self, ctx, pkg):
        staged = fetch_package(ctx, self.key, pkg)
        previous = self.version()
        current = self.exe()
        was_running = self.is_running() if current else False
        backup_dir = BACKUP_DIR / "stock_client"
        backup_dir.mkdir(parents=True, exist_ok=True)
        with ctx.maintenance(self.key):
            if was_running:
                ctx.progress("closing the Stock Client")
                self.stop(ctx)
            ctx.progress(f"installing {pkg['version']}")
            # reinstall in place: /S alone falls back to the default folder and
            # leaves a custom-dir install (e.g. ...\Nexora Supplier Stock\...) stale.
            # NSIS needs /D= last and unquoted, so pass a raw command line.
            cmdline = f'"{staged}" /S'
            if current:
                cmdline += f" /D={current.parent}"
            code, out = run(cmdline, timeout=900)
            if code != 0:
                raise ActionError(f"installer exited with {code}: {out[-300:]}")
            if not wait_until(lambda: self.version() == pkg["version"], 60, interval=2):
                raise ActionError(f"installed version is {self.version()}, expected {pkg['version']}")
            # keep only this installer as the rollback copy for the next update
            for old in backup_dir.glob("*.exe"):
                old.unlink()
            shutil.copy2(str(staged), str(backup_dir / staged.name))
            if was_running:
                self.start(ctx)
        return f"Stock Client {previous or 'not installed'} -> {pkg['version']}"

    def install(self, ctx, pkg, install_dir=None):
        # The NSIS installer handles fresh and in-place installs alike.
        return self.update(ctx, pkg)


# ---------------------------------------------------------------------------
# The controller itself
# ---------------------------------------------------------------------------

UPDATE_MARKER = STATE_DIR / "private" / "self_update.json"


class ControllerApp(App):
    key = "controller"
    label = "Device Controller"
    enforce_running = False

    def installed(self):
        return True

    def status(self):
        return "running"

    def version(self):
        return CONTROLLER_VERSION

    def details(self):
        legacy = {name: service_state(name) for name in LEGACY_WATCHDOG_SERVICES}
        return {"legacy_watchdogs": legacy}

    def restart(self, ctx):
        spawn_detached(["cmd", "/c",
                        f"timeout /t 3 /nobreak >nul & sc stop {SERVICE_NAME} & "
                        f"timeout /t 8 /nobreak >nul & sc start {SERVICE_NAME}"])
        return "controller restart scheduled"

    def retire_legacy_watchdogs(self, ctx):
        done = []
        for name in LEGACY_WATCHDOG_SERVICES:
            if service_state(name) != "not-installed":
                run(["sc", "stop", name])
                run(["sc", "config", name, "start=", "disabled"])
                done.append(name)
        for task in LEGACY_WATCHDOG_TASKS:
            code, _ = run(["schtasks", "/Query", "/TN", task])
            if code == 0:
                run(["schtasks", "/Change", "/TN", task, "/DISABLE"])
                done.append(f"task {task}")
        return ("retired: " + ", ".join(done)) if done else "no legacy watchdogs found"

    def update(self, ctx, pkg):
        staged = fetch_package(ctx, self.key, pkg)
        target = INSTALL_DIR / EXE_NAME
        UPDATE_MARKER.parent.mkdir(parents=True, exist_ok=True)
        UPDATE_MARKER.write_text(json.dumps({"command_id": ctx.command_id, "version": pkg["version"],
                                             "from": CONTROLLER_VERSION}), encoding="utf-8")
        backup = BACKUP_DIR / "controller" / f"{EXE_NAME}.{CONTROLLER_VERSION}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file():
            shutil.copy2(str(target), str(backup))
        # A running exe cannot replace itself: a detached cmd stops the
        # service, swaps the exe (restoring the backup if the copy fails) and
        # starts it again. The new controller reports the result on start.
        script = STAGING_DIR / "controller_update.cmd"
        script.write_text(
            "@echo off\r\n"
            "timeout /t 3 /nobreak >nul\r\n"
            f"sc stop {SERVICE_NAME} >nul\r\n"
            "timeout /t 8 /nobreak >nul\r\n"
            f"copy /y \"{staged}\" \"{target}\" >nul || copy /y \"{backup}\" \"{target}\" >nul\r\n"
            f"sc start {SERVICE_NAME} >nul\r\n",
            encoding="utf-8",
        )
        spawn_detached(["cmd", "/c", str(script)])
        ctx.defer_result = True
        return f"controller update to {pkg['version']} scheduled"


def all_apps():
    # An HO node is either an exe node (UniNexHO service) or the git build node
    # (NexoraBackend task); report whichever this PC actually has.
    ho = HoBackendApp()
    if not ho.installed():
        git_ho = HoBackendGitApp()
        if git_ho.installed():
            ho = git_ho
    return [StoreAgentApp(), MailTransferApp(), StockClientApp(), ho, ControllerApp()]
