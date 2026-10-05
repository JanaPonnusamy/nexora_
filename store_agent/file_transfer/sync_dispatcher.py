"""Ties the FILE_TRANSFER orchestrator, outbox, and transport together for
one full cycle: process any results HO has published back, build (at most)
one new package from current deltas, then attempt to send everything still
outstanding in the outbox.

Mirrors SyncRuntimeOrchestrator.flush_pending()'s retry semantics: a
transport failure stops further send attempts for this cycle (the next
scheduled cycle retries), it never raises out of run().
"""
import json
import os
from pathlib import Path


class FileTransferSyncDispatcher:
    def __init__(self, orchestrator, outbox, sender_transport):
        self.orchestrator = orchestrator
        self.outbox = outbox
        self.sender_transport = sender_transport

    def run(self):
        self._process_results()
        build_result = self.orchestrator.run_cycle()
        send_result = self._flush_pending()
        return {"build": build_result, "send": send_result}

    def run_delivery_only(self):
        """Process ACKs + send whatever is already durably queued in the
        outbox, WITHOUT building a new package (self.orchestrator is not
        touched -- may be None).

        Used by the standalone NexoraMailTransfer process (Phase 2
        extraction): when transport.mode is EMAIL, package *building* stays
        in the main Store Agent process (run_agent.py calls
        FileTransferRuntimeOrchestrator.run_cycle() directly), while package
        *delivery* (SMTP send + IMAP ACK poll) runs here, in a separate
        process, against the same SQLite outbox -- so a mail-server outage
        never blocks sync extraction, and the main agent process never has to
        hold a live SMTP/IMAP connection open."""
        process_result = self._process_results()
        send_result = self._flush_pending()
        return {"acks_processed": process_result, "send": send_result}

    def _flush_pending(self):
        sent = 0
        failed = 0
        for pkg in self.outbox.due_for_send():
            package_id = pkg["package_id"]
            zip_path = pkg["zip_path"]
            if not Path(zip_path).exists():
                continue
            sending_path = self.outbox.mark_sending(package_id, zip_path)
            try:
                remote_name = Path(sending_path).name
                self.sender_transport.upload(sending_path, remote_name)
                self.outbox.mark_sent(package_id, sending_path)
                sent += 1
            except Exception as ex:
                self.outbox.mark_failed(package_id, sending_path, str(ex))
                failed += 1
                break  # transport unreachable/failing; retry the rest next cycle
        return {"sent": sent, "failed": failed}

    def _process_results(self):
        processed = 0
        for remote_name, local_path in self.sender_transport.list_results():
            try:
                with open(local_path, "r", encoding="utf-8") as fh:
                    result = json.load(fh)
                package_id = result.get("package_id")
                if package_id:
                    self.outbox.mark_acknowledged(package_id, result)
                    processed += 1
                self.sender_transport.remove_result(remote_name)
            except Exception:
                pass  # left un-removed on the transport; retried next cycle
            finally:
                try:
                    os.remove(local_path)
                except OSError:
                    pass
        return processed
