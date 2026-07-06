import requests


class SyncAckProcessor:
    """SYNC-039 ACK Engine."""

    def __init__(self, ho_api_url):
        self.base = ho_api_url.rstrip("/")

    def ack(self, chunk_execution_id):
        response = requests.post(
            self.base + "/api/sync/chunks/ack",
            json={"chunk_execution_id": chunk_execution_id},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
