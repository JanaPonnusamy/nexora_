@echo off
REM Runs purge_agent_heartbeat_log.sql against NEXORA_PLATFORM.
REM Registered as scheduled task NexoraHeartbeatLogJanitor (every 6 hours, SYSTEM).
sqlcmd -S 192.168.10.73 -U sa -P Admin123 -d NEXORA_PLATFORM -i "%~dp0purge_agent_heartbeat_log.sql"
