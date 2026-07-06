class RuntimeReadyService:

    def build(self, verification):

        return {
            "runtime_ready": verification.get("is_connected", False)
        }
