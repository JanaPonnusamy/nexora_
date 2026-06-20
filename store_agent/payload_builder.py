class PayloadBuilder:

    def build(self, store_id, database_name, tables):
        return {
            "store_id": store_id,
            "database_name": database_name,
            "tables": tables
        }
