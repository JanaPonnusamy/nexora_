"""NexoraDeviceController: the Windows service + its setup CLI.

    NexoraDeviceController.exe                 (no args: started by the SCM)
    NexoraDeviceController.exe setup --ho URL[,URL] [--code XXXXX-XXXXX]
    NexoraDeviceController.exe install-service [--ho URL[,URL]]
    NexoraDeviceController.exe enroll --code XXXXX-XXXXX [--ho URL]
    NexoraDeviceController.exe status | console | uninstall

Two loops run while the service is up:
  * inbox loop  -- long-polls HO for signed messages (commands, terminal I/O)
                   and runs them (commands on worker threads).
  * state loop  -- every 30s: heartbeat app status/versions to HO, receive the
                   desired run-state per app and enforce it (this is what
                   replaces the old per-app watchdogs), pick up enrollment.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

_MEI = getattr(sys, "_MEIPASS", None)
if _MEI and _MEI not in sys.path:
    sys.path.insert(0, _MEI)
_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if _BACKEND.is_dir() and str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))  # modules.device_identity / device_controller.protocol in dev

from modules.device_controller import protocol  # noqa: E402

from . import (  # noqa: E402
    CONFIG_FILE,
    CONTROLLER_VERSION,
    EXE_NAME,
    INBOX_DIR,
    INSTALL_DIR,
    PRIVATE_DIR,
    SEEN_FILE,
    SERVICE_DESCRIPTION,
    SERVICE_DISPLAY_NAME,
    SERVICE_NAME,
    STATUS_FILE,
)
from . import apps as app_mod  # noqa: E402
from .ho import HoClient, NotEnrolled, enroll_with_code  # noqa: E402
from .terminal import TerminalManager  # noqa: E402
from .util import (  # noqa: E402
    bundled_path,
    load_config,
    local_ip,
    log,
    machine_fingerprint,
    normalize_urls,
    os_version,
    run,
    save_config,
    secure_state_dirs,
    sha256_of,
)

INFLIGHT_DIR = PRIVATE_DIR / "inflight"
STATE_INTERVAL = 30
ROUTE_LEARN_INTERVAL = 600
POLL_WAIT = 20
MAX_SEEN = 2000
CLOCK_SKEW = 300

# Apps that should be running unless HO says otherwise.
DEFAULT_DESIRED = {"store_agent": "RUNNING", "ho_backend": "RUNNING"}


class CommandContext:
    def __init__(self, controller, command_id, app_key):
        self.controller = controller
        self.ho = controller.ho
        self.command_id = command_id
        self.app_key = app_key
        self.defer_result = False
        self.lines = []

    def progress(self, text):
        self.lines.append(text)
        log(f"[cmd {self.command_id[:8]}] {text}")
        self.controller.post_result(self.command_id, "RUNNING", None, "\n".join(self.lines[-20:]))

    @contextlib.contextmanager
    def maintenance(self, app_key):
        """While an app is being updated the enforcement loop leaves it alone."""
        self.controller.maintenance.add(app_key)
        try:
            yield
        finally:
            self.controller.maintenance.discard(app_key)


class Controller:
    def __init__(self):
        self.cfg = load_config()
        self.ho = HoClient(self.cfg)
        self.apps = {a.key: a for a in app_mod.all_apps()}
        self.hq_public_key = self._load_hq_key()
        bundled_path("stock_release_signing_key.pub.pem")  # keep a durable copy
        self.seen = self._load_seen()
        self.seen_lock = threading.Lock()
        self.terminal = TerminalManager(self.ho)
        self.maintenance = set()
        self.app_locks = {k: threading.Lock() for k in self.apps}
        self.desired = {}
        self.last_desired = {}
        self.stop_event = threading.Event()
        self._last_routes = 0.0
        self._legacy_done = False
        self._self_update_reported = False
        self._config_mtime = None

    # ---- keys + replay protection ----------------------------------------

    def _load_hq_key(self):
        path = bundled_path("device_controller_command_key.pub.pem")
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            log(f"[init] HO command public key missing at {path}; commands will be rejected")
            return None

    def _load_seen(self):
        try:
            return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _remember(self, message_id, result=None):
        with self.seen_lock:
            self.seen[message_id] = {"at": int(time.time()), "result": result}
            if len(self.seen) > MAX_SEEN:
                for key in sorted(self.seen, key=lambda k: self.seen[k]["at"])[:len(self.seen) - MAX_SEEN]:
                    self.seen.pop(key, None)
            try:
                SEEN_FILE.write_text(json.dumps(self.seen), encoding="utf-8")
            except OSError:
                pass

    def verify(self, msg):
        payload, signature = msg.get("payload") or {}, msg.get("signature")
        if not self.hq_public_key or not protocol.verify(self.hq_public_key, payload, signature):
            return "bad signature"
        if str(payload.get("device_id", "")).lower() != str(self.cfg.get("device_id", "")).lower():
            return "message is for another device"
        if int(payload.get("expires_at") or 0) < time.time() - CLOCK_SKEW:
            return "message expired"
        return None

    # ---- results ----------------------------------------------------------

    def post_result(self, command_id, status, exit_code, text):
        try:
            self.ho.request("POST", f"/api/agent/controller/commands/{command_id}/result",
                            json={"status": status, "exit_code": exit_code,
                                  "result_text": (text or "")[-100000:]}, timeout=20)
        except Exception as ex:
            log(f"[result] could not report {command_id[:8]} {status}: {ex}")

    # ---- inbox ------------------------------------------------------------

    def handle(self, msg):
        problem = self.verify(msg)
        payload = msg.get("payload") or {}
        mid = str(payload.get("id") or "")
        if problem:
            log(f"[inbox] rejected {payload.get('kind')} {mid[:8]}: {problem}")
            return
        with self.seen_lock:
            known = self.seen.get(mid)
        if known:
            if payload.get("kind") == protocol.KIND_COMMAND and known.get("result"):
                r = known["result"]
                self.post_result(mid, r["status"], r.get("exit_code"), r.get("text"))
            return
        self._remember(mid)
        kind = payload.get("kind")
        if kind == protocol.KIND_COMMAND:
            threading.Thread(target=self.run_command, args=(payload,), daemon=True).start()
        elif kind in (protocol.KIND_TERM_OPEN, protocol.KIND_TERM_INPUT,
                      protocol.KIND_TERM_RESET, protocol.KIND_TERM_CLOSE):
            sid = str(payload.get("session_id") or "").lower()
            if kind == protocol.KIND_TERM_OPEN:
                self.terminal.open(sid)
            elif kind == protocol.KIND_TERM_INPUT:
                self.terminal.input(sid, payload.get("data") or "")
            elif kind == protocol.KIND_TERM_RESET:
                self.terminal.reset(sid)
            else:
                self.terminal.close(sid)

    def run_command(self, payload):
        cid, app_key, action = payload["id"], payload.get("app"), payload.get("action")
        args = payload.get("args") or {}
        ctx = CommandContext(self, cid, app_key)
        self.post_result(cid, "RUNNING", None, f"{action} {app_key} accepted by {socket.gethostname()}")
        app = self.apps.get(app_key)
        status, code, text = "FAILED", 1, ""
        inflight = INFLIGHT_DIR / f"{cid}.json"
        try:
            INFLIGHT_DIR.mkdir(parents=True, exist_ok=True)
            inflight.write_text(json.dumps({
                "command_id": cid, "app": app_key, "action": action,
                "target_version": ((args.get("package") or {}).get("version")),
            }), encoding="utf-8")
        except OSError:
            pass
        try:
            if app is None or action not in protocol.APP_ACTIONS.get(app_key, ()):
                raise app_mod.ActionError(f"unsupported: {app_key}.{action}")
            with self.app_locks[app_key]:
                result = self._dispatch(app, action, args, ctx)
            status, code, text = "SUCCEEDED", 0, result or f"{action} done"
        except Exception as ex:
            text = f"{ex}\n{traceback.format_exc(limit=3)}"
            log(f"[cmd {cid[:8]}] FAILED: {ex}")
        finally:
            try:
                inflight.unlink()
            except OSError:
                pass
        if ctx.defer_result:
            # the new controller exe reports the final result after restart
            self._remember(cid, None)
            return
        if ctx.lines:
            text = "\n".join(ctx.lines + [text])
        self._remember(cid, {"status": status, "exit_code": code, "text": text})
        self.post_result(cid, status, code, text)
        self.state_tick()  # report the new state right away

    def _dispatch(self, app, action, args, ctx):
        if action == "update":
            return app.update(ctx, args["package"])
        if action == "install":
            return app.install(ctx, args["package"], args.get("install_dir"))
        if action == "set_ho_urls":
            return app.set_ho_urls(ctx, args["urls"], args.get("restart", True))
        if action == "retire_legacy_watchdogs":
            return app.retire_legacy_watchdogs(ctx)
        if action == "pause":
            app.pause(ctx, args.get("minutes"))
            self.last_desired[app.key] = "PAUSED"
            return f"{app.label} paused for {args.get('minutes')} min"
        if action in ("start", "resume"):
            app.start(ctx)
            return f"{app.label} started"
        if action == "stop":
            app.stop(ctx)
            return f"{app.label} stopped"
        if action == "restart":
            return app.restart(ctx) or f"{app.label} restarted"
        raise app_mod.ActionError(f"unknown action {action}")

    def inbox_loop(self):
        while not self.stop_event.is_set():
            if not self.ho.ready():
                self.stop_event.wait(15)
                continue
            try:
                resp = self.ho.request("GET", f"/api/agent/controller/poll?wait={POLL_WAIT}",
                                       timeout=POLL_WAIT + 15)
                if resp.status_code == 200:
                    for msg in resp.json().get("messages") or []:
                        try:
                            self.handle(msg)
                        except Exception as ex:
                            log(f"[inbox] handling failed: {ex}")
                else:
                    log(f"[inbox] poll HTTP {resp.status_code}: {resp.text[:200]}")
                    self.stop_event.wait(10)
            except NotEnrolled as ex:
                log(f"[inbox] not enrolled: {ex}")
                self.stop_event.wait(60)
            except Exception as ex:
                log(f"[inbox] poll failed: {ex}")
                self.stop_event.wait(5)

    # ---- state ------------------------------------------------------------

    def pick_up_enrollment(self):
        """The Stock Client registers this controller with the logged-in
        user's HO session and drops {device_id, ho_urls} in the inbox."""
        path = INBOX_DIR / "enrollment.json"
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        try:
            path.unlink()
        except OSError:
            pass
        device_id = str(data.get("device_id") or "").strip()
        urls = normalize_urls(data.get("ho_urls") or [data.get("ho_url")])
        if not device_id or not urls:
            return
        old = (self.cfg.get("device_id"), list(self.cfg.get("ho_urls") or []))
        self.cfg["device_id"] = device_id
        self.cfg["ho_urls"] = normalize_urls(urls + list(self.cfg.get("ho_urls") or []))
        self.ho._tokens.clear()
        with self.ho._lock:
            # Prove the new id against the HO that issued it, not a previously
            # active URL of another HO (which would reject it and undo this).
            self.ho._active = urls[0]
        try:
            self.ho._token(self.ho.active_url(), force=True)  # proves HO knows OUR key
            save_config(self.cfg)
            log(f"[enroll] enrolled via Stock Client as {device_id}")
        except Exception as ex:
            self.cfg["device_id"], self.cfg["ho_urls"] = old
            log(f"[enroll] ignored inbox enrollment ({ex})")

    def _report_self_update(self):
        marker = app_mod.UPDATE_MARKER
        if not marker.is_file():
            return
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            ok = data.get("version") == CONTROLLER_VERSION
            self.post_result(data["command_id"], "SUCCEEDED" if ok else "FAILED", 0 if ok else 1,
                             f"controller now {CONTROLLER_VERSION} (was {data.get('from')})")
            self._remember(data["command_id"], {"status": "SUCCEEDED" if ok else "FAILED",
                                                "exit_code": 0 if ok else 1, "text": CONTROLLER_VERSION})
        except Exception as ex:
            log(f"[self-update] could not report: {ex}")
        try:
            marker.unlink()
        except OSError:
            pass

    def _resolve_interrupted(self):
        """Commands that were running when the controller restarted (e.g. a
        Stock Client installer that also upgraded the controller). An update
        whose target version is now installed counts as done."""
        if not INFLIGHT_DIR.is_dir():
            return
        for path in INFLIGHT_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                app = self.apps.get(data.get("app"))
                target = data.get("target_version")
                ok = bool(target and app and app.version() == target)
                text = (f"{data.get('app')} is now {target}" if ok else
                        "interrupted by a controller restart; check the app state and retry")
                self.post_result(data["command_id"], "SUCCEEDED" if ok else "FAILED", 0 if ok else 1, text)
                self._remember(data["command_id"], {"status": "SUCCEEDED" if ok else "FAILED",
                                                    "exit_code": 0 if ok else 1, "text": text})
            except Exception as ex:
                log(f"[init] could not resolve interrupted command {path.name}: {ex}")
            try:
                path.unlink()
            except OSError:
                pass

    def snapshot(self):
        apps = []
        for key, app in self.apps.items():
            try:
                snap = app.snapshot()
            except Exception as ex:
                snap = {"app_key": key, "installed": False, "status": "unknown",
                        "details": {"error": str(ex)}}
            snap["desired_state"] = (self.desired.get(key) or {}).get("desired_state") \
                or (DEFAULT_DESIRED.get(key) if snap.get("installed") else None)
            snap.setdefault("details", {})["maintenance"] = key in self.maintenance
            apps.append(snap)
        return {
            "hostname": socket.gethostname(),
            "local_ip": local_ip(),
            "os_version": os_version(),
            "controller_version": CONTROLLER_VERSION,
            "ho_url": self.ho.active_url() if self.ho.urls() else None,
            "apps": apps,
        }

    def enforce(self):
        for key, app in self.apps.items():
            if key in self.maintenance or not self.app_locks[key].acquire(blocking=False):
                continue
            try:
                if not app.installed():
                    continue
                want = (self.desired.get(key) or {}).get("desired_state") or DEFAULT_DESIRED.get(key)
                prev = self.last_desired.get(key)
                self.last_desired[key] = want
                if not want:
                    continue
                running = app.is_running()
                if want in ("STOPPED", "PAUSED") and running:
                    log(f"[enforce] {key}: desired {want} but running -> stop")
                    app.stop(None)
                elif want == "RUNNING" and not running:
                    if app.enforce_running and app.status() == "stopped":
                        log(f"[enforce] {key}: desired RUNNING but stopped -> start")
                        app.start(None)
                    elif not app.enforce_running and prev == "PAUSED":
                        log(f"[enforce] {key}: pause ended -> start")
                        app.start(None)
            except Exception as ex:
                log(f"[enforce] {key}: {ex}")
            finally:
                self.app_locks[key].release()

    def _reload_config_if_changed(self):
        """`setup`/`enroll` run from a prompt write the config while the
        service is running -- adopt a new device_id / HO URLs without a restart."""
        try:
            mtime = CONFIG_FILE.stat().st_mtime
        except OSError:
            return
        if self._config_mtime is None:
            self._config_mtime = mtime
            return
        if mtime == self._config_mtime:
            return
        self._config_mtime = mtime
        fresh = load_config()
        if (fresh.get("device_id"), fresh.get("ho_urls")) != (self.cfg.get("device_id"), self.cfg.get("ho_urls")):
            self.cfg["device_id"] = fresh.get("device_id")
            self.cfg["ho_urls"] = fresh.get("ho_urls") or []
            self.ho._tokens.clear()
            log(f"[config] reloaded: device={self.cfg.get('device_id')} ho={self.cfg.get('ho_urls')}")

    def state_tick(self):
        self._reload_config_if_changed()
        self.pick_up_enrollment()
        if self.cfg.get("retire_legacy", True) and not self._legacy_done:
            try:
                log("[init] " + self.apps["controller"].retire_legacy_watchdogs(None))
            except Exception as ex:
                log(f"[init] legacy watchdog retirement failed: {ex}")
            self._legacy_done = True
        snap = self.snapshot()
        try:
            STATUS_FILE.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
        except OSError:
            pass
        if self.ho.ready():
            try:
                resp = self.ho.request("POST", "/api/agent/controller/heartbeat", json=snap, timeout=25)
                if resp.status_code == 200:
                    self.desired = resp.json().get("desired") or {}
                else:
                    log(f"[state] heartbeat HTTP {resp.status_code}: {resp.text[:200]}")
            except Exception as ex:
                log(f"[state] heartbeat failed: {ex}")
            if time.time() - self._last_routes > ROUTE_LEARN_INTERVAL:
                self._last_routes = time.time()
                if self.ho.learn_routes():
                    save_config(self.cfg)
        self.enforce()

    def state_loop(self):
        while not self.stop_event.is_set():
            try:
                if self.ho.ready() and not self._self_update_reported:
                    self._report_self_update()
                    self._resolve_interrupted()
                    self._self_update_reported = True
                self.state_tick()
            except Exception:
                log("[state] tick crashed:\n" + traceback.format_exc())
            self.stop_event.wait(STATE_INTERVAL)

    def run(self):
        log(f"[init] Nexora Device Controller {CONTROLLER_VERSION} starting "
            f"(device={self.cfg.get('device_id') or 'not enrolled'}, ho={self.ho.urls()})")
        threading.Thread(target=self.inbox_loop, daemon=True, name="inbox").start()
        self.state_loop()
        self.terminal.close_all()


