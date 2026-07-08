import datetime
import decimal


def _json_safe(value):
    if value is None:
        return None
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    return value


class DataExtractionService:
    """SYNC-033 Data Extraction Engine."""

    def __init__(self, connection):
        self.connection = connection

    def _source_columns(self, table_name):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ?
            """,
            (table_name,),
        )
        return {row[0].lower() for row in cursor.fetchall()}

    def extract(self, table_config, watermark=None):
        table_name = table_config["table_name"]
        columns = [c["column_name"] for c in table_config.get("columns", [])]

        # Schema-version resilience: only request columns this store actually
        # has. Different RShopaid versions expose different column sets.
        available = self._source_columns(table_name)
        if columns and available:
            columns = [c for c in columns if c.lower() in available]

        if not columns:
            select_list = "*"
        else:
            select_list = ", ".join("[" + c + "]" for c in columns)

        where = []
        params = []

        watermark_column = table_config.get("watermark_column")

        # Drop watermark filtering when this store lacks the watermark column.
        if watermark_column and available and watermark_column.lower() not in available:
            watermark_column = None

        # Rolling-window tables must always re-scan the whole trailing window,
        # not just rows past the last watermark: some sources (e.g. ProductTrans)
        # key the watermark column to a business bucket (MonthOfStatistics) that
        # stays fixed while the row itself keeps getting updated in place all
        # month. A strict "> last watermark" cursor would see that bucket once
        # and then never re-fetch it again, silently freezing the row. Re-scanning
        # the full window every run is safe: the hash-diff stage downstream only
        # uploads rows whose content actually changed.
        if watermark_column:
            if table_config.get("window_days"):
                where.append(
                    "[" + watermark_column + "] >= DATEADD(day, ?, GETDATE())"
                )
                params.append(-int(table_config["window_days"]))
            elif watermark:
                where.append("[" + watermark_column + "] > ?")
                params.append(watermark)

        custom_where = table_config.get("custom_where")
        if custom_where:
            where.append("(" + custom_where + ")")

        sql = "SELECT " + select_list + " FROM [" + table_name + "]"
        if where:
            sql += " WHERE " + " AND ".join(where)

        cursor = self.connection.cursor()
        cursor.execute(sql, params)
        col_names = [c[0] for c in cursor.description]

        rows = []
        max_watermark = watermark
        for record in cursor.fetchall():
            row = {
                col_names[i]: _json_safe(record[i])
                for i in range(len(col_names))
            }
            rows.append(row)
            if watermark_column and watermark_column in row:
                value = row[watermark_column]
                if value is not None and (
                    max_watermark is None or str(value) > str(max_watermark)
                ):
                    max_watermark = value

        return {
            "table_name": table_name,
            "columns": col_names,
            "rows": rows,
            "row_count": len(rows),
            "max_watermark": max_watermark,
        }
