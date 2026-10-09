Imports System.IO
Imports System.Data.SqlClient
Imports System.Threading

Module SQL_Connection_Module

    Public destinationConnectionString As String
    Public destinationConnectionStringinstant As String
    Public serverName As String
    Dim logFilePath As String = "D:\OrderDotNet\Log\DBStatus.log"

    ' ================================
    '  Initialize Connection Strings
    ' ================================
    Public Sub InitializeConnectionString()
        Try
            ' Load settings from secure registry
            Dim settings() As String = SecureSettingsManager.LoadSettings()
            If settings Is Nothing OrElse settings.Length < 4 Then
                MessageBox.Show("Failed to load settings from registry.")
                Exit Sub
            End If

            serverName = settings(0)
            Dim databaseName As String = settings(1)
            Dim username As String = settings(2)
            Dim password As String = settings(3)

            destinationConnectionString = "Data Source=" & serverName & ";Initial Catalog=" & databaseName & ";User ID=" & username & ";Password=" & password
            destinationConnectionStringinstant = "Data Source=" & serverName & ";Initial Catalog=master;User ID=" & username & ";Password=" & password

            WriteToLog("Connection initialized for server: " & serverName)

        Catch ex As Exception
            WriteToLog("Error initializing connection string: " & ex.Message)
        End Try
    End Sub


    Private Function LoadSettingsFromFile(path As String) As String()
        Try
            If Not File.Exists(path) Then
                WriteToLog("Settings file missing: " & path)
                Return Nothing
            End If

            Dim lines As List(Of String) = New List(Of String)
            Using sr As New StreamReader(path)
                While Not sr.EndOfStream
                    Dim line As String = sr.ReadLine().Trim()
                    If line <> "" Then lines.Add(line)
                End While
            End Using
            Return lines.ToArray()
        Catch ex As Exception
            WriteToLog("Error reading settings file: " & ex.Message)
            Return Nothing
        End Try
    End Function

    ' ================================
    '  Check DB Status and Recover
    ' ================================
    Public Sub CheckDatabaseStatusAndConnect()
        WriteToLog("Checking database status...")

        Try
            Using connection As New SqlConnection(destinationConnectionStringinstant)
                connection.Open()
                WriteToLog("Connected to SQL Server instance successfully.")
                CheckDatabaseState(connection, "OrderNMc")
                CheckDatabaseState(connection, "Order")
            End Using
        Catch ex As Exception
            WriteToLog("Connection check failed: " & ex.Message)
        End Try
    End Sub

    ' ================================
    '  Check Single DB State
    ' ================================
    Private Sub CheckDatabaseState(connection As SqlConnection, databaseName As String)
        Try
            Dim dbState As String = ""
            Dim userAccess As String = ""
            Dim cmdText As String = "SELECT state_desc, user_access_desc FROM sys.databases WHERE name = @db"

            Using cmd As New SqlCommand(cmdText, connection)
                cmd.Parameters.AddWithValue("@db", databaseName)
                Using rd As SqlDataReader = cmd.ExecuteReader()
                    If rd.Read() Then
                        dbState = rd("state_desc").ToString()
                        userAccess = rd("user_access_desc").ToString()
                    End If
                End Using
            End Using

            WriteToLog("Database '" & databaseName & "' state: " & dbState & ", access: " & userAccess)

            If dbState = "ONLINE" AndAlso userAccess = "MULTI_USER" Then
                WriteToLog("Database '" & databaseName & "' is healthy.")
                Exit Sub
            End If

            ' Destructive recovery (KILL / SINGLE_USER / EMERGENCY / DBCC REPAIR_ALLOW_DATA_LOSS) is no longer run
            ' automatically. It only runs when an administrator sets registry value AllowAutoDbRepair = "1".
            If Not IsAutoRepairAllowed() Then
                If dbState = "" Then
                    WriteToLog("Database '" & databaseName & "' not found on this server. No action taken.")
                Else
                    WriteToLog("Database '" & databaseName & "' needs attention (state: " & dbState & ", access: " & userAccess & "). Automatic repair is disabled; contact the administrator.")
                End If
                Exit Sub
            End If

            If dbState = "ONLINE" AndAlso userAccess = "SINGLE_USER" Then
                FixSingleUser(databaseName)
                Exit Sub
            End If

            If dbState = "SUSPECT" Or dbState = "RECOVERY_PENDING" Or dbState = "EMERGENCY" Then
                AttemptEmergencyRepair(databaseName)
            Else
                AttemptEmergencyRepair(databaseName)
            End If

        Catch ex As Exception
            WriteToLog("Error checking state: " & ex.Message)
        End Try
    End Sub

    ' ================================
    '  Fix SINGLE_USER → MULTI_USER
    ' ================================
    Private Sub FixSingleUser(databaseName As String)
        WriteToLog("Database '" & databaseName & "' is SINGLE_USER. Fixing...")
        Try
            Using conn As New SqlConnection(destinationConnectionStringinstant)
                conn.Open()
                KillExistingSessions(conn, databaseName)
                ExecuteSQL(conn, "ALTER DATABASE [" & databaseName & "] SET MULTI_USER", "Set MULTI_USER")
                WriteToLog("Database '" & databaseName & "' set to MULTI_USER successfully.")
            End Using
            TestDatabaseConnection(databaseName)
        Catch ex As Exception
            WriteToLog("Failed to fix SINGLE_USER: " & ex.Message)
        End Try
    End Sub

    ' ================================
    '  Attempt Emergency Repair
    ' ================================
    Private Sub AttemptEmergencyRepair(databaseName As String)
        WriteToLog("Starting emergency repair for database: " & databaseName)

        Try
            Using conn As New SqlConnection(destinationConnectionStringinstant)
                conn.Open()

                KillExistingSessions(conn, databaseName)

                ExecuteSQL(conn, "ALTER DATABASE [" & databaseName & "] SET EMERGENCY", "Set EMERGENCY")
                ExecuteSQL(conn, "ALTER DATABASE [" & databaseName & "] SET SINGLE_USER WITH ROLLBACK IMMEDIATE", "Set SINGLE_USER")
                ExecuteSQL(conn, "DBCC CHECKDB([" & databaseName & "], REPAIR_ALLOW_DATA_LOSS)", "Run DBCC CHECKDB")
                ExecuteSQL(conn, "ALTER DATABASE [" & databaseName & "] SET ONLINE", "Set ONLINE")
                ExecuteSQL(conn, "ALTER DATABASE [" & databaseName & "] SET MULTI_USER", "Set MULTI_USER")

                WriteToLog("Database '" & databaseName & "' repaired and set to MULTI_USER.")
                TestDatabaseConnection(databaseName)
            End Using

        Catch ex As Exception
            WriteToLog("Repair failed for '" & databaseName & "': " & ex.Message)
        End Try
    End Sub

    ' ================================
    '  Kill Active Sessions
    ' ================================
    Private Sub KillExistingSessions(conn As SqlConnection, databaseName As String)
        Try
            WriteToLog("Killing active sessions for '" & databaseName & "'...")
            Dim cmdText As String = "SELECT session_id FROM sys.dm_exec_sessions WHERE database_id = DB_ID(@db)"
            Dim spidList As New List(Of Integer)
            Using cmd As New SqlCommand(cmdText, conn)
                cmd.Parameters.AddWithValue("@db", databaseName)
                Using rd As SqlDataReader = cmd.ExecuteReader()
                    While rd.Read()
                        spidList.Add(rd.GetInt32(0))
                    End While
                End Using
            End Using

            For Each spid As Integer In spidList
                ExecuteSQL(conn, "KILL " & spid, "Killed SPID " & spid)
            Next

        Catch ex As Exception
            WriteToLog("Error killing sessions: " & ex.Message)
        End Try
    End Sub

    ' ================================
    '  Helper Execute SQL
    ' ================================
    Private Sub ExecuteSQL(conn As SqlConnection, query As String, action As String)
        Try
            Using cmd As New SqlCommand(query, conn)
                cmd.CommandTimeout = 120
                cmd.ExecuteNonQuery()
                WriteToLog("Success: " & action)
            End Using
        Catch ex As Exception
            WriteToLog("Failed: " & action & " - " & ex.Message)
        End Try
    End Sub

    ' ================================
    '  Verify DB Connectivity
    ' ================================
    Private Sub TestDatabaseConnection(databaseName As String)
        Try
            WriteToLog("Testing connection to '" & databaseName & "'...")
            ' Uses the configured login (registry) instead of a hard-coded one
            Dim builder As New SqlConnectionStringBuilder(destinationConnectionStringinstant)
            builder.InitialCatalog = databaseName
            Using conn As New SqlConnection(builder.ConnectionString)
                conn.Open()
                WriteToLog("Database '" & databaseName & "' verified OK.")
            End Using
        Catch ex As Exception
            WriteToLog("Connection test failed for '" & databaseName & "': " & ex.Message)
        End Try
    End Sub

    ' ================================
    '  Auto repair opt-in (registry)
    ' ================================
    Private Function IsAutoRepairAllowed() As Boolean
        Try
            Dim rk As Microsoft.Win32.RegistryKey = Microsoft.Win32.Registry.CurrentUser.OpenSubKey("Software\OrderDotNetApp\Config")
            If rk Is Nothing Then Return False
            Dim v As Object = rk.GetValue("AllowAutoDbRepair", "0")
            rk.Close()
            Return v IsNot Nothing AndAlso v.ToString() = "1"
        Catch
            Return False
        End Try
    End Function

    ' ================================
    '  NMV integration (HO-managed orders)
    ' ================================
    ' A store is integration-managed when it is listed in dbo.nmv_integration_store with IsManaged = 1.
    ' Databases without that table (other stores) are never managed, so their behaviour is unchanged.
    ' If the check itself fails, the store is treated as managed so that destructive actions stay blocked.
    Public Sub GetIntegrationFlags(storeName As String, ByRef isManaged As Boolean, ByRef allowWebExport As Boolean)
        isManaged = False
        allowWebExport = True
        If String.IsNullOrWhiteSpace(storeName) Then Exit Sub
        Try
            Using con As New SqlConnection(destinationConnectionString)
                con.Open()
                Dim sql As String = "IF OBJECT_ID('dbo.nmv_integration_store','U') IS NOT NULL " & _
                                    "SELECT IsManaged, AllowWebExport FROM dbo.nmv_integration_store WHERE StoreName = @s AND IsManaged = 1"
                Using cmd As New SqlCommand(sql, con)
                    cmd.Parameters.AddWithValue("@s", storeName.Trim())
                    Using rd As SqlDataReader = cmd.ExecuteReader()
                        If rd.Read() Then
                            isManaged = True
                            allowWebExport = Convert.ToBoolean(rd("AllowWebExport"))
                        End If
                    End Using
                End Using
            End Using
        Catch ex As Exception
            WriteToLog("Integration flag check failed for store '" & storeName & "': " & ex.Message & " - treating as managed.")
            isManaged = True
            allowWebExport = False
        End Try
    End Sub

    Public Function IsIntegrationManagedStore(storeName As String) As Boolean
        Dim managed As Boolean, webExport As Boolean
        GetIntegrationFlags(storeName, managed, webExport)
        Return managed
    End Function

    ' ================================
    '  Logging
    ' ================================
    Private Sub WriteToLog(message As String)
        Try
            Dim dir As String = Path.GetDirectoryName(logFilePath)
            If Not Directory.Exists(dir) Then Directory.CreateDirectory(dir)
            Using sw As New StreamWriter(logFilePath, True)
                sw.WriteLine(DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") & " - " & message)
            End Using
        Catch
        End Try
    End Sub

End Module
