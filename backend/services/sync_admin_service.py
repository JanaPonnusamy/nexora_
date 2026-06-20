
from repositories.sync_admin_repository import SyncAdminRepository

class SyncAdminService:

    # read-only
    def control_center(self):
        return SyncAdminRepository().control_center()

    def get_schedules(self):
        return SyncAdminRepository().get_schedules()

    def store_health(self):
        return SyncAdminRepository().store_health()

    def get_history(self):
        return SyncAdminRepository().get_history()

    def get_history_details(self, sync_id):
        return SyncAdminRepository().get_history_details(sync_id)

    # table configuration
    def catalog_tables(self, search=None):
        return SyncAdminRepository().catalog_tables(search)

    def get_tables(self):
        return SyncAdminRepository().get_tables()

    def get_table_by_id(self, sync_table_id):
        return SyncAdminRepository().get_table_by_id(sync_table_id)

    def table_name_exists(self, table_name, exclude_id=None):
        return SyncAdminRepository().table_name_exists(table_name, exclude_id)

    def create_table(self, table_name, sync_mode, watermark_column, window_days, custom_where, sync_order, is_active):
        return SyncAdminRepository().create_table(table_name, sync_mode, watermark_column, window_days, custom_where, sync_order, is_active)

    def update_table(self, sync_table_id, table_name, sync_mode, watermark_column, window_days, custom_where, sync_order):
        return SyncAdminRepository().update_table(sync_table_id, table_name, sync_mode, watermark_column, window_days, custom_where, sync_order)

    def set_table_active(self, sync_table_id, is_active):
        return SyncAdminRepository().set_table_active(sync_table_id, is_active)

    # column mapping
    def get_table_columns(self, sync_table_id):
        return SyncAdminRepository().get_table_columns(sync_table_id)

    def upsert_mapping(self, body):
        return SyncAdminRepository().upsert_mapping(
            body.sync_table_id, body.table_name, body.column_name, body.data_type,
            body.is_selected, body.is_pk, body.is_hash, body.is_watermark, body.column_order
        )

    @staticmethod
    def normalize_mode_fields(sync_mode, watermark_column, window_days):
        """UPSERT clears watermark/window; ROLLING_WINDOW requires them. Returns (error, watermark, window)."""
        mode = (sync_mode or "").upper()
        if mode == "UPSERT":
            return None, None, None
        if mode == "ROLLING_WINDOW":
            wc = (watermark_column or "").strip() or None
            if not wc:
                return "Watermark column is required for ROLLING_WINDOW", None, None
            if window_days is None:
                return "Window days is required for ROLLING_WINDOW", None, None
            return None, wc, window_days
        return "Sync mode must be UPSERT or ROLLING_WINDOW", None, None
