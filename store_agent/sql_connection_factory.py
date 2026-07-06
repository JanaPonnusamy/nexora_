import pyodbc


class SqlConnectionFactory:

    SUPPORTED_DRIVERS = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "ODBC Driver 11 for SQL Server",
        "SQL Server Native Client 11.0",
        "SQL Server"
    ]

    def _get_driver(self):

        installed = pyodbc.drivers()

        for driver in self.SUPPORTED_DRIVERS:
            if driver in installed:
                return driver

        raise RuntimeError(
            "No supported SQL Server ODBC driver installed. "
            f"Installed drivers: {installed}"
        )

    def build_connection_string(self, runtime_context):

        driver = self._get_driver()

        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={runtime_context.sql_server};"
            f"DATABASE={runtime_context.database_name};"
            f"UID={runtime_context.sql_username};"
            f"PWD={runtime_context.sql_password};"
            "TrustServerCertificate=yes;"
        )