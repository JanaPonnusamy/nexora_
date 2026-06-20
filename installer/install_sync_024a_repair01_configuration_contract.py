from pathlib import Path

print("=" * 60)
print("SYNC-024A-REPAIR-01")
print("Configuration Contract Alignment")
print("=" * 60)

project_root = Path(__file__).resolve().parent.parent

target = project_root / "store_agent" / "runtime_configuration_loader.py"

code = """from store_agent.store_agent_configuration_service import (
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
"""

target.write_text(code, encoding="utf-8")

print(f"[OK] Updated: {target}")
print("SYNC-024A-REPAIR-01 COMPLETE")
