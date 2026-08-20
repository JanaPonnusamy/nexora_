"""Nexora Store Agent Setup Wizard (Tkinter GUI).

Ten-step flow: Welcome -> HO URL -> Tenant -> Store -> Location ->
Download config -> Install files -> Register service -> Start service ->
Validate. Packaged as NexoraStoreAgentSetup.exe.
"""
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .deployment import Deployment
from .ho_client import HoClient, HoConnectionError
from .paths import default_install_path

PRIMARY = "#0B6E4F"
BG = "#f4f6f8"


class SetupWizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Nexora Store Agent Setup")
        self.geometry("680x520")
        self.configure(bg=BG)
        self.resizable(False, False)

        # shared state — three HO routes (tried in this order at runtime), plus
        # ho_url = the one reachable from this machine (used to talk to HO now).
        self.lan_url = tk.StringVar(value="http://192.168.10.80:8000")
        self.static_url = tk.StringVar(value="http://122.252.246.181:8000")
        self.domain_url = tk.StringVar(value="https://ho.qvault.in")
        self.ho_url = tk.StringVar(value="")
        self.install_path = tk.StringVar(value=default_install_path())
        self.log_level = tk.StringVar(value="INFO")
        self.tenants = []
        self.stores = []
        self.selected_tenant = None
        self.selected_store = None
        self.deployment = None

        self._build_chrome()
        self.steps = [
            self.page_welcome, self.page_ho_url, self.page_tenant,
            self.page_store, self.page_location, self.page_install,
            self.page_validate,
        ]
        self.index = 0
        self.show_step()

    # ---- chrome -----------------------------------------------------------

    def _build_chrome(self):
        header = tk.Frame(self, bg=PRIMARY, height=64)
        header.pack(fill="x")
        tk.Label(header, text="  NEXORA  Store Agent Setup",
                 bg=PRIMARY, fg="white",
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
        if page == self.page_ho_url and not self._ho_tested:
            messagebox.showwarning("Test required",
                                   "Please test the HO connection first.")
            return False
        if page == self.page_tenant and not self.selected_tenant:
            messagebox.showwarning("Select tenant", "Please select a tenant.")
            return False
        if page == self.page_store and not self.selected_store:
            messagebox.showwarning("Select store", "Please select a store.")
            return False
        return True

    # ---- STEP 1 -----------------------------------------------------------

    def page_welcome(self):
        self._title("Welcome",
                    "This wizard installs the Nexora Store Agent on this machine.")
        msg = (
            "The agent connects this store to the Nexora Head Office (HO),\n"
            "downloads its configuration automatically, and keeps data in sync.\n\n"
            "You will need:\n"
            "   -  the HO server URL (e.g. http://192.168.1.10:8000)\n"
            "   -  which tenant and store this machine belongs to\n\n"
            "No SQL or database details are entered by hand - everything comes\n"
            "from HO. Click Next to begin."
        )
        tk.Label(self.body, text=msg, bg="white", fg="#333", justify="left",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=4)

    # ---- STEP 2 -----------------------------------------------------------

    _ho_tested = False

    def page_ho_url(self):
        self._title("Head Office URLs",
                    "Enter the three routes to HO. The agent tries them in this "
                    "order and fails over automatically.")

        def field(label, var, hint):
            row = tk.Frame(self.body, bg="white")
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label, bg="white", width=10, anchor="w",
                     font=("Segoe UI", 10)).pack(side="left")
            ttk.Entry(row, textvariable=var, width=42).pack(side="left", padx=6)
            tk.Label(self.body, text=hint, bg="white", fg="#888",
                     font=("Segoe UI", 8)).pack(anchor="w", padx=90)

        field("1. LAN:", self.lan_url, "Local network address — tried first on-site.")
        field("2. Static IP:", self.static_url, "Public static IP — used off-site / when LAN is down.")
        field("3. Domain:", self.domain_url, "Domain / tunnel URL — final fallback. Optional.")

        btnrow = tk.Frame(self.body, bg="white")
        btnrow.pack(anchor="w", pady=8, padx=90)
        ttk.Button(btnrow, text="Test Connection",
                   command=self._test_connection).pack(side="left")
        self.ho_result = tk.Label(self.body, text="", bg="white",
                                  font=("Segoe UI", 10))
        self.ho_result.pack(anchor="w", pady=6, padx=90)

    def _route_urls(self):
        """Ordered, de-duplicated non-empty routes: LAN, static, domain."""
        urls = []
        for var in (self.lan_url, self.static_url, self.domain_url):
            u = var.get().strip().rstrip("/")
            if u and u not in urls:
                urls.append(u)
        return urls

    def _test_connection(self):
        self.set_status("Testing HO connections...")
        routes = self._route_urls()
        if not routes:
            SetupWizard._ho_tested = False
            self.ho_result.config(text="Enter at least one HO URL.", fg="#b00020")
            self.set_status("")
            return
        # Use the first reachable route to talk to HO during install.
        errors = []
        for url in routes:
            try:
                HoClient(url).test_connection()
                self.ho_url.set(url)
                SetupWizard._ho_tested = True
                self.ho_result.config(
                    text=f"Reachable via {url}  ({len(routes)} route(s) will be saved).",
                    fg=PRIMARY)
                self.set_status("")
                return
            except HoConnectionError as ex:
                errors.append(f"{url} -> {ex}")
        SetupWizard._ho_tested = False
        # Surface the real per-route failure so a misconfigured URL, closed
        # port, or unhealthy HO is diagnosable instead of a blank "unreachable".
        detail = "\n".join(errors) if errors else ""
        self.ho_result.config(
            text="None of the URLs are reachable from this machine.\n" + detail,
            fg="#b00020", justify="left")
        self.set_status("")

    # ---- STEP 3 -----------------------------------------------------------

    def page_tenant(self):
        self._title("Select Tenant", "Active tenants loaded from HO.")
        self.tenant_list = tk.Listbox(self.body, height=10,
                                      font=("Segoe UI", 10))
        self.tenant_list.pack(fill="both", expand=True, padx=4, pady=6)
        self.tenant_list.bind("<<ListboxSelect>>", self._on_tenant_select)
        ttk.Button(self.body, text="Reload tenants",
                   command=self._load_tenants).pack(anchor="w", pady=4)
        self._load_tenants()

    def _load_tenants(self):
        self.set_status("Loading tenants...")
        try:
            self.tenants = HoClient(self.ho_url.get()).get_tenants()
            self.tenant_list.delete(0, tk.END)
            for t in self.tenants:
                self.tenant_list.insert(
                    tk.END, f"{t.get('tenant_abbreviation') or t.get('tenant_code')}"
                            f"  -  {t.get('tenant_name')}")
        except HoConnectionError as ex:
            messagebox.showerror("HO error", str(ex))
        self.set_status("")

    def _on_tenant_select(self, _evt):
        sel = self.tenant_list.curselection()
        self.selected_tenant = self.tenants[sel[0]] if sel else None

    # ---- STEP 4 -----------------------------------------------------------

    def page_store(self):
        name = (self.selected_tenant or {}).get("tenant_name", "")
        self._title("Select Store", f"Stores for tenant: {name}")
        self.store_list = tk.Listbox(self.body, height=10,
                                     font=("Segoe UI", 10))
        self.store_list.pack(fill="both", expand=True, padx=4, pady=6)
        self.store_list.bind("<<ListboxSelect>>", self._on_store_select)
        ttk.Button(self.body, text="Reload stores",
                   command=self._load_stores).pack(anchor="w", pady=4)
        self._load_stores()

    def _load_stores(self):
        self.set_status("Loading stores...")
        try:
            self.stores = HoClient(self.ho_url.get()).get_stores(
                self.selected_tenant["tenant_id"])
            self.store_list.delete(0, tk.END)
            for s in self.stores:
                self.store_list.insert(
                    tk.END, f"{s.get('store_code')}  -  {s.get('store_name')}")
        except HoConnectionError as ex:
            messagebox.showerror("HO error", str(ex))
        self.set_status("")

    def _on_store_select(self, _evt):
        sel = self.store_list.curselection()
        self.selected_store = self.stores[sel[0]] if sel else None

    # ---- STEP 5 -----------------------------------------------------------

    def page_location(self):
        self._title("Installation Location",
                    "Choose where the agent will be installed.")
        row = tk.Frame(self.body, bg="white")
        row.pack(fill="x", pady=10)
        tk.Label(row, text="Path:", bg="white",
                 font=("Segoe UI", 10)).pack(side="left")
        ttk.Entry(row, textvariable=self.install_path, width=46).pack(
            side="left", padx=8)
        ttk.Button(row, text="Browse", command=self._browse).pack(side="left")

        lvl = tk.Frame(self.body, bg="white")
        lvl.pack(fill="x", pady=6)
        tk.Label(lvl, text="Log level:", bg="white",
                 font=("Segoe UI", 10)).pack(side="left")
        ttk.Combobox(lvl, textvariable=self.log_level, width=12,
                     values=["DEBUG", "INFO", "WARNING", "ERROR"],
                     state="readonly").pack(side="left", padx=8)

        tk.Label(self.body,
                 text=f"Default chosen automatically: {default_install_path()}",
                 bg="white", fg="#666", font=("Segoe UI", 9)).pack(
            anchor="w", pady=8)

    def _browse(self):
        path = filedialog.askdirectory(initialdir="C:/")
        if path:
            self.install_path.set(path.replace("/", "\\"))

    # ---- STEP 6-9 (execute) ----------------------------------------------

    def page_install(self):
        s = self.selected_store or {}
        t = self.selected_tenant or {}
        self._title("Install",
                    f"{s.get('store_code')} - {s.get('store_name')}  "
                    f"({t.get('tenant_name')})")
        self.log_box = tk.Text(self.body, height=14, font=("Consolas", 9),
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
            self.deployment = Deployment(
                self.ho_url.get(), self.selected_tenant, self.selected_store,
                self.install_path.get(), log_level=self.log_level.get(),
                log=lambda m: self.after(0, self._logln, m),
                route_urls=self._route_urls(),
            )
            self.after(0, self._logln, "[STEP 6] Downloading agent configuration...")
            self.deployment.download_configuration()
            self.after(0, self._logln, "[STEP 7] Installing runtime files...")
            self.after(0, self._logln, "[STEP 8] Registering Windows service...")
            self.after(0, self._logln, "[STEP 9] Starting service...")
            self.deployment.install()
            self.after(0, self._logln, "Install complete. Click Next to validate.")
            self.after(0, lambda: self.btn_next.config(
                state="normal", text="Next >", command=self.next))
            self.after(0, lambda: self.btn_back.config(state="normal"))
        except Exception as ex:
            self.after(0, self._logln, f"ERROR: {ex}")
            self.after(0, lambda: messagebox.showerror("Install failed", str(ex)))
            self.after(0, lambda: self.btn_next.config(
                state="normal", text="Retry", command=self._run_install))
            self.after(0, lambda: self.btn_back.config(state="normal"))

    # ---- STEP 10 ----------------------------------------------------------

    def page_validate(self):
        self._title("Validation", "Verifying the installation end-to-end.")
        self.val_frame = tk.Frame(self.body, bg="white")
        self.val_frame.pack(fill="both", expand=True, pady=6)
        self.btn_next.config(text="Finish", state="disabled", command=self.destroy)
        threading.Thread(target=self._validate_worker, daemon=True).start()

    def _validate_worker(self):
        result = self.deployment.validate()
        self.after(0, self._render_validation, result)

    def _render_validation(self, result):
        for label, ok, detail in result.steps:
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
            text="Installation Successful" if result.ok else "Installation Incomplete",
            bg="white", fg=PRIMARY if result.ok else "#b00020",
            font=("Segoe UI", 14, "bold"))
        banner.pack(pady=10)
        self.btn_next.config(state="normal")


def main():
    SetupWizard().mainloop()


if __name__ == "__main__":
    main()
