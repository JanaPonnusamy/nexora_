
from store_agent.store_password_encryption_runtime import (
    StorePasswordEncryptionRuntime
)
from store_agent.store_password_repository_update import (
    StorePasswordRepositoryUpdate
)

class StorePasswordPersistenceIntegration:

    def build(
        self,
        store_id,
        password
    ):
        encrypted_password = (
            StorePasswordEncryptionRuntime()
            .encrypt_password(password)
        )

        sql, params = (
            StorePasswordRepositoryUpdate()
            .build_update_command(
                store_id,
                encrypted_password
            )
        )

        return {
            "sql": sql,
            "params": params,
            "encrypted_password": encrypted_password
        }