# ---------------------------------------------------------------------------
# Windows service shell
# ---------------------------------------------------------------------------

try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil

    class DeviceControllerService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY_NAME
        _svc_description_ = SERVICE_DESCRIPTION

        def __init__(self, args):
            super().__init__(args)
            self.stop_handle = win32event.CreateEvent(None, 0, 0, None)
            self.controller = None

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            if self.controller:
                self.controller.stop_event.set()
            win32event.SetEvent(self.stop_handle)

        def SvcDoRun(self):
            servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                                  servicemanager.PYS_SERVICE_STARTED, (self._svc_name_, ""))
            try:
                secure_state_dirs()
                self.controller = Controller()
                threading.Thread(target=self.controller.run, daemon=True).start()
            except Exception:
                log("[service] failed to start:\n" + traceback.format_exc())
            win32event.WaitForSingleObject(self.stop_handle, win32event.INFINITE)

    _HAVE_SERVICE = True
except ImportError:  # pragma: no cover
    _HAVE_SERVICE = False


# ---------------------------------------------------------------------------
# Setup CLI
# ---------------------------------------------------------------------------

def _is_admin():
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _install_exe():
    """Copy the running exe to the fixed install dir (frozen builds only)."""
    if not getattr(sys, "frozen", False):
        return None
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    target = INSTALL_DIR / EXE_NAME
    src = Path(sys.executable).resolve()
    if target.is_file() and sha256_of(src) == sha256_of(target):
        return target  # same build already installed: leave the running service alone
    if src != target.resolve():
        if app_mod.service_state(SERVICE_NAME) == "running":
            run(["sc", "stop", SERVICE_NAME])
            time.sleep(5)
        app_mod.replace_file(src, target)
    return target


