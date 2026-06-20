from store_agent.store_agent_configuration_service import (
    StoreAgentConfigurationService
)

class RuntimeConfigurationLoader:

    def load(self, url):

        config = (
            StoreAgentConfigurationService()
            .get_runtime_config(url)
        )

        return {
            "store_id": config.get("store_id"),
            "sql_server": config.get("server_name"),
            "database_name": config.get("database_name"),
            "sql_username": config.get("username"),
            "password_encrypted": config.get("password_encrypted"),
            "connection_type": config.get("connection_type"),
            "is_active": config.get("is_active")
        }
