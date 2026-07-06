import requests

class ExecutionClient:

    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")

    def get_pending_execution(self, store_id):
        response = requests.get(
            f"{self.base_url}/api/sync/execution/pending/{store_id}",
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def start_execution(self, execution_id):
        response = requests.post(
            f"{self.base_url}/api/sync/execution/{execution_id}/start",
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def complete_execution(self, execution_id):
        response = requests.post(
            f"{self.base_url}/api/sync/execution/{execution_id}/complete",
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def fail_execution(self, execution_id, error_message):
        response = requests.post(
            f"{self.base_url}/api/sync/execution/{execution_id}/fail",
            json={"error_message": error_message},
            timeout=30
        )
        response.raise_for_status()
        return response.json()
