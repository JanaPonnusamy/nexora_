"""HO deployment orchestration.

Runs the install as an ordered, rollback-protected sequence and exposes the
post-install health check. The wizard GUI drives this; keeping the logic here
makes it independently testable and reusable by the uninstaller/ops tooling.

Internal ordering is dependency-correct (config + files + database must exist
before the service starts, and the frontend must be deployed before the service
serves it), which realises the requested workflow:

    SQL config -> DB deploy -> configure -> backend -> service -> frontend ->
    health check.
"""
import shutil
from pathlib import Path

from .backend_deployer import BackendDeployer
from .frontend_deployer import FrontendDeployer
from .health_check import HealthChecker
from .installer_logging import Rollback
from .service_manager import ServiceManager
from .sql_deployer import SqlDeployer, SqlError


class Deployment:
    def __init__(self, config, logger):
        self.cfg = config
        self.logger = logger                      # InstallLogger (callable)
        self.rollback = Rollback(log=logger)
        self.sql = SqlDeployer(config, log=logger)
        self.backend = BackendDeployer(config, log=logger)
        self.frontend = FrontendDeployer(config, log=logger)
        self.service = ServiceManager(config.install_path, log=logger)

    # ---- STEP 4 -----------------------------------------------------------

    def test_sql(self):
        return self.sql.test_connection()

    def database_exists(self):
        return self.sql.database_exists()

    # ---- STEP 5-9: full install ------------------------------------------

    def install(self, replace_existing=False):
        root = Path(self.cfg.install_path)
        existed_before = root.exists()
        try:
            self.logger.info("[STEP 7] Installing backend files...")
            self.backend.create_directories()
            if not existed_before:
                self.rollback.push(
                    f"remove install dir {root}",
                    lambda: shutil.rmtree(root, ignore_errors=True),
                )
            self.backend.copy_backend_files()
            self.backend.deploy_uninstaller()

            self.logger.info("[STEP 6] Generating production configuration...")
            self.backend.write_config()

            self.logger.info("[STEP 9] Deploying production frontend...")
            self.frontend.deploy()

            self.logger.info("[STEP 5] Deploying database (restore .bak)...")
            bak = self.backend.stage_backup()
            if self.sql.database_exists() and not replace_existing:
                raise SqlError(
                    f"Database {self.cfg.database} already exists. Re-run and "
                    "choose 'Replace existing database' to overwrite it."
                )
            self.sql.restore_database(bak, replace=replace_existing)
            self.sql.verify_restore()

            self.logger.info("[STEP 8] Installing Windows service...")
            self.service.install()
            self.rollback.push("remove service", self.service.remove)
            self.logger.info("[STEP 8] Starting Windows service...")
            self.service.start()

            self.rollback.commit()
            self.logger.info("Installation steps completed.")
        except Exception as ex:
            self.logger.error(f"Install failed: {ex}")
            self.logger.info("Rolling back...")
            self.rollback.unwind()
            raise

    # ---- STEP 10 ----------------------------------------------------------

    def validate(self):
        return HealthChecker(self.cfg, log=self.logger).run()
