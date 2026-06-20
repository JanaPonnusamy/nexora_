
from backend.services.store_crypto_service import (
    StoreCryptoService
)

class StoreAgentConfigDecryptionService:

    def decrypt_password(
        self,
        encrypted_password,
        key
    ):
        return StoreCryptoService.decrypt_password(
            encrypted_password,
            key
        )
