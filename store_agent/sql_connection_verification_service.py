
class SqlConnectionVerificationService:

    def verify(self, connection):

        cursor = connection.cursor()

        cursor.execute("SELECT @@VERSION")
        version = cursor.fetchone()[0]

        cursor.execute("SELECT DB_NAME()")
        database_name = cursor.fetchone()[0]

        return {
            "is_connected": True,
            "sql_version": version,
            "database_name": database_name
        }
