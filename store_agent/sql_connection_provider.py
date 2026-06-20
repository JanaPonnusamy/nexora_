import pyodbc

from store_agent.sql_connection_factory import (
    SqlConnectionFactory
)

class SqlConnectionProvider:

    def get_connection(self, runtime_context):

        connection_string = (
            SqlConnectionFactory()
            .build_connection_string(runtime_context)
        )

        return pyodbc.connect(connection_string)
