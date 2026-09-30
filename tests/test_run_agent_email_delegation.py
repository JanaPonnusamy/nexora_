"""run_agent._run_file_transfer_cycle: Phase 2 extraction contract -- for
transport.mode == EMAIL, this process must build a package (orchestrator.
run_cycle()) and STOP, never constructing a sender transport or running
FileTransferSyncDispatcher.run() (which would send over SMTP / poll IMAP).
That job belongs exclusively to the standalone NexoraMailTransfer process.
For FILE_DROP/SFTP, behaviour is unchanged: build AND deliver in one call.
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from store_agent import run_agent


def _ft_cfg(mode):
    return {
        "enabled": True,
        "interval_seconds": 1800,
        "mail_transfer_interval_seconds": 300,
        "transport": {"mode": mode},
    }


def test_email_mode_builds_only_never_constructs_sender_or_dispatcher():
    fake_orchestrator = mock.MagicMock()
    fake_orchestrator.run_cycle.return_value = {"status": "PACKAGED"}

    with mock.patch.object(run_agent, "RuntimeSqlConnectionService") as conn_svc, \
         mock.patch.object(run_agent.file_transfer_config, "file_transfer_config",
                            return_value=_ft_cfg("EMAIL")), \
         mock.patch.object(run_agent, "FileTransferOutbox"), \
         mock.patch.object(run_agent, "FileTransferRuntimeOrchestrator",
                            return_value=fake_orchestrator), \
         mock.patch.object(run_agent, "build_sender_transport") as build_sender, \
         mock.patch.object(run_agent, "FileTransferSyncDispatcher") as dispatcher_cls:
        conn_svc.return_value.connect.return_value = mock.MagicMock()
        run_agent._run_file_transfer_cycle(
            runtime_context=mock.MagicMock(), runtime_config={"tenant_id": "T1"},
            cache=mock.MagicMock(),
        )

    fake_orchestrator.run_cycle.assert_called_once()
    build_sender.assert_not_called()
    dispatcher_cls.assert_not_called()


def test_file_drop_mode_still_builds_and_delivers_in_one_call():
    fake_orchestrator = mock.MagicMock()
    fake_dispatcher = mock.MagicMock()
    fake_dispatcher.run.return_value = {"build": "x", "send": "y"}

    with mock.patch.object(run_agent, "RuntimeSqlConnectionService") as conn_svc, \
         mock.patch.object(run_agent.file_transfer_config, "file_transfer_config",
                            return_value=_ft_cfg("FILE_DROP")), \
         mock.patch.object(run_agent, "FileTransferOutbox"), \
         mock.patch.object(run_agent, "FileTransferRuntimeOrchestrator",
                            return_value=fake_orchestrator), \
         mock.patch.object(run_agent, "build_sender_transport") as build_sender, \
         mock.patch.object(run_agent, "FileTransferSyncDispatcher",
                            return_value=fake_dispatcher) as dispatcher_cls:
        conn_svc.return_value.connect.return_value = mock.MagicMock()
        run_agent._run_file_transfer_cycle(
            runtime_context=mock.MagicMock(), runtime_config={"tenant_id": "T1"},
            cache=mock.MagicMock(),
        )

    build_sender.assert_called_once()
    dispatcher_cls.assert_called_once()
    fake_dispatcher.run.assert_called_once()
    fake_orchestrator.run_cycle.assert_not_called()  # dispatcher.run() owns this, not us directly
