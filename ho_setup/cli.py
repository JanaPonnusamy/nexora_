"""Headless deployment CLI, packaged as HO_Deploy.exe.

The Inno Setup installer (HO_Setup.exe) drives this for every step that needs
the real deployment logic: test the SQL connection, generate configuration,
restore NEXORA_PLATFORM.bak, install/start the Windows service, run the health
check, and (on uninstall) remove the service.

All parameters are read from an INI file (written by the Inno wizard) so secrets
never appear on the command line:

    [deploy]
    server      = localhost\\SQLEXPRESS
    auth_mode   = SQL            ; SQL | WINDOWS
    username    = sa
    password    = ******
    database    = NEXORA_PLATFORM
    install_dir = C:\\Program Files\\UniNex\\HO
    public_host = HO-SERVER
    port        = 8000
    replace     = false          ; overwrite an existing database

Usage:
    HO_Deploy.exe test-sql      --params <file>
    HO_Deploy.exe db-exists     --params <file>          (exit 0=yes 3=no)
    HO_Deploy.exe configure     --params <file>
    HO_Deploy.exe restore       --params <file> [--bak <path>] [--replace]
    HO_Deploy.exe install-service --params <file>
    HO_Deploy.exe health        --params <file>
    HO_Deploy.exe deploy        --params <file>          (configure+restore+service+health)
    HO_Deploy.exe uninstall     --install-dir <dir> [--dropdb]

Exit code 0 = success, non-zero = failure (Inno aborts on non-zero).
"""
import argparse
import configparser
import sys
from datetime import datetime
from pathlib import Path

from . import BACKUP_FILE_NAME
from .ho_config import HoConfig, default_public_host

# Persisted log handle. The installer reads this file to show the operator the
# ACTUAL Windows error (e.g. the sc.exe message) when deployment fails.
_LOG_FH = None


def _set_log_file(path):
    global _LOG_FH
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        _LOG_FH = open(path, "a", encoding="utf-8", buffering=1)
        _LOG_FH.write(f"\n==== HO_Deploy {datetime.now().isoformat()} ====\n")
    except OSError:
        _LOG_FH = None


def _log(msg):
    print(msg, flush=True)
    if _LOG_FH is not None:
        try:
            _LOG_FH.write(str(msg) + "\n")
        except OSError:
            pass


def _load_params(path):
    parser = configparser.ConfigParser()
    if not Path(path).is_file():
        raise SystemExit(f"params file not found: {path}")
    parser.read(path, encoding="utf-8")
    if not parser.has_section("deploy"):
        raise SystemExit("params file missing [deploy] section")
    return parser["deploy"]


def _config_from_params(p):
    return HoConfig(
        sql_server=p.get("server", "localhost").strip(),
        auth_mode=p.get("auth_mode", "SQL").strip().upper(),
        sql_username=p.get("username", "sa").strip(),
        sql_password=p.get("password", ""),
        database=p.get("database", "NEXORA_PLATFORM").strip() or "NEXORA_PLATFORM",
        install_path=p.get("install_dir", "").strip(),
        public_host=p.get("public_host", "").strip() or default_public_host(),
        port=int(p.get("port", "8000") or "8000"),
    )


