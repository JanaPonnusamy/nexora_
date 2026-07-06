import requests


class TaskPollingService:
    """SYNC-029 Store Agent Polling Engine."""

    def __init__(self, ho_api_url):
        self.base = ho_api_url.rstrip("/")

    def poll(self, store_id):
        response = requests.get(
            self.base + "/api/sync/tasks/pending/" + str(store_id),
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def create_task(self, tenant_id, store_id, execution_type="FULL",
                    sync_mode="FULL", total_tables=0):
        response = requests.post(
            self.base + "/api/sync/tasks/create",
            json={
                "tenant_id": tenant_id,
                "store_id": store_id,
                "execution_type": execution_type,
                "sync_mode": sync_mode,
                "total_tables": total_tables,
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def start(self, task_id):
        response = requests.post(
            self.base + "/api/sync/tasks/" + str(task_id) + "/start",
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def complete(self, task_id):
        response = requests.post(
            self.base + "/api/sync/tasks/" + str(task_id) + "/complete",
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def fail(self, task_id, message):
        response = requests.post(
            self.base + "/api/sync/tasks/" + str(task_id) + "/fail",
            json={"message": message},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
