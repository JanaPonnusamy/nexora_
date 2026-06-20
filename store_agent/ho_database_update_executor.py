
import pyodbc

class HoDatabaseUpdateExecutor:

    def execute(
        self,
        connection_string,
        sql,
        params
    ):
        connection = pyodbc.connect(
            connection_string
        )

        try:
            cursor = connection.cursor()

            cursor.execute(
                sql,
                params
            )

            rows_affected = cursor.rowcount

            connection.commit()

            return rows_affected

        finally:
            connection.close()
