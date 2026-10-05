"""Sender-side transport adapter interface for FILE_TRANSFER sync mode.

Store Agent (sender) and HO (receiver, backend/modules/sync/
file_transfer_transport/ -- a separate deployable that cannot import this
package) each implement their half of the same physical channel (a
shared/mounted folder, an SFTP server, or a mailbox) so neither the package
format nor the merge logic ever needs to know which transport moved the
bytes. Swapping FILE_DROP <-> SFTP <-> EMAIL is a configuration change only
-- see transport_factory.py.
"""
from abc import ABC, abstractmethod


class SenderTransport(ABC):
    """Store-agent side: push outgoing packages, collect HO's result files."""

    @abstractmethod
    def upload(self, local_path, remote_name):
        """Copy local_path into the remote inbox as remote_name.

        Must raise on any failure so the caller leaves the package FAILED in
        the outbox for retry next cycle -- never silently drop it."""

    @abstractmethod
    def list_results(self):
        """Return [(remote_name, local_temp_path)] for result/ack files HO
        has published back for this store. Caller must call remove_result
        once a result has been durably recorded locally."""

    @abstractmethod
    def remove_result(self, remote_name):
        """Remove/archive a result file after it has been processed, so it
        is never read twice."""
