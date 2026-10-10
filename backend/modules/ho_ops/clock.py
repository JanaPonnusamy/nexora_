"""HO clock discipline -- a base rule of every HO node.

Some HO boxes (notably the one behind the public NAT) have drifted hours off real
time, which silently breaks everything that depends on a correct clock: the NMV
agent's HMAC request signatures (verified against the receiving node's clock with
a +/-300s window), JWT expiry, and every ``SYSUTCDATETIME()`` timestamp written
by the SQL Server that box also hosts.

So each HO node keeps its own clock honest: it reads the real time from the
internet (NTP, HTTP ``Date`` fallback) and, if the local clock is off by more
than a threshold, sets the system clock to match. This runs at backend startup
and on a periodic guardian thread (so a node self-heals without a human), and is
also invoked right before a sync (the user's "read internet time and update HO
before sync" rule).

Best-effort and non-fatal: if there is no reachable time source, or the process
lacks the privilege to set the clock, it logs and moves on -- a sync must never
fail because the clock could not be checked. Setting the clock needs
SeSystemtimePrivilege, which the SYSTEM account the HO service runs under has.
"""
from __future__ import annotations

import logging
import os
import socket
import struct
import sys
import threading
import time

logger = logging.getLogger("nexora.ho_ops.clock")

# Public NTP sources, tried in order.
_NTP_HOSTS = tuple(
    h.strip() for h in os.getenv(
        "NEXORA_HO_NTP_HOSTS",
        "time.windows.com,time.google.com,pool.ntp.org,time.cloudflare.com",
    ).split(",") if h.strip()
)
# Correct the clock only when it is off by at least this much (avoids thrashing
# on sub-second network jitter; the real problem is hours, not seconds).
_MAX_SKEW = int(os.getenv("NEXORA_HO_CLOCK_MAX_SKEW", "30"))
# Guardian cadence.
_INTERVAL = int(os.getenv("NEXORA_HO_CLOCK_INTERVAL", "1800"))
# Master off switch.
_ENABLED = os.getenv("NEXORA_HO_CLOCK_SYNC", "1").strip().lower() not in ("0", "false", "no")

_NTP_EPOCH = 2208988800  # seconds between 1900-01-01 and 1970-01-01
_guardian_started = False
_guardian_lock = threading.Lock()


# ---- read real time from the internet -------------------------------------

def _ntp_time(host, timeout=3.0):
    """UTC epoch seconds from an NTP server, or None."""
    pkt = b"\x1b" + 47 * b"\0"
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(pkt, (host, 123))
        data, _ = s.recvfrom(48)
    except OSError:
        return None
    finally:
        s.close()
    if len(data) < 48:
        return None
    transmit = struct.unpack("!12I", data)[10]
    if not transmit:
        return None
    return float(transmit - _NTP_EPOCH)


def _http_time(timeout=4.0):
    """UTC epoch seconds from an HTTPS ``Date`` header, or None (NTP fallback)."""
    import email.utils
    import urllib.request

    for url in ("https://www.cloudflare.com", "https://www.google.com"):
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                date = resp.headers.get("Date")
            if date:
                parsed = email.utils.parsedate_tz(date)
                if parsed:
                    return float(email.utils.mktime_tz(parsed))
        except Exception:
            continue
    return None


def internet_utc():
    """Real UTC epoch seconds from the first reachable source, or None."""
    for host in _NTP_HOSTS:
        t = _ntp_time(host)
        if t:
            return t, f"ntp:{host}"
    t = _http_time()
    if t:
        return t, "http:date-header"
    return None, None


# ---- set the local system clock (Windows) ---------------------------------

def _enable_privilege(name="SeSystemtimePrivilege"):
    """Enable a privilege in this process token. Needed because SetSystemTime
    requires SeSystemtimePrivilege ENABLED -- the SYSTEM account holds it but it
    can be present-but-disabled. Raises PermissionError if the account lacks it.

    argtypes/restype are set explicitly: without them ctypes truncates 64-bit
    HANDLEs to int and the call fails with 'invalid handle'."""
    import ctypes
    from ctypes import wintypes

    TOKEN_ADJUST_PRIVILEGES, TOKEN_QUERY = 0x0020, 0x0008
    SE_PRIVILEGE_ENABLED, ERROR_NOT_ALL_ASSIGNED = 0x00000002, 1300

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

    class LUID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]

    class TOKEN_PRIVILEGES(ctypes.Structure):
        _fields_ = [("PrivilegeCount", wintypes.DWORD),
                    ("Privileges", LUID_AND_ATTRIBUTES * 1)]

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                          ctypes.POINTER(wintypes.HANDLE)]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.LookupPrivilegeValueW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR,
                                               ctypes.POINTER(LUID)]
    advapi32.LookupPrivilegeValueW.restype = wintypes.BOOL
    advapi32.AdjustTokenPrivileges.argtypes = [
        wintypes.HANDLE, wintypes.BOOL, ctypes.POINTER(TOKEN_PRIVILEGES),
        wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    advapi32.AdjustTokenPrivileges.restype = wintypes.BOOL

    htok = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(),
                                     TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
                                     ctypes.byref(htok)):
        raise ctypes.WinError(ctypes.get_last_error())
    luid = LUID()
    if not advapi32.LookupPrivilegeValueW(None, name, ctypes.byref(luid)):
        raise ctypes.WinError(ctypes.get_last_error())
    tp = TOKEN_PRIVILEGES(1, (LUID_AND_ATTRIBUTES * 1)(
        LUID_AND_ATTRIBUTES(luid, SE_PRIVILEGE_ENABLED)))
    ctypes.set_last_error(0)
    advapi32.AdjustTokenPrivileges(htok, False, ctypes.byref(tp), 0, None, None)
    if ctypes.get_last_error() == ERROR_NOT_ALL_ASSIGNED:
        raise PermissionError("SeSystemtimePrivilege is not held by this account")


