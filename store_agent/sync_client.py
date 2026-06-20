import requests

class SyncClient:

    def post_schema(self, url, payload):
        response = requests.post(url, json=payload, timeout=60)
        return response.status_code
