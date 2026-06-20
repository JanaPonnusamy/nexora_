
from store_agent.store_password_encryption_runtime import (
    StorePasswordEncryptionRuntime
)

def test_password_encryption_runtime_exists():

    runtime = StorePasswordEncryptionRuntime()

    assert runtime is not None
