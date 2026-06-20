
from store_agent.config import STORE_ID, HO_API_URL
from store_agent.runtime_configuration_loader import RuntimeConfigurationLoader
from store_agent.runtime_context_factory import RuntimeContextFactory
from store_agent.runtime_sql_connection_service import RuntimeSqlConnectionService
from store_agent.services.column_schema_discovery_service import ColumnSchemaDiscoveryService

config_url = f"{HO_API_URL}/api/stores/{STORE_ID}/agent-config"
runtime_config = RuntimeConfigurationLoader().load(config_url)
runtime_context = RuntimeContextFactory().create(runtime_config)
connection = RuntimeSqlConnectionService().connect(runtime_context)

result = ColumnSchemaDiscoveryService(connection).discover()

print("[OK] Column Schema Discovery Complete")
print(f"COLUMNS  : {result['column_count']}")
print(f"OUTPUT   : {result['output_file']}")
