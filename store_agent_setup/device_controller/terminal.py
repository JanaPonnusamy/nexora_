"""Remote PowerShell sessions hosted by the controller.

Each HO terminal tab = one long-lived `powershell.exe -Command -` process with
piped stdin/stdout (running as the controller's account, LocalSystem). Input
arrives as signed term_input messages; output is batched and posted back to
HO every ~250ms, where it is stored for the audit trail.
"""
from __future__ import annotations

import codecs
import os
import subprocess
import threading
import time

from .util import CREATE_NO_WINDOW, log, run

IDLE_TIMEOUT_SECONDS = 30 * 60
FLUSH_INTERVAL = 0.25
MAX_POST_CHARS = 60000

_PROMPT = 'Write-Host -NoNewline ("PS " + (Get-Location).Path + "> ")\n'
_INIT = (
    "$ProgressPreference = 'SilentlyContinue'\n"
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
    "$OutputEncoding = [System.Text.Encoding]::UTF8\n"
    "Set-Location $env:SystemDrive\\\n"
    'Write-Host ("Nexora remote PowerShell on " + $env:COMPUTERNAME + " as " + '
    "[Security.Principal.WindowsIdentity]::GetCurrent().Name)\n"
)


class _Session:
    def __init__(self, session_id):
        self.session_id = session_id
        self.proc = None
        self.buffer = []
        self.lock = threading.Lock()
        self.last_activity = time.time()
        self.closed = False
        self.close_reason = None

    def spawn(self):
        self.proc = subprocess.Popen(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-OutputFormat", "Text", "-Command", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW, bufsize=0,
        )
        threading.Thread(target=self._pump, args=(self.proc,), daemon=True).start()
        self.write(_INIT)
        self.write(_PROMPT)

    def _pump(self, proc):
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        fd = proc.stdout.fileno()
        while True:
            try:
                data = os.read(fd, 4096)
            except OSError:
                break
            if not data:
                break
            text = decoder.decode(data)
            if text:
                with self.lock:
                    self.buffer.append(text)
        tail = decoder.decode(b"", final=True)
        if tail:
            with self.lock:
                self.buffer.append(tail)

    def write(self, text):
        if not self.proc or self.proc.poll() is not None:
            raise RuntimeError("PowerShell process is not running")
        self.proc.stdin.write(text.encode("utf-8"))
        self.proc.stdin.flush()

    def send_line(self, data):
        self.last_activity = time.time()
        # Every submitted block ends with a newline so PowerShell runs it, then
        # a prompt so the operator sees where the output ends.
        if not data.endswith("\n"):
            data += "\n"
        self.write(data)
        self.write(_PROMPT)

    def kill(self):
        if self.proc and self.proc.poll() is None:
            run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], timeout=20)

    def take_output(self):
        with self.lock:
            if not self.buffer:
                return []
            text = "".join(self.buffer)
            self.buffer = []
        return [text[i:i + MAX_POST_CHARS] for i in range(0, len(text), MAX_POST_CHARS)]

    def exited(self):
        return self.proc is None or self.proc.poll() is not None


class TerminalManager:
    def __init__(self, ho):
        self.ho = ho
        self.sessions = {}
        self.lock = threading.Lock()
        threading.Thread(target=self._flush_loop, daemon=True, name="term-flush").start()

    def open(self, session_id):
        with self.lock:
            if session_id in self.sessions:
                return
            session = _Session(session_id)
            self.sessions[session_id] = session
        try:
            session.spawn()
            log(f"[terminal] opened {session_id}")
        except Exception as ex:
            session.closed = True
            session.close_reason = f"could not start PowerShell: {ex}"
            log(f"[terminal] open failed {session_id}: {ex}")

    def input(self, session_id, data):
        session = self.sessions.get(session_id)
        if not session or session.closed:
            return
        try:
            session.send_line(data)
        except Exception as ex:
            with session.lock:
                session.buffer.append(f"\n[controller] input failed: {ex}\n")

    def reset(self, session_id):
        session = self.sessions.get(session_id)
        if not session or session.closed:
            return
        session.kill()
        with session.lock:
            session.buffer.append("\n[controller] session reset -- new PowerShell started\n")
        try:
            session.spawn()
        except Exception as ex:
            session.closed = True
            session.close_reason = f"reset failed: {ex}"

    def close(self, session_id, reason="closed by HO"):
        session = self.sessions.get(session_id)
        if not session:
            # Unknown here (e.g. controller restarted) -- still tell HO it's gone.
            self._post(session_id, [], closed=True, reason=reason)
            return
        session.kill()
        session.closed = True
        session.close_reason = reason

    def close_all(self, reason="controller stopping"):
        for sid in list(self.sessions):
            self.close(sid, reason)
        self._flush_once()

    def _post(self, session_id, chunks, closed=False, reason=None):
        try:
            self.ho.request("POST", f"/api/agent/controller/terminals/{session_id}/output",
                            json={"chunks": chunks, "closed": closed, "reason": reason}, timeout=20)
            return True
        except Exception as ex:
            log(f"[terminal] post failed {session_id}: {ex}")
            return False

    def _flush_once(self):
        for sid, session in list(self.sessions.items()):
            if not session.closed and session.exited():
                session.closed = True
                session.close_reason = session.close_reason or "PowerShell exited"
            if not session.closed and time.time() - session.last_activity > IDLE_TIMEOUT_SECONDS:
                session.kill()
                session.closed = True
                session.close_reason = "idle timeout"
            chunks = session.take_output()
            if session.closed:
                if self._post(sid, chunks, closed=True, reason=session.close_reason):
                    with self.lock:
                        self.sessions.pop(sid, None)
                    log(f"[terminal] closed {sid} ({session.close_reason})")
                else:
                    with session.lock:
                        session.buffer[:0] = chunks
            elif chunks and not self._post(sid, chunks):
                with session.lock:
                    session.buffer[:0] = chunks

    def _flush_loop(self):
        while True:
            try:
                self._flush_once()
            except Exception as ex:
                log(f"[terminal] flush error: {ex}")
            time.sleep(FLUSH_INTERVAL)
