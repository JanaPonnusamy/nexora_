"""This PC's spec, read once when the kit starts. It is shown to the operator
and sent to HO's /api/setup/v1/plan, which decides what may be installed here."""
from __future__ import annotations

import ctypes
import json
import os
import platform
import socket
import subprocess
import sys

from store_agent_setup.device_controller import CONFIG_FILE, SERVICE_NAME, STATUS_FILE

CREATE_NO_WINDOW = 0x08000000

SERVICES = {
    "controller": SERVICE_NAME,
    "store_agent": "NexoraStoreAgent",
    "ho_backend": "UniNexHO",
}


def detect() -> dict:
    drives = fixed_drives()
    return {
        "machine_name": socket.gethostname(),
        "os": os_name(),
        "is_win7": is_win7(),
        "arch": arch(),
        "ram_mb": ram_mb(),
        "cpu_count": os.cpu_count() or 0,
        "odbc_drivers": odbc_drivers(),
        "sql_instances": sql_instances(),
        "drives": drives,
        "services": {key: service_state(name) for key, name in SERVICES.items()},
        "controller": controller_state(),
        "is_admin": is_admin(),
        "agent_dir": default_agent_dir(drives),
    }


def os_name() -> str:
    return f"Windows {platform.release()} ({platform.version()})"


def is_win7() -> bool:
    try:
        return tuple(sys.getwindowsversion()[:2]) == (6, 1)
    except AttributeError:
        return False


def arch() -> str:
    # A 32-bit process on 64-bit Windows sees x86 in PROCESSOR_ARCHITECTURE.
    return (os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE")
            or platform.machine() or "")


def ram_mb() -> int:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    try:
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(stat)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return int(stat.ullTotalPhys // (1024 * 1024))
    except (AttributeError, OSError):
        pass
    return 0


def _reg_values(path, view) -> dict:
    try:
        import winreg

        out = {}
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ | view) as key:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                except OSError:
                    break
                out[name] = value
                i += 1
        return out
    except (ImportError, OSError):
        return {}


def odbc_drivers() -> list:
    """64-bit ODBC drivers (the Nexora apps are 64-bit)."""
    try:
        import winreg
    except ImportError:
        return []
    values = _reg_values(r"SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers", winreg.KEY_WOW64_64KEY)
    return sorted(name for name, state in values.items() if str(state).lower() == "installed")


def sql_instances() -> list:
    """Local SQL Server instances as connection names (HOST or HOST\\INSTANCE)."""
    try:
        import winreg
    except ImportError:
        return []
    host = socket.gethostname().upper()
    names = set()
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        names.update(_reg_values(r"SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL", view))
    return sorted(host if n.upper() == "MSSQLSERVER" else f"{host}\\{n}" for n in names)


def fixed_drives() -> list:
    out = []
    try:
        k32 = ctypes.windll.kernel32
        mask = k32.GetLogicalDrives()
    except (AttributeError, OSError):
        return out
    for i in range(26):
        if not mask & (1 << i):
            continue
        root = f"{chr(65 + i)}:\\"
        if k32.GetDriveTypeW(root) != 3:  # DRIVE_FIXED
            continue
        free, total = ctypes.c_ulonglong(), ctypes.c_ulonglong()
        if k32.GetDiskFreeSpaceExW(root, ctypes.byref(free), ctypes.byref(total), None):
            out.append({"drive": root[:2], "free_gb": round(free.value / 2 ** 30, 1),
                        "total_gb": round(total.value / 2 ** 30, 1)})
    return out


def service_state(name) -> str:
    """running / stopped / ... / not-installed (from `sc query`)."""
    try:
        r = subprocess.run(["sc", "query", name], capture_output=True, text=True, timeout=15,
                           creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    out = r.stdout or ""
    if r.returncode == 1060 or "1060" in out:
        return "not-installed"
    for line in out.splitlines():
        if "STATE" in line and ":" in line:
            return line.split()[-1].lower()
    return "unknown"


def controller_state() -> dict:
    """The installed controller's enrollment (its private config is readable by
    Administrators, which the kit runs as) and version."""
    out = {}
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) or {}
        out["device_id"] = cfg.get("device_id")
        out["ho_urls"] = list(cfg.get("ho_urls") or [])
    except (OSError, ValueError):
        pass
    try:
        out["version"] = (json.loads(STATUS_FILE.read_text(encoding="utf-8")) or {}).get("controller_version")
    except (OSError, ValueError):
        pass
    return out


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def default_agent_dir(drives) -> str:
    """Where the old wizard put the agent: D:\\ when the PC has a fixed D: drive."""
    if any(d.get("drive", "").upper() == "D:" for d in drives or []):
        return r"D:\NexoraStoreAgent"
    return r"C:\NexoraStoreAgent"


def summary_lines(spec) -> list:
    """Human-readable lines for the first page."""
    svc = spec.get("services") or {}
    lines = [
        f"PC name:      {spec.get('machine_name')}",
        f"Windows:      {spec.get('os')}{'  (Windows 7)' if spec.get('is_win7') else ''}",
        f"CPU / RAM:    {spec.get('arch')}, {spec.get('cpu_count')} cores, {spec.get('ram_mb')} MB",
        "Drives:       " + (", ".join(f"{d['drive']} {d['free_gb']} GB free" for d in spec.get("drives") or []) or "-"),
        "SQL Server:   " + (", ".join(spec.get("sql_instances") or []) or "none found"),
        "ODBC drivers: " + (", ".join(d for d in spec.get("odbc_drivers") or [] if "SQL" in d.upper()) or "no SQL Server driver"),
    ]
    installed = [f"{key} ({state})" for key, state in svc.items() if state not in ("not-installed", "unknown")]
    lines.append("Nexora apps:  " + (", ".join(installed) or "none installed"))
    ctl = spec.get("controller") or {}
    if ctl.get("device_id"):
        lines.append(f"Controller:   enrolled as {ctl['device_id']} with {', '.join(ctl.get('ho_urls') or [])}")
    return lines
