from __future__ import annotations

import atexit
import base64
import concurrent.futures
import json
import re
import shutil
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
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
SEND_LOG_FILE = STORAGE_DIR / "send_log.json"
SEND_LOG_MAX = 300

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

# Playwright's sync API is pinned to whichever OS thread created the driver —
# a second thread touching it tears the connection down (the browser opens,
# then closes within seconds). FastAPI hands sync endpoints to whatever
# thread is free in its pool, so a lock alone (mutual exclusion) isn't
# enough; every driver-touching entrypoint below is routed through this one
# dedicated thread so the driver, contexts and pages stay on a single thread
# for their whole lifetime.
_DRIVER_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="wa-driver")


def _run_on_driver_thread(fn, *args, **kwargs):
    return _DRIVER_EXECUTOR.submit(fn, *args, **kwargs).result()


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
        # `row.get("profile_id")` can be JSON null (str(None) == "None") from an
        # entry written before upsert_profile collapsed None to "". Treat those
        # sentinel strings as absent so a corrupt id never resurfaces as "None".
        profile_id = str(row.get("profile_id") or "").strip()
        if not profile_id or profile_id.lower() in {"none", "null", "undefined"}:
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
        # No window-size CLI args for the headed path: Chromium's
        # --width=/--height= are not Firefox flags at all, and even
        # Firefox's own single-dash -width/-height aren't reliably accepted
        # by this Playwright-bundled build ("-height" logs as an
        # unrecognized flag here). An unrecognized flag's value falls
        # through to Firefox's positional "open this as a URL" argument,
        # and a bare integer like 1280 gets canonicalised as a decimal IPv4
        # literal (1280 = 0x0500 = 0.0.5.0) -- exactly the bogus
        # "Unable to connect... 0.0.5.0" page this was producing. Simplest
        # fix: don't pass size args; Firefox opens at its own default size.
        args=[],
        firefox_user_prefs=_FIREFOX_USER_PREFS,
        # First-run profile bootstrap (cache/cert DB init) can exceed 45s
        # under antivirus file-scanning on a locked-down machine -- give it
        # real headroom rather than failing a launch that was still in
        # progress.
        timeout=120000,
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
        # Short settle only; _ensure_logged_in polls for the chat UI afterwards.
        page.wait_for_timeout(1000)
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

# The chat-list search box in current WhatsApp Web is a plain <input> in the
# left-pane header (aria-label "Search or start a new chat", data-tab="3").
# CRITICAL: the message composer is ALSO a role="textbox"/contenteditable with
# an aria-label, so a broad "any textbox" selector grabs the COMPOSER when a
# chat is already open and types the query as a message instead of searching.
# Every entry here therefore targets the header search box specifically and
# EXCLUDES the footer composer (id="conversation-compose-box-input",
# data-tab="10", inside <footer>).
_SEARCH_BOX_SELECTORS = [
    "xpath=//input[@aria-label='Search or start a new chat']",
    "xpath=//input[@type='text'][@data-tab='3']",
    # Older builds used a contenteditable search box with data-tab='3'.
    "xpath=//div[@contenteditable='true'][@data-tab='3']",
    # Last resort: a contenteditable textbox that is NOT the composer.
    "xpath=//div[@contenteditable='true'][@role='textbox'][not(ancestor::footer)][not(@id='conversation-compose-box-input')][not(@data-tab='10')][not(@aria-placeholder='Type a message')]",
]

