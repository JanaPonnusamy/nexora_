from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    _HAVE_SELENIUM = True
except Exception:  # pragma: no cover - optional runtime dependency
    webdriver = None
    By = Keys = WebDriverWait = EC = None
    _HAVE_SELENIUM = False


REPO_ROOT = Path(__file__).resolve().parents[3]
STORAGE_DIR = REPO_ROOT / "backend" / "storage" / "whatsapp"
FILES_DIR = STORAGE_DIR / "files"
DEBUG_DIR = STORAGE_DIR / "debug"
PROFILES_DIR = STORAGE_DIR / "profiles"
SETTINGS_FILE = STORAGE_DIR / "settings.json"
PROFILES_FILE = STORAGE_DIR / "profiles.json"
TARGETS_FILE = STORAGE_DIR / "targets.json"
INBOX_FILE = STORAGE_DIR / "inbox.json"

DEFAULT_SETTINGS = {
    "browser_command": "",
    "delivery_mode": "manual_browser",
    "launch_wait_seconds": 15,
    "headless": True,
    # When a background (headless) send fails, do NOT pop a visible browser
    "manual_fallback": False,
}


# Persistent, reusable WhatsApp browser sessions keyed by profile_id.
# Selenium drivers are not thread-safe and FastAPI runs sync endpoints in a
# threadpool, so every interaction with a driver is serialized under this lock.
_DRIVER_LOCK = threading.RLock()
_DRIVERS: dict[str, Any] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    _ensure_dirs()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _detect_browser_command() -> str:
    env_candidate = os.getenv("NEXORA_WHATSAPP_BROWSER", "").strip()
    if env_candidate:
        return env_candidate

    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    return ""


def _load_settings() -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    settings.update(_read_json(SETTINGS_FILE, {}))
    if not settings.get("browser_command"):
        detected = _detect_browser_command()
        if detected:
            settings["browser_command"] = detected
    if settings.get("delivery_mode") not in {"manual_browser", "selenium"}:
        settings["delivery_mode"] = "manual_browser"
    settings["headless"] = bool(settings.get("headless", True))
    settings["manual_fallback"] = bool(settings.get("manual_fallback", False))
    return settings


def _save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULT_SETTINGS)
    merged.update(settings)
    if merged.get("delivery_mode") not in {"manual_browser", "selenium"}:
        merged["delivery_mode"] = "manual_browser"
    merged["browser_command"] = str(merged.get("browser_command", "")).strip()
    merged["launch_wait_seconds"] = int(merged.get("launch_wait_seconds", 15) or 15)
    merged["headless"] = bool(merged.get("headless", True))
    merged["manual_fallback"] = bool(merged.get("manual_fallback", False))
    _write_json(SETTINGS_FILE, merged)
    return merged


def _load_profiles() -> list[dict[str, Any]]:
    rows = _read_json(PROFILES_FILE, [])
    if not isinstance(rows, list):
        return []
    profiles: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        profile_id = str(row.get("profile_id", "")).strip()
        if not profile_id:
            continue
        session_dir = PROFILES_DIR / profile_id
        profile = {
            "profile_id": profile_id,
            "profile_name": str(row.get("profile_name", "")).strip() or f"Profile {profile_id[:8]}",
            "owner_type": str(row.get("owner_type", "store")).strip() or "store",
            "owner_name": str(row.get("owner_name", "")).strip(),
            "tenant_id": str(row.get("tenant_id", "")).strip(),
            "store_id": str(row.get("store_id", "")).strip(),
            "default_phone": str(row.get("default_phone", "")).strip(),
            "notes": str(row.get("notes", "")).strip(),
            "is_default": bool(row.get("is_default", False)),
            "session_dir": str(session_dir),
            "created_at": str(row.get("created_at", "")).strip() or _now_iso(),
            "updated_at": str(row.get("updated_at", "")).strip() or _now_iso(),
            "last_used_at": str(row.get("last_used_at", "")).strip(),
        }
        profiles.append(profile)
    return sorted(profiles, key=lambda item: (not item["is_default"], item["profile_name"].lower()))


