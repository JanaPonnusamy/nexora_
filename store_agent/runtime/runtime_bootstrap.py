from store_agent import config
from store_agent.config import STORE_ID
from store_agent.runtime_configuration_loader import RuntimeConfigurationLoader
from store_agent.runtime_context_factory import RuntimeContextFactory
from store_agent.runtime_sql_connection_service import RuntimeSqlConnectionService
from store_agent.sql_connection_verification_service import SqlConnectionVerificationService

class RuntimeBootstrap:

    def bootstrap(self):

        config_url = (
            f"{config.active_ho_url()}/api/stores/{STORE_ID}/agent-config"
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

        verification = (
            SqlConnectionVerificationService()
            .verify(connection)
        )

        return {
            "runtime_context": runtime_context,
            "verification": verification
        }
