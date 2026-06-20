from backend.services.store_crypto_service import StoreCryptoService

def test_encrypt_decrypt_password():

    key = StoreCryptoService.generate_key()

    encrypted = StoreCryptoService.encrypt_password(
        "Admin123",
        key
    )

    assert encrypted != b"Admin123"

    decrypted = StoreCryptoService.decrypt_password(
        encrypted,
        key
    )

    assert decrypted == "Admin123"
