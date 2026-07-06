from config.database import get_connection

def get_sync_tables():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT sync_table_id,table_name,is_active,sync_mode,
               watermark_column,window_days,window_months,
               custom_where,sync_order,created_at
        FROM sync.sync_table_master
        WHERE is_active=1
        ORDER BY sync_order
        """)
        cols=[c[0] for c in cursor.description]
        return [dict(zip(cols,row)) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_sync_columns():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT mapping_id,sync_table_id,table_name,column_name,
               data_type,is_selected,is_pk,is_hash,
               is_watermark,column_order,created_at
        FROM sync.sync_column_mapping
        WHERE is_selected=1
        ORDER BY table_name,column_order
        """)
        cols=[c[0] for c in cursor.description]
        return [dict(zip(cols,row)) for row in cursor.fetchall()]
    finally:
        conn.close()