def _save_profiles(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serializable: list[dict[str, Any]] = []
    for profile in profiles:
        serializable.append(
            {
                "profile_id": profile["profile_id"],
                "profile_name": profile["profile_name"],
                "owner_type": profile["owner_type"],
                "owner_name": profile["owner_name"],
                "tenant_id": profile["tenant_id"],
                "store_id": profile["store_id"],
                "default_phone": profile["default_phone"],
                "notes": profile["notes"],
                "is_default": profile["is_default"],
                "created_at": profile["created_at"],
                "updated_at": profile["updated_at"],
                "last_used_at": profile["last_used_at"],
            }
        )
    _write_json(PROFILES_FILE, serializable)
    return _load_profiles()


def _sanitize_phone(phone: str) -> str:
    return re.sub(r"[^\d]", "", phone or "")


def _browser_ready(browser_command: str) -> bool:
    return bool(browser_command and Path(browser_command).is_file())


def _capabilities(settings: dict[str, Any], profiles: list[dict[str, Any]]) -> dict[str, Any]:
    browser_command = settings.get("browser_command", "")
    return {
        "browser_detected": _browser_ready(browser_command),
        "browser_command": browser_command,
        "selenium_available": _HAVE_SELENIUM,
        "delivery_mode": settings.get("delivery_mode", "manual_browser"),
        "headless": bool(settings.get("headless", True)),
        "manual_fallback": bool(settings.get("manual_fallback", False)),
        "can_launch_qr": _browser_ready(browser_command),
        "can_auto_send_attachment": bool(_HAVE_SELENIUM and _browser_ready(browser_command)),
        "can_read_messages": bool(_HAVE_SELENIUM and _browser_ready(browser_command)),
        "profile_count": len(profiles),
        "default_profile_id": next((profile["profile_id"] for profile in profiles if profile["is_default"]), ""),
    }


def _resolve_profile(profile_id: str, profiles: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = profiles or _load_profiles()
    for row in rows:
        if row["profile_id"] == profile_id:
            return row
    raise ValueError("WhatsApp profile not found.")


def _load_targets() -> list[dict[str, Any]]:
    rows = _read_json(TARGETS_FILE, [])
    if not isinstance(rows, list):
        return []
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        target_id = str(row.get("target_id", "")).strip()
        if not target_id:
            continue
        result.append(
            {
                "target_id": target_id,
                "profile_id": str(row.get("profile_id", "")).strip(),
                "target_kind": str(row.get("target_kind", "contact")).strip() or "contact",
                "target_name": str(row.get("target_name", "")).strip(),
                "target_ref": str(row.get("target_ref", "")).strip(),
                "can_send": bool(row.get("can_send", True)),
                "can_read": bool(row.get("can_read", False)),
                "is_active": bool(row.get("is_active", True)),
                "notes": str(row.get("notes", "")).strip(),
                "created_at": str(row.get("created_at", "")).strip() or _now_iso(),
                "updated_at": str(row.get("updated_at", "")).strip() or _now_iso(),
                "last_synced_at": str(row.get("last_synced_at", "")).strip(),
            }
        )
    return sorted(result, key=lambda item: (item["profile_id"], item["target_name"].lower(), item["target_kind"]))


def _save_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    _write_json(TARGETS_FILE, targets)
    return _load_targets()


def _resolve_target(target_id: str, targets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = targets or _load_targets()
    for row in rows:
        if row["target_id"] == target_id:
            return row
    raise ValueError("WhatsApp target not found.")


def _load_inbox() -> list[dict[str, Any]]:
    rows = _read_json(INBOX_FILE, [])
    if not isinstance(rows, list):
        return []
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        message_id = str(row.get("message_id", "")).strip()
        if not message_id:
            continue
        result.append(
            {
                "message_id": message_id,
                "target_id": str(row.get("target_id", "")).strip(),
                "profile_id": str(row.get("profile_id", "")).strip(),
                "direction": str(row.get("direction", "incoming")).strip() or "incoming",
                "message_text": str(row.get("message_text", "")).strip(),
                "message_time": str(row.get("message_time", "")).strip() or _now_iso(),
                "source_label": str(row.get("source_label", "")).strip(),
                "captured_at": str(row.get("captured_at", "")).strip() or _now_iso(),
            }
        )
    return sorted(result, key=lambda item: item["message_time"], reverse=True)


def _save_inbox(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    _write_json(INBOX_FILE, messages)
    return _load_inbox()


def _append_inbox_messages(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current = _load_inbox()
    seen = {(item["target_id"], item["message_text"], item["message_time"], item["direction"]) for item in current}
    for item in items:
        key = (item["target_id"], item["message_text"], item["message_time"], item["direction"])
        if key in seen:
            continue
        seen.add(key)
        current.append(item)
    return _save_inbox(current)


def _whatsapp_url(phone: str, message: str) -> str:
    base = "https://web.whatsapp.com/"
    if phone:
        return f"{base}send?phone={quote(phone)}&text={quote(message or '')}"
    if message:
        return f"{base}?text={quote(message)}"
    return base


def _launch_browser(profile: dict[str, Any], settings: dict[str, Any], url: str) -> dict[str, Any]:
    browser_command = settings.get("browser_command", "")
    if not _browser_ready(browser_command):
        raise ValueError("WhatsApp browser is not configured. Set a valid browser path in WhatsApp settings.")

    session_dir = Path(profile["session_dir"])
    session_dir.mkdir(parents=True, exist_ok=True)
    command = [
        browser_command,
        f"--user-data-dir={session_dir}",
        "--new-window",
        url,
    ]
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {
        "status": "launched",
        "message": "WhatsApp Web opened with the selected profile.",
        "mode": settings.get("delivery_mode", "manual_browser"),
        "url": url,
    }


# The full headed login profile (extensions + GPU/component caches) crashes
# headless Chrome ("DevToolsActivePort file doesn't exist"). WhatsApp's login
# lives in IndexedDB / Local Storage, so we run headless against a clean mirror
# that carries only the session data — it starts headless and stays logged in.
_HEADLESS_KEEP_ROOT = ["Local State"]
_HEADLESS_KEEP_DEFAULT = [
    "Local Storage",
    "IndexedDB",
    "Session Storage",
    "Service Worker",
    "Preferences",
    "Secure Preferences",
    "shared_proto_db",
    "WebStorage",
    "blob_storage",
    "databases",
    "Network",
]


def _headless_dir(profile: dict[str, Any]) -> Path:
    return PROFILES_DIR / f"{profile['profile_id']}__headless"


def _copy_resilient(src: Path, dst: Path) -> None:
    """Recursive copy that skips individual locked/missing files instead of
    aborting the whole tree (the login profile may be open during a copy)."""
    try:
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            for child in src.iterdir():
                _copy_resilient(child, dst / child.name)
    except Exception:
        pass


def _sync_headless_profile(profile: dict[str, Any]) -> Path:
    """Build the lightweight, headless-capable mirror of the login profile."""
    src_root = Path(profile["session_dir"])
    dst_root = _headless_dir(profile)
    (dst_root / "Default").mkdir(parents=True, exist_ok=True)
    for name in _HEADLESS_KEEP_ROOT:
        _copy_resilient(src_root / name, dst_root / name)
    for name in _HEADLESS_KEEP_DEFAULT:
        _copy_resilient(src_root / "Default" / name, dst_root / "Default" / name)
    return dst_root


def _prepare_headless_dir(profile: dict[str, Any]) -> Path:
    """Return the headless mirror dir, adopting the login session on first use.
    After a fresh QR login the mirror is wiped (see launch_qr) so it re-adopts."""
    dst = _headless_dir(profile)
    if not (dst / "Default" / "IndexedDB").exists():
        _sync_headless_profile(profile)
    return dst


def _kill_profile_chrome(user_data_dir: str) -> None:
    """Best-effort kill of any Chrome still holding this user-data-dir.

    Only matches the exact (unique) mirror path, so it never touches the user's
    normal browser or the visible QR-login window (a different directory)."""
    if os.name != "nt" or not user_data_dir:
        return
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
        "Where-Object { $_.CommandLine -like '*" + str(user_data_dir) + "*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            timeout=20,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.6)
    except Exception:
        pass


def _build_driver(profile: dict[str, Any], settings: dict[str, Any]):
    if not _HAVE_SELENIUM:
        raise RuntimeError("Selenium is not installed in the backend runtime.")
    headless = bool(settings.get("headless", True))
    user_data_dir = profile["session_dir"]
    options = webdriver.ChromeOptions()
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-dev-shm-usage")
    if headless:
        # Run against the clean mirror so the background session never shows a
        # window and doesn't crash on the bloated headed profile.
        user_data_dir = str(_prepare_headless_dir(profile))
        # uvicorn --reload / a hard restart can orphan a headless Chrome that
        # keeps this folder locked; a new launch then exits immediately
        # ("Chrome instance exited"). Reap any leftover before launching.
        _kill_profile_chrome(user_data_dir)
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280,960")
        options.add_argument("--no-sandbox")
        options.add_argument("--remote-debugging-port=0")
        options.add_argument("--profile-directory=Default")
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    browser_command = settings.get("browser_command", "")
    if browser_command and Path(browser_command).is_file():
        options.binary_location = browser_command
    return webdriver.Chrome(options=options)


def _driver_alive(driver: Any) -> bool:
    if driver is None:
        return False
    try:
        _ = driver.current_url
        return True
    except Exception:
        return False


def _acquire_driver(profile: dict[str, Any], settings: dict[str, Any]):
    """Return a persistent, logged-in headless driver for this profile.

    The driver is created once and reused across sends so WhatsApp Web loads
    and authenticates a single time. Subsequent messages navigate inside the
    same background session — no new Chrome window, no fresh WhatsApp load.
    Callers must hold ``_DRIVER_LOCK``.
    """
    profile_id = profile["profile_id"]
    driver = _DRIVERS.get(profile_id)
    if _driver_alive(driver):
        return driver
    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass
        _DRIVERS.pop(profile_id, None)

    driver = _build_driver(profile, settings)
    _DRIVERS[profile_id] = driver
    # Warm the session up once so the WhatsApp Web SPA is loaded and the
    # persisted login (from the profile dir) is restored before we send.
    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    try:
        driver.get("https://web.whatsapp.com/")
        WebDriverWait(driver, wait_seconds).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(3)
    except Exception:
        pass
    return driver


def _shutdown_driver(profile_id: str) -> None:
    """Close and forget the background driver for a profile (releases its
    user-data-dir so a visible browser can reuse the same profile)."""
    with _DRIVER_LOCK:
        driver = _DRIVERS.pop(profile_id, None)
    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass


def shutdown_all_drivers() -> None:
    with _DRIVER_LOCK:
        drivers = list(_DRIVERS.values())
        _DRIVERS.clear()
    for driver in drivers:
        try:
            driver.quit()
        except Exception:
            pass


atexit.register(shutdown_all_drivers)


# --- Robust WhatsApp Web automation helpers -------------------------------
# WhatsApp Web changes its DOM often and headless is stricter about visibility,
# so every interaction tries several selectors and falls back to a JS click /
# Enter key. On failure we snapshot the page so the real cause is visible.

_SEARCH_BOX_LOCATORS = [
    (By.XPATH, "//input[@aria-label='Search or start a new chat']"),
    (By.XPATH, "//div[@aria-label='Chat list']//input[@role='textbox']"),
    (By.XPATH, "//div[@contenteditable='true'][@data-tab='3']"),
    (By.XPATH, "//div[@role='textbox'][@contenteditable='true'][@aria-label]"),
]
_COMPOSER_LOCATORS = [
    (By.XPATH, "//footer//div[@contenteditable='true'][@data-tab='10']"),
    (By.XPATH, "//div[@contenteditable='true'][starts-with(@aria-label,'Type a message')]"),
    (By.XPATH, "//footer//div[@contenteditable='true']"),
    (By.XPATH, "(//div[@contenteditable='true'])[last()]"),
]
_SEND_BUTTON_LOCATORS = [
    (By.XPATH, "//button[@aria-label='Send']"),
    (By.XPATH, "//span[@data-icon='send']"),
    (By.XPATH, "//span[@data-icon='wds-ic-send-filled']"),
]


def _capture_debug(driver, tag: str) -> str | None:
    """Save a screenshot + page source so a failed send is diagnosable."""
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        base = DEBUG_DIR / f"{stamp}_{re.sub(r'[^a-zA-Z0-9._-]+', '_', tag)}"
        try:
            driver.save_screenshot(str(base) + ".png")
        except Exception:
            pass
        try:
            (Path(str(base) + ".html")).write_text(driver.page_source or "", encoding="utf-8")
        except Exception:
            pass
        try:
            meta = {"url": driver.current_url, "title": driver.title, "logged_in": _is_logged_in(driver)}
            (Path(str(base) + ".json")).write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except Exception:
            pass
        return str(base)
    except Exception:
        return None


def _is_logged_in(driver) -> bool:
    """True when the chat UI is present; False on the QR / landing screen."""
    try:
        if driver.find_elements(By.XPATH, "//input[@aria-label='Search or start a new chat']"):
            return True
        if driver.find_elements(By.XPATH, "//div[@contenteditable='true'][@data-tab='3']"):
            return True
        if driver.find_elements(By.XPATH, "//div[@id='pane-side']"):
            return True
        # QR canvas / linked-device landing => not logged in
        if driver.find_elements(By.XPATH, "//canvas[@aria-label] | //div[@data-ref]"):
            return False
    except Exception:
        return False
    return False


def _first_element(driver, locators, timeout: int, clickable: bool = False):
    """Return the first element that matches any locator within the timeout."""
    end = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < end:
        for by, sel in locators:
            try:
                elements = driver.find_elements(by, sel)
                for el in elements:
                    try:
                        if el.is_displayed() and (not clickable or el.is_enabled()):
                            return el
                    except Exception:
                        continue
            except Exception as exc:  # pragma: no cover - defensive
                last_error = exc
        time.sleep(0.5)
    if last_error is not None:
        raise last_error
    raise TimeoutError(f"None of the selectors matched: {[sel for _, sel in locators]}")


def _safe_click(driver, element) -> None:
    """Click an element, scrolling it in view and falling back to a JS click."""
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    except Exception:
        pass
    try:
        element.click()
        return
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def _ensure_logged_in(driver, settings: dict[str, Any]) -> None:
    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    end = time.time() + wait_seconds
    while time.time() < end:
        if _is_logged_in(driver):
            return
        time.sleep(1)
    raise RuntimeError(
        "WhatsApp Web is not logged in for this profile in the background session. "
        "Open the profile and scan the QR code once (Launch WhatsApp), then retry."
    )


def _type_and_send(driver, settings: dict[str, Any], message: str) -> None:
    """Focus the message composer, type the message and send with Enter."""
    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    composer = _first_element(driver, _COMPOSER_LOCATORS, wait_seconds, clickable=True)
    _safe_click(driver, composer)
    time.sleep(0.5)
    if message:
        composer.send_keys(Keys.CONTROL, "a")
        composer.send_keys(Keys.DELETE)
        composer.send_keys(message)
        time.sleep(0.5)
    # Enter is the most reliable way to send and avoids send-button churn.
    try:
        composer.send_keys(Keys.ENTER)
    except Exception:
        try:
            send = _first_element(driver, _SEND_BUTTON_LOCATORS, wait_seconds, clickable=True)
            _safe_click(driver, send)
        except Exception:
            raise
    time.sleep(2)


def _open_target_chat(driver, target: dict[str, Any], settings: dict[str, Any], message: str = "") -> str:
    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    wait = WebDriverWait(driver, wait_seconds)
    if target["target_kind"] == "contact":
        phone = _sanitize_phone(target["target_ref"])
        if not phone:
            raise ValueError("Contact target requires a phone number.")
        url = _whatsapp_url(phone, message)
        driver.get(url)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        _ensure_logged_in(driver, settings)
        time.sleep(4)
        return url

    driver.get("https://web.whatsapp.com/")
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    _ensure_logged_in(driver, settings)
    label = target["target_name"] or target["target_ref"]
    query = target["target_ref"] or target["target_name"]

    search = _first_element(driver, _SEARCH_BOX_LOCATORS, wait_seconds, clickable=True)
    _safe_click(driver, search)
    search.send_keys(Keys.CONTROL, "a")
    search.send_keys(Keys.DELETE)
    search.send_keys(query)
    time.sleep(2)

    chat_locators = [
        (By.XPATH, f"//span[@title={json.dumps(label)}]"),
        (By.XPATH, f"//*[@title={json.dumps(label)}]"),
        (By.XPATH, f"//span[contains(@title, {json.dumps(label)})]"),
    ]
    try:
        chat = _first_element(driver, chat_locators, wait_seconds, clickable=True)
    except Exception:
        raise ValueError(
            f"No WhatsApp chat named '{label}' was found for this account. "
            "Use the exact chat/group name as it appears in WhatsApp."
        )
    _safe_click(driver, chat)
    time.sleep(2)
    return "https://web.whatsapp.com/"


def _attach_file(driver, settings: dict[str, Any], attachment_path: str) -> None:
    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    clip = _first_element(
        driver,
        [
            (By.XPATH, "//button[@aria-label='Attach']"),
            (By.XPATH, "//span[@data-icon='plus-rounded']"),
            (By.XPATH, "//span[@data-icon='clip']"),
            (By.XPATH, "//button[@title='Attach']"),
        ],
        wait_seconds,
        clickable=True,
    )
    _safe_click(driver, clip)
    file_input = _first_element(driver, [(By.XPATH, "//input[@type='file']")], wait_seconds)
    file_input.send_keys(str(Path(attachment_path).resolve()))
    time.sleep(3)


def _send_via_selenium(profile: dict[str, Any], settings: dict[str, Any], phone: str, message: str, attachment_path: str | None) -> dict[str, Any]:
    mode = "headless" if bool(settings.get("headless", True)) else "selenium"
    url = _whatsapp_url(phone, message)
    with _DRIVER_LOCK:
        driver = _acquire_driver(profile, settings)
        wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
        try:
            driver.get(url)
            WebDriverWait(driver, wait_seconds).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            _ensure_logged_in(driver, settings)
            time.sleep(4)
            if attachment_path:
                _attach_file(driver, settings, attachment_path)
            _type_and_send(driver, settings, message)
            return {
                "status": "sent",
                "message": "Message sent in the background through WhatsApp automation.",
                "mode": mode,
                "url": url,
            }
        except Exception:
            _capture_debug(driver, "send-text-fail")
            raise


def _send_target_via_selenium(profile: dict[str, Any], target: dict[str, Any], settings: dict[str, Any], message: str, attachment_path: str | None) -> dict[str, Any]:
    mode = "headless" if bool(settings.get("headless", True)) else "selenium"
    with _DRIVER_LOCK:
        driver = _acquire_driver(profile, settings)
        try:
            url = _open_target_chat(driver, target, settings, message)
            if attachment_path:
                _attach_file(driver, settings, attachment_path)
            _type_and_send(driver, settings, message)
            return {
                "status": "sent",
                "message": f"Message sent to {target['target_name'] or target['target_ref']}.",
                "mode": mode,
                "url": url,
            }
        except Exception:
            _capture_debug(driver, f"send-target-{target.get('target_kind', 'x')}-fail")
            raise


def _scrape_target_messages(profile: dict[str, Any], target: dict[str, Any], settings: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
    if not _HAVE_SELENIUM:
        raise RuntimeError("Selenium is not installed in the backend runtime.")
    with _DRIVER_LOCK:
        driver = _acquire_driver(profile, settings)
        _open_target_chat(driver, target, settings)
        message_nodes = driver.find_elements(By.XPATH, "//div[contains(@class,'message-')]")
        captured: list[dict[str, Any]] = []
        for node in message_nodes[-limit:]:
            classes = (node.get_attribute("class") or "").lower()
            direction = "incoming" if "message-in" in classes else "outgoing"
            text_nodes = node.find_elements(By.XPATH, ".//span[contains(@class,'selectable-text')]")
            text = " ".join((part.text or "").strip() for part in text_nodes).strip()
            if not text:
                continue
            timestamp = node.get_attribute("data-pre-plain-text") or ""
            captured.append(
                {
                    "message_id": str(uuid.uuid4()),
                    "target_id": target["target_id"],
                    "profile_id": profile["profile_id"],
                    "direction": direction,
                    "message_text": text,
                    "message_time": timestamp.strip() or _now_iso(),
                    "source_label": target["target_name"] or target["target_ref"],
                    "captured_at": _now_iso(),
                }
            )
        return captured


def get_state() -> dict[str, Any]:
    settings = _load_settings()
    profiles = _load_profiles()
    targets = _load_targets()
    inbox = _load_inbox()
    return {
        "settings": settings,
        "profiles": profiles,
        "targets": targets,
        "messages": inbox[:100],
        "capabilities": _capabilities(settings, profiles),
    }


def update_settings(browser_command: str, delivery_mode: str, launch_wait_seconds: int, headless: bool | None = None, manual_fallback: bool | None = None) -> dict[str, Any]:
    current = _load_settings()
    settings = _save_settings(
        {
            "browser_command": browser_command,
            "delivery_mode": delivery_mode,
            "launch_wait_seconds": launch_wait_seconds,
            "headless": current.get("headless", True) if headless is None else bool(headless),
            "manual_fallback": current.get("manual_fallback", False) if manual_fallback is None else bool(manual_fallback),
        }
    )
    # Drop any live sessions so the new headless/visibility choice takes effect
    # on the next send instead of reusing an old-mode browser.
    shutdown_all_drivers()
    return {
        "settings": settings,
        "profiles": _load_profiles(),
        "capabilities": _capabilities(settings, _load_profiles()),
    }


def upsert_profile(payload: dict[str, Any]) -> dict[str, Any]:
    profiles = _load_profiles()
    profile_id = str(payload.get("profile_id", "")).strip() or str(uuid.uuid4())
    now = _now_iso()
    existing = next((row for row in profiles if row["profile_id"] == profile_id), None)
    if existing is None:
        existing = {
            "profile_id": profile_id,
            "created_at": now,
            "last_used_at": "",
        }
        profiles.append(existing)

    existing.update(
        {
            "profile_name": str(payload.get("profile_name", "")).strip() or existing.get("profile_name", ""),
            "owner_type": str(payload.get("owner_type", "store")).strip() or "store",
            "owner_name": str(payload.get("owner_name", "")).strip(),
            "tenant_id": str(payload.get("tenant_id", "")).strip(),
            "store_id": str(payload.get("store_id", "")).strip(),
            "default_phone": _sanitize_phone(str(payload.get("default_phone", "")).strip()),
            "notes": str(payload.get("notes", "")).strip(),
            "is_default": bool(payload.get("is_default", False)),
            "updated_at": now,
            "session_dir": str((PROFILES_DIR / profile_id).resolve()),
        }
    )
    if existing["is_default"]:
        for row in profiles:
            if row["profile_id"] != profile_id:
                row["is_default"] = False
    saved = _save_profiles(profiles)
    return {
        "profiles": saved,
        "profile": _resolve_profile(profile_id, saved),
        "capabilities": _capabilities(_load_settings(), saved),
    }


def delete_profile(profile_id: str) -> dict[str, Any]:
    profiles = _load_profiles()
    profile = _resolve_profile(profile_id, profiles)
    remaining = [row for row in profiles if row["profile_id"] != profile_id]
    remaining_targets = [row for row in _load_targets() if row["profile_id"] != profile_id]
    remaining_messages = [row for row in _load_inbox() if row["profile_id"] != profile_id]
    _shutdown_driver(profile_id)
    session_dir = Path(profile["session_dir"])
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)
    shutil.rmtree(_headless_dir(profile), ignore_errors=True)
    saved = _save_profiles(remaining)
    _save_targets(remaining_targets)
    _save_inbox(remaining_messages)
    return {
        "profiles": saved,
        "targets": _load_targets(),
        "messages": _load_inbox()[:100],
        "capabilities": _capabilities(_load_settings(), saved),
    }


def launch_qr(profile_id: str) -> dict[str, Any]:
    settings = _load_settings()
    profiles = _load_profiles()
    profile = _resolve_profile(profile_id, profiles)
    # QR login needs a visible window sharing this profile's user-data-dir, so
    # the background headless session must let go of it first.
    _shutdown_driver(profile_id)
    # Drop the headless mirror so the next send re-adopts the freshly-scanned
    # login instead of an old (possibly logged-out) session.
    shutil.rmtree(_headless_dir(profile), ignore_errors=True)
    result = _launch_browser(profile, settings, "https://web.whatsapp.com/")
    profile["last_used_at"] = _now_iso()
    _save_profiles(profiles)
    return result


def _stage_attachment(file_name: str, content: bytes) -> str:
    _ensure_dirs()
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", file_name or "attachment.bin")
    target = FILES_DIR / f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{safe_name}"
    target.write_bytes(content)
    return str(target.resolve())


def _headless_failure(exc: Exception, staged_attachment: str | None = None, target_hint: str = "") -> dict[str, Any]:
    """Return a structured failure (no visible browser popped) for a headless send."""
    result: dict[str, Any] = {
        "status": "failed",
        "mode": "headless",
        "message": (
            f"Background WhatsApp send failed: {exc}. A diagnostic snapshot was saved under "
            "backend/storage/whatsapp/debug. If the session is logged out, open the profile "
            "and scan the QR once, then retry."
        ),
    }
    if target_hint:
        result["target_hint"] = target_hint
    if staged_attachment:
        result["attachment_path"] = staged_attachment
    return result


def send_message(profile_id: str, phone: str, message: str, attachment_name: str | None = None, attachment_content: bytes | None = None) -> dict[str, Any]:
    profiles = _load_profiles()
    settings = _load_settings()
    profile = _resolve_profile(profile_id, profiles)
    phone_value = _sanitize_phone(phone or profile.get("default_phone", ""))
    if not phone_value:
        raise ValueError("Target phone number is required.")

    staged_attachment = None
    if attachment_name and attachment_content is not None:
        staged_attachment = _stage_attachment(attachment_name, attachment_content)

    profile["last_used_at"] = _now_iso()
    _save_profiles(profiles)

    if settings.get("delivery_mode") == "selenium" and _HAVE_SELENIUM:
        try:
            return _send_via_selenium(profile, settings, phone_value, message, staged_attachment)
        except Exception as exc:
            if not bool(settings.get("manual_fallback", False)):
                return _headless_failure(exc, staged_attachment)
            _shutdown_driver(profile["profile_id"])
            fallback = _launch_browser(profile, settings, _whatsapp_url(phone_value, message))
            fallback["status"] = "manual-fallback"
            fallback["message"] = (
                f"Selenium send failed and WhatsApp Web was opened for manual send instead: {exc}"
            )
            if staged_attachment:
                fallback["attachment_path"] = staged_attachment
            return fallback

    result = _launch_browser(profile, settings, _whatsapp_url(phone_value, message))
    result["status"] = "manual"
    if staged_attachment:
        result["attachment_path"] = staged_attachment
        result["message"] = (
            "WhatsApp Web opened with the selected profile. "
            "Attach the prepared file manually and click send."
        )
    else:
        result["message"] = "WhatsApp Web opened with a prefilled message. Click send to deliver it."
    return result


def upsert_target(payload: dict[str, Any]) -> dict[str, Any]:
    profiles = _load_profiles()
    profile_id = str(payload.get("profile_id", "")).strip()
    if not profile_id:
        raise ValueError("Profile is required for a WhatsApp target.")
    _resolve_profile(profile_id, profiles)
    targets = _load_targets()
    target_id = str(payload.get("target_id", "")).strip() or str(uuid.uuid4())
    now = _now_iso()
    existing = next((row for row in targets if row["target_id"] == target_id), None)
    if existing is None:
        existing = {"target_id": target_id, "created_at": now, "last_synced_at": ""}
        targets.append(existing)
    kind = str(payload.get("target_kind", "contact")).strip() or "contact"
    target_ref = str(payload.get("target_ref", "")).strip()
    if kind == "contact":
        target_ref = _sanitize_phone(target_ref)
    existing.update(
        {
            "profile_id": profile_id,
            "target_kind": kind,
            "target_name": str(payload.get("target_name", "")).strip(),
            "target_ref": target_ref,
            "can_send": bool(payload.get("can_send", True)),
            "can_read": bool(payload.get("can_read", False)),
            "is_active": bool(payload.get("is_active", True)),
            "notes": str(payload.get("notes", "")).strip(),
            "updated_at": now,
            "created_at": existing.get("created_at", now),
            "last_synced_at": existing.get("last_synced_at", ""),
        }
    )
    saved = _save_targets(targets)
    return {
        "targets": saved,
        "target": _resolve_target(target_id, saved),
        "messages": _load_inbox()[:100],
        "capabilities": _capabilities(_load_settings(), profiles),
    }


def delete_target(target_id: str) -> dict[str, Any]:
    targets = _load_targets()
    _resolve_target(target_id, targets)
    remaining_targets = [row for row in targets if row["target_id"] != target_id]
    remaining_messages = [row for row in _load_inbox() if row["target_id"] != target_id]
    return {
        "targets": _save_targets(remaining_targets),
        "messages": _save_inbox(remaining_messages)[:100],
        "capabilities": _capabilities(_load_settings(), _load_profiles()),
    }


def send_target_message(target_id: str, message: str, attachment_name: str | None = None, attachment_content: bytes | None = None) -> dict[str, Any]:
    profiles = _load_profiles()
    settings = _load_settings()
    target = _resolve_target(target_id)
    if not target["can_send"] or not target["is_active"]:
        raise ValueError("This WhatsApp target is not enabled for sending.")
    profile = _resolve_profile(target["profile_id"], profiles)
    staged_attachment = None
    if attachment_name and attachment_content is not None:
        staged_attachment = _stage_attachment(attachment_name, attachment_content)
    profile["last_used_at"] = _now_iso()
    _save_profiles(profiles)

    if settings.get("delivery_mode") == "selenium" and _HAVE_SELENIUM:
        try:
            return _send_target_via_selenium(profile, target, settings, message, staged_attachment)
        except Exception as exc:
            if not bool(settings.get("manual_fallback", False)):
                return _headless_failure(exc, staged_attachment, target["target_name"] or target["target_ref"])
            _shutdown_driver(profile["profile_id"])
            fallback_url = "https://web.whatsapp.com/" if target["target_kind"] == "group" else _whatsapp_url(_sanitize_phone(target["target_ref"]), message)
            fallback = _launch_browser(profile, settings, fallback_url)
            fallback["status"] = "manual-fallback"
            fallback["message"] = f"Selenium send failed. WhatsApp Web opened for manual send instead: {exc}"
            fallback["target_hint"] = target["target_name"] or target["target_ref"]
            if staged_attachment:
                fallback["attachment_path"] = staged_attachment
            return fallback

    if target["target_kind"] == "contact":
        result = _launch_browser(profile, settings, _whatsapp_url(_sanitize_phone(target["target_ref"]), message))
    else:
        result = _launch_browser(profile, settings, "https://web.whatsapp.com/")
        result["target_hint"] = target["target_name"] or target["target_ref"]
    result["status"] = "manual"
    result["message"] = (
        f"WhatsApp Web opened for {target['target_name'] or target['target_ref']}. "
        "If this is a group target, search/select that chat in WhatsApp Web before sending."
    )
    if staged_attachment:
        result["attachment_path"] = staged_attachment
    return result


def sync_target_messages(target_id: str, limit: int = 20) -> dict[str, Any]:
    profiles = _load_profiles()
    settings = _load_settings()
    target = _resolve_target(target_id)
    if not target["can_read"] or not target["is_active"]:
        raise ValueError("This WhatsApp target is not enabled for reading.")
    if not (_HAVE_SELENIUM and _browser_ready(settings.get("browser_command", ""))):
        raise RuntimeError("Incoming message sync requires Selenium plus a configured browser runtime.")
    profile = _resolve_profile(target["profile_id"], profiles)
    messages = _scrape_target_messages(profile, target, settings, limit=max(1, min(limit, 100)))
    stored = _append_inbox_messages(messages)
    targets = _load_targets()
    for row in targets:
        if row["target_id"] == target_id:
            row["last_synced_at"] = _now_iso()
            row["updated_at"] = _now_iso()
    saved_targets = _save_targets(targets)
    return {
        "targets": saved_targets,
        "messages": stored[:100],
        "synced_count": len(messages),
        "target": _resolve_target(target_id, saved_targets),
        "capabilities": _capabilities(settings, profiles),
    }
