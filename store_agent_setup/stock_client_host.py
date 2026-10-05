"""Session + process control for the Axythic Supplier Stock GUI.

The Stock Client is a per-user Electron app, not a Windows service. The watchdog
runs as SYSTEM, so it must do two things a service normally never does:

  * Find and stop ONLY the GUI's processes, matched by their exact install path
    (never a broad taskkill by image name -- another Electron app, or a second
    copy installed elsewhere, must not be caught).
  * Launch the GUI back into the interactive desktop of whoever is logged on,
    by duplicating that session's user token (WTSQueryUserToken) and calling
    CreateProcessAsUser -- a SYSTEM service cannot just ShellExecute a window
    onto a user's desktop (session 0 isolation).

All Win32 access goes through pywin32, already a watchdog dependency. Every
helper degrades to a safe default (empty list / None / False) when a call fails,
so a transient Win32 error can never crash the reconcile loop.
"""
import os
from pathlib import Path

try:
    import win32api
    import win32con
    import win32event
    import win32process
    import win32profile
    import win32security
    import win32ts
    _HAVE_WIN32 = True
except ImportError:  # pragma: no cover - only importable on Windows w/ pywin32
    _HAVE_WIN32 = False


def active_session_id():
    """The console session currently showing a logged-on user, or None.

    Prefer an explicitly ACTIVE WTS session over the raw console session id:
    after a fast-user-switch or RDP connect the console id can point at a
    disconnected session with no desktop to launch into."""
    if not _HAVE_WIN32:
        return None
    try:
        sessions = win32ts.WTSEnumerateSessions(win32ts.WTS_CURRENT_SERVER_HANDLE)
        for s in sessions:
            if s["State"] == win32ts.WTSActive:
                return s["SessionId"]
    except Exception:
        pass
    try:
        sid = win32ts.WTSGetActiveConsoleSessionId()
        # 0xFFFFFFFF means "no session currently attached to the console".
        return None if sid == 0xFFFFFFFF else sid
    except Exception:
        return None


def active_session_username():
    """DOMAIN\\user of the active session, for logging + resolving their profile."""
    if not _HAVE_WIN32:
        return None
    sid = active_session_id()
    if sid is None:
        return None
    try:
        user = win32ts.WTSQuerySessionInformation(
            win32ts.WTS_CURRENT_SERVER_HANDLE, sid, win32ts.WTSUserName
        )
        domain = win32ts.WTSQuerySessionInformation(
            win32ts.WTS_CURRENT_SERVER_HANDLE, sid, win32ts.WTSDomainName
        )
        if not user:
            return None
        return f"{domain}\\{user}" if domain else user
    except Exception:
        return None


def _user_token(session_id):
    """A primary token for the active user, usable with CreateProcessAsUser."""
    return win32ts.WTSQueryUserToken(session_id)


def user_localappdata(session_id=None):
    """Resolve the logged-on user's %LOCALAPPDATA% from SYSTEM.

    The Electron app installs per-user under
    %LOCALAPPDATA%\\Programs\\axythic-supplier-stock, but SYSTEM's own
    environment points at its profile, not the user's -- so we expand the
    environment block of the user's token instead of reading os.environ."""
    if not _HAVE_WIN32:
        return None
    if session_id is None:
        session_id = active_session_id()
    if session_id is None:
        return None
    token = None
    try:
        token = _user_token(session_id)
        env = win32profile.CreateEnvironmentBlock(token, False)
        # CreateEnvironmentBlock returns a dict-like {NAME: VALUE}.
        local = env.get("LOCALAPPDATA") if hasattr(env, "get") else None
        if local:
            return Path(local)
        profile = win32profile.GetUserProfileDirectory(token)
        if profile:
            return Path(profile) / "AppData" / "Local"
    except Exception:
        return None
    finally:
        if token:
            try:
                win32api.CloseHandle(token)
            except Exception:
                pass
    return None


def processes_by_path(exe_path):
    """PIDs whose executable IS exe_path (case-insensitive full-path match).

    Uses WMI (Win32_Process.ExecutablePath) so we match the real binary, not
    just the image name -- the whole point of path-scoped control."""
    target = str(exe_path).lower()
    name = Path(exe_path).name
    pids = []
    try:
        import win32com.client

        wmi = win32com.client.GetObject("winmgmts:")
        query = (
            "SELECT ProcessId, ExecutablePath FROM Win32_Process "
            f"WHERE Name = '{name}'"
        )
        for proc in wmi.ExecQuery(query):
            path = (proc.ExecutablePath or "").lower()
            if path == target:
                pids.append(int(proc.ProcessId))
    except Exception:
        pass
    return pids


