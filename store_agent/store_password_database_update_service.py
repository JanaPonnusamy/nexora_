
class StorePasswordDatabaseUpdateService:

    def build_update_payload(
        self,
        store_id,
        encrypted_password
    ):

        return {
            "store_id": store_id,
            "password_encrypted": encrypted_password
        }
