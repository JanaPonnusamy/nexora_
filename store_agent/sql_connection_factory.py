class SqlConnectionFactory:

    def build_connection_string(self, runtime_context):

        return (
            'DRIVER={ODBC Driver 17 for SQL Server};'
            f'SERVER={runtime_context.sql_server};'
            f'DATABASE={runtime_context.database_name};'
            f'UID={runtime_context.sql_username};'
            f'PWD={runtime_context.sql_password};'
            'TrustServerCertificate=yes;'
        )
