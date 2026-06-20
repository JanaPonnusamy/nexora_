
from store_agent.store_password_repository_update import (
    StorePasswordRepositoryUpdate
)

class StorePasswordPersistenceService:

    def create_update_request(
        self,
        store_id,
        encrypted_password
    ):
        return (
            StorePasswordRepositoryUpdate()
            .build_update_command(
                store_id,
                encrypted_password
            )
        )
