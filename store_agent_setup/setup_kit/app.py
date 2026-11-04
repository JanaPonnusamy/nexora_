"""Nexora Setup window (Tkinter): This PC -> Head Office -> Store -> Apps -> Install.

    NexoraSetup.exe [--ho http://HOST:PORT]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import messagebox, ttk

from store_agent_setup.setup_kit import KIT_VERSION, KNOWN_HO_URLS, spec as spec_mod
from store_agent_setup.setup_kit.client import HoError, SetupClient, normalize_url
from store_agent_setup.setup_kit.engine import SetupError, SetupRun

PRIMARY = "#0B6E4F"
ERROR = "#b00020"
BG = "#f4f6f8"
LOG_DIR = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Nexora" / "Setup"


class SetupKit(tk.Tk):
    def __init__(self, ho_url=None):
        super().__init__()
        self.title("Nexora Setup")
        self.geometry("720x560")
        self.configure(bg=BG)
        self.resizable(False, False)

        self.spec = spec_mod.detect()
        self.client = None
        self.stores = []
        self.choose_store = False
        self.plan = None
        self.store = None
        self.done = False
        self.busy = False

        known = [f"{url}   ({label})" for url, label in KNOWN_HO_URLS]
        self.ho_choices = ([ho_url] if ho_url else []) + known
        self.ho_url = tk.StringVar(value=self.ho_choices[0])
        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.store_choice = tk.StringVar()
        self.agent_dir = tk.StringVar(value=self.spec.get("agent_dir") or r"C:\NexoraStoreAgent")
        self.picks = {}

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.log_path = LOG_DIR / f"setup_{datetime.datetime.now():%Y%m%d_%H%M%S}.log"
        self._write_log("Nexora Setup " + KIT_VERSION + "\nspec: " + json.dumps(self.spec, default=str))

        self._build_chrome()
        self.steps = [self.page_pc, self.page_ho, self.page_store, self.page_apps, self.page_install]
        self.index = 0
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.show_step()

    # ---- chrome -----------------------------------------------------------

    def _build_chrome(self):
        header = tk.Frame(self, bg=PRIMARY, height=64)
        header.pack(fill="x")
        tk.Label(header, text="  NEXORA  Setup", bg=PRIMARY, fg="white",
                 font=("Segoe UI", 16, "bold")).pack(side="left", pady=14)
        tk.Label(header, text=f"v{KIT_VERSION}  ", bg=PRIMARY, fg="white",
                 font=("Segoe UI", 9)).pack(side="right", pady=20)
        self.body = tk.Frame(self, bg="white")
        self.body.pack(fill="both", expand=True, padx=16, pady=12)
        nav = tk.Frame(self, bg=BG)
        nav.pack(fill="x", padx=16, pady=(0, 12))
        self.btn_back = ttk.Button(nav, text="< Back", command=self.back)
        self.btn_back.pack(side="left")
        self.btn_next = ttk.Button(nav, text="Next >", command=self.next)
        self.btn_next.pack(side="right")
        self.status = tk.Label(nav, text="", bg=BG, fg="#555", font=("Segoe UI", 9))
        self.status.pack(side="left", padx=12)

    def _clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    def _title(self, text, subtitle=""):
        tk.Label(self.body, text=text, bg="white", fg="#222",
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(8, 2))
        if subtitle:
            tk.Label(self.body, text=subtitle, bg="white", fg="#666", justify="left",
                     wraplength=660, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 10))

    def _note(self, text, color="#333", font=("Segoe UI", 10)):
        label = tk.Label(self.body, text=text, bg="white", fg=color, justify="left",
                         wraplength=660, font=font)
        label.pack(anchor="w", pady=2)
        return label

    def _write_log(self, text):
        try:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(f"{datetime.datetime.now():%H:%M:%S} {text}\n")
        except OSError:
            pass

    # ---- navigation -------------------------------------------------------

    def show_step(self):
        self._clear()
        self.status.config(text="")
        self.btn_back.config(state="normal" if self.index > 0 else "disabled")
        self.btn_next.config(text="Next >", state="normal", command=self.next)
        self.steps[self.index]()

    def next(self):
        problem = self._step_problem()
        if problem:
            messagebox.showwarning("Nexora Setup", problem)
            return
        self.index += 1
        self.show_step()

    def back(self):
        if self.index > 0:
            self.index -= 1
            self.show_step()

    def _step_problem(self):
        page = self.steps[self.index]
        if page == self.page_pc and not self.spec.get("is_admin"):
            return "Nexora Setup must run as Administrator (right-click > Run as administrator)."
        if page == self.page_ho and not (self.client and self.client.token and self.plan):
            return "Connect and sign in to HO first."
        if page == self.page_store and not self._selected_store():
            return "Choose the store this PC belongs to."
        return None

    def close(self):
        if self.busy and not messagebox.askyesno(
                "Nexora Setup", "Setup is still installing. Close anyway? (Running it again later is safe.)"):
            return
        if self.client and self.client.token:
            threading.Thread(target=self.client.logout, daemon=True).start()
        self.after(300, self.destroy)

    # ---- 1. This PC -------------------------------------------------------

    def page_pc(self):
        self._title("This PC", "Nexora Setup installs the Device Controller on every PC; it then "
                               "installs and looks after the Nexora apps HO assigns here.")
        box = tk.Text(self.body, height=11, font=("Consolas", 9), bg="#f7f9fa", relief="flat")
        box.insert("1.0", "\n".join(spec_mod.summary_lines(self.spec)))
        box.config(state="disabled")
        box.pack(fill="x", pady=4)
        if not self.spec.get("is_admin"):
            self._note("Not running as Administrator: close this and run Nexora Setup as administrator.",
                       ERROR)
        if not self.spec.get("odbc_drivers"):
            self._note("No SQL Server ODBC driver: install 'ODBC Driver 17 for SQL Server' before the "
                       "Store Agent can sync.", "#a15c00")

    # ---- 2. Head Office ---------------------------------------------------

    def page_ho(self):
        self._title("Head Office", "Choose the HO this PC belongs to and sign in once. A super admin "
                                   "picks the store next; a store login binds its own store.")

        def row(label, widget):
            r = tk.Frame(self.body, bg="white")
            r.pack(fill="x", pady=5)
            tk.Label(r, text=label, bg="white", width=12, anchor="w",
                     font=("Segoe UI", 10)).pack(side="left")
            widget(r).pack(side="left", padx=6)

        row("HO address:", lambda r: ttk.Combobox(r, textvariable=self.ho_url, values=self.ho_choices,
                                                  width=58))
        row("Username:", lambda r: ttk.Entry(r, textvariable=self.username, width=32))
        row("Password:", lambda r: ttk.Entry(r, textvariable=self.password, width=32, show="*"))
        bar = tk.Frame(self.body, bg="white")
        bar.pack(anchor="w", pady=10, padx=110)
        self.btn_connect = ttk.Button(bar, text="Connect & Sign in", command=self._connect)
        self.btn_connect.pack(side="left")
        self.connect_note = self._note("")
        if self.client and self.client.token:
            self._signed_in_note()

    def _signed_in_note(self):
        who = (self.client.user or {}).get("username") or self.username.get()
        self.connect_note.config(text=f"Signed in to {self.client.base} as {who}. Click Next.", fg=PRIMARY)

    def _connect(self):
        url = normalize_url(self.ho_url.get())
        if not url:
            self.connect_note.config(text="Enter the HO address.", fg=ERROR)
            return
        if not self.username.get().strip() or not self.password.get():
            self.connect_note.config(text="Enter the username and password.", fg=ERROR)
            return
        if self.client and self.client.token:
            if self.client.base == url:
                self._signed_in_note()
                return
            threading.Thread(target=self.client.logout, daemon=True).start()
        self.client, self.plan = None, None
        self.btn_connect.config(state="disabled")
        self.status.config(text="Connecting to HO...")
        threading.Thread(target=self._connect_worker, args=(url,), daemon=True).start()

    def _connect_worker(self, url):
        client = SetupClient(url)
        try:
            client.probe()
            client.login(self.username.get().strip(), self.password.get())
            stores = client.stores()
            plan = client.plan(self.spec)
        except HoError as ex:
            if client.token:
                client.logout()
            self.after(0, self._connect_failed, str(ex))
            return
        self._write_log(f"signed in to {url} as {(client.user or {}).get('username')}; "
                        f"plan: {json.dumps(plan, default=str)}")
        self.after(0, self._connected, client, stores, plan)

    def _connect_failed(self, message):
        self.status.config(text="")
        self.btn_connect.config(state="normal")
        self.connect_note.config(text=message, fg=ERROR)
        self._write_log("connect failed: " + message)

    def _connected(self, client, stores, plan):
        self.client, self.plan = client, plan
        self.stores = stores.get("stores") or []
        self.choose_store = bool(stores.get("choose"))
        self.store_choice.set(self._store_label(self.stores[0]) if len(self.stores) == 1 else "")
        self.status.config(text="")
        self.btn_connect.config(state="normal")
        if not self.stores:
            self.connect_note.config(text="Signed in, but this login has no store. Ask HO to assign one, "
                                          "or sign in as a super admin.", fg=ERROR)
            return
        self._signed_in_note()

    # ---- 3. Store -----------------------------------------------------------

    @staticmethod
    def _store_label(s):
        name = s.get("store_name") or ""
        tenant = s.get("tenant_code") or s.get("tenant_name") or "-"
        return f"{tenant}  /  {s.get('store_code')}" + (f"  -  {name}" if name and name != s.get("store_code") else "")

    def _selected_store(self):
        label = self.store_choice.get()
        return next((s for s in self.stores if self._store_label(s) == label), None)

    def page_store(self):
        if self.choose_store:
            self._title("Store", "Super admin: choose the store this PC belongs to.")
            ttk.Combobox(self.body, textvariable=self.store_choice, state="readonly", width=70,
                         values=[self._store_label(s) for s in self.stores]).pack(anchor="w", pady=8)
        else:
            self._title("Store", "This login belongs to one store, so the PC is bound to it.")
            self._note(self.store_choice.get(), PRIMARY, ("Segoe UI", 12, "bold"))
        self._note("Every app installed now is registered to this store. HO can add more stores to the "
                   "PC later.", "#666")

    # ---- 4. Apps ------------------------------------------------------------

    def page_apps(self):
        self.store = self._selected_store()
        self._title("Apps", f"What to install on {self.spec.get('machine_name')} for "
                            f"{self.store.get('store_code')}.")
        services = self.spec.get("services") or {}
        for comp in self.plan.get("components") or []:
            key = comp["app_key"]
            if key not in self.picks:
                default = comp["required"] or (key == "store_agent" and comp["eligible"])
                self.picks[key] = tk.BooleanVar(value=default)
            if not comp["eligible"]:
                self.picks[key].set(False)
            text = f"{comp['label']}  {comp.get('version') or ''}"
            if comp["required"]:
                text += "   (always installed)"
            if services.get(key) not in (None, "not-installed", "unknown"):
                text += f"   [already here: {services[key]}]"
            cb = ttk.Checkbutton(self.body, text=text, variable=self.picks[key])
            cb.pack(anchor="w", pady=(6, 0))
            if comp["required"] or not comp["eligible"]:
                cb.state(["disabled"])
            if comp.get("reason"):
                self._note("      " + comp["reason"], ERROR if not comp["eligible"] else "#a15c00",
                           ("Segoe UI", 9))
        r = tk.Frame(self.body, bg="white")
        r.pack(fill="x", pady=(14, 4))
        tk.Label(r, text="Store Agent folder:", bg="white", font=("Segoe UI", 10)).pack(side="left")
        ttk.Entry(r, textvariable=self.agent_dir, width=40).pack(side="left", padx=8)
        for w in self.plan.get("warnings") or []:
            self._note(w, "#a15c00")

    # ---- 5. Install ---------------------------------------------------------

    def page_install(self):
        picked = [k for k, v in self.picks.items() if v.get()]
        self._title("Install", "Installing: " + ", ".join(picked))
        self.log_box = tk.Text(self.body, height=17, font=("Consolas", 9), bg="#101418",
                               fg="#d8e0e6", relief="flat")
        self.log_box.pack(fill="both", expand=True, pady=6)
        self.btn_next.config(text="Install now", command=self._install)
        if self.done:
            self.btn_next.config(text="Close", command=self.close)

    def _logln(self, text):
        self._write_log(text)
        self.after(0, self._append_log, text)

    def _append_log(self, text):
        self.log_box.insert(tk.END, text + "\n")
        self.log_box.see(tk.END)

    def _install(self):
        components = [k for k, v in self.picks.items() if v.get()]
        dirs = {"store_agent": self.agent_dir.get().strip() or self.spec.get("agent_dir")}
        self.btn_next.config(state="disabled")
        self.btn_back.config(state="disabled")
        self.busy = True
        self._write_log(f"install {components} for store {self.store} dirs {dirs}")
        threading.Thread(target=self._install_worker, args=(components, dirs), daemon=True).start()

    def _install_worker(self, components, dirs):
        try:
            run = SetupRun(self.client, self.store["store_id"], self._logln)
            result = run.run_all(self.plan, components, dirs, self.spec)
            if result["failed"]:
                self._logln("Not finished: " + ", ".join(result["failed"]) + ". HO's Device Control "
                            "page shows the details; running Setup again is safe.")
            else:
                self._logln("Done. This PC is managed from HO's Device Control page.")
            self.after(0, self._finished, not result["failed"])
        except (HoError, SetupError) as ex:
            self._logln(f"ERROR: {ex}")
            self.after(0, self._finished, False)
        except Exception:
            self._logln("ERROR:\n" + traceback.format_exc())
            self.after(0, self._finished, False)

    def _finished(self, ok):
        self._append_log(f"Log saved to {self.log_path}")
        self.busy = False
        self.done = ok
        if ok:
            threading.Thread(target=self.client.logout, daemon=True).start()
            self.btn_next.config(state="normal", text="Close", command=self.close)
        else:
            self.btn_next.config(state="normal", text="Retry", command=self._install)
            self.btn_back.config(state="normal")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="NexoraSetup")
    parser.add_argument("--ho", default="")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--finish", action="store_true")
    parser.add_argument("--user", default="")
    parser.add_argument("--store-id", default="")
    parser.add_argument("--agent-dir", default="")
    parser.add_argument("--agent-exe", default="")
    parser.add_argument("--agent-version", default="")
    args, _ = parser.parse_known_args(argv)
    if args.prepare or args.finish:
        from store_agent_setup.setup_kit import unattended
        try:
            if args.finish:
                return unattended.finish()
            unattended.prepare(args.ho, args.user, args.store_id, args.agent_dir, args.agent_exe,
                               args.agent_version, os.environ.get(unattended.PASSWORD_ENV, ""),
                               sys.executable if getattr(sys, "frozen", False) else None)
            return 0
        except Exception:
            unattended.log("ERROR: " + traceback.format_exc())
            return 1
    try:
        SetupKit(normalize_url(args.ho) or None).mainloop()
    except Exception:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        crash = LOG_DIR / "setup_crash.log"
        with open(crash, "a", encoding="utf-8") as fh:
            fh.write(f"\n--- {datetime.datetime.now().isoformat()} ---\n")
            traceback.print_exc(file=fh)
        try:
            messagebox.showerror("Nexora Setup", f"Setup could not start. Details: {crash}")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