def _register_service(exe):
    if app_mod.service_state(SERVICE_NAME) == "not-installed":
        bin_path = f'"{exe}"' if exe else f'"{sys.executable}" -m store_agent_setup.device_controller.service'
        run(["sc", "create", SERVICE_NAME, "binPath=", bin_path, "start=", "auto",
             "DisplayName=", SERVICE_DISPLAY_NAME, "obj=", "LocalSystem"], check=True)
    run(["sc", "config", SERVICE_NAME, "start=", "auto"])
    run(["sc", "description", SERVICE_NAME, SERVICE_DESCRIPTION])
    run(["sc", "failure", SERVICE_NAME, "reset=", "86400",
         "actions=", "restart/30000/restart/60000/restart/60000"])
    if app_mod.service_state(SERVICE_NAME) == "running":
        # Already running (e.g. started by the Stock Client installer) with the
        # config it loaded at start -- restart so a new enrollment takes effect.
        run(["sc", "stop", SERVICE_NAME])
        app_mod.wait_until(lambda: app_mod.service_state(SERVICE_NAME) == "stopped", 30)
    run(["sc", "start", SERVICE_NAME])


def cmd_setup(args, require_code=False):
    if not _is_admin():
        raise SystemExit("Run this from an elevated (Administrator) prompt.")
    secure_state_dirs()
    cfg = load_config()
    if args.ho:
        cfg["ho_urls"] = normalize_urls([args.ho] + list(cfg.get("ho_urls") or []))
    if getattr(args, "code", None):
        if not cfg["ho_urls"]:
            raise SystemExit("--ho is required to enroll")
        cfg["device_id"] = enroll_with_code(cfg["ho_urls"], args.code, cfg, CONTROLLER_VERSION,
                                            socket.gethostname(), machine_fingerprint())
        print(f"Enrolled as device {cfg['device_id']}")
    elif require_code and not cfg.get("device_id"):
        print("Not enrolled yet: enroll with --code, or sign in to the Stock Client on this PC.")
    save_config(cfg)
    exe = _install_exe()
    _register_service(exe)
    print(f"{SERVICE_DISPLAY_NAME} {CONTROLLER_VERSION} installed and started.")


