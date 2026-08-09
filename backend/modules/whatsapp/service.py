from __future__ import annotations

import atexit
import json
import re
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

try:
    from playwright.sync_api import sync_playwright
    _HAVE_PLAYWRIGHT = True
except Exception:  # pragma: no cover - optional runtime dependency
    sync_playwright = None
    _HAVE_PLAYWRIGHT = False


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
    # Legacy field, unused now that Playwright manages its own bundled Firefox.
    "browser_command": "",
    "delivery_mode": "manual_browser",
    "launch_wait_seconds": 15,
    "headless": True,
    # When a background (headless) send fails, do NOT pop a visible browser
    "manual_fallback": False,
}


# Persistent, reusable WhatsApp browser sessions keyed by profile_id.
# Playwright sync objects are not thread-safe and FastAPI runs sync endpoints
# in a threadpool, so every interaction with a context is serialized under
# this lock. Firefox (unlike headless Chrome) does not crash against a real,
# already-bloated profile, so we run headless directly on the login profile —
# no mirror-copy workaround needed.
_DRIVER_LOCK = threading.RLock()
_PLAYWRIGHT_DRIVER: Any = None
_CONTEXTS: dict[str, dict[str, Any]] = {}  # profile_id -> {context, page, headless}


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


def _load_settings() -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    settings.update(_read_json(SETTINGS_FILE, {}))
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


