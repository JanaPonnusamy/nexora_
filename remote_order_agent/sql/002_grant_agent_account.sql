/*  Grant the agent's virtual service account access to OrderNMC only (no sa, no password).
    Run AFTER the Windows service NMVSyncAgent exists:
      sqlcmd -S "DESKTOP-2\SQLEXPRESSORDER" -E -b -v DB=OrderNMC -i 002_grant_agent_account.sql
*/
:on error exit
SET NOCOUNT ON;
USE [master];
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'NT SERVICE\NMVSyncAgent')
    CREATE LOGIN [NT SERVICE\NMVSyncAgent] FROM WINDOWS WITH DEFAULT_DATABASE = [$(DB)];
GO
USE [$(DB)];
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'NT SERVICE\NMVSyncAgent')
    CREATE USER [NT SERVICE\NMVSyncAgent] FOR LOGIN [NT SERVICE\NMVSyncAgent];
ALTER ROLE db_datareader ADD MEMBER [NT SERVICE\NMVSyncAgent];
ALTER ROLE db_datawriter ADD MEMBER [NT SERVICE\NMVSyncAgent];
GRANT EXECUTE TO [NT SERVICE\NMVSyncAgent];
PRINT 'NT SERVICE\NMVSyncAgent granted db_datareader, db_datawriter, EXECUTE on $(DB).';
GO
