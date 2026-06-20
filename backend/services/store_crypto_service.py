from cryptography.fernet import Fernet

class StoreCryptoService:

    @staticmethod
    def generate_key():
        return Fernet.generate_key()

    @staticmethod
    def encrypt_password(password: str, key: bytes) -> bytes:
        return Fernet(key).encrypt(
            password.encode("utf-8")
        )

    @staticmethod
    def decrypt_password(
        encrypted_password: bytes,
        key: bytes
    ) -> str:
        return Fernet(key).decrypt(
            encrypted_password
        ).decode("utf-8")