# WhatsApp Web pops a "What's new on WhatsApp Web" (and similar) startup modal
# -- role="dialog" aria-modal="true" -- that overlays the chat list AND blocks
# the search box's contenteditable from mounting, so every search selector
# fails until it is dismissed. These target the modal's primary dismiss
# control across wording drift ("Continue" / "OK" / "Got it") plus the X.
_STARTUP_DIALOG_DISMISS_SELECTORS = [
    "xpath=//div[@role='dialog']//div[@role='button'][.//span[normalize-space()='Continue'] or normalize-space()='Continue']",
    "xpath=//div[@role='dialog']//button[.//span[normalize-space()='Continue'] or normalize-space()='Continue']",
    "xpath=//div[@role='dialog']//*[self::button or @role='button'][normalize-space()='OK' or normalize-space()='Got it' or normalize-space()='Okay']",
    "xpath=//div[@role='dialog']//*[@aria-label='Close']",
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
# After a file is attached, WhatsApp opens a preview overlay with its OWN
# caption box -- it is NOT inside <footer>, unlike the normal chat composer.
# The regular _COMPOSER_SELECTORS' footer-scoped entry still matches the
# background chat composer (Playwright's is_visible() checks CSS
# visibility/size, not z-index occlusion, so a covered-but-present element
# still reads as "visible"), so typing there sends a bare text message while
# the actual attachment preview is left unconfirmed. These selectors target
# the caption box specifically so the caption travels WITH the file.
_CAPTION_SELECTORS = [
    "xpath=//div[@data-testid='media-caption-input-container']",
    "xpath=//div[@aria-label='Add a caption'][@contenteditable='true']",
    "xpath=//div[@contenteditable='true'][@data-tab='10'][not(ancestor::footer)]",
]
_ATTACH_SELECTORS = [
    "xpath=//button[@aria-label='Attach']",
    "xpath=//span[@data-icon='plus-rounded']",
    "xpath=//span[@data-icon='clip']",
    "xpath=//button[@title='Attach']",
]
# Current WhatsApp Web opens a type-picker menu after Attach (Document /
# Photos & videos / Camera / Audio / ...) instead of exposing the file input
# directly -- "Document" must be clicked first for a generic file (e.g. the
# distribution Excel) to activate the right <input type="file">.
_ATTACH_DOCUMENT_SELECTORS = [
    "xpath=//div[@aria-label='Document']",
    "xpath=//li[@aria-label='Document']",
    "xpath=//span[normalize-space(text())='Document']",
    "xpath=//div[normalize-space(text())='Document']",
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


def _dismiss_startup_dialogs(page: Any) -> None:
    """Close any WhatsApp Web startup modal (e.g. "What's new on WhatsApp Web")
    that overlays the chat list. Left open, it prevents the search box's
    contenteditable from mounting, so every _open_target_chat search fails with
    "None of the selectors matched". Best-effort and idempotent: a couple of
    passes (the app can chain more than one dialog), Escape as a final nudge."""
    for _ in range(3):
        try:
            if page.locator("xpath=//div[@role='dialog']").count() == 0:
                return
        except Exception:
            return
        clicked = False
        for sel in _STARTUP_DIALOG_DISMISS_SELECTORS:
            try:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    _safe_click(loc.first)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
        try:
            page.wait_for_timeout(500)
        except Exception:
            pass


def _ensure_logged_in(page: Any, settings: dict[str, Any]) -> None:
    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    end = time.time() + wait_seconds
    while time.time() < end:
        if _is_logged_in(page):
            _dismiss_startup_dialogs(page)
            return
        time.sleep(1)
    raise RuntimeError(
        "WhatsApp Web is not logged in for this profile. "
        "Open the profile and scan the QR code once (Launch WhatsApp), then retry."
    )


def _wait_composer_cleared(composer: Any, timeout_seconds: float = 5.0) -> None:
    """After Enter, WhatsApp empties the composer once the message is queued for
    delivery. Poll for that instead of sleeping a fixed 2s -- returns as soon as
    the box is empty (usually <1s), falls back to the timeout if we can't read
    it (e.g. an attachment preview flow with a different box)."""
    end = time.time() + timeout_seconds
    while time.time() < end:
        try:
            if not (composer.inner_text() or "").strip():
                return
        except Exception:
            return
        time.sleep(0.15)


def _type_and_send(page: Any, settings: dict[str, Any], message: str) -> None:
    """Focus the message composer, type the message and send with Enter."""
    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    composer = _first_locator(page, _COMPOSER_SELECTORS, wait_seconds)
    _safe_click(composer)
    if message:
        composer.press("Control+a")
        composer.press("Delete")
        composer.type(message, delay=5)
    # Enter is the most reliable way to send and avoids send-button churn.
    try:
        composer.press("Enter")
    except Exception:
        send = _first_locator(page, _SEND_BUTTON_SELECTORS, wait_seconds)
        _safe_click(send)
    _wait_composer_cleared(composer)


def _caption_and_send_attachment(page: Any, settings: dict[str, Any], message: str) -> None:
    """Type the caption into the FILE PREVIEW's own caption box (not the
    background chat composer -- see _CAPTION_SELECTORS) and click Send
    explicitly. Must be called right after _attach_file, while the preview
    overlay is still open."""
    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    caption = _first_locator(page, _CAPTION_SELECTORS, wait_seconds)
    _safe_click(caption)
    time.sleep(0.3)
    if message:
        caption.type(message, delay=8)
        time.sleep(0.3)
    send = _first_locator(page, _SEND_BUTTON_SELECTORS, wait_seconds)
    _safe_click(send)
    time.sleep(3)


def _open_target_chat(page: Any, target: dict[str, Any], settings: dict[str, Any], message: str = "") -> str:
    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    if target["target_kind"] == "contact":
        phone = _sanitize_phone(target["target_ref"])
        if not phone:
            raise ValueError("Contact target requires a phone number.")
        url = _whatsapp_url(phone, message)
        page.goto(url, timeout=wait_seconds * 1000)
        _ensure_logged_in(page, settings)
        # send?phone= opens the chat directly; the caller's composer/attach
        # _first_locator polls until it is ready, so a short settle suffices.
        time.sleep(1)
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
    search.type(query, delay=8)
    # Brief settle for the search index to return results; the chat-result
    # _first_locator below then polls, so no fixed multi-second wait is needed.
    time.sleep(0.6)

    # Case-insensitive fallbacks: WhatsApp group names are configured
    # elsewhere (e.g. dbo.stores.w_group_name) and easily drift in case from
    # the real chat title ("NMV GROUP" vs the actual "NMV Group") -- XPath 1.0
    # has no case-insensitive contains(), so translate() both sides to
    # lowercase before comparing.
    _UPPER, _LOWER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"
    label_lower = json.dumps(label.lower())
    chat_selectors = [
        f"xpath=//span[@title={json.dumps(label)}]",
        f"xpath=//*[@title={json.dumps(label)}]",
        f"xpath=//span[contains(@title, {json.dumps(label)})]",
        f"xpath=//span[translate(@title, '{_UPPER}', '{_LOWER}')={label_lower}]",
        f"xpath=//span[contains(translate(@title, '{_UPPER}', '{_LOWER}'), {label_lower})]",
    ]
    try:
        chat = _first_locator(page, chat_selectors, wait_seconds)
    except Exception:
        raise ValueError(
            f"No WhatsApp chat named '{label}' was found for this account. "
            "Use the exact chat/group name as it appears in WhatsApp."
        )
    _safe_click(chat)
    # No fixed wait: the caller's composer/attach _first_locator polls until the
    # opened chat is ready.
    time.sleep(0.3)
    return "https://web.whatsapp.com/"


def _attach_file(page: Any, settings: dict[str, Any], attachment_path: str) -> None:
    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    resolved_path = str(Path(attachment_path).resolve())
    clip = _first_locator(page, _ATTACH_SELECTORS, wait_seconds)
    _safe_click(clip)

    try:
        doc_item = _first_locator(page, _ATTACH_DOCUMENT_SELECTORS, 5)
        # expect_file_chooser intercepts the native/JS file dialog directly --
        # more robust than hunting for a hidden <input type="file"> whose
        # visibility/activation is menu-state-dependent in the current UI.
        with page.expect_file_chooser(timeout=8000) as fc_info:
            _safe_click(doc_item)
        fc_info.value.set_files(resolved_path)
        time.sleep(3)
        return
    except Exception:
        pass  # fall through: older UI, or no menu/chooser appeared

    # File inputs are display:none, so a visibility-gated locator (_first_locator)
    # never returns them -- that was the "None of the selectors matched
    # [input[type=file]]" attach failure. Set files directly on the (hidden)
    # input instead; Playwright supports this without the element being visible.
    loc = page.locator("xpath=//input[@type='file']")
    end = time.time() + wait_seconds
    while loc.count() == 0 and time.time() < end:
        page.wait_for_timeout(300)
    if loc.count() == 0:
        raise TimeoutError("No file input was found to attach the document.")
    loc.last.set_input_files(resolved_path)
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
            time.sleep(1)
            if attachment_path:
                _attach_file(page, settings, attachment_path)
                _caption_and_send_attachment(page, settings, message)
            else:
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
                _caption_and_send_attachment(page, settings, message)
            else:
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


# --- Chat-list reading (WhatsApp-like picker) -----------------------------
# Filter chips at the top of the chat list ("All / Unread / Favourites /
# Groups"). Clicking "Groups" narrows the list to groups so we can label each
# scraped chat; "All" restores the full list. Wording/DOM drift is covered by
# several fallbacks.
_FILTER_GROUPS_SELECTORS = [
    "xpath=//div[@aria-label='chat-list-filters']//button[normalize-space()='Groups']",
    "xpath=//button[@id='group-filter']",
    "xpath=//*[@role='button'][normalize-space()='Groups']",
    "xpath=//div[@role='tab'][normalize-space()='Groups']",
]
_FILTER_ALL_SELECTORS = [
    "xpath=//div[@aria-label='chat-list-filters']//button[normalize-space()='All']",
    "xpath=//button[@id='all-filter']",
    "xpath=//*[@role='button'][normalize-space()='All']",
    "xpath=//div[@role='tab'][normalize-space()='All']",
]
# Chat rows live under #pane-side; the chat name is the row's titled span. We
# read one name per row (the first titled span) to avoid picking up message
# previews. Fallbacks in case the row role differs across builds.
_CHAT_ROW_SELECTORS = [
    "xpath=//div[@id='pane-side']//div[@role='listitem']",
    "xpath=//div[@id='pane-side']//div[@role='row']",
    "xpath=//div[@id='pane-side']//div[@role='gridcell']",
]


def _click_first(page: Any, selectors: list[str]) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                _safe_click(loc.first)
                return True
        except Exception:
            continue
    return False


# One JS round-trip returns EVERY visible chat name from the pane -- far faster
# than per-row Playwright locator calls (which turn a 99+/50-group account into
# thousands of IPC calls and make the scrape look like a hang).
_SCRAPE_NAMES_JS = """() => {
  const pane = document.getElementById('pane-side');
  if (!pane) return [];
  const rows = pane.querySelectorAll('[role="listitem"], [role="row"], [role="gridcell"]');
  const nodes = rows.length ? rows : pane.querySelectorAll('span[title]');
  const out = [];
  nodes.forEach((n) => {
    const s = (n.matches && n.matches('span[title]')) ? n : n.querySelector('span[title]');
    if (s) { const t = (s.getAttribute('title') || '').trim(); if (t) out.push(t); }
  });
  return out;
}"""
_SCROLL_PANE_JS = """() => { const p = document.getElementById('pane-side'); if (!p) return; const s = p.querySelector('[role="grid"]') || p; s.scrollTop = s.scrollHeight; }"""


def _scrape_chat_names(page: Any, max_rows: int = 1000, time_budget: float = 15.0) -> list[str]:
    """Collect chat names from the (virtualized) chat list, scrolling to the
    bottom to load more. Uses a single JS evaluate per pass (fast) and a hard
    time budget + stagnation cut-off so it can never hang. De-duplicated,
    list order preserved."""
    names: list[str] = []
    seen: set[str] = set()
    end = time.time() + time_budget
    stagnant = 0
    while time.time() < end and len(names) < max_rows:
        try:
            batch = page.evaluate(_SCRAPE_NAMES_JS) or []
        except Exception:
            batch = []
        added = 0
        for t in batch:
            t = (t or "").strip()
            if t and t not in seen:
                seen.add(t)
                names.append(t)
                added += 1
        try:
            page.evaluate(_SCROLL_PANE_JS)
        except Exception:
            pass
        page.wait_for_timeout(250)
        stagnant = stagnant + 1 if added == 0 else 0
        if stagnant >= 3:  # no new names after several scrolls -> end of list
            break
    return names[:max_rows]


def list_chats(profile_id: str) -> dict[str, Any]:
    return _run_on_driver_thread(_list_chats_impl, profile_id)


def _list_chats_impl(profile_id: str) -> dict[str, Any]:
    """Read the profile's WhatsApp chat list (recent contacts + groups) so the
    UI can offer a WhatsApp-like picker. Groups are labelled by scraping the
    'Groups' filter; everything else is a contact. Best-effort: on an empty
    result a debug snapshot is saved so the selectors can be refined."""
    if not _HAVE_PLAYWRIGHT:
        raise RuntimeError("Playwright is not installed in the backend runtime.")
    settings = _load_settings()
    profiles = _load_profiles()
    profile = _resolve_profile(profile_id, profiles)
    with _DRIVER_LOCK:
        page = _acquire_context(profile, settings, bool(settings.get("headless", True)))
        if "web.whatsapp.com" not in (page.url or ""):
            try:
                page.goto("https://web.whatsapp.com/", timeout=30000)
            except Exception:
                pass
        _ensure_logged_in(page, settings)

        group_names: set[str] = set()
        # 1) Groups filter -> label groups.
        if _click_first(page, _FILTER_GROUPS_SELECTORS):
            page.wait_for_timeout(600)
            group_names = set(_scrape_chat_names(page))
            _click_first(page, _FILTER_ALL_SELECTORS)
            page.wait_for_timeout(600)
        # 2) All chats.
        all_names = _scrape_chat_names(page)
        if not all_names and not group_names:
            _capture_debug(page, "list-chats-empty")

    chats = [
        {"name": name, "kind": "group" if name in group_names else "contact"}
        for name in all_names
    ]
    # Include any group-only names not present in the "All" pass.
    for name in group_names:
        if name not in {c["name"] for c in chats}:
            chats.append({"name": name, "kind": "group"})
    chats.sort(key=lambda c: (c["kind"] != "group", c["name"].lower()))
    return {
        "profile_id": profile_id,
        "chats": chats,
        "count": len(chats),
        "group_count": sum(1 for c in chats if c["kind"] == "group"),
        "checked_at": _now_iso(),
    }


# --- Ad-hoc send to any chat by name (no saved target needed) ---------------

def send_to_chat(profile_id: str, chat_name: str, message: str, attachment_name: str | None = None, attachment_content: bytes | None = None) -> dict[str, Any]:
    return _run_on_driver_thread(_send_to_chat_impl, profile_id, chat_name, message, attachment_name, attachment_content)


def _send_to_chat_impl(profile_id: str, chat_name: str, message: str, attachment_name: str | None = None, attachment_content: bytes | None = None) -> dict[str, Any]:
    settings = _load_settings()
    profiles = _load_profiles()
    profile = _resolve_profile(profile_id, profiles)
    chat_name = (chat_name or "").strip()
    if not chat_name:
        raise ValueError("A chat name is required.")
    staged_attachment = None
    if attachment_name and attachment_content is not None:
        staged_attachment = _stage_attachment(attachment_name, attachment_content)
    profile["last_used_at"] = _now_iso()
    _save_profiles(profiles)

    if not (settings.get("delivery_mode") == "selenium" and _HAVE_PLAYWRIGHT):
        raise RuntimeError("Automated sending is not enabled (set delivery mode to the automation engine).")

    # A raw phone number (e.g. "+91 95855 50296") won't reliably surface in the
    # name search unless it's a saved contact, so route it through the direct
    # send?phone= path instead. Anything else is a chat/group name -> search path.
    digits = _sanitize_phone(chat_name)
    looks_like_phone = len(digits) >= 8 and bool(re.fullmatch(r"[\d +\-()]+", chat_name))
    try:
        if looks_like_phone:
            result = _send_via_playwright(profile, settings, digits, message, staged_attachment)
        else:
            target = {"target_kind": "group", "target_name": chat_name, "target_ref": chat_name}
            result = _send_target_via_playwright(profile, target, settings, message, staged_attachment)
        _record_send(profile, chat_name, "chat", "sent", message, "", None)
        return result
    except Exception as exc:
        snapshot = _latest_debug_snapshot()
        _record_send(profile, chat_name, "chat", "failed", message, str(exc), snapshot)
        return _headless_failure(exc, staged_attachment, chat_name)


# --- Read a chat's message history (desktop-WhatsApp-like) ------------------

def _parse_msg_date(meta: str) -> "datetime | None":
    """Best-effort parse of the date inside a message's data-pre-plain-text
    (e.g. "[10:30 am, 4/9/2026] Sender: "). Date order varies by locale, so we
    disambiguate D/M vs M/D when one value is > 12; otherwise assume D/M/Y (the
    store's locale). Returns None when it can't be parsed."""
    m = re.search(r",\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\]", meta or "")
    if not m:
        return None
    a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    day, mon = a, b
    if a <= 12 and b > 12:  # value b can only be a day -> input was M/D/Y
        day, mon = b, a
    for d, mo in ((day, mon), (mon, day)):
        try:
            return datetime(y, mo, d)
        except ValueError:
            continue
    return None


def read_chat_messages(profile_id: str, chat_name: str, days: int = 10, limit: int = 500) -> dict[str, Any]:
    return _run_on_driver_thread(_read_chat_messages_impl, profile_id, chat_name, days, limit)


def _read_chat_messages_impl(profile_id: str, chat_name: str, days: int = 10, limit: int = 500) -> dict[str, Any]:
    """Open a chat by its visible name and scrape its message history for the
    last ``days`` days, scrolling up (like scrolling back in desktop WhatsApp)
    until messages older than the cutoff are loaded or a scroll cap is hit."""
    if not _HAVE_PLAYWRIGHT:
        raise RuntimeError("Playwright is not installed in the backend runtime.")
    settings = _load_settings()
    profiles = _load_profiles()
    profile = _resolve_profile(profile_id, profiles)
    chat_name = (chat_name or "").strip()
    if not chat_name:
        raise ValueError("A chat name is required.")
    days = max(1, min(days, 90))
    limit = max(1, min(limit, 1000))
    cutoff = datetime.now() - timedelta(days=days)
    target = {"target_kind": "group", "target_name": chat_name, "target_ref": chat_name, "target_id": ""}

    def _oldest_loaded_date(page: Any) -> "datetime | None":
        try:
            first = page.locator("xpath=(//div[@id='main']//div[contains(@class,'message-')])[1]")
            if first.count() > 0:
                return _parse_msg_date(first.get_attribute("data-pre-plain-text") or "")
        except Exception:
            pass
        return None

    with _DRIVER_LOCK:
        page = _acquire_context(profile, settings, bool(settings.get("headless", True)))
        _open_target_chat(page, target, settings)
        # Scroll the message panel up until we've loaded past the cutoff date or
        # hit the cap (guards against very large / infinite histories).
        max_passes = min(80, max(8, days * 6))
        for _ in range(max_passes):
            try:
                page.evaluate(
                    "() => { const rows = document.querySelectorAll('#main [class*=\"message-\"]');"
                    " if (!rows.length) return;"
                    " let el = rows[0].parentElement;"
                    " while (el && el.scrollHeight <= el.clientHeight) el = el.parentElement;"
                    " if (el) el.scrollTop = 0; }"
                )
            except Exception:
                pass
            page.wait_for_timeout(450)
            oldest = _oldest_loaded_date(page)
            if oldest is not None and oldest < cutoff:
                break

        nodes = page.locator("xpath=//div[@id='main']//div[contains(@class,'message-')]")
        count = nodes.count()
        out: list[dict[str, Any]] = []
        for i in range(count):
            node = nodes.nth(i)
            classes = (node.get_attribute("class") or "").lower()
            if "message-in" in classes:
                direction = "incoming"
            elif "message-out" in classes:
                direction = "outgoing"
            else:
                direction = "system"
            text_nodes = node.locator("xpath=.//span[contains(@class,'selectable-text')]")
            parts = [(text_nodes.nth(j).inner_text() or "").strip() for j in range(text_nodes.count())]
            text = " ".join(p for p in parts if p).strip()
            meta = (node.get_attribute("data-pre-plain-text") or "").strip()
            if not text and not meta:
                continue
            # Filter to the requested window when we can read the date; keep
            # undated rows (system/date separators, media-only) so context isn't lost.
            mdate = _parse_msg_date(meta)
            if mdate is not None and mdate < cutoff:
                continue
            out.append({"direction": direction, "text": text, "meta": meta})
        out = out[-limit:]
    return {
        "profile_id": profile_id,
        "chat_name": chat_name,
        "days": days,
        "messages": out,
        "count": len(out),
        "checked_at": _now_iso(),
    }


# --- Send log (inspect slow / failed sends) --------------------------------

def _load_send_log() -> list[dict[str, Any]]:
    rows = _read_json(SEND_LOG_FILE, [])
    return rows if isinstance(rows, list) else []


def _latest_debug_snapshot() -> str | None:
    """Path (basename) of the newest debug capture, to link a failure to it."""
    try:
        files = sorted(DEBUG_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[0].name if files else None
    except Exception:
        return None


def _record_send(profile: dict[str, Any], target_name: str, kind: str, status: str, message: str, error: str, snapshot: str | None) -> None:
    try:
        rows = _load_send_log()
        rows.append(
            {
                "id": str(uuid.uuid4()),
                "profile_id": profile.get("profile_id", ""),
                "profile_name": profile.get("profile_name", ""),
                "target_name": target_name,
                "kind": kind,
                "status": status,
                "message_preview": (message or "")[:140],
                "error": error or "",
                "snapshot": snapshot or "",
                "at": _now_iso(),
            }
        )
        _write_json(SEND_LOG_FILE, rows[-SEND_LOG_MAX:])
    except Exception:
        pass


def get_send_log(limit: int = 100) -> dict[str, Any]:
    rows = _load_send_log()
    rows = sorted(rows, key=lambda r: r.get("at", ""), reverse=True)[: max(1, min(limit, SEND_LOG_MAX))]
    return {"entries": rows, "count": len(rows)}


def _warmup_log(msg: str) -> None:
    """Append a timestamped line to storage/whatsapp/warmup.log (best-effort)."""
    try:
        _ensure_dirs()
        line = f"{_now_iso()}  {msg}\n"
        with (STORAGE_DIR / "warmup.log").open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


def _warmup_impl() -> None:
    """Warm the default profile's WhatsApp Web session so the FIRST real send of
    the day doesn't fail against a cold / half-loaded page.

    The daily failure the user sees is exactly this: on a fresh backend start
    WhatsApp Web hasn't finished authenticating and still shows the "What's new"
    startup modal (which stops the search box from mounting), so the first send
    errors and only the second succeeds. Here we pre-load the session, dismiss
    that modal (via _ensure_logged_in -> _dismiss_startup_dialogs) and, when
    automated sending is configured, fire one self-message so the whole send
    path is primed. Runs on the single driver thread; never raises."""
    if not _HAVE_PLAYWRIGHT:
        _warmup_log("skipped: Playwright not installed")
        return
    settings = _load_settings()
    profiles = _load_profiles()
    if not profiles:
        _warmup_log("skipped: no profiles configured")
        return
    profile = next((row for row in profiles if row.get("is_default")), profiles[0])
    want_headless = bool(settings.get("headless", True))
    try:
        with _DRIVER_LOCK:
            page = _acquire_context(profile, settings, want_headless)
            _ensure_logged_in(page, settings)  # also dismisses the startup modal
    except Exception as exc:
        _warmup_log(f"context/login not ready for '{profile.get('profile_name')}': {exc}")
        return

    # Only actively send when the automated (Playwright) path is the delivery
    # mode -- in manual_browser mode a "send" would pop a visible window, which
    # is not wanted at unattended startup. Pre-loading the context above is the
    # useful part in that case.
    if settings.get("delivery_mode") != "selenium":
        _warmup_log(f"session pre-loaded for '{profile.get('profile_name')}' (manual mode, no self-message)")
        return
    phone = _sanitize_phone(profile.get("default_phone", ""))
    if not phone:
        _warmup_log(f"session pre-loaded for '{profile.get('profile_name')}' (no default_phone for self-message)")
        return
    try:
        # Call the impl directly (not the public send_message, which re-submits
        # to the single-worker driver executor -- doing that from within the
        # driver thread would deadlock). _send_via_playwright re-enters the
        # reentrant _DRIVER_LOCK safely.
        _send_via_playwright(
            profile,
            settings,
            phone,
            f"Nexora HO backend started — WhatsApp session warmed up ({_now_iso()}).",
            None,
        )
        _warmup_log(f"self-message sent for '{profile.get('profile_name')}' -> {phone}")
    except Exception as exc:
        _warmup_log(f"self-message failed for '{profile.get('profile_name')}': {exc}")


def warmup_on_startup(delay_seconds: float = 8.0) -> None:
    """Kick off the WhatsApp warm-up in a background daemon thread so it never
    blocks or crashes backend startup. Safe to call unconditionally from the
    FastAPI startup hook."""
    def _runner() -> None:
        try:
            time.sleep(max(0.0, delay_seconds))  # let uvicorn bind the port first
            _run_on_driver_thread(_warmup_impl)
        except Exception:
            pass

    try:
        threading.Thread(target=_runner, name="wa-warmup", daemon=True).start()
    except Exception:
        pass


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
        "send_log": get_send_log(50)["entries"],
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
    profiles = _load_profiles()
    return {
        "settings": settings,
        "profiles": profiles,
        "targets": _load_targets(),
        "messages": _load_inbox()[:100],
        "capabilities": _capabilities(settings, profiles),
    }


def upsert_profile(payload: dict[str, Any]) -> dict[str, Any]:
    profiles = _load_profiles()
    # `payload.get("profile_id", "")` returns the JSON `null` the Pydantic
    # model sends for an unset optional field, not the "" default -- and
    # str(None) == "None", a truthy string that skipped the uuid4()
    # fallback below. `or ""` collapses None/""/missing to the same "".
    profile_id = str(payload.get("profile_id") or "").strip() or str(uuid.uuid4())
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
    _run_on_driver_thread(_shutdown_context, profile_id)
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
    return _run_on_driver_thread(_launch_qr_impl, profile_id)


def _launch_qr_impl(profile_id: str) -> dict[str, Any]:
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


def check_status(profile_id: str) -> dict[str, Any]:
    return _run_on_driver_thread(_check_status_impl, profile_id)


def _check_status_impl(profile_id: str) -> dict[str, Any]:
    """Headless check of whether this profile's saved session is still logged
    in to WhatsApp Web, without sending anything. Reuses a live background
    context if one is already open; otherwise opens one just for the check."""
    settings = _load_settings()
    profiles = _load_profiles()
    profile = _resolve_profile(profile_id, profiles)
    with _DRIVER_LOCK:
        page = _acquire_context(profile, settings, want_headless=True)
        try:
            page.wait_for_timeout(1500)
        except Exception:
            pass
        logged_in = _is_logged_in(page)
    return {
        "profile_id": profile_id,
        "logged_in": logged_in,
        "checked_at": _now_iso(),
    }


# WhatsApp Web renders the login QR inside a <canvas> under a div[data-ref].
# Selectors (most specific first) so we screenshot the QR image itself, not the
# whole landing page. The aria-label wording drifts ("Scan me!", "Scan this QR
# code to link a device!"), so match on the "Scan" prefix.
_QR_SELECTORS = [
    "xpath=//canvas[contains(@aria-label,'Scan')]",
    "xpath=//div[@data-ref]//canvas",
    "xpath=//div[@data-ref]",
    "xpath=//canvas",
]
# When the QR expires WA hides it behind a "Click to reload QR code" button;
# clicking it re-renders a fresh canvas in place (no page reload).
_QR_RELOAD_SELECTORS = [
    "xpath=//div[@role='button'][contains(translate(., 'RELOAD', 'reload'), 'reload')]",
    "xpath=//button[contains(translate(., 'RELOAD', 'reload'), 'reload')]",
    "xpath=//span[@data-icon='refresh-large']/ancestor::*[@role='button'][1]",
]


def _locate_qr(page: Any) -> Any | None:
    for sel in _QR_SELECTORS:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                return loc.first
        except Exception:
            continue
    return None


def _maybe_reload_qr(page: Any) -> None:
    for sel in _QR_RELOAD_SELECTORS:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                _safe_click(loc.first)
                page.wait_for_timeout(800)
                return
        except Exception:
            continue


def get_login_qr(profile_id: str) -> dict[str, Any]:
    return _run_on_driver_thread(_get_login_qr_impl, profile_id)


def _get_login_qr_impl(profile_id: str) -> dict[str, Any]:
    """Headless-capture the WhatsApp Web login QR for this profile and return it
    as a PNG data URI so the user can scan it from their own browser -- the
    server-side Firefox window is never visible to a remote/HO backend.

    Reuses the SAME headless context the background sends use, so once the user
    scans this QR the session is already logged in for the very next send. If
    the profile is already logged in, returns logged_in=True with no QR.
    """
    settings = _load_settings()
    profiles = _load_profiles()
    profile = _resolve_profile(profile_id, profiles)
    qr_data_uri: str | None = None
    logged_in = False
    with _DRIVER_LOCK:
        page = _acquire_context(profile, settings, want_headless=True)
        try:
            if "web.whatsapp.com" not in (page.url or ""):
                page.goto("https://web.whatsapp.com/", timeout=30000)
        except Exception:
            pass
        # Keep this short: the frontend re-polls every few seconds and every
        # call serializes on the single driver thread, so a long block here
        # backs up the queue. The QR normally renders in 1-2s.
        deadline = time.time() + 12
        while time.time() < deadline:
            if _is_logged_in(page):
                logged_in = True
                break
            _maybe_reload_qr(page)
            qr = _locate_qr(page)
            if qr is not None:
                try:
                    png = qr.screenshot()
                    qr_data_uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
                    break
                except Exception:
                    pass
            try:
                page.wait_for_timeout(500)
            except Exception:
                break
        else:
            logged_in = _is_logged_in(page)
        if qr_data_uri is None and not logged_in:
            _capture_debug(page, "qr-capture-fail")
    profile["last_used_at"] = _now_iso()
    _save_profiles(profiles)
    return {
        "profile_id": profile_id,
        "logged_in": logged_in,
        "qr_data_uri": qr_data_uri,
        "checked_at": _now_iso(),
    }


def logout_profile(profile_id: str) -> dict[str, Any]:
    return _run_on_driver_thread(_logout_profile_impl, profile_id)


def _logout_profile_impl(profile_id: str) -> dict[str, Any]:
    """Clear this profile's WhatsApp Web session (cookies/local storage) so
    the next send/launch requires a fresh QR scan. Unlike delete_profile,
    the saved profile record (name, targets, message history) is kept."""
    profiles = _load_profiles()
    profile = _resolve_profile(profile_id, profiles)
    with _DRIVER_LOCK:
        _shutdown_context(profile_id)
        session_dir = _firefox_profile_dir(profile)
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
    profile["last_used_at"] = _now_iso()
    saved = _save_profiles(profiles)
    return {
        "profile_id": profile_id,
        "logged_in": False,
        "profiles": saved,
        "capabilities": _capabilities(_load_settings(), saved),
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
    return _run_on_driver_thread(_send_message_impl, profile_id, phone, message, attachment_name, attachment_content)


def _send_message_impl(profile_id: str, phone: str, message: str, attachment_name: str | None = None, attachment_content: bytes | None = None) -> dict[str, Any]:
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
    profile_id = str(payload.get("profile_id") or "").strip()
    if not profile_id:
        raise ValueError("Profile is required for a WhatsApp target.")
    _resolve_profile(profile_id, profiles)
    targets = _load_targets()
    # See upsert_profile: None -> "" here too, so a fresh target actually
    # gets a uuid4() instead of the literal string "None".
    target_id = str(payload.get("target_id") or "").strip() or str(uuid.uuid4())
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
    return _run_on_driver_thread(_send_target_message_impl, target_id, message, attachment_name, attachment_content)


def _send_target_message_impl(target_id: str, message: str, attachment_name: str | None = None, attachment_content: bytes | None = None) -> dict[str, Any]:
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
        label = target["target_name"] or target["target_ref"]
        try:
            result = _send_target_via_playwright(profile, target, settings, message, staged_attachment)
            _record_send(profile, label, target["target_kind"], "sent", message, "", None)
            return result
        except Exception as exc:
            _record_send(profile, label, target["target_kind"], "failed", message, str(exc), _latest_debug_snapshot())
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
    return _run_on_driver_thread(_sync_target_messages_impl, target_id, limit)


def _sync_target_messages_impl(target_id: str, limit: int = 20) -> dict[str, Any]:
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
