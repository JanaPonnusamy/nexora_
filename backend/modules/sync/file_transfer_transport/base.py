"""HO-side (receiver) transport interface. See store_agent/file_transfer/
transport_base.py for the sender-side counterpart -- same protocol, opposite
role, independently implemented (backend and store_agent never share a
runtime)."""
from abc import ABC, abstractmethod


class ReceiverTransport(ABC):
    @abstractmethod
    def list_incoming(self):
        """Return [(remote_name, local_temp_path)] for new packages waiting
        to be imported, across all stores (remote_name must let the caller
        recover which store it came from, e.g. '<store_id>/<file>')."""

    @abstractmethod
    def archive_incoming(self, remote_name, success):
        """Move a processed package out of the inbox so it is never
        re-imported. success=False routes it to a quarantine location
        instead of deleting it, so a rejected package can be inspected."""

    @abstractmethod
    def send_result(self, store_id, result_filename, local_path):
        """Deliver a result/ack file back to the originating store."""
