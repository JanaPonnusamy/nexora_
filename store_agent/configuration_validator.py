class ConfigurationValidator:

    def validate(self, config):
        required = [
            "SQL_SERVER",
            "SQL_DATABASE",
            "STORE_ID",
            "HO_API_URL"
        ]

        return all(k in config for k in required)
