# HO_Setup bundled assets

Place the production database backup here before building the installer:

```
ho_setup/assets/NEXORA_PLATFORM.bak
```

## How to produce NEXORA_PLATFORM.bak

On a reference machine that already has a correct, seeded `NEXORA_PLATFORM`
database (schema + stored procedures + seed roles/permissions, and the initial
platform admin), create a clean full backup:

```sql
BACKUP DATABASE [NEXORA_PLATFORM]
TO DISK = N'C:\temp\NEXORA_PLATFORM.bak'
WITH INIT, COPY_ONLY, FORMAT, COMPRESSION,
     NAME = N'NEXORA_PLATFORM full backup';
```

Copy the resulting `.bak` into this folder. `python -m ho_setup.build` bundles
it into `HO_Setup.exe`; at install time it is restored onto the tenant's SQL
Server (logical files are remapped automatically to the instance's default data
and log directories).

> This file is intentionally **not** committed to git (`*.bak` is git-ignored).
> Keep it in your release pipeline / artifact store.
