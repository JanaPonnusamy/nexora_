
class RuntimeBootstrapVerification:

    def build_status(
        self,
        config_downloaded,
        credentials_decrypted,
        sql_connected,
        sql_verified,
        database_verified
    ):

        return {
            "config_downloaded": config_downloaded,
            "credentials_decrypted": credentials_decrypted,
            "sql_connected": sql_connected,
            "sql_verified": sql_verified,
            "database_verified": database_verified,
            "runtime_ready": (
                config_downloaded and
                credentials_decrypted and
                sql_connected and
                sql_verified and
                database_verified
            )
        }
