"""SQL Server deployment (wizard STEP 4 + 5).

Responsibilities:
* Test the SQL connection with the operator-supplied credentials.
* Detect whether the target database already exists.
* Provision the database by RESTORING the bundled NEXORA_PLATFORM.bak
  (no manual schema creation), remapping the backup's logical files onto the
  target instance's default data/log directories.
* Verify the restore succeeded.

The installer assumes SQL Server is installed on the SAME machine as HO (first
tenant deployment), so the .bak is restored FROM DISK using a local path the
SQL Server service account can read.
"""
import pyodbc

# Tables expected in a valid NEXORA_PLATFORM database (used by verify()).
_EXPECTED_TABLES = ("tenants", "stores", "roles")


class SqlError(Exception):
    pass


class SqlDeployer:
    def __init__(self, config, log=None):
        self.cfg = config
        self._log = log or (lambda msg: None)

    def log(self, msg):
        self._log(msg)

    # ---- connection -------------------------------------------------------

    def _conn_str(self, database="master"):
        cfg = self.cfg
        parts = [
            f"DRIVER={{{cfg.sql_driver}}};",
            f"SERVER={cfg.sql_server};",
            f"DATABASE={database};",
            "TrustServerCertificate=yes;",
        ]
        if str(cfg.auth_mode).upper() == "WINDOWS":
            parts.append("Trusted_Connection=yes;")
        else:
            parts.append(f"UID={cfg.sql_username};")
            parts.append(f"PWD={cfg.sql_password};")
        return "".join(parts)

    def _connect(self, database="master", autocommit=False):
        try:
            return pyodbc.connect(
                self._conn_str(database), autocommit=autocommit, timeout=15
            )
        except pyodbc.Error as ex:
            raise SqlError(self._friendly(ex)) from ex

    @staticmethod
    def _friendly(ex):
        text = str(ex)
        if "IM002" in text:
            return ("ODBC driver not found. Install 'ODBC Driver 17 for SQL "
                    "Server' on this machine.")
        if "Login failed" in text:
            return "Login failed. Check the SQL username/password."
        if "08001" in text or "SQL Server does not exist" in text:
            return ("Cannot reach SQL Server. Check the instance name and that "
                    "the SQL Server service is running.")
        return text

    # ---- STEP 4: test -----------------------------------------------------

    def test_connection(self):
        """Return the SQL Server @@VERSION on success; raise SqlError otherwise."""
        conn = self._connect("master")
        try:
            cur = conn.cursor()
            cur.execute("SELECT @@VERSION")
            version = cur.fetchone()[0]
            self.log("SQL connection OK")
            return version
        finally:
            conn.close()

    # ---- STEP 5: existence + restore -------------------------------------

    def database_exists(self):
        conn = self._connect("master")
        try:
            cur = conn.cursor()
            cur.execute("SELECT DB_ID(?)", self.cfg.database)
            return cur.fetchone()[0] is not None
        finally:
            conn.close()

    def _default_paths(self, cur):
        """(data_dir, log_dir) for the target instance."""
        cur.execute(
            "SELECT CAST(SERVERPROPERTY('InstanceDefaultDataPath') AS NVARCHAR(4000)),"
            " CAST(SERVERPROPERTY('InstanceDefaultLogPath') AS NVARCHAR(4000))"
        )
        data_dir, log_dir = cur.fetchone()
        if not data_dir or not log_dir:
            # Older SQL Server: derive from the master database's own files.
            cur.execute(
                "SELECT physical_name FROM sys.master_files "
                "WHERE database_id = 1 AND type = 0"
            )
            master_mdf = cur.fetchone()[0]
            folder = master_mdf.rsplit("\\", 1)[0]
            data_dir = data_dir or (folder + "\\")
            log_dir = log_dir or (folder + "\\")
        return data_dir.rstrip("\\") + "\\", log_dir.rstrip("\\") + "\\"

    def _filelist(self, cur, bak_path):
        """[(logical_name, type)] from RESTORE FILELISTONLY. type: D data / L log."""
        cur.execute("RESTORE FILELISTONLY FROM DISK = ?", bak_path)
        columns = [c[0].lower() for c in cur.description]
        li = columns.index("logicalname")
        ti = columns.index("type")
        return [(row[li], str(row[ti]).upper()) for row in cur.fetchall()]

    def _safe_db_identifier(self):
        name = self.cfg.database
        if "]" in name or "[" in name:
            raise SqlError(f"Unsafe database name: {name!r}")
        return f"[{name}]"

    def restore_database(self, bak_path, replace=False):
        """Restore NEXORA_PLATFORM.bak onto the target instance.

        ``replace=True`` is required (and confirmed by the wizard) when the
        database already exists.
        """
        bak_path = str(bak_path)
        db_ident = self._safe_db_identifier()
        conn = self._connect("master", autocommit=True)  # RESTORE: no transaction
        try:
            cur = conn.cursor()

            self.log("verifying backup file...")
            cur.execute("RESTORE VERIFYONLY FROM DISK = ?", bak_path)

            data_dir, log_dir = self._default_paths(cur)
            files = self._filelist(cur, bak_path)
            if not files:
                raise SqlError("Backup contains no files (invalid .bak).")

            move_clauses = []
            params = [bak_path]
            data_seen = 0
            for logical, ftype in files:
                if ftype == "L":
                    target = f"{log_dir}{self.cfg.database}_log.ldf"
                else:
                    suffix = "" if data_seen == 0 else f"_{data_seen}"
                    ext = "mdf" if data_seen == 0 else "ndf"
                    target = f"{data_dir}{self.cfg.database}{suffix}.{ext}"
                    data_seen += 1
                move_clauses.append("MOVE ? TO ?")
                params.append(logical)
                params.append(target)
                self.log(f"  {logical} -> {target}")

            if replace and self.database_exists():
                self.log("setting existing database to SINGLE_USER...")
                cur.execute(
                    f"ALTER DATABASE {db_ident} SET SINGLE_USER "
                    "WITH ROLLBACK IMMEDIATE"
                )

            self.log("restoring database (this can take a few minutes)...")
            sql = (
                f"RESTORE DATABASE {db_ident} FROM DISK = ? WITH "
                + ", ".join(move_clauses)
                + ", REPLACE, STATS = 5"
            )
            cur.execute(sql, *params)
            while cur.nextset():  # drain RESTORE progress result sets
                pass

            # Return to multi-user (ignore if it was a fresh restore).
            try:
                cur.execute(f"ALTER DATABASE {db_ident} SET MULTI_USER")
            except pyodbc.Error:
                pass

            self.log("restore completed.")
        except pyodbc.Error as ex:
            raise SqlError(f"Restore failed: {self._friendly(ex)}") from ex
        finally:
            conn.close()

    # ---- STEP 5: verify ---------------------------------------------------

    def verify_restore(self):
        """Confirm the database exists and contains the expected core tables."""
        if not self.database_exists():
            raise SqlError(f"Database {self.cfg.database} not found after restore.")
        conn = self._connect(self.cfg.database)
        try:
            cur = conn.cursor()
            missing = []
            for table in _EXPECTED_TABLES:
                cur.execute(
                    "SELECT OBJECT_ID(?, 'U')", table
                )
                if cur.fetchone()[0] is None:
                    missing.append(table)
            if missing:
                raise SqlError(
                    "Restore verification failed; missing tables: "
                    + ", ".join(missing)
                )
            self.log("restore verified (core tables present).")
            return True
        finally:
            conn.close()
