from pathlib import Path

print("=" * 60)
print("SYNC-024A-REPAIR-03")
print("Real Schema Discovery Runner")
print("=" * 60)

project_root = Path(__file__).resolve().parent.parent

target = project_root / "store_agent" / "run_schema_discovery.py"

code = """
from pathlib import Path

from store_agent.runtime_configuration_loader import RuntimeConfigurationLoader
from store_agent.runtime_context_factory import RuntimeContextFactory
from store_agent.runtime_sql_connection_service import RuntimeSqlConnectionService
from store_agent.services.schema_discovery_service import SchemaDiscoveryService

CONFIG_URL = "REPLACE_WITH_AGENT_CONFIG_URL"


def main():

    runtime_config = (
        RuntimeConfigurationLoader()
        .load(CONFIG_URL)
    )

    runtime_context = (
        RuntimeContextFactory()
        .create(runtime_config)
    )

    connection = (
        RuntimeSqlConnectionService()
        .connect(runtime_context)
    )

    discovery_service = SchemaDiscoveryService(connection)

    snapshot = discovery_service.discover_schema()

    output_dir = Path(__file__).parent / "schema"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "schema_snapshot.json"

    discovery_service.save_snapshot(
        snapshot,
        str(output_file)
    )

    print("[OK] Schema Discovery Complete")
    print(f"SERVER   : {snapshot['server_name']}")
    print(f"DATABASE : {snapshot['database_name']}")
    print(f"TABLES   : {snapshot['table_count']}")
    print(f"OUTPUT   : {output_file}")


if __name__ == "__main__":
    main()
"""

target.write_text(code, encoding="utf-8")

print(f"[OK] Updated: {target}")
print("SYNC-024A-REPAIR-03 COMPLETE")
