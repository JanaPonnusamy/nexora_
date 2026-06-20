import pyodbc
from store_agent.config import (
    SQL_SERVER,
    SQL_DATABASE,
    SQL_USERNAME,
    SQL_PASSWORD
)

def get_connection():
    conn_str = (
        'DRIVER={ODBC Driver 17 for SQL Server};'
        f'SERVER={SQL_SERVER};'
        f'DATABASE={SQL_DATABASE};'
        f'UID={SQL_USERNAME};'
        f'PWD={SQL_PASSWORD};'
        'TrustServerCertificate=yes;'
    )
    return pyodbc.connect(conn_str)
