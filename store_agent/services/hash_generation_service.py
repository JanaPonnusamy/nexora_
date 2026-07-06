import hashlib


class HashGenerationService:
    """SYNC-032 Hash Generation Engine."""

    def compute_row_hash(self, row, columns):
        parts = []
        for column in columns:
            value = row.get(column)
            parts.append("" if value is None else str(value))
        joined = "|".join(parts)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def attach_hash(self, rows, columns, hash_column="row_hash"):
        for row in rows:
            row[hash_column] = self.compute_row_hash(row, columns)
        return rows
