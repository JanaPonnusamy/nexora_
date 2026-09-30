"""Nexora Store Agent Setup Wizard (Tkinter GUI) - device / zero-config flow.

Lightweight five-step flow: Welcome -> Connect & Sign in -> Location ->
Install -> Validate. The operator enters ONLY the HO URL and a store-user
login (created in HO, assigned to a tenant+store). The machine registers its
own device key and learns its assigned stores from HO at runtime; there is no
tenant/store picker and no SQL details. Packaged as NexoraStoreAgentSetup.exe.
"""
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .deployment import DeviceDeployment
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

        self.ho_url = tk.StringVar(value="http://192.168.10.73:8000")
        self.extra_routes = tk.StringVar(value="")
        self.username = tk.StringVar(value="")
        self.password = tk.StringVar(value="")
        self.install_path = tk.StringVar(value=default_install_path())
        self.log_level = tk.StringVar(value="INFO")
        self.deployment = None
        self._signed_in = False
        self._token = None

        self._build_chrome()
        self.steps = [
            self.page_welcome, self.page_connect, self.page_location,
            self.page_install, self.page_validate,
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
                     font=("Segoe UI", 10), justify="left").pack(anchor="w", pady=(0, 10))

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
        if page == self.page_connect and not self._signed_in:
            messagebox.showwarning(
                "Sign in required",
                "Please test the connection and sign in with the store login first.")
            return False
        return True

    def _route_urls(self):
        """Ordered, de-duplicated routes: primary HO URL then any extras."""
        urls = []
        for value in [self.ho_url.get()] + self.extra_routes.get().split(","):
            u = (value or "").strip().rstrip("/")
            if u and u not in urls:
                urls.append(u)
        return urls

    # ---- STEP 1 -----------------------------------------------------------

    def page_welcome(self):
        self._title("Welcome",
                    "This installs the Nexora Store Agent on this machine.")
        msg = (
            "You only need two things:\n"
            "   -  the Head Office (HO) URL  (e.g. http://192.168.1.10:8000)\n"
            "   -  a store login  (created in HO and assigned to this store)\n\n"
            "The agent registers this machine automatically, then learns which\n"
            "stores it handles from HO. No tenant/store picker, no SQL details.\n\n"
            "After install you never touch this machine again - stores and\n"
            "credentials are managed entirely from HO.  Click Next to begin."
        )
        tk.Label(self.body, text=msg, bg="white", fg="#333", justify="left",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=4)

    # ---- STEP 2 -----------------------------------------------------------

    def page_connect(self):
        self._title("Connect & Sign in",
                    "Enter the HO URL and the store login created for this machine.")

        def field(label, var, show=None):
            row = tk.Frame(self.body, bg="white")
            row.pack(fill="x", pady=5)
            tk.Label(row, text=label, bg="white", width=16, anchor="w",
                     font=("Segoe UI", 10)).pack(side="left")
            ttk.Entry(row, textvariable=var, width=40, show=show).pack(side="left", padx=6)

        field("HO URL:", self.ho_url)
        field("More routes:", self.extra_routes)
        tk.Label(self.body, text="(optional - extra HO URLs, comma separated, for failover)",
                 bg="white", fg="#888", font=("Segoe UI", 8)).pack(anchor="w", padx=140)
        field("Username:", self.username)
        field("Password:", self.password, show="*")

        btnrow = tk.Frame(self.body, bg="white")
        btnrow.pack(anchor="w", pady=10, padx=140)
        ttk.Button(btnrow, text="Test & Sign in",
                   command=self._test_and_signin).pack(side="left")
        self.connect_result = tk.Label(self.body, text="", bg="white",
                                       font=("Segoe UI", 10), justify="left")
        self.connect_result.pack(anchor="w", pady=6, padx=140)

    def _test_and_signin(self):
        self.set_status("Connecting to HO...")
        routes = self._route_urls()
        if not routes:
            self.connect_result.config(text="Enter the HO URL.", fg="#b00020")
            self.set_status("")
            return
        if not self.username.get().strip() or not self.password.get():
            self.connect_result.config(text="Enter the store username and password.",
                                       fg="#b00020")
            self.set_status("")
            return
        # First reachable route wins for the install-time conversation.
        reachable = None
        errors = []
        for url in routes:
            try:
                HoClient(url).test_connection()
                reachable = url
                break
            except HoConnectionError as ex:
                errors.append(f"{url} -> {ex}")
        if not reachable:
            self._signed_in = False
            self.connect_result.config(
                text="HO not reachable:\n" + "\n".join(errors), fg="#b00020")
            self.set_status("")
            return
        # Validate the login now, so a bad credential is caught here, not
        # halfway through install.
        try:
            dep = DeviceDeployment(reachable, self.username.get().strip(),
                                   self.password.get(), self.install_path.get(),
                                   route_urls=routes)
            dep.authenticate()
            self._token = dep._token
            self._signed_in = True
            self.connect_result.config(
                text=f"Signed in via {reachable}.  Click Next.", fg=PRIMARY)
        except HoConnectionError as ex:
            self._signed_in = False
            self.connect_result.config(text=f"Sign in failed: {ex}", fg="#b00020")
        self.set_status("")

    # ---- STEP 3 -----------------------------------------------------------

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

    def _browse(self):
        path = filedialog.askdirectory(initialdir="C:/")
        if path:
            self.install_path.set(path.replace("/", "\\"))

    # ---- STEP 4 -----------------------------------------------------------

    def page_install(self):
        self._title("Install", f"Registering this machine and installing the agent.")
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
            routes = self._route_urls()
            self.deployment = DeviceDeployment(
                routes[0], self.username.get().strip(), self.password.get(),
                self.install_path.get(), log_level=self.log_level.get(),
                log=lambda m: self.after(0, self._logln, m), route_urls=routes,
            )
            self.after(0, self._logln, "[1/4] Authenticating store login...")
            self.deployment.authenticate()
            self.after(0, self._logln, "[2/4] Registering this machine (device key)...")
            self.deployment.register_device()
            self.after(0, self._logln, "[3/4] Installing agent + watchdog services...")
            self.after(0, self._logln, "[4/4] Starting services...")
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

    # ---- STEP 5 -----------------------------------------------------------

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
