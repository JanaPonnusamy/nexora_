"""Deployment orchestration: runs install + validation as an ordered sequence.

The wizard GUI drives this; keeping the logic here makes it independently
testable and reusable by the settings utility.
"""
from . import WATCHDOG_DISPLAY_NAME, WATCHDOG_EXE_NAME, WATCHDOG_SERVICE_NAME
from .agent_config import build_config
from .ho_client import HoClient, HoConnectionError
from .installer import Installer
from .service_manager import ServiceManager


class DeploymentResult:
    def __init__(self):
        self.steps = []  # list of (label, ok, detail)

    def add(self, label, ok, detail=""):
        self.steps.append((label, ok, detail))
        return ok

    @property
    def ok(self):
        return all(ok for _, ok, _ in self.steps)


class Deployment:
    def __init__(self, ho_url, tenant, store, install_path,
                 log_level="INFO", log=None, route_urls=None):
        # ho_url = the route reachable from THIS machine (used to talk to HO
        # during install). route_urls = the ordered list written to the config
        # (LAN, static, domain) that the runtime fails over across.
        self.ho_url = ho_url.rstrip("/")
        self.tenant = tenant
        self.store = store
        self.install_path = install_path
        self.log_level = log_level
        self.route_urls = [u for u in (route_urls or []) if u] or [self.ho_url]
        self.log = log or (lambda msg: None)
        self.ho = HoClient(self.ho_url)
        self.installer = Installer(install_path, log=self.log)
        self.service = ServiceManager(install_path, log=self.log)
        self.watchdog = ServiceManager(
            install_path,
            log=self.log,
            service_name=WATCHDOG_SERVICE_NAME,
            service_display_name=WATCHDOG_DISPLAY_NAME,
            exe_name=WATCHDOG_EXE_NAME,
            module_name="store_agent_setup.watchdog_service",
            description=(
                "Keeps NexoraStoreAgent on the version and run-state HO wants, "
                "so it can be updated/started/stopped remotely."
            ),
        )
        self.ho_agent_config = None

    # ---- STEP 6: download -------------------------------------------------

    def download_configuration(self):
        self.log(f"downloading agent-config for store {self.store.get('store_id')}")
        self.ho_agent_config = self.ho.get_agent_config(self.store["store_id"])
        return self.ho_agent_config

    # ---- STEP 7-9: install + service -------------------------------------

    def install(self):
        if self.ho_agent_config is None:
            self.download_configuration()
        # Write ho_urls in the fixed operator order (LAN, static, domain),
        # independent of which route the wizard used to reach HO.
        agent_cfg = build_config(
            self.route_urls[0], self.tenant, self.store, self.install_path,
            log_level=self.log_level, fallback_urls=self.route_urls[1:],
        )
        self.installer.install(agent_cfg, self.ho_agent_config)
        self.service.install()
        self.watchdog.install()
        self.service.start()
        self.watchdog.start()
        return agent_cfg

    # ---- STEP 10: validation ---------------------------------------------

    def validate(self):
        result = DeploymentResult()

        # HO reachable
        try:
            self.ho.test_connection()
            result.add("HO reachable", True, self.ho_url)
        except HoConnectionError as ex:
            result.add("HO reachable", False, str(ex))

        # Config downloaded
        from .agent_config import config_path
        cfg_ok = config_path(self.install_path).is_file()
        ho_cfg_ok = (self.installer.root / "cache" / "ho_agent_config.json").is_file()
        result.add("Config downloaded", cfg_ok and ho_cfg_ok,
                   str(config_path(self.install_path)))

        # Service installed
        result.add("Service installed", self.service.is_installed())
        result.add("Watchdog installed", self.watchdog.is_installed())

        # Service running
        running = self.service.status() == "running"
        result.add("Service running", running, self.service.status())
        watchdog_running = self.watchdog.status() == "running"
        result.add("Watchdog running", watchdog_running, self.watchdog.status())

        # Heartbeat successful
        try:
            self.ho.post_heartbeat(
                self.store["store_id"],
                connection_type=self.ho_agent_config.get("connection_type")
                if self.ho_agent_config else None,
            )
            result.add("Heartbeat successful", True)
        except HoConnectionError as ex:
            result.add("Heartbeat successful", False, str(ex))

        return result
