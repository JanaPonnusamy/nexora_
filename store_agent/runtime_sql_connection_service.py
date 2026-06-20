
from store_agent.sql_connection_provider import (
    SqlConnectionProvider
)

class RuntimeSqlConnectionService:

    def connect(self, runtime_context):

        return (
            SqlConnectionProvider()
            .get_connection(runtime_context)
        )