def is_running(exe_path):
    return bool(processes_by_path(exe_path))


def stop(exe_path, log=lambda m: None, grace_seconds=20):
    """Close the GUI at exe_path: ask windows to close first, then terminate
    only the matched PIDs if they outlast the grace period. Returns True once
    nothing at that path is left running."""
    pids = processes_by_path(exe_path)
    if not pids:
        return True
    if not _HAVE_WIN32:
        return False

    # Phase 1: polite WM_CLOSE to each top-level window owned by those PIDs, so
    # Electron runs its normal quit (flushes state) instead of being killed.
    try:
        import win32gui

        pidset = set(pids)

        def _ask_close(hwnd, _):
            try:
                _, wpid = win32process.GetWindowThreadProcessId(hwnd)
                if wpid in pidset and win32gui.IsWindowVisible(hwnd):
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
            return True

        win32gui.EnumWindows(_ask_close, None)
    except Exception:
        pass

    # Wait out the grace period for the processes to exit on their own.
    import time

    deadline = time.time() + grace_seconds
    while time.time() < deadline:
        if not processes_by_path(exe_path):
            log(f"[stop] GUI exited gracefully: {exe_path}")
            return True
        time.sleep(1)

    # Phase 2: forcibly terminate ONLY the still-running matched PIDs.
    remaining = processes_by_path(exe_path)
    for pid in remaining:
        try:
            h = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
            win32process.TerminateProcess(h, 1)
            win32api.CloseHandle(h)
            log(f"[stop] terminated pid {pid} ({exe_path})")
        except Exception as ex:
            log(f"[stop] could not terminate pid {pid}: {ex}")

    time.sleep(2)
    return not processes_by_path(exe_path)


def launch_in_user_session(command, args="", log=lambda m: None, show=True):
    """Start `command` on the logged-on user's interactive desktop.

    Returns True if the process was created. Used both to relaunch the GUI after
    an update and to run the NSIS installer in the user's own context (a per-user
    install must NOT run as SYSTEM, or it lands in the wrong profile)."""
    if not _HAVE_WIN32:
        log("[launch] pywin32 unavailable; cannot launch in user session")
        return False
    session_id = active_session_id()
    if session_id is None:
        log("[launch] no active user session; GUI will start when a user logs in")
        return False

    token = None
    dup = None
    env = None
    try:
        token = _user_token(session_id)
        dup = win32security.DuplicateTokenEx(
            token,
            win32security.SecurityImpersonation,
            win32con.MAXIMUM_ALLOWED,
            win32security.TokenPrimary,
            None,
        )
        env = win32profile.CreateEnvironmentBlock(dup, False)

        startup = win32process.STARTUPINFO()
        startup.dwFlags = win32con.STARTF_USESHOWWINDOW
        startup.wShowWindow = win32con.SW_SHOW if show else win32con.SW_HIDE
        startup.lpDesktop = "winsta0\\default"  # the interactive desktop

        cmdline = f'"{command}" {args}'.strip()
        creation = (
            win32con.CREATE_UNICODE_ENVIRONMENT | win32con.CREATE_NEW_CONSOLE
        )
        proc_info = win32process.CreateProcessAsUser(
            dup, None, cmdline, None, None, False,
            creation, env, str(Path(command).parent), startup,
        )
        handles = [h for h in proc_info if hasattr(h, "Close") or hasattr(h, "close")]
        log(f"[launch] started in session {session_id}: {cmdline}")
        return proc_info, handles
    except Exception as ex:
        log(f"[launch] CreateProcessAsUser failed: {ex}")
        return False
    finally:
        for h in (dup, token):
            if h:
                try:
                    win32api.CloseHandle(h)
                except Exception:
                    pass


def run_in_user_session_and_wait(command, args="", log=lambda m: None,
                                 timeout_seconds=600):
    """Launch in the user session and block until it exits (or times out).

    Used for the silent NSIS installer: we must know it finished before we
    health-check the result. Returns the process exit code, or None on failure
    / timeout."""
    result = launch_in_user_session(command, args=args, log=log, show=False)
    if not result:
        return None
    proc_info, _ = result
    h_process = proc_info[0]
    try:
        win32event.WaitForSingleObject(h_process, int(timeout_seconds * 1000))
        code = win32process.GetExitCodeProcess(h_process)
        return code
    except Exception as ex:
        log(f"[run] wait failed: {ex}")
        return None
    finally:
        for h in proc_info:
            try:
                win32api.CloseHandle(h)
            except Exception:
                pass
