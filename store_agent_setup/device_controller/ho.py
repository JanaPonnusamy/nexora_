"""HO connection for the controller: device-token auth (Ed25519 challenge,
reusing modules.device_identity), multi-URL failover, downloads, enrollment."""
from __future__ import annotations

import base64
import threading
import time
import uuid

from .util import log, normalize_urls

TOKEN_REFRESH_SECONDS = 20 * 60


class NotEnrolled(Exception):
    pass


class HoClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self._tokens = {}          # base_url -> (token, expires_at)
        self._active = None
        self._lock = threading.Lock()

    # ---- url selection ----------------------------------------------------

    def urls(self):
        return normalize_urls(self.cfg.get("ho_urls") or [])

    def active_url(self):
        urls = self.urls()
        if not urls:
            raise NotEnrolled("no HO URL configured")
        with self._lock:
            if self._active not in urls:
                self._active = urls[0]
            return self._active

    def _ordered(self):
        urls = self.urls()
        first = self.active_url()
        return [first] + [u for u in urls if u != first]

    def ready(self):
        return bool(self.urls() and self.cfg.get("device_id") and self.cfg.get("device_private_key_pem"))

    # ---- auth -------------------------------------------------------------

    def _token(self, base, force=False):
        import requests
        from modules.device_identity import crypto

        cached = self._tokens.get(base)
        if cached and not force and time.time() < cached[1]:
            return cached[0]
        device_id = self.cfg.get("device_id")
        if not device_id:
            raise NotEnrolled("device is not enrolled")
        ts = str(int(time.time()))
        nonce = uuid.uuid4().hex
        sig = base64.b64encode(
            crypto.sign(self.cfg["device_private_key_pem"], crypto.canonical_message(device_id, ts, nonce))
        ).decode("ascii")
        resp = requests.post(f"{base}/api/auth/device/token",
                             json={"device_id": device_id, "timestamp": ts, "nonce": nonce,
                                   "signature": sig}, timeout=20)
        if resp.status_code in (401, 403):
            raise NotEnrolled(f"HO rejected the device token request: {resp.text[:200]}")
        resp.raise_for_status()
        token = resp.json()["token"]
        self._tokens[base] = (token, time.time() + TOKEN_REFRESH_SECONDS)
        return token

    # ---- requests with failover -------------------------------------------

    def request(self, method, path, timeout=30, base=None, **kwargs):
        """Authenticated request. Tries the active URL first, then the others;
        the first URL that answers becomes active. 401 refreshes the token once."""
        import requests

        last_error = None
        candidates = [base] if base else self._ordered()
        for url in candidates:
            for attempt in (0, 1):
                try:
                    headers = dict(kwargs.pop("headers", {}) or {})
                    headers["Authorization"] = f"Bearer {self._token(url, force=attempt == 1)}"
                    resp = requests.request(method, url + path, headers=headers,
                                            timeout=timeout, **kwargs)
                    if resp.status_code == 401 and attempt == 0:
                        continue
                    if resp.status_code >= 500:
                        last_error = RuntimeError(f"{url}{path}: HTTP {resp.status_code}")
                        break
                    with self._lock:
                        self._active = url
                    return resp
                except NotEnrolled:
                    raise
                except Exception as ex:
                    last_error = ex
                    break
        raise last_error or RuntimeError("no HO URL reachable")

    def download(self, sources, path, dest, timeout=900):
        """Download `path` from the first source that has it (each source with
        its own token -- tokens are per node). This controller's own HO goes
        first: it fetches + caches packages it lacks from its peers, and the
        publishing node in `sources` is often LAN-only (unreachable from an
        internet store)."""
        import requests

        errors = []
        tried = []
        for base in normalize_urls(self.urls() + list(sources or [])):
            if base in tried:
                continue
            tried.append(base)
            try:
                token = self._token(base)
                with requests.get(base + path, headers={"Authorization": f"Bearer {token}"},
                                  stream=True, timeout=timeout) as r:
                    if r.status_code == 404:
                        errors.append(f"{base}: not held")
                        continue
                    r.raise_for_status()
                    with open(dest, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 1024):
                            f.write(chunk)
                log(f"[download] {path} from {base}")
                return base
            except Exception as ex:
                errors.append(f"{base}: {ex}")
        raise RuntimeError("download failed: " + "; ".join(errors))

    # ---- routes + enrollment ----------------------------------------------

    def learn_routes(self):
        """Merge HO's advertised routes (dbo.ho_routes) after the configured ones."""
        import requests

        try:
            base = self.active_url()
            resp = requests.get(base + "/api/bootstrap/routes", timeout=10)
            if not resp.ok:
                return False
            fetched = normalize_urls(resp.json().get("urls") or [])
        except Exception:
            return False
        merged = normalize_urls(self.urls() + fetched)
        if merged != self.urls():
            self.cfg["ho_urls"] = merged
            return True
        return False


def enroll_with_code(ho_urls, code, cfg, app_version, machine_name, fingerprint):
    """One-time registration with an HO-issued enrollment code."""
    import requests

    errors = []
    for base in normalize_urls(ho_urls):
        try:
            resp = requests.post(f"{base}/api/auth/device-controller/enroll", json={
                "code": code.strip().upper(),
                "device_fingerprint": fingerprint,
                "public_key": cfg["device_public_key_pem"],
                "machine_name": machine_name,
                "app_version": app_version,
            }, timeout=20)
            if resp.status_code >= 400:
                errors.append(f"{base}: HTTP {resp.status_code} {resp.text[:200]}")
                if resp.status_code in (400, 403, 422):
                    break  # the code itself was rejected; other URLs will say the same
                continue
            return resp.json()["device_id"]
        except Exception as ex:
            errors.append(f"{base}: {ex}")
    raise RuntimeError("enrollment failed: " + "; ".join(errors))
