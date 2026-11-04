"""Logging, config persistence and small Windows helpers for the controller."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from . import (
    CONFIG_FILE,
    FINGERPRINT_FILE,
    INBOX_DIR,
    LOG_FILE,
    PRIVATE_DIR,
    PUBLIC_KEY_FILE,
    STATE_DIR,
)

LOG_MAX_BYTES = 2 * 1024 * 1024
_log_lock = threading.Lock()

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def log(msg):
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    with _log_lock:
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            if LOG_FILE.is_file() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
                backup = LOG_FILE.with_suffix(".log.1")
                if backup.exists():
                    backup.unlink()
                LOG_FILE.rename(backup)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
    try:
        print(line, flush=True)
    except Exception:
        pass


def run(cmd, timeout=120, check=False):
    """Run a console command hidden; returns (code, combined output)."""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW, errors="replace",
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        if check and proc.returncode != 0:
            raise RuntimeError(f"{subprocess.list2cmdline(cmd)} failed ({proc.returncode}): {out}")
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        if check:
            raise
        return -1, "timeout"


def spawn_detached(cmd):
    subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
        close_fds=True,
    )


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def os_version():
    try:
        import platform

        return f"{platform.system()} {platform.release()} ({platform.version()})"
    except Exception:
        return sys.platform


def bundled_path(name):
    """Path of a file bundled into the exe. The onefile _MEI dir lives in TEMP,
    which Storage Sense / the temp janitor purge while the service runs, so a
    copy is kept in PRIVATE_DIR (SYSTEM + Administrators only) and used once
    the extracted file is gone."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return Path(__file__).resolve().parents[2] / "backend" / "config" / name
    extracted = Path(base) / name
    durable = PRIVATE_DIR / "bundled" / name
    try:
        if extracted.is_file():
            data = extracted.read_bytes()
            if not (durable.is_file() and durable.read_bytes() == data):
                durable.parent.mkdir(parents=True, exist_ok=True)
                durable.write_bytes(data)
            return extracted
    except OSError:
        pass
    return durable if durable.is_file() else extracted


def machine_fingerprint():
    """Stable per-machine id (Windows MachineGuid), so re-enrolling the same PC
    updates its existing device row instead of creating a new one."""
    guid = None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            guid = winreg.QueryValueEx(key, "MachineGuid")[0]
    except Exception:
        pass
    return "dc:" + (guid or socket.gethostname()).lower()


# ---- state dir + ACLs ------------------------------------------------------

def secure_state_dirs():
    """private\\ -> SYSTEM + Administrators only (holds the device private key);
    inbox\\ -> Users may write (the Stock Client drops its enrollment there);
    the rest readable by Users (public key, fingerprint, status)."""
    for d in (STATE_DIR, PRIVATE_DIR, INBOX_DIR):
        d.mkdir(parents=True, exist_ok=True)
    run(["icacls", str(PRIVATE_DIR), "/inheritance:r",
         "/grant:r", "*S-1-5-18:(OI)(CI)F", "/grant:r", "*S-1-5-32-544:(OI)(CI)F"])
    run(["icacls", str(INBOX_DIR), "/grant", "*S-1-5-32-545:(OI)(CI)M"])


# ---- controller config -----------------------------------------------------

_cfg_lock = threading.Lock()


def load_config():
    """{ ho_urls: [..], device_id, device_private_key_pem, device_public_key_pem,
         retire_legacy: bool }  -- keypair self-generated on first run."""
    with _cfg_lock:
        cfg = {}
        try:
            if CONFIG_FILE.is_file():
                cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError):
            cfg = {}
        changed = False
        if not cfg.get("device_private_key_pem") or not cfg.get("device_public_key_pem"):
            from modules.device_identity import crypto

            cfg["device_private_key_pem"], cfg["device_public_key_pem"] = crypto.generate_keypair()
            changed = True
        cfg.setdefault("ho_urls", [])
        cfg.setdefault("retire_legacy", True)
        if not cfg.get("installation_id"):
            cfg["installation_id"] = "dc-" + uuid.uuid4().hex[:16]
            changed = True
        if changed:
            _write_config(cfg)
        _publish_public_files(cfg)
        return cfg


def save_config(cfg):
    with _cfg_lock:
        _write_config(cfg)


def _write_config(cfg):
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(CONFIG_FILE))


def _publish_public_files(cfg):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if not PUBLIC_KEY_FILE.is_file() or PUBLIC_KEY_FILE.read_text(encoding="utf-8") != cfg["device_public_key_pem"]:
            PUBLIC_KEY_FILE.write_text(cfg["device_public_key_pem"], encoding="utf-8")
        fp = machine_fingerprint()
        if not FINGERPRINT_FILE.is_file() or FINGERPRINT_FILE.read_text(encoding="utf-8").strip() != fp:
            FINGERPRINT_FILE.write_text(fp, encoding="utf-8")
    except OSError as ex:
        log(f"[config] could not publish public files: {ex}")


def normalize_urls(urls):
    out = []
    for u in urls or []:
        for part in str(u).split(","):
            v = part.strip().rstrip("/")
            if v and (v.startswith("http://") or v.startswith("https://")) and v not in out:
                out.append(v)
    return out


def wait_until(pred, timeout, interval=1.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if pred():
                return True
        except Exception:
            pass
        time.sleep(interval)
    try:
        return bool(pred())
    except Exception:
        return False
