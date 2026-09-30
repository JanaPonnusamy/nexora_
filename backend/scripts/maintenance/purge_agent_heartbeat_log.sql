-- Heartbeat log is a pure agent-health ping (~30s interval per store), never
-- read for business data (see repositories/sync_admin_repository.py). Keep
-- only the last 3 days; run on a recurring schedule (NexoraHeartbeatLogJanitor).
SET NOCOUNT ON;
DECLARE @rc INT = 1;
WHILE @rc > 0
BEGIN
    DELETE TOP (5000) FROM dbo.agent_heartbeat_log WHERE heartbeat_time < DATEADD(DAY, -3, GETDATE());
    SET @rc = @@ROWCOUNT;
END
