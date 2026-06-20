class StoreAgentRuntimeContext:

    def __init__(self, runtime_config):

        self.store_id = runtime_config.get("store_id")
        self.sql_server = runtime_config.get("sql_server")
        self.database_name = runtime_config.get("database_name")
        self.sql_username = runtime_config.get("sql_username")
        self.sql_password = runtime_config.get("sql_password")
        self.ho_api_url = runtime_config.get("ho_api_url")

    def to_dict(self):

        return {
            "store_id": self.store_id,
            "sql_server": self.sql_server,
            "database_name": self.database_name,
            "sql_username": self.sql_username,
            "sql_password": self.sql_password,
            "ho_api_url": self.ho_api_url
        }
