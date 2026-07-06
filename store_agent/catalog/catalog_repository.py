
from .catalog_database import get_connection, initialize_database

initialize_database()

def get_table_count():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sync_table_catalog")
        return cursor.fetchone()[0]
    finally:
        conn.close()
