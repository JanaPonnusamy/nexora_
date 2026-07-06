"""UniNex HO Setup wizard (Tkinter GUI), packaged as HO_Setup.exe.

Ten-step flow:
  1 Welcome  2 License  3 Install folder  4 SQL config (+Test)
  5 Database deployment (restore .bak)  6 Configure  7 Backend  8 Service
  9 Frontend  10 Health check + summary

Steps 6-9 run as one rollback-protected install batch (Deployment.install); the
remaining steps are individual wizard pages. Mirrors the Store Agent wizard.
"""
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import DEFAULT_DATABASE, __version__
from .deployment import Deployment
from .ho_config import HoConfig, default_public_host
from .installer_logging import InstallLogger
from .paths import default_install_path, resource_root
from .sql_deployer import SqlDeployer, SqlError

PRIMARY = "#0B6E4F"
BG = "#f4f6f8"

_FALLBACK_LICENSE = (
    "UniNex Head Office - Software License Agreement\n\n"
    "This software is proprietary to UniNex and is licensed, not sold. By "
    "installing it you agree to use it solely for operating your licensed "
    "UniNex tenant deployment. You may not redistribute, reverse engineer, or "
    "sublicense the software. The software is provided \"as is\" without "
    "warranty of any kind. All rights reserved."
)


def _load_license_text():
    for path in (resource_root() / "LICENSE.txt",
                 resource_root() / "ho_setup" / "LICENSE.txt"):
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8")
        except OSError:
            pass
    return _FALLBACK_LICENSE


class SetupWizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("UniNex HO Setup")
        self.geometry("720x560")
        self.configure(bg=BG)
        self.resizable(False, False)

        # shared state
        self.install_path = tk.StringVar(value=default_install_path())
        self.public_host = tk.StringVar(value=default_public_host())
        self.sql_server = tk.StringVar(value="localhost")
        self.auth_mode = tk.StringVar(value="SQL")
        self.sql_username = tk.StringVar(value="sa")
        self.sql_password = tk.StringVar(value="")
        self.database = tk.StringVar(value=DEFAULT_DATABASE)
        self.license_accepted = tk.BooleanVar(value=False)
        self.replace_existing = tk.BooleanVar(value=False)

        self._sql_tested = False
        self._db_exists = None
        self.config = None
        self.logger = None
        self.deployment = None

        self._build_chrome()
        self.steps = [
            self.page_welcome, self.page_license, self.page_location,
            self.page_sql, self.page_dbdeploy, self.page_install,
            self.page_validate,
        ]
        self.index = 0
        self.show_step()

    # ---- chrome -----------------------------------------------------------

    def _build_chrome(self):
        header = tk.Frame(self, bg=PRIMARY, height=64)
        header.pack(fill="x")
        tk.Label(header, text="  UniNex  HO Setup", bg=PRIMARY, fg="white",
                 font=("Segoe UI", 16, "bold")).pack(side="left", pady=14)
        tk.Label(header, text=f"v{__version__}  ", bg=PRIMARY, fg="white",
                 font=("Segoe UI", 9)).pack(side="right", pady=20)

        self.body = tk.Frame(self, bg="white")
        self.body.pack(fill="both", expand=True, padx=16, pady=12)

        nav = tk.Frame(self, bg=BG)
        nav.pack(fill="x", padx=16, pady=(0, 12))
        self.btn_back = ttk.Button(nav, text="< Back", command=self.back)
        self.btn_back.pack(side="left")
        self.btn_next = ttk.Button(nav, text="Next >", command=self.next)
        self.btn_next.pack(side="right")
        self.status = tk.Label(nav, text="", bg=BG, fg="#555",
                               font=("Segoe UI", 9))
        self.status.pack(side="left", padx=12)

    def _clear_body(self):
        for w in self.body.winfo_children():
            w.destroy()

    def _title(self, text, subtitle=""):
        tk.Label(self.body, text=text, bg="white", fg="#222",
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(8, 2))
        if subtitle:
            tk.Label(self.body, text=subtitle, bg="white", fg="#666",
                     font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 10))

    def set_status(self, text):
        self.status.config(text=text)
        self.update_idletasks()

    # ---- navigation -------------------------------------------------------

    def show_step(self):
        self._clear_body()
        self.btn_back.config(state="normal" if self.index > 0 else "disabled")
        self.btn_next.config(text="Next >", state="normal", command=self.next)
        self.steps[self.index]()

    def next(self):
        if not self._validate_step():
            return
        if self.index < len(self.steps) - 1:
            self.index += 1
            self.show_step()

    def back(self):
        if self.index > 0:
            self.index -= 1
            self.show_step()

    def _validate_step(self):
        page = self.steps[self.index]
        if page == self.page_license and not self.license_accepted.get():
            messagebox.showwarning("License", "Please accept the license to continue.")
            return False
        if page == self.page_sql and not self._sql_tested:
            messagebox.showwarning("Test required",
                                   "Please test the SQL connection first.")
            return False
        if page == self.page_dbdeploy and self._db_exists and \
                not self.replace_existing.get():
            messagebox.showwarning(
                "Database exists",
                "The database already exists. Tick 'Replace existing database' "
                "to overwrite it, or Cancel the installation.")
            return False
        return True

    # ---- STEP 1: Welcome --------------------------------------------------

    def page_welcome(self):
        self._title("Welcome",
                    "This wizard installs the UniNex Head Office (HO) on this PC.")
        msg = (
            "The installer will:\n"
            "   -  configure and test the SQL Server connection\n"
            "   -  deploy the HO database by restoring the bundled backup\n"
            "   -  install the HO backend as a Windows service (auto-start)\n"
            "   -  deploy the production web frontend\n"
            "   -  run a full health check\n\n"
            "Requirements:\n"
            "   -  SQL Server installed and running on this machine\n"
            "   -  'ODBC Driver 17 for SQL Server' installed\n"
            "   -  run this installer as Administrator\n\n"
            "Click Next to begin."
        )
        tk.Label(self.body, text=msg, bg="white", fg="#333", justify="left",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=4)

    # ---- STEP 2: License --------------------------------------------------

    def page_license(self):
        self._title("License Agreement", "Please review and accept to continue.")
        box = tk.Text(self.body, height=14, wrap="word", font=("Segoe UI", 9),
                      relief="solid", borderwidth=1)
        box.insert("1.0", _load_license_text())
        box.config(state="disabled")
        box.pack(fill="both", expand=True, pady=6)
        tk.Checkbutton(self.body, text="I accept the terms of the license agreement",
                       variable=self.license_accepted, bg="white",
                       font=("Segoe UI", 10)).pack(anchor="w", pady=6)

    # ---- STEP 3: Install folder ------------------------------------------

    def page_location(self):
        self._title("Installation Folder",
                    "Choose where the HO system will be installed.")
        row = tk.Frame(self.body, bg="white")
        row.pack(fill="x", pady=10)
        tk.Label(row, text="Folder:", bg="white",
                 font=("Segoe UI", 10)).pack(side="left")
        ttk.Entry(row, textvariable=self.install_path, width=50).pack(
            side="left", padx=8)
        ttk.Button(row, text="Browse", command=self._browse).pack(side="left")

        host = tk.Frame(self.body, bg="white")
        host.pack(fill="x", pady=10)
        tk.Label(host, text="Server address (browser-facing host or IP):",
                 bg="white", font=("Segoe UI", 10)).pack(side="left")
        ttk.Entry(host, textvariable=self.public_host, width=24).pack(
            side="left", padx=8)
        tk.Label(self.body,
                 text="Used to build the API/frontend URLs the browser connects to.",
                 bg="white", fg="#666", font=("Segoe UI", 9)).pack(anchor="w")

    def _browse(self):
        path = filedialog.askdirectory(initialdir="C:/")
        if path:
            self.install_path.set(path.replace("/", "\\"))

    # ---- STEP 4: SQL configuration ---------------------------------------

    def page_sql(self):
        self._title("SQL Server Configuration",
                    "Enter the SQL Server details and test the connection.")
        frm = tk.Frame(self.body, bg="white")
        frm.pack(fill="x", pady=4)

        self._field(frm, "SQL Server instance:", self.sql_server, 0)
        tk.Label(frm, text="Authentication:", bg="white",
                 font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w", pady=6)
        auth = ttk.Combobox(frm, textvariable=self.auth_mode, width=20,
                            values=["SQL", "WINDOWS"], state="readonly")
        auth.grid(row=1, column=1, sticky="w")
        auth.bind("<<ComboboxSelected>>", lambda _e: self._toggle_auth())

        self.user_entry = self._field(frm, "Username:", self.sql_username, 2)
        self.pass_entry = self._field(frm, "Password:", self.sql_password, 3,
                                      show="*")
        self._field(frm, "Database name:", self.database, 4)

        ttk.Button(self.body, text="Test Connection",
                   command=self._test_sql).pack(anchor="w", pady=10)
        self.sql_result = tk.Label(self.body, text="", bg="white",
                                   font=("Segoe UI", 10), wraplength=640,
                                   justify="left")
        self.sql_result.pack(anchor="w")
        self._toggle_auth()

    def _field(self, parent, label, var, r, show=None):
        tk.Label(parent, text=label, bg="white",
                 font=("Segoe UI", 10)).grid(row=r, column=0, sticky="w", pady=6)
        entry = ttk.Entry(parent, textvariable=var, width=36, show=show)
        entry.grid(row=r, column=1, sticky="w")
        return entry

    def _toggle_auth(self):
        windows = self.auth_mode.get().upper() == "WINDOWS"
        state = "disabled" if windows else "normal"
        try:
            self.user_entry.config(state=state)
            self.pass_entry.config(state=state)
        except tk.TclError:
            pass

    def _current_config(self):
        return HoConfig(
            sql_server=self.sql_server.get().strip(),
            auth_mode=self.auth_mode.get().strip().upper(),
            sql_username=self.sql_username.get().strip(),
            sql_password=self.sql_password.get(),
            database=self.database.get().strip() or DEFAULT_DATABASE,
            install_path=self.install_path.get().strip(),
            public_host=self.public_host.get().strip() or default_public_host(),
        )

    def _test_sql(self):
        self.set_status("Testing SQL connection...")
        try:
            version = SqlDeployer(self._current_config()).test_connection()
            self._sql_tested = True
            self.sql_result.config(
                text="Connection OK:\n" + version.splitlines()[0], fg=PRIMARY)
        except SqlError as ex:
            self._sql_tested = False
            self.sql_result.config(text=str(ex), fg="#b00020")
        self.set_status("")

    # ---- STEP 5: Database deployment -------------------------------------

    def page_dbdeploy(self):
        self._title("Database Deployment",
                    "The HO database is created by restoring the bundled backup.")
        tk.Label(self.body,
                 text=f"Target database:  {self.database.get()}\n"
                      f"Server:  {self.sql_server.get()}",
                 bg="white", fg="#333", justify="left",
                 font=("Segoe UI", 10)).pack(anchor="w", pady=6)
        self.db_status = tk.Label(self.body, text="Checking for existing database...",
                                  bg="white", fg="#666", font=("Segoe UI", 10),
                                  wraplength=640, justify="left")
        self.db_status.pack(anchor="w", pady=8)
        self.replace_chk = tk.Checkbutton(
            self.body, text="Replace existing database (overwrite)",
            variable=self.replace_existing, bg="white", font=("Segoe UI", 10))
        threading.Thread(target=self._check_db_worker, daemon=True).start()

    def _check_db_worker(self):
        try:
            exists = SqlDeployer(self._current_config()).database_exists()
        except SqlError as ex:
            self.after(0, lambda: self.db_status.config(
                text=str(ex), fg="#b00020"))
            return
        self._db_exists = exists
        self.after(0, self._render_db_status, exists)

    def _render_db_status(self, exists):
        if exists:
            self.db_status.config(
                text="WARNING: a database with this name already exists.\n"
                     "Choose to replace it (the current data will be overwritten) "
                     "or click Back/Cancel to stop.", fg="#b00020")
            self.replace_chk.pack(anchor="w", pady=6)
        else:
            self.db_status.config(
                text="No existing database found. A fresh database will be "
                     "restored from the bundled backup.", fg=PRIMARY)

    # ---- STEP 6-9: install ------------------------------------------------

    def page_install(self):
        self._title("Install",
                    "Configuring, deploying files, database, service and frontend.")
        self.log_box = tk.Text(self.body, height=16, font=("Consolas", 9),
                               bg="#101418", fg="#d8e0e6", relief="flat")
        self.log_box.pack(fill="both", expand=True, pady=6)
        self.btn_next.config(text="Install Now", command=self._run_install)

    def _logln(self, msg):
        self.log_box.insert(tk.END, msg + "\n")
        self.log_box.see(tk.END)
        self.update_idletasks()

    def _run_install(self):
        self.btn_next.config(state="disabled")
        self.btn_back.config(state="disabled")
        threading.Thread(target=self._install_worker, daemon=True).start()

    def _install_worker(self):
        try:
            self.config = self._current_config()
            self.logger = InstallLogger(
                ui_callback=lambda m: self.after(0, self._logln, m))
            self.after(0, self._logln, f"Log file: {self.logger.log_file}")
            self.deployment = Deployment(self.config, self.logger)
            self.deployment.install(replace_existing=self.replace_existing.get())
            self.after(0, self._logln, "Install complete. Click Next to verify.")
            self.after(0, lambda: self.btn_next.config(
                state="normal", text="Next >", command=self.next))
            self.after(0, lambda: self.btn_back.config(state="normal"))
        except Exception as ex:
            self.after(0, self._logln, f"ERROR: {ex}")
            self.after(0, lambda: messagebox.showerror("Install failed", str(ex)))
            self.after(0, lambda: self.btn_next.config(
                state="normal", text="Retry", command=self._run_install))
            self.after(0, lambda: self.btn_back.config(state="normal"))

    # ---- STEP 10: health check -------------------------------------------

    def page_validate(self):
        self._title("Health Check", "Verifying the deployment end-to-end.")
        self.val_frame = tk.Frame(self.body, bg="white")
        self.val_frame.pack(fill="both", expand=True, pady=6)
        self.btn_next.config(text="Finish", state="disabled", command=self.destroy)
        threading.Thread(target=self._validate_worker, daemon=True).start()

    def _validate_worker(self):
        result = self.deployment.validate()
        self.after(0, self._render_validation, result)

    def _render_validation(self, result):
        for label, ok, detail in result.checks:
            mark = "OK " if ok else "X  "
            color = PRIMARY if ok else "#b00020"
            row = tk.Frame(self.val_frame, bg="white")
            row.pack(fill="x", anchor="w", pady=3)
            tk.Label(row, text=mark, bg="white", fg=color,
                     font=("Consolas", 11, "bold")).pack(side="left")
            tk.Label(row, text=label, bg="white", fg="#222",
                     font=("Segoe UI", 10)).pack(side="left")
            if detail and not ok:
                tk.Label(row, text=f"  ({detail})", bg="white", fg="#888",
                         font=("Segoe UI", 8)).pack(side="left")
        banner = tk.Label(
            self.body,
            text="Deployment Successful" if result.ok else "Deployment Incomplete",
            bg="white", fg=PRIMARY if result.ok else "#b00020",
            font=("Segoe UI", 14, "bold"))
        banner.pack(pady=8)
        if result.ok:
            tk.Label(self.body,
                     text=f"HO is live at  {self.config.frontend_url}",
                     bg="white", fg="#333", font=("Segoe UI", 10)).pack()
        self.btn_next.config(state="normal")


def main():
    SetupWizard().mainloop()


if __name__ == "__main__":
    main()
