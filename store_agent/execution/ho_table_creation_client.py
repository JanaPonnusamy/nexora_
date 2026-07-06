import requests

class HOTableCreationClient:

    def __init__(self, base_url='http://127.0.0.1:8000'):
        self.base_url = base_url.rstrip('/')

    def build(self, execution_id):

        response = requests.post(
            f'{self.base_url}/api/sync/table-creation/build/{execution_id}',
            timeout=120
        )

        response.raise_for_status()

        return response.json()
