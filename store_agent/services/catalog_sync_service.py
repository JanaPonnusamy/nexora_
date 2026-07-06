import requests


class CatalogSyncService:
    """SYNC-030/031 Configuration + Catalog Synchronization Engine."""

    def __init__(self, ho_api_url):
        self.base = ho_api_url.rstrip("/")

    def download_configuration(self, task_id):
        response = requests.get(
            self.base + "/api/sync/configuration/" + str(task_id),
            timeout=120,
        )
        response.raise_for_status()
        return response.json()
