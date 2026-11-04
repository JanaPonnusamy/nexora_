"""HO calls made by Nexora Setup.

ONE sign-in per run: store users are single-session on HO (a second login is
refused with 409), so the Connect step's token is reused for every call and
released with /logout when the kit finishes."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import requests


class HoError(Exception):
    pass


def normalize_url(url) -> str:
    """'122.252.246.181:8444  (label)' -> 'http://122.252.246.181:8444'."""
    text = (url or "").strip()
    text = text.split()[0] if text else ""
    if text and "://" not in text:
        text = "http://" + text
    return text.rstrip("/")


def _detail(resp) -> str:
    try:
        body = resp.json()
        detail = body.get("detail") if isinstance(body, dict) else None
        if isinstance(detail, list):  # FastAPI validation errors
            detail = "; ".join(str(d.get("msg", d)) if isinstance(d, dict) else str(d) for d in detail)
        if detail:
            return str(detail)
    except ValueError:
        pass
    return (resp.text or "").strip()[:200] or f"HTTP {resp.status_code}"


class SetupClient:
    def __init__(self, base_url, timeout=30):
        self.base = normalize_url(base_url)
        self.timeout = timeout
        self.token = None
        self.user = None

    def _call(self, method, path, timeout=None, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            resp = requests.request(method, self.base + path, headers=headers,
                                    timeout=timeout or self.timeout, **kwargs)
        except requests.RequestException as ex:
            raise HoError(f"Cannot reach HO at {self.base}: {ex}") from ex
        if resp.status_code >= 400:
            raise HoError(f"{_detail(resp)} (HTTP {resp.status_code} on {path})")
        return resp

    # ---- connect ----------------------------------------------------------

    def probe(self) -> dict:
        body = self._call("GET", "/health", timeout=10).json()
        if str(body.get("status", "")).lower() != "healthy":
            raise HoError(f"HO at {self.base} reports it is not healthy: {body}")
        return body

    def login(self, username, password) -> dict:
        if self.token:
            return self.user
        try:
            resp = requests.post(self.base + "/api/auth/login",
                                 json={"username": username, "password": password},
                                 timeout=self.timeout)
        except requests.RequestException as ex:
            raise HoError(f"Cannot reach HO at {self.base}: {ex}") from ex
        if resp.status_code == 409:
            raise HoError("This login is already signed in on another PC or app. "
                          "Sign out there first, or use another login.")
        if resp.status_code >= 400:
            raise HoError(f"Sign-in failed: {_detail(resp)}")
        body = resp.json()
        self.token = body.get("token")
        if not self.token:
            raise HoError("HO returned no token")
        self.user = body.get("user") or {}
        return self.user

    def logout(self):
        """Free the single-session lease so the user can sign in elsewhere."""
        if not self.token:
            return
        try:
            self._call("POST", "/api/auth/logout", timeout=10)
        except HoError:
            pass
        self.token = None

    # ---- setup API --------------------------------------------------------

    def stores(self) -> dict:
        return self._call("GET", "/api/setup/v1/stores").json()

    def plan(self, spec) -> dict:
        return self._call("POST", "/api/setup/v1/plan", json={"spec": spec}).json()

    def download_controller(self, version, dest, sha256=None, progress=None) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        digest = hashlib.sha256()
        try:
            with requests.get(f"{self.base}/api/setup/v1/packages/controller/{version}",
                              headers={"Authorization": f"Bearer {self.token}"},
                              stream=True, timeout=300) as resp:
                if resp.status_code >= 400:
                    raise HoError(f"Controller download failed: {_detail(resp)}")
                total = int(resp.headers.get("Content-Length") or 0)
                got = 0
                with open(part, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        fh.write(chunk)
                        digest.update(chunk)
                        got += len(chunk)
                        if progress:
                            progress(got, total)
        except requests.RequestException as ex:
            raise HoError(f"Controller download failed: {ex}") from ex
        if sha256 and digest.hexdigest().lower() != str(sha256).lower():
            part.unlink()
            raise HoError("The downloaded Device Controller failed its checksum; run Setup again.")
        os.replace(str(part), str(dest))
        return dest

    def register_device(self, payload) -> dict:
        return self._call("POST", "/api/auth/device/register", json=payload).json()

    def install(self, controller_device_id, components, install_dirs) -> list:
        body = {"controller_device_id": controller_device_id, "components": list(components),
                "install_dirs": dict(install_dirs or {})}
        return self._call("POST", "/api/setup/v1/install", json=body).json().get("commands") or []

    def commands(self, ids) -> list:
        return self._call("GET", "/api/setup/v1/commands",
                          params={"ids": ",".join(ids)}).json().get("commands") or []
