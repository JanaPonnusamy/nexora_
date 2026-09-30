"""Post-install health check (wizard STEP 10).

Verifies the live deployment end-to-end and returns a structured result the
wizard renders as a deployment summary:

    SQL Connection -> Database Exists -> Backend Service Running ->
    API Responding -> Frontend Accessible
"""
import time

import requests

from .service_manager import ServiceManager
from .sql_deployer import SqlDeployer, SqlError

# How long the backend gets to import the app and bind its port after the SCM
# reports RUNNING, and how often to probe it meanwhile.
API_STARTUP_TIMEOUT = 90
API_POLL_INTERVAL = 2


class HealthResult:
    def __init__(self):
        self.checks = []  # (label, ok, detail)

    def add(self, label, ok, detail=""):
        self.checks.append((label, bool(ok), detail))
        return ok

    @property
    def ok(self):
        return all(ok for _, ok, _ in self.checks)


class HealthChecker:
    def __init__(self, config, log=None):
        self.cfg = config
        self._log = log or (lambda msg: None)

    def log(self, msg):
        self._log(msg)

    def run(self, app_only=False):
        result = HealthResult()
        sql = SqlDeployer(self.cfg, log=self.log)

        # SQL connection + Database Exists are skipped for app-only (developer)
        # builds where the database is provisioned manually.
        if not app_only:
            # 1. SQL connection
            try:
                sql.test_connection()
                result.add("SQL Connection", True, self.cfg.sql_server)
            except SqlError as ex:
                result.add("SQL Connection", False, str(ex))

            # 2. Database exists
            try:
                exists = sql.database_exists()
                result.add("Database Exists", exists, self.cfg.database)
            except SqlError as ex:
                result.add("Database Exists", False, str(ex))

        # 3. Backend service running
        svc = ServiceManager(self.cfg.install_path, log=self.log)
        running = svc.status() == "running"
        result.add("Backend Service Running", running, svc.status())

        # 4. API responding -- freshly started, the backend can take a while to
        # import the full module tree and bind its port even after the SCM
        # reports RUNNING, so poll instead of a single one-shot request.
        base = f"http://127.0.0.1:{self.cfg.port}"
        healthy, detail = self._wait_for_api(f"{base}/health")
        result.add("API Responding", healthy, detail)

        # 5. Frontend accessible (served by the same backend service). Only
        # worth checking once the API is confirmed up; otherwise this would
        # just re-race the same startup window.
        if healthy:
            try:
                resp = requests.get(f"{base}/", timeout=10)
                served = resp.ok and "<div id=\"root\">" in resp.text
                result.add("Frontend Accessible", served, self.cfg.frontend_url)
            except Exception as ex:
                result.add("Frontend Accessible", False, str(ex))
        else:
            result.add("Frontend Accessible", False, "skipped: API never came up")

        return result

    def _wait_for_api(self, url):
        """Poll ``url`` until it reports healthy or API_STARTUP_TIMEOUT expires.

        Returns (healthy, detail); on failure detail is the last error seen.
        """
        deadline = time.time() + API_STARTUP_TIMEOUT
        last = "no response"
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = requests.get(url, timeout=10)
                if resp.ok and str(resp.json().get("status", "")).lower() == "healthy":
                    self.log(f"API healthy after {attempt} attempt(s)")
                    return True, url
                last = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except Exception as ex:
                last = str(ex)
            if time.time() >= deadline:
                return False, f"{url} not healthy after {API_STARTUP_TIMEOUT}s: {last}"
            time.sleep(API_POLL_INTERVAL)
