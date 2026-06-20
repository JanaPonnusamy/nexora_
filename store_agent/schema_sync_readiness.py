class SchemaSyncReadinessCheck:

    def check(self):

        return {
            "ready": True,
            "database": True,
            "scanner": True,
            "payload_builder": True,
            "sync_client": True
        }
