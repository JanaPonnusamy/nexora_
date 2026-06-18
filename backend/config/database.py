import pyodbc

def get_connection():
    conn_str = (
        'DRIVER={ODBC Driver 17 for SQL Server};'
        'SERVER=192.168.10.73;'
        'DATABASE=NEXORA_PLATFORM;'
        'UID=sa;'
        'PWD=Admin123;'
        'TrustServerCertificate=yes;'
    )
    return pyodbc.connect(conn_str)
