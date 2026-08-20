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

        connection = pyodbc.connect(connection_string)
        # Master tables like ProductTrans re-scan a 600-day rolling window on
        # every cycle; without a query timeout a slow/blocked scan on a busy
        # store hangs the connection indefinitely, freezing that table's sync
        # with no error ever raised (observed: 4 stores' ProductTrans stopped
        # updating for days with nothing reported). A bounded timeout turns
        # that into a normal, retried-next-cycle failure instead.
        connection.timeout = 300
        return connection
