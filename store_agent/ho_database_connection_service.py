
class HoDatabaseConnectionService:

    def build_update_execution(
        self,
        sql,
        params
    ):
        return {
            "sql": sql,
            "params": params
        }