def _capabilities(settings: dict[str, Any], profiles: list[dict[str, Any]]) -> dict[str, Any]:
    ready = _HAVE_PLAYWRIGHT
    return {
        "browser_detected": ready,
        "browser_command": settings.get("browser_command", ""),
        "selenium_available": ready,  # kept for frontend compatibility; now means "automation engine ready"
        "delivery_mode": settings.get("delivery_mode", "manual_browser"),
        "headless": bool(settings.get("headless", True)),
        "manual_fallback": bool(settings.get("manual_fallback", False)),
        "can_launch_qr": ready,
        "can_auto_send_attachment": ready,
        "can_read_messages": ready,
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


# --- Playwright / Firefox session management -------------------------------

def _ensure_playwright_driver() -> Any:
    """Start (once) the Playwright driver process for this backend's lifetime."""
    global _PLAYWRIGHT_DRIVER
    if not _HAVE_PLAYWRIGHT:
        raise RuntimeError("Playwright is not installed in the backend runtime.")
    if _PLAYWRIGHT_DRIVER is None:
        _PLAYWRIGHT_DRIVER = sync_playwright().start()
    return _PLAYWRIGHT_DRIVER


def _firefox_profile_dir(profile: dict[str, Any]) -> Path:
    """Firefox gets its own clean subfolder, separate from any legacy Chrome
    profile data that may still sit under session_dir (from before the switch
    to Playwright) — mixing the two profile formats in one folder is fragile
    and slows first-run bootstrap under antivirus file scanning."""
    return Path(profile["session_dir"]) / "firefox_profile"


# Skip network calls Firefox normally makes on first run (telemetry, remote
# settings sync, update/experiment checks, new-tab content) — on a locked-down
# network these can stall persistent-context startup for minutes and add
# nothing for our use case. This is the standard automation preference set
# (the same family geckodriver/mozprofile use for test profiles).
_FIREFOX_USER_PREFS = {
    "app.update.auto": False,
    "app.update.enabled": False,
    "app.normandy.enabled": False,
    "app.normandy.api_url": "",
    "datareporting.healthreport.uploadEnabled": False,
    "datareporting.policy.dataSubmissionEnabled": False,
    "datareporting.policy.dataSubmissionPolicyBypassNotification": True,
    "toolkit.telemetry.enabled": False,
    "toolkit.telemetry.unified": False,
    "toolkit.telemetry.server": "",
    "toolkit.telemetry.archive.enabled": False,
    "toolkit.telemetry.reportingpolicy.firstRun": False,
    "toolkit.telemetry.shutdownPingSender.enabled": False,
    "services.settings.server": "",
    "extensions.getAddons.cache.enabled": False,
    "extensions.update.enabled": False,
    "extensions.pocket.enabled": False,
    "identity.fxaccounts.enabled": False,
    "browser.aboutwelcome.enabled": False,
    "browser.newtabpage.enabled": False,
    "browser.newtabpage.activity-stream.feeds.telemetry": False,
    "browser.newtabpage.activity-stream.feeds.snippets": False,
    "browser.newtabpage.activity-stream.feeds.section.topstories": False,
    "browser.newtabpage.activity-stream.showSponsored": False,
    "browser.discovery.enabled": False,
    "browser.ping-centre.telemetry": False,
    "browser.shell.checkDefaultBrowser": False,
    "browser.startup.homepage": "about:blank",
    "browser.uitour.enabled": False,
    "network.captive-portal-service.enabled": False,
    "network.connectivity-service.enabled": False,
    "network.prefetch-next": False,
    "network.dns.disablePrefetch": True,
}


def _build_context(profile: dict[str, Any], headless: bool) -> tuple[Any, Any]:
    """Launch a persistent Firefox context against a clean, dedicated profile
    folder (separate from any legacy Chrome data).

    Unlike headless Chrome (which crashed against a bloated, extension-laden
    profile), Playwright's bundled Firefox runs headless directly on the same
    profile used for a visible QR-login session — no mirror copy required.
    """
    driver = _ensure_playwright_driver()
    session_dir = _firefox_profile_dir(profile)
    session_dir.mkdir(parents=True, exist_ok=True)
    context = driver.firefox.launch_persistent_context(
        user_data_dir=str(session_dir),
        headless=headless,
        viewport={"width": 1280, "height": 960} if headless else None,
        args=["--width=1280", "--height=960"] if not headless else [],
        firefox_user_prefs=_FIREFOX_USER_PREFS,
        timeout=45000,
    )
    page = context.pages[0] if context.pages else context.new_page()
    return context, page


def _context_alive(entry: dict[str, Any] | None) -> bool:
    if not entry:
        return False
    try:
        _ = entry["page"].url
        return True
    except Exception:
        return False


def _acquire_context(profile: dict[str, Any], settings: dict[str, Any], want_headless: bool) -> Any:
    """Return a persistent, logged-in Firefox page for this profile.

    The context is created once per (profile, headless-mode) and reused across
    sends so WhatsApp Web loads and authenticates a single time. Subsequent
    messages navigate inside the same session — no new window, no reload.
    Callers must hold ``_DRIVER_LOCK``.
    """
    profile_id = profile["profile_id"]
    entry = _CONTEXTS.get(profile_id)
    if entry and entry["headless"] == want_headless and _context_alive(entry):
        return entry["page"]
    if entry is not None:
        try:
            entry["context"].close()
        except Exception:
            pass
        _CONTEXTS.pop(profile_id, None)

    context, page = _build_context(profile, want_headless)
    _CONTEXTS[profile_id] = {"context": context, "page": page, "headless": want_headless}

    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    try:
        page.goto("https://web.whatsapp.com/", timeout=wait_seconds * 1000)
        page.wait_for_timeout(3000)
    except Exception:
        pass
    return page


def _shutdown_context(profile_id: str) -> None:
    """Close and forget the live session for a profile (releases its profile
    dir so a different mode/window can reuse it)."""
    with _DRIVER_LOCK:
        entry = _CONTEXTS.pop(profile_id, None)
    if entry is not None:
        try:
            entry["context"].close()
        except Exception:
            pass


def shutdown_all_drivers() -> None:
    with _DRIVER_LOCK:
        entries = list(_CONTEXTS.values())
        _CONTEXTS.clear()
    for entry in entries:
        try:
            entry["context"].close()
        except Exception:
            pass
    global _PLAYWRIGHT_DRIVER
    if _PLAYWRIGHT_DRIVER is not None:
        try:
            _PLAYWRIGHT_DRIVER.stop()
        except Exception:
            pass
        _PLAYWRIGHT_DRIVER = None


atexit.register(shutdown_all_drivers)


# --- Robust WhatsApp Web automation helpers -------------------------------
# WhatsApp Web changes its DOM often, so every interaction tries several
# selectors and falls back to a JS click. On failure we snapshot the page so
# the real cause is visible (backend/storage/whatsapp/debug).

_SEARCH_BOX_SELECTORS = [
    "xpath=//input[@aria-label='Search or start a new chat']",
    "xpath=//div[@aria-label='Chat list']//input[@role='textbox']",
    "xpath=//div[@contenteditable='true'][@data-tab='3']",
    "xpath=//div[@role='textbox'][@contenteditable='true'][@aria-label]",
]
_COMPOSER_SELECTORS = [
    "xpath=//footer//div[@contenteditable='true'][@data-tab='10']",
    "xpath=//div[@contenteditable='true'][starts-with(@aria-label,'Type a message')]",
    "xpath=//footer//div[@contenteditable='true']",
    "xpath=(//div[@contenteditable='true'])[last()]",
]
_SEND_BUTTON_SELECTORS = [
    "xpath=//button[@aria-label='Send']",
    "xpath=//span[@data-icon='send']",
    "xpath=//span[@data-icon='wds-ic-send-filled']",
]
_ATTACH_SELECTORS = [
    "xpath=//button[@aria-label='Attach']",
    "xpath=//span[@data-icon='plus-rounded']",
    "xpath=//span[@data-icon='clip']",
    "xpath=//button[@title='Attach']",
]


def _capture_debug(page: Any, tag: str) -> str | None:
    """Save a screenshot + page source so a failed send is diagnosable."""
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        base = DEBUG_DIR / f"{stamp}_{re.sub(r'[^a-zA-Z0-9._-]+', '_', tag)}"
        try:
            page.screenshot(path=str(base) + ".png")
        except Exception:
            pass
        try:
            (Path(str(base) + ".html")).write_text(page.content() or "", encoding="utf-8")
        except Exception:
            pass
        try:
            meta = {"url": page.url, "title": page.title(), "logged_in": _is_logged_in(page)}
            (Path(str(base) + ".json")).write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except Exception:
            pass
        return str(base)
    except Exception:
        return None


def _is_logged_in(page: Any) -> bool:
    """True when the chat UI is present; False on the QR / landing screen."""
    try:
        if page.locator("xpath=//input[@aria-label='Search or start a new chat']").count() > 0:
            return True
        if page.locator("xpath=//div[@id='pane-side']").count() > 0:
            return True
    except Exception:
        return False
    return False


def _first_locator(page: Any, selectors: list[str], timeout_seconds: int) -> Any:
    """Return the first visible element that matches any selector within the timeout."""
    end = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < end:
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    first = loc.first
                    if first.is_visible():
                        return first
            except Exception as exc:  # pragma: no cover - defensive
                last_error = exc
        time.sleep(0.4)
    if last_error is not None:
        raise last_error
    raise TimeoutError(f"None of the selectors matched: {selectors}")


def _safe_click(locator: Any) -> None:
    """Click an element, falling back to a JS click if the normal click is blocked."""
    try:
        locator.click(timeout=5000)
        return
    except Exception:
        try:
            locator.evaluate("el => el.click()")
        except Exception:
            raise


def _ensure_logged_in(page: Any, settings: dict[str, Any]) -> None:
    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    end = time.time() + wait_seconds
    while time.time() < end:
        if _is_logged_in(page):
            return
        time.sleep(1)
    raise RuntimeError(
        "WhatsApp Web is not logged in for this profile. "
        "Open the profile and scan the QR code once (Launch WhatsApp), then retry."
    )


def _type_and_send(page: Any, settings: dict[str, Any], message: str) -> None:
    """Focus the message composer, type the message and send with Enter."""
    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    composer = _first_locator(page, _COMPOSER_SELECTORS, wait_seconds)
    _safe_click(composer)
    time.sleep(0.3)
    if message:
        composer.press("Control+a")
        composer.press("Delete")
        composer.type(message, delay=8)
        time.sleep(0.3)
    # Enter is the most reliable way to send and avoids send-button churn.
    try:
        composer.press("Enter")
    except Exception:
        send = _first_locator(page, _SEND_BUTTON_SELECTORS, wait_seconds)
        _safe_click(send)
    time.sleep(2)


def _open_target_chat(page: Any, target: dict[str, Any], settings: dict[str, Any], message: str = "") -> str:
    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    if target["target_kind"] == "contact":
        phone = _sanitize_phone(target["target_ref"])
        if not phone:
            raise ValueError("Contact target requires a phone number.")
        url = _whatsapp_url(phone, message)
        page.goto(url, timeout=wait_seconds * 1000)
        _ensure_logged_in(page, settings)
        time.sleep(4)
        return url

    if "web.whatsapp.com" not in (page.url or ""):
        page.goto("https://web.whatsapp.com/", timeout=wait_seconds * 1000)
    _ensure_logged_in(page, settings)
    label = target["target_name"] or target["target_ref"]
    query = target["target_ref"] or target["target_name"]

    search = _first_locator(page, _SEARCH_BOX_SELECTORS, wait_seconds)
    _safe_click(search)
    search.press("Control+a")
    search.press("Delete")
    search.type(query, delay=15)
    time.sleep(2)

    chat_selectors = [
        f"xpath=//span[@title={json.dumps(label)}]",
        f"xpath=//*[@title={json.dumps(label)}]",
        f"xpath=//span[contains(@title, {json.dumps(label)})]",
    ]
    try:
        chat = _first_locator(page, chat_selectors, wait_seconds)
    except Exception:
        raise ValueError(
            f"No WhatsApp chat named '{label}' was found for this account. "
            "Use the exact chat/group name as it appears in WhatsApp."
        )
    _safe_click(chat)
    time.sleep(2)
    return "https://web.whatsapp.com/"


def _attach_file(page: Any, settings: dict[str, Any], attachment_path: str) -> None:
    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    clip = _first_locator(page, _ATTACH_SELECTORS, wait_seconds)
    _safe_click(clip)
    file_input = _first_locator(page, ["xpath=//input[@type='file']"], wait_seconds)
    file_input.set_input_files(str(Path(attachment_path).resolve()))
    time.sleep(3)


def _send_via_playwright(profile: dict[str, Any], settings: dict[str, Any], phone: str, message: str, attachment_path: str | None) -> dict[str, Any]:
    mode = "headless" if bool(settings.get("headless", True)) else "playwright"
    url = _whatsapp_url(phone, message)
    with _DRIVER_LOCK:
        page = _acquire_context(profile, settings, bool(settings.get("headless", True)))
        wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
        try:
            page.goto(url, timeout=wait_seconds * 1000)
            _ensure_logged_in(page, settings)
            time.sleep(4)
            if attachment_path:
                _attach_file(page, settings, attachment_path)
            _type_and_send(page, settings, message)
            return {
                "status": "sent",
                "message": "Message sent in the background through WhatsApp automation.",
                "mode": mode,
                "url": url,
            }
        except Exception:
            _capture_debug(page, "send-text-fail")
            raise


def _send_target_via_playwright(profile: dict[str, Any], target: dict[str, Any], settings: dict[str, Any], message: str, attachment_path: str | None) -> dict[str, Any]:
    mode = "headless" if bool(settings.get("headless", True)) else "playwright"
    with _DRIVER_LOCK:
        page = _acquire_context(profile, settings, bool(settings.get("headless", True)))
        try:
            url = _open_target_chat(page, target, settings, message)
            if attachment_path:
                _attach_file(page, settings, attachment_path)
            _type_and_send(page, settings, message)
            return {
                "status": "sent",
                "message": f"Message sent to {target['target_name'] or target['target_ref']}.",
                "mode": mode,
                "url": url,
            }
        except Exception:
            _capture_debug(page, f"send-target-{target.get('target_kind', 'x')}-fail")
            raise


def _scrape_target_messages(profile: dict[str, Any], target: dict[str, Any], settings: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
    if not _HAVE_PLAYWRIGHT:
        raise RuntimeError("Playwright is not installed in the backend runtime.")
    with _DRIVER_LOCK:
        page = _acquire_context(profile, settings, bool(settings.get("headless", True)))
        _open_target_chat(page, target, settings)
        message_nodes = page.locator("xpath=//div[contains(@class,'message-')]")
        count = message_nodes.count()
        captured: list[dict[str, Any]] = []
        start_idx = max(0, count - limit)
        for i in range(start_idx, count):
            node = message_nodes.nth(i)
            classes = (node.get_attribute("class") or "").lower()
            direction = "incoming" if "message-in" in classes else "outgoing"
            text_nodes = node.locator("xpath=.//span[contains(@class,'selectable-text')]")
            parts = [(text_nodes.nth(j).inner_text() or "").strip() for j in range(text_nodes.count())]
            text = " ".join(parts).strip()
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
    # on the next send instead of reusing an old-mode session.
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
    _shutdown_context(profile_id)
    session_dir = Path(profile["session_dir"])
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)
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
    """Open a visible Firefox window for QR login. Leaves it running so the
    user can scan the code; subsequent headless sends reuse the same profile
    dir once the headed window is closed (or explicitly relaunched)."""
    settings = _load_settings()
    profiles = _load_profiles()
    profile = _resolve_profile(profile_id, profiles)
    with _DRIVER_LOCK:
        # A headed and a headless session can't share the same profile dir at
        # once, so drop any live background session before opening the visible one.
        _shutdown_context(profile_id)
        page = _acquire_context(profile, settings, want_headless=False)
        try:
            if "web.whatsapp.com" not in (page.url or ""):
                page.goto("https://web.whatsapp.com/", timeout=30000)
        except Exception:
            pass
    profile["last_used_at"] = _now_iso()
    _save_profiles(profiles)
    return {
        "status": "launched",
        "message": "A WhatsApp Web window was opened for this profile. Scan the QR code with your phone to log in.",
        "mode": "playwright-visible",
        "url": "https://web.whatsapp.com/",
    }


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


def _visible_open(profile: dict[str, Any], settings: dict[str, Any], url: str) -> dict[str, Any]:
    """Open a visible Firefox window on this profile without auto-sending,
    used for delivery_mode='manual_browser' and as a fallback after a failed
    automated send when manual_fallback is enabled."""
    with _DRIVER_LOCK:
        _shutdown_context(profile["profile_id"])
        page = _acquire_context(profile, settings, want_headless=False)
        try:
            page.goto(url, timeout=30000)
        except Exception:
            pass
    return {
        "status": "launched",
        "message": "WhatsApp Web opened with the selected profile.",
        "mode": "playwright-visible",
        "url": url,
    }


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

    if settings.get("delivery_mode") == "selenium" and _HAVE_PLAYWRIGHT:
        try:
            return _send_via_playwright(profile, settings, phone_value, message, staged_attachment)
        except Exception as exc:
            if not bool(settings.get("manual_fallback", False)):
                return _headless_failure(exc, staged_attachment)
            fallback = _visible_open(profile, settings, _whatsapp_url(phone_value, message))
            fallback["status"] = "manual-fallback"
            fallback["message"] = (
                f"Automated send failed and WhatsApp Web was opened for manual send instead: {exc}"
            )
            if staged_attachment:
                fallback["attachment_path"] = staged_attachment
            return fallback

    result = _visible_open(profile, settings, _whatsapp_url(phone_value, message))
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

    if settings.get("delivery_mode") == "selenium" and _HAVE_PLAYWRIGHT:
        try:
            return _send_target_via_playwright(profile, target, settings, message, staged_attachment)
        except Exception as exc:
            if not bool(settings.get("manual_fallback", False)):
                return _headless_failure(exc, staged_attachment, target["target_name"] or target["target_ref"])
            fallback_url = "https://web.whatsapp.com/" if target["target_kind"] == "group" else _whatsapp_url(_sanitize_phone(target["target_ref"]), message)
            fallback = _visible_open(profile, settings, fallback_url)
            fallback["status"] = "manual-fallback"
            fallback["message"] = f"Automated send failed. WhatsApp Web opened for manual send instead: {exc}"
            fallback["target_hint"] = target["target_name"] or target["target_ref"]
            if staged_attachment:
                fallback["attachment_path"] = staged_attachment
            return fallback

    if target["target_kind"] == "contact":
        result = _visible_open(profile, settings, _whatsapp_url(_sanitize_phone(target["target_ref"]), message))
    else:
        result = _visible_open(profile, settings, "https://web.whatsapp.com/")
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
    if not _HAVE_PLAYWRIGHT:
        raise RuntimeError("Incoming message sync requires the Playwright runtime.")
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