def _set_system_time_utc(epoch):
    """Set the Windows system clock (UTC). Raises on failure."""
    import ctypes
    from ctypes import wintypes
    import datetime

    _enable_privilege()

    class SYSTEMTIME(ctypes.Structure):
        _fields_ = [
            ("wYear", wintypes.WORD), ("wMonth", wintypes.WORD),
            ("wDayOfWeek", wintypes.WORD), ("wDay", wintypes.WORD),
            ("wHour", wintypes.WORD), ("wMinute", wintypes.WORD),
            ("wSecond", wintypes.WORD), ("wMilliseconds", wintypes.WORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.SetSystemTime.argtypes = [ctypes.POINTER(SYSTEMTIME)]
    kernel32.SetSystemTime.restype = wintypes.BOOL

    dt = datetime.datetime.utcfromtimestamp(epoch)
    st = SYSTEMTIME(dt.year, dt.month, dt.isoweekday() % 7, dt.day,
                    dt.hour, dt.minute, dt.second, dt.microsecond // 1000)
    if not kernel32.SetSystemTime(ctypes.byref(st)):
        raise ctypes.WinError(ctypes.get_last_error())


# ---- the base rule --------------------------------------------------------

def ensure_ho_clock(max_skew_seconds=None, reason="startup"):
    """Check this node's clock against internet time and correct it if it is off
    by more than the threshold. Returns a result dict; never raises."""
    result = {"checked": False, "corrected": False, "reason": reason}
    if not _ENABLED:
        result["error"] = "disabled (NEXORA_HO_CLOCK_SYNC=0)"
        return result
    threshold = _MAX_SKEW if max_skew_seconds is None else max_skew_seconds
    try:
        net, source = internet_utc()
        if net is None:
            result["error"] = "no reachable time source"
            logger.warning("HO clock: no reachable internet time source (%s)", reason)
            return result
        local = time.time()
        skew = net - local
        result.update({"checked": True, "source": source,
                       "skew_seconds": round(skew, 1)})
        if abs(skew) <= threshold:
            logger.info("HO clock OK (skew %.1fs via %s, %s)", skew, source, reason)
            return result
        if sys.platform != "win32":
            result["error"] = f"skew {skew:.0f}s but clock-set is Windows-only"
            logger.warning("HO clock off by %.0fs but cannot set on %s", skew, sys.platform)
            return result
        try:
            _set_system_time_utc(net)
            result["corrected"] = True
            logger.warning("HO clock CORRECTED by %.0fs (was %.0fs off real time via %s, %s)",
                           skew, skew, source, reason)
        except Exception as ex:  # privilege or API error
            result["error"] = f"set failed: {ex}"
            logger.error("HO clock off by %.0fs but could not set it: %s "
                         "(service needs SeSystemtimePrivilege / run as SYSTEM)", skew, ex)
    except Exception as ex:  # never let the clock check break the caller
        result["error"] = str(ex)
        logger.exception("HO clock check failed (%s)", reason)
    return result


def _guardian_loop(interval):
    while True:
        try:
            ensure_ho_clock(reason="guardian")
        except Exception:
            logger.exception("HO clock guardian iteration failed")
        time.sleep(interval)


def start_clock_guardian(interval_seconds=None):
    """Start the background clock guardian once per process. The guardian's first
    loop iteration runs immediately (so a freshly (re)started node self-heals
    right away) -- in the daemon thread, so a slow/absent internet never blocks
    backend startup."""
    global _guardian_started
    if not _ENABLED:
        return
    with _guardian_lock:
        if _guardian_started:
            return
        _guardian_started = True
    interval = _INTERVAL if interval_seconds is None else interval_seconds
    t = threading.Thread(target=_guardian_loop, args=(interval,),
                         name="ho-clock-guardian", daemon=True)
    t.start()
    logger.info("HO clock guardian started (immediate check + every %ss)", interval)
