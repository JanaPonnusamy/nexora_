"""Background poller for the FILE_TRANSFER receiver -- mirrors
modules/sync/scheduler_service.py's daemon-thread pattern (start once at
app startup, idempotent, never dies on an uncaught exception).

Kept entirely separate from the DIRECT_HTTP scheduler: they poll different
things (dbo.sync_schedule/dbo.sync_execution vs. a transport inbox) and one
failing must never affect the other.

Phase 2 extraction: for transport_mode == EMAIL, this in-process thread
deliberately does NOT start (see start_background_loop) -- the standalone
NexoraHOMailReceiver process (backend/mail_receiver_main.py) owns IMAP
polling exclusively for that mode, so there is never more than one process
holding an IMAP connection / racing over the same mailbox's UNSEEN messages.
FILE_DROP and SFTP are unaffected: this in-process thread keeps polling them
exactly as before.
"""
import threading

from modules.sync import file_transfer_config as cfg
from modules.sync import file_transfer_receiver_service as receiver
from modules.sync.file_transfer_transport.factory import build_receiver_transport

_stop_event = threading.Event()
_thread = None


def _log(line):
    try:
        print(line, flush=True)
    except Exception:
        pass


def _safe_tb():
    import traceback
    try:
        return traceback.format_exc()
    except Exception:
        return "<traceback unavailable>"


def run_forever(stop_event=None):
    """Blocking poll loop -- runs until stop_event is set. Public so it can
    be driven either by a background thread inside the FastAPI process
    (start_background_loop, FILE_DROP/SFTP) or as the entire body of the
    standalone NexoraHOMailReceiver process (backend/mail_receiver_main.py,
    EMAIL only). Identical polling logic either way -- no second receiver
    implementation, just a second place it can be hosted from."""
    stop_event = stop_event or _stop_event
    tick_seconds = cfg.tick_seconds()
    _log("[FILE_TRANSFER] Receiver loop started | tick_seconds=%s | mode=%s"
        % (tick_seconds, cfg.transport_config().get("mode")))
    while not stop_event.is_set():
        try:
            transport = build_receiver_transport(cfg.transport_config())
            summary = receiver.run_tick(transport)
            if summary.get("imported") or summary.get("rejected") or summary.get("failed"):
                _log("[FILE_TRANSFER] tick: " + str(summary))
        except Exception:
            _log("[FILE_TRANSFER] tick raised past run_tick() -- loop continues:\n" + _safe_tb())
        stop_event.wait(tick_seconds)
    _log("[FILE_TRANSFER] Receiver loop stopped")


def start_background_loop():
    """Idempotent: only starts if FILE_TRANSFER is enabled (objective 20:
    additive, never runs unless explicitly turned on), not already running,
    and NOT in EMAIL mode -- EMAIL polling is owned exclusively by the
    standalone NexoraHOMailReceiver process once that mode is configured
    (see module docstring); starting a second in-process poller against the
    same mailbox would race over the same UNSEEN messages."""
    global _thread
    if not cfg.enabled():
        return None
    if cfg.transport_config().get("mode") == "EMAIL":
        _log("[FILE_TRANSFER] mode=EMAIL: in-process receiver thread skipped "
            "-- run the standalone NexoraHOMailReceiver service instead")
        return None
    if _thread is not None and _thread.is_alive():
        return _thread
    _stop_event.clear()
    _thread = threading.Thread(
        target=run_forever, name="nexora-file-transfer-receiver", daemon=True
    )
    _thread.start()
    return _thread


def stop_background_loop():
    _stop_event.set()
