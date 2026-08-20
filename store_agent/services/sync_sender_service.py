import requests


class SyncSenderService:
    """SYNC-035 Chunk Sender Engine."""

    def __init__(self, ho_api_url):
        self.base = ho_api_url.rstrip("/")

    def send_chunk(self, execution_id, table_name, chunk_no, rows,
                   total_rows=None, sync_type=None):
        response = requests.post(
            self.base + "/api/sync/chunks/upload",
            json={
                "execution_id": execution_id,
                "table_name": table_name,
                "chunk_no": chunk_no,
                "rows": rows,
                "total_rows": total_rows,
                "sync_type": sync_type,
            },
            timeout=600,
        )
        response.raise_for_status()
        return response.json()

    def report_table_metrics(self, execution_id, table_name, sync_type,
                             rows_examined, rows_changed, rows_uploaded,
                             rows_skipped, source_total, status="COMPLETED",
                             error_message=None):
        response = requests.post(
            self.base + "/api/sync/tables/report",
            json={
                "execution_id": execution_id,
                "table_name": table_name,
                "sync_type": sync_type,
                "rows_examined": rows_examined,
                "rows_changed": rows_changed,
                "rows_uploaded": rows_uploaded,
                "rows_skipped": rows_skipped,
                "source_total": source_total,
                "status": status,
                "error_message": error_message,
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
