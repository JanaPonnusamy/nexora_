"""Post-install health check (wizard STEP 10).

Verifies the live deployment end-to-end and returns a structured result the
wizard renders as a deployment summary:

    SQL Connection -> Database Exists -> Backend Service Running ->
    API Responding -> Frontend Accessible
"""
import requests

from .service_manager import ServiceManager
from .sql_deployer import SqlDeployer, SqlError


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

        # 4. API responding
        base = f"http://127.0.0.1:{self.cfg.port}"
        try:
            resp = requests.get(f"{base}/health", timeout=10)
            healthy = (
                resp.ok and str(resp.json().get("status", "")).lower() == "healthy"
            )
            result.add("API Responding", healthy, f"{base}/health")
        except Exception as ex:
            result.add("API Responding", False, str(ex))

        # 5. Frontend accessible (served by the same backend service)
        try:
            resp = requests.get(f"{base}/", timeout=10)
            served = resp.ok and "<div id=\"root\">" in resp.text
            result.add("Frontend Accessible", served, self.cfg.frontend_url)
        except Exception as ex:
            result.add("Frontend Accessible", False, str(ex))

        return result
