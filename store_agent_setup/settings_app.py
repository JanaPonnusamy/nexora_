"""Post-install configuration utility (NexoraStoreAgentSettings.exe).

Change HO URL, store assignment, or log level WITHOUT reinstalling.
Workflow on Apply: Stop Service -> Update Config -> Validate -> Restart Service.
"""
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

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
        self.geometry("620x520")
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

        bar = tk.Frame(self)
        bar.pack(fill="x", padx=16, pady=10)
        self.status = tk.Label(bar, text="", fg="#555")
        self.status.pack(side="left")
        ttk.Button(bar, text="Apply", command=self._apply).pack(side="right")

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
        except (FileNotFoundError, ValueError) as ex:
            messagebox.showwarning("No config", str(ex))

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
