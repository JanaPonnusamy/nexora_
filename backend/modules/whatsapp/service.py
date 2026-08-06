from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
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
PROFILES_DIR = STORAGE_DIR / "profiles"
SETTINGS_FILE = STORAGE_DIR / "settings.json"
PROFILES_FILE = STORAGE_DIR / "profiles.json"
TARGETS_FILE = STORAGE_DIR / "targets.json"
INBOX_FILE = STORAGE_DIR / "inbox.json"

DEFAULT_SETTINGS = {
    "browser_command": "",
    "delivery_mode": "manual_browser",
    "launch_wait_seconds": 15,
}


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
    return settings


def _save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULT_SETTINGS)
    merged.update(settings)
    if merged.get("delivery_mode") not in {"manual_browser", "selenium"}:
        merged["delivery_mode"] = "manual_browser"
    merged["browser_command"] = str(merged.get("browser_command", "")).strip()
    merged["launch_wait_seconds"] = int(merged.get("launch_wait_seconds", 15) or 15)
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


def _build_driver(profile: dict[str, Any], settings: dict[str, Any]):
    if not _HAVE_SELENIUM:
        raise RuntimeError("Selenium is not installed in the backend runtime.")
    options = webdriver.ChromeOptions()
    options.add_argument(f"user-data-dir={profile['session_dir']}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    browser_command = settings.get("browser_command", "")
    if browser_command and Path(browser_command).is_file():
        options.binary_location = browser_command
    return webdriver.Chrome(options=options)


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
        time.sleep(4)
        return url

    driver.get("https://web.whatsapp.com/")
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    time.sleep(4)
    search = wait.until(
        EC.presence_of_element_located((By.XPATH, "//div[@contenteditable='true' and @role='textbox']"))
    )
    search.click()
    search.send_keys(Keys.CONTROL, "a")
    search.send_keys(target["target_ref"] or target["target_name"])
    time.sleep(2)
    label = target["target_name"] or target["target_ref"]
    try:
        chat = wait.until(
            EC.element_to_be_clickable((By.XPATH, f"//*[@title={json.dumps(label)}]"))
        )
    except Exception:
        chat = wait.until(
            EC.element_to_be_clickable((By.XPATH, f"//*[contains(@title, {json.dumps(label)})]"))
        )
    chat.click()
    time.sleep(2)
    return "https://web.whatsapp.com/"


def _send_via_selenium(profile: dict[str, Any], settings: dict[str, Any], phone: str, message: str, attachment_path: str | None) -> dict[str, Any]:
    driver = _build_driver(profile, settings)
    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    url = _whatsapp_url(phone, message)
    try:
        driver.get(url)
        wait = WebDriverWait(driver, wait_seconds)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(5)

        if attachment_path:
            clip = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[@data-icon='clip']")))
            clip.click()
            file_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='file']")))
            file_input.send_keys(str(Path(attachment_path).resolve()))
            time.sleep(2)

        editable = wait.until(
            EC.presence_of_all_elements_located((By.XPATH, "//div[@contenteditable='true']"))
        )
        target = editable[-1]
        target.click()
        if message:
            target.send_keys(Keys.CONTROL, "a")
            target.send_keys(message)
        send = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[@data-icon='send']")))
        send.click()
        time.sleep(2)
        return {
            "status": "sent",
            "message": "Message sent through WhatsApp automation.",
            "mode": "selenium",
            "url": url,
        }
    finally:
        driver.quit()


def _send_target_via_selenium(profile: dict[str, Any], target: dict[str, Any], settings: dict[str, Any], message: str, attachment_path: str | None) -> dict[str, Any]:
    driver = _build_driver(profile, settings)
    wait_seconds = max(int(settings.get("launch_wait_seconds", 15) or 15), 10)
    wait = WebDriverWait(driver, wait_seconds)
    try:
        url = _open_target_chat(driver, target, settings, message)
        if attachment_path:
            clip = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[@data-icon='clip']")))
            clip.click()
            file_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='file']")))
            file_input.send_keys(str(Path(attachment_path).resolve()))
            time.sleep(3)

        editable = wait.until(
            EC.presence_of_all_elements_located((By.XPATH, "//div[@contenteditable='true']"))
        )
        target_box = editable[-1]
        target_box.click()
        if message:
            target_box.send_keys(Keys.CONTROL, "a")
            target_box.send_keys(message)
        send = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[@data-icon='send']")))
        send.click()
        time.sleep(2)
        return {
            "status": "sent",
            "message": f"Message sent to {target['target_name'] or target['target_ref']}.",
            "mode": "selenium",
            "url": url,
        }
    finally:
        driver.quit()


def _scrape_target_messages(profile: dict[str, Any], target: dict[str, Any], settings: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
    if not _HAVE_SELENIUM:
        raise RuntimeError("Selenium is not installed in the backend runtime.")
    driver = _build_driver(profile, settings)
    try:
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
    finally:
        driver.quit()


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


def update_settings(browser_command: str, delivery_mode: str, launch_wait_seconds: int) -> dict[str, Any]:
    settings = _save_settings(
        {
            "browser_command": browser_command,
            "delivery_mode": delivery_mode,
            "launch_wait_seconds": launch_wait_seconds,
        }
    )
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
    settings = _load_settings()
    profiles = _load_profiles()
    profile = _resolve_profile(profile_id, profiles)
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
