from pathlib import Path

ROOT = Path(r'E:\Nexora')
catalog_dir = ROOT / 'store_agent' / 'catalog'
catalog_dir.mkdir(parents=True, exist_ok=True)

(catalog_dir / 'catalog_client.py').write_text('''import requests
from store_agent.config import HO_API_URL

def download_catalog():
    response = requests.get(f"{HO_API_URL}/api/sync/catalog/full", timeout=60)
    response.raise_for_status()
    return response.json()
''', encoding='utf-8')

(catalog_dir / 'catalog_sync_service.py').write_text('''from .catalog_client import download_catalog
from .catalog_database import get_connection

def refresh_catalog():
    payload = download_catalog()

    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute("DELETE FROM sync_column_catalog")
        cur.execute("DELETE FROM sync_table_catalog")

        for row in payload.get("tables", []):
            cur.execute(
                "INSERT INTO sync_table_catalog VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    row.get('sync_table_id'),
                    row.get('table_name'),
                    int(bool(row.get('is_active'))),
                    row.get('sync_mode'),
                    row.get('watermark_column'),
                    row.get('window_days'),
                    row.get('window_months'),
                    row.get('custom_where'),
                    row.get('sync_order'),
                    str(row.get('created_at'))
                )
            )

        for row in payload.get("columns", []):
            cur.execute(
                "INSERT INTO sync_column_catalog VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row.get('mapping_id'),
                    row.get('sync_table_id'),
                    row.get('table_name'),
                    row.get('column_name'),
                    row.get('data_type'),
                    int(bool(row.get('is_selected'))),
                    int(bool(row.get('is_pk'))),
                    int(bool(row.get('is_hash'))),
                    int(bool(row.get('is_watermark'))),
                    row.get('column_order'),
                    str(row.get('created_at'))
                )
            )

        conn.commit()
    finally:
        conn.close()
''', encoding='utf-8')

print('SYNC-027C-B INSTALL COMPLETE')
