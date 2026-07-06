/*============================================================================
  seed_sharadha_stores.sql  -  UniNex / NEXORA_PLATFORM

  Idempotent store seed for the Sharadha tenant (SMG, SMA, SMF).

  * Resolves the Sharadha tenant_id automatically (no hardcoded tenant_id).
  * Inserts each store ONLY if it does not already exist (re-runnable).
  * store_id generated with NEWID().
  * password_encrypted uses the EXISTING encryption routine
    (backend.services.store_crypto_service.StoreCryptoService -> Fernet with
    store_agent/config/fernet.key). The VARBINARY literals below are Fernet
    tokens for the plaintext 'Admin123', produced by that routine, and decrypt
    via the SAME key bundled into the Store Agent (StoreAgentConfigDecryptionService).
  * created_at / updated_at set to GETDATE(); all runtime fields left NULL.

  Regenerate the password_encrypted literals (e.g. on key rotation) with:
      python -c "import sys; sys.path.insert(0,'.'); \
        from store_agent.fernet_key_service import FernetKeyService; \
        from backend.services.store_crypto_service import StoreCryptoService; \
        k=FernetKeyService().load_key(); \
        print('0x'+StoreCryptoService.encrypt_password('Admin123',k).hex())"

  Run against the HO database (NEXORA_PLATFORM):
      sqlcmd -S <HO_SQL> -d NEXORA_PLATFORM -E -b -i seed_sharadha_stores.sql
============================================================================*/

SET NOCOUNT ON;
SET XACT_ABORT ON;

USE [NEXORA_PLATFORM];

DECLARE @tenant_id UNIQUEIDENTIFIER;

/* Locate the Sharadha tenant automatically (code / abbreviation / name). */
SELECT TOP (1) @tenant_id = tenant_id
FROM dbo.tenants
WHERE tenant_code = 'Sharadha'
   OR tenant_abbreviation = 'Sharadha'
   OR tenant_name = 'Sharadha';

IF @tenant_id IS NULL
BEGIN
    RAISERROR(
        'Sharadha tenant not found in dbo.tenants (checked tenant_code / tenant_abbreviation / tenant_name). Aborting seed.',
        16, 1);
    RETURN;
END

PRINT 'Sharadha tenant_id = ' + CONVERT(VARCHAR(36), @tenant_id);

BEGIN TRANSACTION;

/*--------------------------------------------------------------------------
  SMG  -  WantedSMG  -  SERVERT30\WONDERSOFT / shopaid  -  branch: NULL
--------------------------------------------------------------------------*/
IF NOT EXISTS (
    SELECT 1 FROM dbo.stores
    WHERE tenant_id = @tenant_id AND store_code = 'SMG')
BEGIN
    INSERT INTO dbo.stores
        (store_id, tenant_id, store_code, store_name,
         server_name, database_name, username, password_encrypted,
         connection_type, branch_codes, is_active, created_at, updated_at)
    VALUES
        (NEWID(), @tenant_id, 'SMG', 'WantedSMG',
         'SERVERT30\WONDERSOFT', 'shopaid', 'sa',
         0x674141414141427151383061435439744e33576e5a5434516932374f2d5f56536e784d57306850583554447669796151643636386b442d4e6d636437745469504d79574c67342d4a7345585773536a4d43513270675468774d6a50497349373741413d3d,
         'SQL', NULL, 1, GETDATE(), GETDATE());
    PRINT 'Inserted store SMG (WantedSMG).';
END
ELSE
    PRINT 'Store SMG already exists - skipped.';

/*--------------------------------------------------------------------------
  SMA  -  WantedSMA  -  DELL-DESKTOP\SQLEXPRESS / OrderNMC  -  branch: L
--------------------------------------------------------------------------*/
IF NOT EXISTS (
    SELECT 1 FROM dbo.stores
    WHERE tenant_id = @tenant_id AND store_code = 'SMA')
BEGIN
    INSERT INTO dbo.stores
        (store_id, tenant_id, store_code, store_name,
         server_name, database_name, username, password_encrypted,
         connection_type, branch_codes, is_active, created_at, updated_at)
    VALUES
        (NEWID(), @tenant_id, 'SMA', 'WantedSMA',
         'DELL-DESKTOP\SQLEXPRESS', 'OrderNMC', 'sa',
         0x6741414141414271513830614d6f5f7159525a7430786b485a79415132553959482d32704b354b4c717758784c65382d596f6d786a326c4d3368514b4464624d6152334d5446736a4164305377314a745169747a72515873344c32596265473437673d3d,
         'SQL', 'L', 1, GETDATE(), GETDATE());
    PRINT 'Inserted store SMA (WantedSMA).';
END
ELSE
    PRINT 'Store SMA already exists - skipped.';

/*--------------------------------------------------------------------------
  SMF  -  WantedSMF  -  DELL-DESKTOP\SQLEXPRESS / OrderNMC  -  branch: L
--------------------------------------------------------------------------*/
IF NOT EXISTS (
    SELECT 1 FROM dbo.stores
    WHERE tenant_id = @tenant_id AND store_code = 'SMF')
BEGIN
    INSERT INTO dbo.stores
        (store_id, tenant_id, store_code, store_name,
         server_name, database_name, username, password_encrypted,
         connection_type, branch_codes, is_active, created_at, updated_at)
    VALUES
        (NEWID(), @tenant_id, 'SMF', 'WantedSMF',
         'DELL-DESKTOP\SQLEXPRESS', 'OrderNMC', 'sa',
         0x6741414141414271513830613675653441343559584b6f31637964735537517548397131436c4a7161584f7037396445386e6b3574556a614949334b6468517277637576736d4172583332696c3865415855795451433650636572685776416b5f413d3d,
         'SQL', 'L', 1, GETDATE(), GETDATE());
    PRINT 'Inserted store SMF (WantedSMF).';
END
ELSE
    PRINT 'Store SMF already exists - skipped.';

COMMIT TRANSACTION;

/* Verification output. */
SELECT store_code, store_name, server_name, database_name, username,
       connection_type, branch_codes, is_active, created_at
FROM dbo.stores
WHERE tenant_id = @tenant_id AND store_code IN ('SMG', 'SMA', 'SMF')
ORDER BY store_code;
GO
