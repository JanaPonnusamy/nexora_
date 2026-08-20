# Remote Store Agent Upgrade

Use this when the store machine already has `NexoraStoreAgent` installed, and
you want to replace the binaries through a network share.

## Important path rule

Use the remote share path only for file copy.

- Remote share path example: `\\server-s\d\NexoraStoreAgent`
- Service runtime path on the store machine: `D:\NexoraStoreAgent`

Do not register the Windows service against the UNC path. The service should
run from the local drive on the target machine.

## Script

The generic upgrade script is:

`scripts/upgrade_store_agent_remote.ps1`

## Example for NMS

If `SERVER-S` is the NMS machine and the share is exposed as `\\server-s\d\`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\upgrade_store_agent_remote.ps1 `
  -ComputerName "SERVER-S" `
  -RemoteSharePath "\\server-s\d\NexoraStoreAgent" `
  -RemoteInstallLocalPath "D:\NexoraStoreAgent"
```

If the machine uses the default admin share, use this instead:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\upgrade_store_agent_remote.ps1 `
  -ComputerName "SERVER-S" `
  -RemoteSharePath "\\server-s\d$\NexoraStoreAgent" `
  -RemoteInstallLocalPath "D:\NexoraStoreAgent"
```

## What the script does

1. Verifies the local build artifacts in `dist\`
2. Backs up the current remote binaries
3. Stops the remote agent and watchdog services
4. Stops leftover remote processes
5. Copies the new binaries to the remote share
6. Recreates the services with the local store-machine path
7. Starts the services again
8. Prints remote service status

## Version marker note

The version marker written to `agent_version_installed.txt` is taken from:

1. the explicit `-Version` parameter, if you pass one
2. otherwise the latest folder under `backend/agent_releases`
3. otherwise the agent exe timestamp

If you want the deployed version marker and watchdog release tracking to match
the newest build, publish the release first.

## Publish a new release first

From the Nexora repo:

```powershell
python -m store_agent_setup.publish_release 2026.07.30.1 --notes "NMS remote upgrade"
```

That updates `backend/agent_releases\<version>\NexoraStoreAgent.exe` and marks
the version current for watchdog workflows.
