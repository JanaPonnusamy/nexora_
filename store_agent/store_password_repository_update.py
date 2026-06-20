
class StorePasswordRepositoryUpdate:

    def build_update_command(
        self,
        store_id,
        encrypted_password
    ):

        sql = """
        UPDATE dbo.stores
        SET
            password_encrypted = ?,
            updated_at = GETDATE()
        WHERE
            store_id = ?
        """

        params = (
            encrypted_password,
            store_id
        )

        return sql, params