def cmd_enroll(args):
    if not _is_admin():
        raise SystemExit("Run this from an elevated (Administrator) prompt.")
    secure_state_dirs()
    cfg = load_config()
    urls = normalize_urls(([args.ho] if args.ho else []) + list(cfg.get("ho_urls") or []))
    if not urls:
        raise SystemExit("--ho is required")
    cfg["ho_urls"] = urls
    cfg["device_id"] = enroll_with_code(urls, args.code, cfg, CONTROLLER_VERSION,
                                        socket.gethostname(), machine_fingerprint())
    save_config(cfg)
    if app_mod.service_state(SERVICE_NAME) == "running":
        run(["sc", "stop", SERVICE_NAME])
        time.sleep(5)
        run(["sc", "start", SERVICE_NAME])
    print(f"Enrolled as device {cfg['device_id']}")


def cmd_uninstall(_args):
    run(["sc", "stop", SERVICE_NAME])
    time.sleep(3)
    run(["sc", "delete", SERVICE_NAME])
    print("Service removed (state in ProgramData\\Nexora\\DeviceController is kept).")


def cmd_status(_args):
    c = Controller()
    print(json.dumps(c.snapshot(), indent=2, default=str))
    print("enrolled device:", c.cfg.get("device_id") or "-")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        if not _HAVE_SERVICE:
            raise SystemExit("pywin32 is required to run as a service")
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(DeviceControllerService)
        servicemanager.StartServiceCtrlDispatcher()
        return
    parser = argparse.ArgumentParser(prog=EXE_NAME)
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("setup")
    p.add_argument("--ho", default="")
    p.add_argument("--code", default="")
    p = sub.add_parser("install-service")
    p.add_argument("--ho", default="")
    p = sub.add_parser("enroll")
    p.add_argument("--code", required=True)
    p.add_argument("--ho", default="")
    sub.add_parser("uninstall")
    sub.add_parser("status")
    sub.add_parser("console")
    args = parser.parse_args(argv)
    if args.cmd == "setup":
        cmd_setup(args, require_code=True)
    elif args.cmd == "install-service":
        cmd_setup(args)
    elif args.cmd == "enroll":
        cmd_enroll(args)
    elif args.cmd == "uninstall":
        cmd_uninstall(args)
    elif args.cmd == "status":
        cmd_status(args)
    elif args.cmd == "console":
        Controller().run()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
