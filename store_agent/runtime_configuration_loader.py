from store_agent.store_agent_configuration_service import (
    StoreAgentConfigurationService
)

from store_agent.store_agent_config_decryption_service import (
    StoreAgentConfigDecryptionService
)

from store_agent.fernet_key_service import (
    FernetKeyService
)

class RuntimeConfigurationLoader:

    def load(self, url):

        config = (
            StoreAgentConfigurationService()
            .get_runtime_config(url)
        )

        key = FernetKeyService().load_key()

        sql_password = (
            StoreAgentConfigDecryptionService()
            .decrypt_password(
                bytes.fromhex(config.get('password_encrypted')),
                key
            )
        )

        return {
            'store_id': config.get('store_id'),
            'sql_server': config.get('server_name'),
            'database_name': config.get('database_name'),
            'sql_username': config.get('username'),
            'sql_password': sql_password,
            'connection_type': config.get('connection_type'),
            'is_active': config.get('is_active')
        }

