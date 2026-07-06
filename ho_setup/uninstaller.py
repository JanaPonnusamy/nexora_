"""UniNex HO uninstaller, packaged as HO_Uninstall.exe.

Removes the Windows service and the application files. The SQL database is
PRESERVED unless the operator explicitly ticks the drop-database option.

Self-deletion: a PyInstaller onedir exe cannot delete its own folder while
running, so the final folder removal is handed to a detached batch script that
waits for this process to exit, then removes the install directory.
"""
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import CONFIG_DIR_NAME, ENV_FILE_NAME, SERVICE_NAME
from .service_manager import ServiceManager

PRIMARY = "#0B6E4F"


def _install_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    env = os.environ.get("NEXORA_HO_INSTALL")
    return Path(env) if env else Path.cwd()


def _read_env(root):
    path = root / CONFIG_DIR_NAME / ENV_FILE_NAME
    values = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                values[key.strip()] = val.strip()
    return values


class _DbConfig:
    """Minimal config shim for SqlDeployer built from ho.env."""

    def __init__(self, env):
        self.sql_server = env.get("DB_SERVER", "localhost")
        self.database = env.get("DB_DATABASE", "NEXORA_PLATFORM")
        self.sql_driver = env.get("DB_DRIVER", "ODBC Driver 17 for SQL Server")
        self.auth_mode = env.get("DB_AUTH_MODE", "SQL")
        self.sql_username = env.get("DB_USERNAME", "sa")
        self.sql_password = env.get("DB_PASSWORD", "")


def drop_database(root, log=print):
    """Drop the HO database. Used only when explicitly requested."""
    from .sql_deployer import SqlError

    import pyodbc

    cfg = _DbConfig(_read_env(root))
    if "]" in cfg.database or "[" in cfg.database:
        raise SqlError(f"Unsafe database name: {cfg.database!r}")
    parts = [
        f"DRIVER={{{cfg.sql_driver}}};",
        f"SERVER={cfg.sql_server};",
        "DATABASE=master;",
        "TrustServerCertificate=yes;",
    ]
    if str(cfg.auth_mode).upper() == "WINDOWS":
        parts.append("Trusted_Connection=yes;")
    else:
        parts.append(f"UID={cfg.sql_username};")
        parts.append(f"PWD={cfg.sql_password};")
    conn = pyodbc.connect("".join(parts), autocommit=True, timeout=15)
    try:
        cur = conn.cursor()
        cur.execute("SELECT DB_ID(?)", cfg.database)
        if cur.fetchone()[0] is None:
            log(f"database {cfg.database} not present; nothing to drop")
            return
        log(f"dropping database {cfg.database}...")
        cur.execute(
            f"ALTER DATABASE [{cfg.database}] SET SINGLE_USER "
            "WITH ROLLBACK IMMEDIATE"
        )
        cur.execute(f"DROP DATABASE [{cfg.database}]")
        log("database dropped")
    finally:
        conn.close()


def _schedule_self_delete(root):
    """Spawn a detached batch that removes the install folder after we exit."""
    bat = Path(os.getenv("TEMP", ".")) / "ho_uninstall_cleanup.bat"
    bat.write_text(
        "@echo off\r\n"
        "ping 127.0.0.1 -n 4 >nul\r\n"
        f'rmdir /s /q "{root}"\r\n'
        'del "%~f0"\r\n',
        encoding="utf-8",
    )
    subprocess.Popen(
        ["cmd", "/c", str(bat)],
        creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | NEW_GROUP
        close_fds=True,
    )


def run_uninstall(root, drop_db=False, remove_files=True, log=print):
    """Stop + remove the service and (optionally) the files / database.

    ``remove_files`` is False when an outer installer (Inno) owns file removal;
    it is True for the standalone HO_Uninstall.exe.
    """
    log(f"removing service {SERVICE_NAME}...")
    svc = ServiceManager(root, log=log)
    if svc.is_installed():
        svc.remove()
    else:
        log("service not installed")

    if drop_db:
        try:
            drop_database(root, log=log)
        except Exception as ex:
            log(f"WARNING: database drop failed: {ex}")

    if remove_files:
        log("scheduling removal of application files...")
        _schedule_self_delete(root)
        log("done. Application files will be removed momentarily.")
    else:
        log("service removed; file cleanup handled by the installer.")


class UninstallApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("UniNex HO Uninstall")
        self.geometry("560x360")
        self.resizable(False, False)
        self.root = _install_root()
        self.drop_db = tk.BooleanVar(value=False)
        self._build()

    def _build(self):
        tk.Label(self, text="Uninstall UniNex HO", fg=PRIMARY,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=16, pady=10)
        tk.Label(self, text=f"Install folder: {self.root}", fg="#333",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=16)
        tk.Label(self,
                 text="This will stop and remove the HO Windows service and "
                      "delete the application files.",
                 fg="#333", wraplength=520, justify="left",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=16, pady=8)
        tk.Checkbutton(
            self, text="Also DROP the SQL database (irreversible data loss)",
            variable=self.drop_db, fg="#b00020",
            font=("Segoe UI", 10)).pack(anchor="w", padx=16, pady=4)

        self.log_box = tk.Text(self, height=8, font=("Consolas", 9),
                               bg="#101418", fg="#d8e0e6", relief="flat")
        self.log_box.pack(fill="both", expand=True, padx=16, pady=8)

        bar = tk.Frame(self)
        bar.pack(fill="x", padx=16, pady=8)
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right")
        self.btn = ttk.Button(bar, text="Uninstall", command=self._go)
        self.btn.pack(side="right", padx=6)

    def _log(self, msg):
        self.log_box.insert(tk.END, str(msg) + "\n")
        self.log_box.see(tk.END)
        self.update_idletasks()

    def _go(self):
        if not messagebox.askyesno(
                "Confirm", "Remove UniNex HO from this machine?"):
            return
        if self.drop_db.get() and not messagebox.askyesno(
                "Confirm database drop",
                "The SQL database will be permanently deleted. Continue?"):
            return
        self.btn.config(state="disabled")
        try:
            run_uninstall(self.root, drop_db=self.drop_db.get(), log=self._log)
            messagebox.showinfo("Uninstall", "UniNex HO has been removed.")
            self.destroy()
        except Exception as ex:
            self._log(f"ERROR: {ex}")
            messagebox.showerror("Uninstall failed", str(ex))
            self.btn.config(state="normal")


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    # Silent/scripted mode: HO_Uninstall.exe /silent [/dropdb]
    if len(argv) >= 2 and argv[1].lower() in ("/silent", "--silent", "-s"):
        drop = any(a.lower() in ("/dropdb", "--dropdb") for a in argv[2:])
        run_uninstall(_install_root(), drop_db=drop, log=print)
        return
    UninstallApp().mainloop()


if __name__ == "__main__":
    main()
