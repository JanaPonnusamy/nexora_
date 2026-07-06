import requests
from store_agent.config import HO_API_URL

def download_catalog():
    response = requests.get(f"{HO_API_URL}/api/sync/catalog/full", timeout=60)
    response.raise_for_status()
    return response.json()
