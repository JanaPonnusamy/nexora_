"""Post-install configuration utility (NexoraStoreAgentSettings.exe).

Change HO URL, store assignment, or log level WITHOUT reinstalling.
Workflow on Apply: Stop Service -> Update Config -> Validate -> Restart Service.

Also hosts the Mail Transfer section (Phase 2 extraction): configures
file_transfer.transport.mode = EMAIL for this store and manages the
NexoraMailTransfer Windows service that delivers those packages. Mail
Transfer is opt-in -- unless "Mail Enabled" is checked, Apply never touches
any existing file_transfer block in agent_config.json.
"""
import os
import smtplib
import sys
import threading
import imaplib
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import MAIL_TRANSFER_DISPLAY_NAME, MAIL_TRANSFER_EXE_NAME, MAIL_TRANSFER_SERVICE_NAME
from .agent_config import build_config, read_config, write_config
from .deployment import Deployment
from .ho_client import HoClient, HoConnectionError
from .paths import default_install_path
from .service_manager import ServiceManager

PRIMARY = "#0B6E4F"


def _detect_install_path():
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve().parent)
    for candidate in (default_install_path(),):
        if (Path(candidate) / "agent_config.json").is_file():
            return candidate
    return default_install_path()


class SettingsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Nexora Store Agent - Settings")
        self.geometry("620x760")
        self.resizable(False, False)

        self.install_path = tk.StringVar(value=_detect_install_path())
        # Three HO routes (tried in this order) + the reachable one for HO calls.
        self.lan_url = tk.StringVar()
        self.static_url = tk.StringVar()
        self.domain_url = tk.StringVar()
        self.ho_url = tk.StringVar()
        self.log_level = tk.StringVar(value="INFO")
        self.tenants = []
        self.stores = []
        self.selected_tenant = None
        self.selected_store = None
        self.config = {}

        # Mail Transfer (EMAIL file_transfer mode) -- see class docstring.
        self.mail_enabled = tk.BooleanVar(value=False)
        self.mail_smtp_host = tk.StringVar()
        self.mail_smtp_port = tk.StringVar(value="587")
        self.mail_imap_host = tk.StringVar()
        self.mail_imap_port = tk.StringVar(value="993")
        self.mail_imap_folder = tk.StringVar(value="INBOX")
        self.mail_username = tk.StringVar()
        self.mail_password_env = tk.StringVar(value="NEXORA_SMTP_PASSWORD")
        self.mail_to_address = tk.StringVar()
        self.mail_max_mb = tk.StringVar(value="20")

        self._build()
        self._load_existing()

    def _build(self):
        tk.Label(self, text="Store Agent Settings", fg=PRIMARY,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=16, pady=10)

        frm = tk.Frame(self)
        frm.pack(fill="x", padx=16)

        self._row(frm, "Install path:", self.install_path, 0, width=46)
        self._row(frm, "LAN URL:", self.lan_url, 1, width=46,
                  button=("Test", self._test))
        self._row(frm, "Static IP URL:", self.static_url, 2, width=46)
        self._row(frm, "Domain URL:", self.domain_url, 3, width=46)
        tk.Label(frm, text="Log level:").grid(row=4, column=0, sticky="w", pady=6)
        ttk.Combobox(frm, textvariable=self.log_level, width=14,
                     values=["DEBUG", "INFO", "WARNING", "ERROR"],
                     state="readonly").grid(row=4, column=1, sticky="w")

        tk.Label(self, text="Store assignment (optional - reselect to reassign):",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        lists = tk.Frame(self)
        lists.pack(fill="both", expand=True, padx=16)
        tk.Label(lists, text="Tenant").grid(row=0, column=0, sticky="w")
        tk.Label(lists, text="Store").grid(row=0, column=1, sticky="w")
        self.tenant_list = tk.Listbox(lists, height=7, width=34)
        self.tenant_list.grid(row=1, column=0, padx=(0, 8))
        self.tenant_list.bind("<<ListboxSelect>>", self._on_tenant)
        self.store_list = tk.Listbox(lists, height=7, width=34)
        self.store_list.grid(row=1, column=1)
        self.store_list.bind("<<ListboxSelect>>", self._on_store)
        ttk.Button(lists, text="Load from HO", command=self._load_tenants).grid(
            row=2, column=0, sticky="w", pady=6)

        self._build_mail_section()

        bar = tk.Frame(self)
        bar.pack(fill="x", padx=16, pady=10)
        self.status = tk.Label(bar, text="", fg="#555")
        self.status.pack(side="left")
        ttk.Button(bar, text="Apply", command=self._apply).pack(side="right")

    def _build_mail_section(self):
        tk.Label(self, text="Mail Transfer (EMAIL file_transfer mode)",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(
            self,
            text="For stores with no LAN/domain/static-IP route to HO but normal "
                 "internet access. Packages are sent as email attachments instead "
                 "of live HTTP calls. Only takes effect once 'Mail Enabled' is "
                 "checked and Apply is pressed.",
            fg="#555", wraplength=580, justify="left",
        ).pack(anchor="w", padx=16)

        frm = tk.Frame(self)
        frm.pack(fill="x", padx=16, pady=(6, 0))
        ttk.Checkbutton(frm, text="Mail Enabled", variable=self.mail_enabled).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self._row(frm, "SMTP Host:", self.mail_smtp_host, 1, width=32)
        self._row(frm, "SMTP Port:", self.mail_smtp_port, 2, width=8)
        self._row(frm, "Username:", self.mail_username, 3, width=32)
        self._row(frm, "Password env var:", self.mail_password_env, 4, width=32)
        self._row(frm, "HO receiver address (To):", self.mail_to_address, 5, width=32)
        self._row(frm, "IMAP Host:", self.mail_imap_host, 6, width=32)
        self._row(frm, "IMAP Port:", self.mail_imap_port, 7, width=8)
        self._row(frm, "IMAP Folder:", self.mail_imap_folder, 8, width=32)
        self._row(frm, "Max attachment (MB, 0=unlimited):", self.mail_max_mb, 9, width=8)

        btns = tk.Frame(self)
        btns.pack(fill="x", padx=16, pady=8)
        ttk.Button(btns, text="Test SMTP", command=self._test_smtp).pack(side="left")
        ttk.Button(btns, text="Test IMAP", command=self._test_imap).pack(
            side="left", padx=6)
        ttk.Button(btns, text="Install/Start Mail Service",
                   command=self._start_mail_service).pack(side="left", padx=6)
        ttk.Button(btns, text="Stop Mail Service",
                   command=self._stop_mail_service).pack(side="left", padx=6)

    def _row(self, parent, label, var, r, width=40, button=None):
        tk.Label(parent, text=label).grid(row=r, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=var, width=width).grid(
            row=r, column=1, sticky="w")
        if button:
            ttk.Button(parent, text=button[0], command=button[1]).grid(
                row=r, column=2, padx=6)

    def set_status(self, text):
        self.status.config(text=text)
        self.update_idletasks()

    # ---- load -------------------------------------------------------------

    def _route_urls(self):
        """Ordered, de-duplicated non-empty routes: LAN, static, domain."""
        urls = []
        for var in (self.lan_url, self.static_url, self.domain_url):
            u = var.get().strip().rstrip("/")
            if u and u not in urls:
                urls.append(u)
        return urls

    def _load_existing(self):
        try:
            self.config = read_config(self.install_path.get())
            # Populate the three route fields from ho_urls (or the legacy single).
            routes = self.config.get("ho_urls") or [self.config.get("ho_url", "")]
            routes = [r for r in routes if r]
            self.lan_url.set(routes[0] if len(routes) > 0 else "")
            self.static_url.set(routes[1] if len(routes) > 1 else "")
            self.domain_url.set(routes[2] if len(routes) > 2 else "")
            self.ho_url.set(routes[0] if routes else "")
            self.log_level.set(self.config.get("log_level", "INFO"))
            self.selected_tenant = {
                "tenant_id": self.config.get("tenant_id"),
                "tenant_name": self.config.get("tenant_name"),
            }
            self.selected_store = {
                "store_id": self.config.get("store_id"),
                "store_name": self.config.get("store_name"),
                "store_code": self.config.get("store_code"),
            }
            self._load_mail_section()
        except (FileNotFoundError, ValueError) as ex:
            messagebox.showwarning("No config", str(ex))

    def _load_mail_section(self):
        ft = self.config.get("file_transfer") or {}
        transport = ft.get("transport") or {}
        email = transport.get("email") or {}
        self.mail_enabled.set(bool(ft.get("enabled")) and transport.get("mode") == "EMAIL")
        self.mail_smtp_host.set(email.get("smtp_host", ""))
        self.mail_smtp_port.set(str(email.get("smtp_port", 587)))
        self.mail_imap_host.set(email.get("imap_host", ""))
        self.mail_imap_port.set(str(email.get("imap_port", 993)))
        self.mail_imap_folder.set(email.get("imap_folder", "INBOX"))
        self.mail_username.set(email.get("username", ""))
        self.mail_password_env.set(email.get("password_env", "NEXORA_SMTP_PASSWORD"))
        self.mail_to_address.set(email.get("to_address", ""))
        max_bytes = email.get("max_attachment_bytes")
        self.mail_max_mb.set(str(int(max_bytes) // (1024 * 1024)) if max_bytes else "20")

    def _mail_email_cfg(self):
        max_mb = float(self.mail_max_mb.get() or 0)
        return {
            "smtp_host": self.mail_smtp_host.get().strip(),
            "smtp_port": int(self.mail_smtp_port.get() or 587),
            "imap_host": self.mail_imap_host.get().strip(),
            "imap_port": int(self.mail_imap_port.get() or 993),
            "imap_folder": self.mail_imap_folder.get().strip() or "INBOX",
            "username": self.mail_username.get().strip(),
            "password_env": self.mail_password_env.get().strip(),
            "to_address": self.mail_to_address.get().strip(),
            "max_attachment_bytes": int(max_mb * 1024 * 1024) if max_mb else 0,
        }

    def _mail_password(self, cfg):
        env_name = cfg.get("password_env")
        value = os.environ.get(env_name) if env_name else None
        if not value:
            raise RuntimeError(
                f"Environment variable '{env_name}' is not set on this machine. "
                "Test Connection reads the SAME variable the running service will "
                "read -- set it here first (this tool never stores the secret)."
            )
        return value

    def _test_smtp(self):
        cfg = self._mail_email_cfg()
        try:
            password = self._mail_password(cfg)
            with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=20) as smtp:
                smtp.starttls()
                smtp.login(cfg["username"], password)
            messagebox.showinfo("SMTP", "Connected and authenticated successfully.")
        except Exception as ex:
            messagebox.showerror("SMTP", str(ex))

    def _test_imap(self):
        cfg = self._mail_email_cfg()
        try:
            password = self._mail_password(cfg)
            conn = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"])
            try:
                conn.login(cfg["username"], password)
                conn.select(cfg["imap_folder"])
            finally:
                conn.logout()
            messagebox.showinfo("IMAP", "Connected and authenticated successfully.")
        except Exception as ex:
            messagebox.showerror("IMAP", str(ex))

    def _mail_service_manager(self):
        return ServiceManager(
            self.install_path.get(),
            log=lambda m: self.after(0, self.set_status, m),
            service_name=MAIL_TRANSFER_SERVICE_NAME,
            service_display_name=MAIL_TRANSFER_DISPLAY_NAME,
            exe_name=MAIL_TRANSFER_EXE_NAME,
            module_name="store_agent_setup.mail_transfer_service",
            description=(
                "Nexora Mail Transfer: sends FILE_TRANSFER packages over SMTP "
                "and polls IMAP for HO acknowledgements."
            ),
        )

    def _start_mail_service(self):
        def worker():
            svc = self._mail_service_manager()
            try:
                self.set_status("Installing/starting Mail Transfer service...")
                if not svc.is_installed():
                    svc.install()
                svc.start()
                self.after(0, lambda: messagebox.showinfo(
                    "Mail Transfer", "Service installed and running."))
                self.set_status("Done.")
            except Exception as ex:
                self.after(0, lambda: messagebox.showerror("Mail Transfer", str(ex)))
                self.set_status("Failed.")
        threading.Thread(target=worker, daemon=True).start()

    def _stop_mail_service(self):
        def worker():
            svc = self._mail_service_manager()
            try:
                self.set_status("Stopping Mail Transfer service...")
                if svc.is_installed():
                    svc.stop()
                self.set_status("Stopped.")
            except Exception as ex:
                self.after(0, lambda: messagebox.showerror("Mail Transfer", str(ex)))
                self.set_status("Failed.")
        threading.Thread(target=worker, daemon=True).start()

    def _test(self):
        routes = self._route_urls()
        if not routes:
            messagebox.showerror("HO", "Enter at least one HO URL.")
            return
        errors = []
        for url in routes:
            try:
                HoClient(url).test_connection()
                self.ho_url.set(url)
                messagebox.showinfo("HO", f"Reachable via {url}.")
                return
            except HoConnectionError as ex:
                errors.append(f"{url}\n  {ex}")
        messagebox.showerror(
            "HO", "None of the URLs are reachable from here.\n\n" + "\n\n".join(errors))

    def _active(self):
        return self.ho_url.get().strip().rstrip("/") or (self._route_urls() or [""])[0]

    def _load_tenants(self):
        self.set_status("Loading tenants...")
        try:
            self.tenants = HoClient(self._active()).get_tenants()
            self.tenant_list.delete(0, tk.END)
            for t in self.tenants:
                self.tenant_list.insert(tk.END, t.get("tenant_name"))
        except HoConnectionError as ex:
            messagebox.showerror("HO", str(ex))
        self.set_status("")

    def _on_tenant(self, _evt):
        sel = self.tenant_list.curselection()
        if not sel:
            return
        self.selected_tenant = self.tenants[sel[0]]
        try:
            self.stores = HoClient(self._active()).get_stores(
                self.selected_tenant["tenant_id"])
            self.store_list.delete(0, tk.END)
            for s in self.stores:
                self.store_list.insert(
                    tk.END, f"{s.get('store_code')} - {s.get('store_name')}")
        except HoConnectionError as ex:
            messagebox.showerror("HO", str(ex))

    def _on_store(self, _evt):
        sel = self.store_list.curselection()
        if sel:
            self.selected_store = self.stores[sel[0]]

    # ---- apply ------------------------------------------------------------

    def _apply(self):
        threading.Thread(target=self._apply_worker, daemon=True).start()

    def _apply_worker(self):
        install = self.install_path.get()
        svc = ServiceManager(install, log=lambda m: self.after(0, self.set_status, m))
        try:
            self.set_status("Stopping service...")
            if svc.is_installed():
                svc.stop()

            self.set_status("Updating configuration...")
            routes = self._route_urls()
            if not routes:
                raise ValueError("Enter at least one HO URL.")
            active = self.ho_url.get().strip().rstrip("/") or routes[0]
            store_changed = (
                self.selected_store.get("store_id")
                != self.config.get("store_id")
            )
            new_cfg = build_config(
                routes[0], self.selected_tenant, self.selected_store,
                install, log_level=self.log_level.get(), fallback_urls=routes[1:],
            )
            # build_config() has no notion of file_transfer -- never clobber
            # an existing block unless the operator explicitly checked "Mail
            # Enabled" this session (preserves FILE_DROP/SFTP configs too).
            existing_ft = self.config.get("file_transfer")
            if self.mail_enabled.get():
                new_cfg["file_transfer"] = {
                    "enabled": True,
                    "interval_seconds": (existing_ft or {}).get("interval_seconds", 1800),
                    "mail_transfer_interval_seconds":
                        (existing_ft or {}).get("mail_transfer_interval_seconds", 300),
                    "transport": {"mode": "EMAIL", "email": self._mail_email_cfg()},
                }
            elif existing_ft:
                new_cfg["file_transfer"] = existing_ft
            write_config(install, new_cfg)

            # Re-download HO agent-config if the store assignment changed.
            if store_changed:
                self.set_status("Re-downloading agent-config from HO...")
                dep = Deployment(active, self.selected_tenant,
                                 self.selected_store, install,
                                 log_level=self.log_level.get(), route_urls=routes)
                dep.installer.save_ho_agent_config(dep.download_configuration())

            self.set_status("Validating...")
            HoClient(active).test_connection()

            self.set_status("Restarting service...")
            if svc.is_installed():
                svc.start()
            self.config = new_cfg
            self.after(0, lambda: messagebox.showinfo(
                "Settings", "Configuration updated and service restarted."))
            self.set_status("Done.")
        except Exception as ex:
            self.after(0, lambda: messagebox.showerror("Apply failed", str(ex)))
            self.set_status("Failed.")


def main():
    SettingsApp().mainloop()


if __name__ == "__main__":
    main()
