from pathlib import Path

print("=" * 60)
print("SYNC-024A-REPAIR-04")
print("Agent Config URL Builder")
print("=" * 60)

project_root = Path(__file__).resolve().parent.parent

target = project_root / "store_agent" / "run_schema_discovery.py"

code = """
from pathlib import Path

from store_agent.config import STORE_ID, HO_API_URL
from store_agent.runtime_configuration_loader import RuntimeConfigurationLoader
from store_agent.runtime_context_factory import RuntimeContextFactory
from store_agent.runtime_sql_connection_service import RuntimeSqlConnectionService
from store_agent.services.schema_discovery_service import SchemaDiscoveryService

def main():

    config_url = (
        f"{HO_API_URL}/api/stores/{STORE_ID}/agent-config"
    )

    runtime_config = (
        RuntimeConfigurationLoader()
        .load(config_url)
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

config_file = project_root / "store_agent" / "config.py"

config_text = config_file.read_text(encoding="utf-8")

config_text = config_text.replace(
    'STORE_ID = ""',
    'STORE_ID = "109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1"'
)

config_file.write_text(config_text, encoding="utf-8")

print(f"[OK] Updated: {target}")
print(f"[OK] Updated: {config_file}")
print("SYNC-024A-REPAIR-04 COMPLETE")