def _truthy(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


# ---- commands -------------------------------------------------------------

def cmd_test_sql(cfg, args):
    from .sql_deployer import SqlDeployer, SqlError

    try:
        version = SqlDeployer(cfg, log=_log).test_connection()
        _log("OK: " + version.splitlines()[0])
        return 0
    except SqlError as ex:
        _log("FAIL: " + str(ex))
        return 1


def cmd_db_exists(cfg, args):
    from .sql_deployer import SqlDeployer, SqlError

    try:
        exists = SqlDeployer(cfg, log=_log).database_exists()
        _log("EXISTS" if exists else "ABSENT")
        return 0 if exists else 3
    except SqlError as ex:
        _log("FAIL: " + str(ex))
        return 1


def cmd_configure(cfg, args):
    from .frontend_deployer import FrontendDeployer

    cfg.config_dir.mkdir(parents=True, exist_ok=True)
    cfg.log_path.mkdir(parents=True, exist_ok=True)
    cfg.upload_path.mkdir(parents=True, exist_ok=True)
    cfg.write_config_files(log=_log)
    FrontendDeployer(cfg, log=_log).configure()
    _log("configuration written")
    return 0


def cmd_restore(cfg, args):
    from .sql_deployer import SqlDeployer, SqlError

    bak = args.bak or str(cfg.root / "backups" / BACKUP_FILE_NAME)
    if not Path(bak).is_file():
        _log(f"FAIL: backup not found: {bak}")
        return 1
    replace = args.replace or _truthy(getattr(args, "_replace_param", "false"))
    sql = SqlDeployer(cfg, log=_log)
    try:
        if sql.database_exists() and not replace:
            _log("FAIL: database exists and --replace not set")
            return 2
        sql.restore_database(bak, replace=replace)
        sql.verify_restore()
        _log("restore OK")
        return 0
    except SqlError as ex:
        _log("FAIL: " + str(ex))
        return 1


def cmd_install_service(cfg, args):
    from . import SERVICE_NAME
    from .service_manager import ServiceError, ServiceManager

    svc = ServiceManager(cfg.install_path, log=_log)
    try:
        svc.install()
        svc.start()
    except ServiceError as ex:
        _log("FAIL: service installation error: " + str(ex))
        return 1
    except Exception as ex:  # any other failure must also abort the install
        _log("FAIL: unexpected service installation error: " + repr(ex))
        return 1

    # Mandatory verification: the service MUST exist and be running. Without
    # this the installer could report success when sc.exe silently did nothing.
    if not svc.is_installed():
        _log(f"FAIL: service {SERVICE_NAME} does not exist after install "
             "(sc create did not register it - check Administrator rights).")
        return 1
    state = svc.status()
    if state != "running":
        _log(f"FAIL: service {SERVICE_NAME} exists but is not running "
             f"(state={state}).")
        return 1
    _log(f"service {SERVICE_NAME} installed, registered and running")
    return 0


def cmd_verify_service(cfg, args):
    """Final gate used by the installer: succeed only if the service exists."""
    from . import SERVICE_NAME
    from .service_manager import ServiceManager

    svc = ServiceManager(cfg.install_path, log=_log)
    if not svc.is_installed():
        _log(f"FAIL: service {SERVICE_NAME} is not installed.")
        return 1
    state = svc.status()
    if state != "running":
        _log(f"FAIL: service {SERVICE_NAME} is not running (state={state}).")
        return 1
    _log(f"OK: service {SERVICE_NAME} present and running.")
    return 0


def cmd_health(cfg, args):
    from .health_check import HealthChecker

    app_only = getattr(args, "app_only", False) or getattr(args, "skip_db", False)
    result = HealthChecker(cfg, log=_log).run(app_only=app_only)
    for label, ok, detail in result.checks:
        _log(f"[{'OK' if ok else 'XX'}] {label}" + (f"  ({detail})" if detail else ""))
    return 0 if result.ok else 1


def cmd_deploy(cfg, args):
    if getattr(args, "skip_db", False):
        steps = (cmd_configure, cmd_install_service, cmd_health)
    else:
        steps = (cmd_configure, cmd_restore, cmd_install_service, cmd_health)
    for step in steps:
        rc = step(cfg, args)
        if rc != 0:
            _log(f"deploy aborted at {step.__name__} (rc={rc})")
            return rc
    _log("deploy complete")
    return 0


def cmd_uninstall(cfg, args):
    from .uninstaller import run_uninstall

    run_uninstall(
        args.install_dir,
        drop_db=args.dropdb,
        remove_files=not getattr(args, "keep_files", False),
        log=_log,
    )
    return 0


# ---- entry ----------------------------------------------------------------

def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(prog="HO_Deploy")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("test-sql", "db-exists", "configure", "install-service",
                 "verify-service", "health", "deploy", "restore"):
        sp = sub.add_parser(name)
        sp.add_argument("--params", required=True)
        if name in ("restore", "deploy"):
            sp.add_argument("--bak", default=None)
            sp.add_argument("--replace", action="store_true")
        if name == "deploy":
            sp.add_argument("--skip-db", action="store_true")
        if name == "health":
            sp.add_argument("--app-only", action="store_true")

    sp_un = sub.add_parser("uninstall")
    sp_un.add_argument("--install-dir", required=True)
    sp_un.add_argument("--dropdb", action="store_true")
    sp_un.add_argument("--keep-files", action="store_true",
                       help="remove the service only; an outer installer owns files")

    args = parser.parse_args(argv)

    handlers = {
        "test-sql": cmd_test_sql,
        "db-exists": cmd_db_exists,
        "configure": cmd_configure,
        "restore": cmd_restore,
        "install-service": cmd_install_service,
        "verify-service": cmd_verify_service,
        "health": cmd_health,
        "deploy": cmd_deploy,
        "uninstall": cmd_uninstall,
    }

    if args.command == "uninstall":
        return cmd_uninstall(None, args)

    params = _load_params(args.params)
    cfg = _config_from_params(params)
    # carry the params 'replace' flag through to restore/deploy
    args._replace_param = params.get("replace", "false")
    # persist all output so the installer can show the real error on failure
    _set_log_file(cfg.log_path / "deploy.log")
    return handlers[args.command](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
