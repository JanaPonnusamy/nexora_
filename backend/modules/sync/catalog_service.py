from .catalog_repository import get_sync_tables,get_sync_columns

def get_tables():
    return get_sync_tables()

def get_columns():
    return get_sync_columns()

def get_full_catalog():
    return {
        'tables': get_sync_tables(),
        'columns': get_sync_columns()
    }
