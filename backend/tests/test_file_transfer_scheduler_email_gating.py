"""file_transfer_scheduler.start_background_loop(): Phase 2 extraction --
must NOT start the in-process receiver thread when transport mode is EMAIL,
since that mode is owned exclusively by the standalone NexoraHOMailReceiver
process. Must still start normally for FILE_DROP/SFTP (unchanged behaviour).
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.sync import file_transfer_scheduler as scheduler


def _reset():
    scheduler.stop_background_loop()
    scheduler._thread = None


def test_email_mode_never_starts_in_process_thread():
    _reset()
    try:
        with mock.patch.object(scheduler.cfg, "enabled", return_value=True), \
             mock.patch.object(scheduler.cfg, "transport_config",
                                return_value={"mode": "EMAIL"}):
            thread = scheduler.start_background_loop()
        assert thread is None
        assert scheduler._thread is None
    finally:
        _reset()


def test_file_drop_mode_starts_in_process_thread():
    _reset()
    try:
        with mock.patch.object(scheduler.cfg, "enabled", return_value=True), \
             mock.patch.object(scheduler.cfg, "transport_config",
                                return_value={"mode": "FILE_DROP"}), \
             mock.patch.object(scheduler, "run_forever") as run_forever:
            run_forever.return_value = None  # thread target; just needs to return
            thread = scheduler.start_background_loop()
            assert thread is not None
            thread.join(timeout=2)
        assert run_forever.called
    finally:
        _reset()


def test_disabled_never_starts_regardless_of_mode():
    _reset()
    try:
        with mock.patch.object(scheduler.cfg, "enabled", return_value=False):
            thread = scheduler.start_background_loop()
        assert thread is None
    finally:
        _reset()
