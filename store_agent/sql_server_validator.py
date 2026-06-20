class SqlServerValidator:

    def validate_version_text(self, version_text):

        if not version_text:
            return False

        return "Microsoft SQL Server" in version_text
