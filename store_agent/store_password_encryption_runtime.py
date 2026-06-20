
from store_agent.fernet_key_service import FernetKeyService
from backend.services.store_crypto_service import StoreCryptoService

class StorePasswordEncryptionRuntime:

    def encrypt_password(self, password):

        key_service = FernetKeyService()

        if key_service.key_exists():
            key = key_service.load_key()
        else:
            key = key_service.generate_key()
            key_service.save_key(key)

        return StoreCryptoService.encrypt_password(
            password,
            key
        )
