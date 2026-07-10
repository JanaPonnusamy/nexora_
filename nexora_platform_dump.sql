/* ============================================================
   NEXORA_PLATFORM sample dump  —  up to 10 real rows per table
   Source : NEXORA_PLATFORM @ 192.168.10.73
   Target : nexora_platform
   Notes  : schema + data only. Foreign keys intentionally omitted
            (a TOP-10 subset will not satisfy cross-table FKs).
   ============================================================ */
IF DB_ID('nexora_platform') IS NULL CREATE DATABASE [nexora_platform];
GO
USE [nexora_platform];
GO
IF SCHEMA_ID('procurement') IS NULL EXEC('CREATE SCHEMA [procurement]');
IF SCHEMA_ID('sync') IS NULL EXEC('CREATE SCHEMA [sync]');
GO

IF OBJECT_ID('dbo.agent_heartbeat_log') IS NOT NULL DROP TABLE [dbo].[agent_heartbeat_log];
GO
CREATE TABLE [dbo].[agent_heartbeat_log] (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [store_id] uniqueidentifier NOT NULL,
    [heartbeat_time] datetime NOT NULL,
    [ip_address] varchar(100) NULL,
    [agent_version] varchar(50) NULL,
    CONSTRAINT [PK_dbo_agent_heartbeat_log] PRIMARY KEY ([id])
);
GO
SET IDENTITY_INSERT [dbo].[agent_heartbeat_log] ON;
INSERT INTO [dbo].[agent_heartbeat_log] ([id], [tenant_id], [store_id], [heartbeat_time], [ip_address], [agent_version]) VALUES
    (1, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 17:59:58.093', N'10.0.0.5', N'1.0.0'),
    (2, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 17:59:58.170', NULL, NULL),
    (3, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 18:08:40.560', N'192.168.10.80', N'1.0.0'),
    (4, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 18:08:40.590', N'192.168.10.80', N'1.0.0'),
    (5, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 18:09:10.603', N'192.168.10.80', N'1.0.0'),
    (6, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 18:09:40.720', N'192.168.10.80', N'1.0.0'),
    (7, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 18:10:10.817', N'192.168.10.80', N'1.0.0'),
    (8, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 18:10:40.897', N'192.168.10.80', N'1.0.0'),
    (9, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 18:11:10.913', N'192.168.10.80', N'1.0.0'),
    (10, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 18:11:40.973', N'192.168.10.80', N'1.0.0');
SET IDENTITY_INSERT [dbo].[agent_heartbeat_log] OFF;
GO

IF OBJECT_ID('dbo.agent_version_catalog') IS NOT NULL DROP TABLE [dbo].[agent_version_catalog];
GO
CREATE TABLE [dbo].[agent_version_catalog] (
    [version_id] bigint IDENTITY(1,1) NOT NULL,
    [version_no] varchar(50) NOT NULL,
    [release_date] datetime NOT NULL,
    [release_notes] nvarchar(max) NULL,
    [is_active] bit NOT NULL,
    CONSTRAINT [PK_dbo_agent_version_catalog] PRIMARY KEY ([version_id])
);
GO

IF OBJECT_ID('dbo.global_audit_log') IS NOT NULL DROP TABLE [dbo].[global_audit_log];
GO
CREATE TABLE [dbo].[global_audit_log] (
    [audit_id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NULL,
    [store_id] uniqueidentifier NULL,
    [user_id] uniqueidentifier NULL,
    [module_name] varchar(100) NULL,
    [action_name] varchar(100) NULL,
    [old_value] nvarchar(max) NULL,
    [new_value] nvarchar(max) NULL,
    [created_at] datetime NOT NULL,
    CONSTRAINT [PK_dbo_global_audit_log] PRIMARY KEY ([audit_id])
);
GO

IF OBJECT_ID('dbo.modules') IS NOT NULL DROP TABLE [dbo].[modules];
GO
CREATE TABLE [dbo].[modules] (
    [module_id] uniqueidentifier NOT NULL,
    [module_code] varchar(50) NOT NULL,
    [module_name] varchar(100) NOT NULL,
    [description] varchar(500) NULL,
    [is_active] bit NOT NULL,
    CONSTRAINT [PK_dbo_modules] PRIMARY KEY ([module_id])
);
GO
INSERT INTO [dbo].[modules] ([module_id], [module_code], [module_name], [description], [is_active]) VALUES
    (N'F8D3A6DD-F47B-41C0-ACE7-0105218481A8', N'PROCUREMENT', N'Procurement', N'Procurement Management', 1),
    (N'B655CFCB-9271-453F-945A-0234DC04F93E', N'ROLES', N'Roles', N'Role Management', 1),
    (N'41A344EB-3A24-4C53-849D-0E423D80C55F', N'SYNC_MONITOR', N'Sync Monitor', N'Synchronization Monitoring', 1),
    (N'4A303000-33EE-4C38-BE61-11A1606A7163', N'SETTINGS', N'Settings', N'Platform Settings', 1),
    (N'210843D0-8875-4F24-9619-1A9FE316695B', N'MODULES', N'Modules', N'Module Management', 1),
    (N'27A99D55-6799-41C4-A9A2-1D66427236D9', N'PRODUCT_MAPPING', N'Product Mapping', N'Cross-store product mapping engine', 1),
    (N'B059C357-0390-4CBA-A13B-460320A7EFBB', N'SUPPLIER', N'Supplier', N'Supplier Management', 1),
    (N'C7E67895-DD4C-4155-A23E-5458DE1FDF0A', N'SYNC_JOBS', N'Sync Jobs', N'Synchronization Jobs', 1),
    (N'482B4EE8-5D10-4DF4-B04B-6BF5988EE993', N'SYNC', N'Sync', N'Store Synchronization', 1),
    (N'F7122D0E-5EF0-4835-938A-7BFE89DE8C32', N'USERS', N'Users', N'User Management', 1);
GO

IF OBJECT_ID('dbo.platform_settings') IS NOT NULL DROP TABLE [dbo].[platform_settings];
GO
CREATE TABLE [dbo].[platform_settings] (
    [setting_id] bigint IDENTITY(1,1) NOT NULL,
    [setting_key] varchar(100) NOT NULL,
    [setting_value] varchar(max) NULL,
    [description] varchar(500) NULL,
    [is_active] bit NULL,
    CONSTRAINT [PK_dbo_platform_settings] PRIMARY KEY ([setting_id])
);
GO
SET IDENTITY_INSERT [dbo].[platform_settings] ON;
INSERT INTO [dbo].[platform_settings] ([setting_id], [setting_key], [setting_value], [description], [is_active]) VALUES
    (1, N'THEME', N'DARK', N'Default Application Theme', 1),
    (2, N'PASSWORD_EXPIRY_DAYS', N'90', N'Password Expiry Policy', 1),
    (3, N'SESSION_TIMEOUT', N'30', N'Session Timeout In Minutes', 1);
SET IDENTITY_INSERT [dbo].[platform_settings] OFF;
GO

IF OBJECT_ID('dbo.product_mapping') IS NOT NULL DROP TABLE [dbo].[product_mapping];
GO
CREATE TABLE [dbo].[product_mapping] (
    [mapping_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [run_id] uniqueidentifier NOT NULL,
    [source_store_id] uniqueidentifier NOT NULL,
    [source_product_code] varchar(50) NOT NULL,
    [source_product_name] varchar(400) NOT NULL,
    [source_normalized_name] varchar(400) NULL,
    [target_store_id] uniqueidentifier NOT NULL,
    [target_product_code] varchar(50) NULL,
    [target_product_name] varchar(400) NULL,
    [match_method] varchar(20) NULL,
    [match_phase] int NULL,
    [confidence] decimal(5,2) NOT NULL,
    [status] varchar(20) NOT NULL,
    [brand] varchar(200) NULL,
    [strength] varchar(50) NULL,
    [unit] varchar(20) NULL,
    [dosage_form] varchar(30) NULL,
    [pack_size] varchar(30) NULL,
    [mrp] decimal(18,2) NULL,
    [created_at] datetime NOT NULL,
    [created_by] uniqueidentifier NULL,
    [updated_at] datetime NULL,
    [updated_by] uniqueidentifier NULL,
    [is_deleted] bit NOT NULL,
    [deleted_at] datetime NULL,
    [deleted_by] uniqueidentifier NULL,
    CONSTRAINT [PK_dbo_product_mapping] PRIMARY KEY ([mapping_id])
);
GO
INSERT INTO [dbo].[product_mapping] ([mapping_id], [tenant_id], [run_id], [source_store_id], [source_product_code], [source_product_name], [source_normalized_name], [target_store_id], [target_product_code], [target_product_name], [match_method], [match_phase], [confidence], [status], [brand], [strength], [unit], [dosage_form], [pack_size], [mrp], [created_at], [created_by], [updated_at], [updated_by], [is_deleted], [deleted_at], [deleted_by]) VALUES
    (N'AB7860EE-8556-4191-85DA-000121A1FBD3', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'DF82C426-7929-4C99-BC25-C2C3C8133D53', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'5857082', N'CAPTAR 40MG', N'CAPTAR40MG', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'5893948', N'CAPTAR TAB', N'SUPPLIER', 1, 100.00, N'AUTO', N'CAPTAR', N'40', N'MG', NULL, NULL, 77.90, '2026-07-05 13:34:21.157', NULL, NULL, NULL, 0, NULL, NULL),
    (N'D58AE5CF-C4F8-4804-A216-0002521FE939', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'E6E1FCC6-D06A-4BA9-A211-397C7C68EFB0', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'5873904', N'RHEZA ASP 75MG CAPS 10''S', N'RHEZAASP75MGCAPS10S', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', NULL, NULL, NULL, 7, 0.00, N'PENDING', N'RHEZA ASP', N'75', N'MG', N'CAP', N'10', 53.50, '2026-07-05 13:10:35.630', NULL, NULL, NULL, 1, '2026-07-05 13:15:14.310', NULL),
    (N'43B37EA3-40CC-42B6-8F83-00027C6B9F4B', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'DF82C426-7929-4C99-BC25-C2C3C8133D53', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'5889345', N'ASWINI HIRAN STRONG OIL', N'ASWINIHIRANSTRONGOIL', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'5883278', N'ASWINI HAND SANITIZER 50ML', N'FUZZY', 7, 42.83, N'PENDING', N'ASWINI HIRAN STRONG OIL', NULL, NULL, NULL, NULL, 180.00, '2026-07-05 13:34:23.660', NULL, NULL, NULL, 0, NULL, NULL),
    (N'1D582931-0AF0-4A14-A9F2-000330BBBA7C', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'A882A66E-9B8C-4CF6-84CD-5B0F679BE4ED', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'19939', N'BIOCET*TAB', N'BIOCETTAB', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'5850740', N'BIOCAINE  TAB', N'FUZZY', 7, 62.70, N'PENDING', N'BIOCET', NULL, NULL, N'TAB', NULL, 25.00, '2026-07-05 13:15:16.410', NULL, NULL, NULL, 0, NULL, NULL),
    (N'96B5AF43-5774-42DB-A114-0003E22FA5F2', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'A882A66E-9B8C-4CF6-84CD-5B0F679BE4ED', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'5869871', N'MYLAMIN PLUS INJ 2ML', N'MYLAMINPLUSINJ2ML', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'5887817', N'MYLAMIN GOLD   CAP', N'FUZZY', 7, 39.79, N'PENDING', N'MYLAMIN PLUS', N'2', N'ML', N'INJ', NULL, 25.30, '2026-07-05 13:15:16.737', NULL, NULL, NULL, 0, NULL, NULL),
    (N'2D1058C0-0C7C-4680-B04D-00051566137F', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'A882A66E-9B8C-4CF6-84CD-5B0F679BE4ED', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'13501', N'ARJIT LINIMENT 30ML', N'ARJITLINIMENT30ML', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'5881766', N'ARJIT CAP', N'FUZZY', 7, 32.98, N'PENDING', N'ARJIT LINIMENT', N'30', N'ML', NULL, NULL, 57.00, '2026-07-05 13:15:16.370', NULL, NULL, NULL, 0, NULL, NULL),
    (N'5207DADD-CCC9-43C0-A932-00059CF25BF7', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'E6E1FCC6-D06A-4BA9-A211-397C7C68EFB0', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'5857905', N'CAROL SACHET', N'CAROLSACHET', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'5885923', N'CARODYL 100MG  TAB [VET]', N'FUZZY', 7, 43.41, N'PENDING', N'CAROL', NULL, NULL, N'SACHET', NULL, 30.00, '2026-07-05 13:10:34.887', NULL, NULL, NULL, 1, '2026-07-05 13:15:14.310', NULL),
    (N'A3071B26-A8FC-452D-87E9-0005EC8A6D9B', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'DF82C426-7929-4C99-BC25-C2C3C8133D53', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'5884128', N'TELMIDUCE CL', N'TELMIDUCECL', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'5886906', N'TELMIDUCE CL  TAB', N'STRUCTURED', 4, 96.00, N'AUTO', N'TELMIDUCE CL', NULL, NULL, NULL, NULL, 100.00, '2026-07-05 13:34:22.620', NULL, NULL, NULL, 0, NULL, NULL),
    (N'981262B8-198A-4254-ABEE-0006DCD2A9C3', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'E6E1FCC6-D06A-4BA9-A211-397C7C68EFB0', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'571', N'DAFLON 500', N'DAFLON500', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'571', N'DAFLON 500', N'SUPPLIER', 1, 100.00, N'AUTO', N'DAFLON', N'500', NULL, NULL, NULL, 188.73, '2026-07-05 13:10:30.300', NULL, NULL, NULL, 0, NULL, NULL),
    (N'87AFB502-7A10-4354-A5FF-0006F9CB5CDB', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'E6E1FCC6-D06A-4BA9-A211-397C7C68EFB0', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'5864088', N'ALKASTON-B6 ORAL SUL 200ML', N'ALKASTONB6ORALSUL200ML', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'5864088', N'ALKASTON B6 SYP 200ML', N'SUPPLIER', 1, 100.00, N'AUTO', N'ALKASTON B', N'6', NULL, NULL, NULL, 252.20, '2026-07-05 13:10:32.993', NULL, NULL, NULL, 0, NULL, NULL);
GO

IF OBJECT_ID('dbo.product_mapping_audit') IS NOT NULL DROP TABLE [dbo].[product_mapping_audit];
GO
CREATE TABLE [dbo].[product_mapping_audit] (
    [audit_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [mapping_id] uniqueidentifier NULL,
    [run_id] uniqueidentifier NULL,
    [action] varchar(20) NOT NULL,
    [old_status] varchar(20) NULL,
    [new_status] varchar(20) NULL,
    [actor_user_id] uniqueidentifier NULL,
    [detail] varchar(1000) NULL,
    [created_at] datetime NOT NULL,
    CONSTRAINT [PK_dbo_product_mapping_audit] PRIMARY KEY ([audit_id])
);
GO
INSERT INTO [dbo].[product_mapping_audit] ([audit_id], [tenant_id], [mapping_id], [run_id], [action], [old_status], [new_status], [actor_user_id], [detail], [created_at]) VALUES
    (N'57952EA5-B036-49A7-80CF-0000D4054E9C', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'B257DA8B-93BE-474C-BEDD-C67C65CDC5B1', N'A882A66E-9B8C-4CF6-84CD-5B0F679BE4ED', N'RUN', NULL, N'PENDING', NULL, N'no-match @ 0.0', '2026-07-05 13:15:22.450'),
    (N'2B587C31-9EDE-48EF-BBE4-0000FC004DC3', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'EB7F0325-4E9D-4512-A6F8-17D3D6720366', N'A882A66E-9B8C-4CF6-84CD-5B0F679BE4ED', N'RUN', NULL, N'PENDING', NULL, N'FUZZY @ 56.11', '2026-07-05 13:15:22.540'),
    (N'190D7D6D-DA51-40C2-AA5A-0000FD0E03A4', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'E31CE24A-6518-4E37-A39F-ECE9303361C4', N'A882A66E-9B8C-4CF6-84CD-5B0F679BE4ED', N'RUN', NULL, N'PENDING', NULL, N'no-match @ 0.0', '2026-07-05 13:15:22.747'),
    (N'63D2D2BF-996A-4F52-8F0B-000143990409', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'945E7E11-A4BE-488F-9F02-C8D939F2BCB1', N'E6E1FCC6-D06A-4BA9-A211-397C7C68EFB0', N'RUN', NULL, N'PENDING', NULL, N'no-match @ 0.0', '2026-07-05 13:10:44.507'),
    (N'5E82FEE3-BBF7-4575-A933-0001B494831A', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'64D0CB56-6780-4B03-BFA9-8E59FAE1723C', N'E6E1FCC6-D06A-4BA9-A211-397C7C68EFB0', N'AUTO_MATCH', NULL, N'AUTO', NULL, N'EXACT @ 99.0', '2026-07-05 13:10:43.747'),
    (N'EB6C8B27-D045-422F-835A-0001F8D022B6', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'7A94FAA6-84AF-493D-AD30-921093809A87', N'E6E1FCC6-D06A-4BA9-A211-397C7C68EFB0', N'AUTO_MATCH', NULL, N'AUTO', NULL, N'EXACT @ 99.0', '2026-07-05 13:10:43.810'),
    (N'2951657C-5139-4B38-8CF3-0001FE8A742D', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'8BF1AC92-EDC2-42D0-9342-D779EF88F6A3', N'E6E1FCC6-D06A-4BA9-A211-397C7C68EFB0', N'AUTO_MATCH', NULL, N'AUTO', NULL, N'EXACT @ 99.0', '2026-07-05 13:10:43.703'),
    (N'35F41AE4-4736-4DD4-9E3C-00036BC7C73E', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'2BEDE559-83A2-47B5-8976-448AC1425F37', N'DF82C426-7929-4C99-BC25-C2C3C8133D53', N'AUTO_MATCH', NULL, N'AUTO', NULL, N'STRUCTURED @ 96.0', '2026-07-05 13:34:27.760'),
    (N'F0632A04-7839-4E05-BBBC-000378DA051E', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'E4507C13-6517-4379-B47F-2BBAB6D28B6D', N'A882A66E-9B8C-4CF6-84CD-5B0F679BE4ED', N'RUN', NULL, N'PENDING', NULL, N'FUZZY @ 45.22', '2026-07-05 13:15:23.480'),
    (N'952A104A-1ABA-4FCC-B84B-0004E9F4089D', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'9D57A50B-FF7F-4DD5-ACCB-4DA0EA6CC410', N'DF82C426-7929-4C99-BC25-C2C3C8133D53', N'AUTO_MATCH', NULL, N'AUTO', NULL, N'SUPPLIER @ 100.0', '2026-07-05 13:34:27.230');
GO

IF OBJECT_ID('dbo.product_mapping_candidate') IS NOT NULL DROP TABLE [dbo].[product_mapping_candidate];
GO
CREATE TABLE [dbo].[product_mapping_candidate] (
    [candidate_id] uniqueidentifier NOT NULL,
    [mapping_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [target_product_code] varchar(50) NOT NULL,
    [target_product_name] varchar(400) NOT NULL,
    [target_normalized_name] varchar(400) NULL,
    [name_score] decimal(5,2) NOT NULL,
    [brand_score] decimal(5,2) NOT NULL,
    [strength_score] decimal(5,2) NOT NULL,
    [form_score] decimal(5,2) NOT NULL,
    [mrp_score] decimal(5,2) NOT NULL,
    [total_score] decimal(5,2) NOT NULL,
    [brand] varchar(200) NULL,
    [strength] varchar(50) NULL,
    [dosage_form] varchar(30) NULL,
    [mrp] decimal(18,2) NULL,
    [reason] varchar(500) NULL,
    [created_at] datetime NOT NULL,
    CONSTRAINT [PK_dbo_product_mapping_candidate] PRIMARY KEY ([candidate_id])
);
GO
INSERT INTO [dbo].[product_mapping_candidate] ([candidate_id], [mapping_id], [tenant_id], [target_product_code], [target_product_name], [target_normalized_name], [name_score], [brand_score], [strength_score], [form_score], [mrp_score], [total_score], [brand], [strength], [dosage_form], [mrp], [reason], [created_at]) VALUES
    (N'30D5363D-4E62-41DD-B632-0001021C3C84', N'E5660F9D-41ED-4D64-BFA0-2FA7545FC7EC', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'5882793', N'LUVLAP FEEDING BOT [NATURA FLO] 250ML', N'LUVLAPFEEDINGBOTNATURAFLO250ML', 32.59, 20.00, 0.00, 0.00, 3.33, 55.92, N'LUVLAP FEEDING BOT NATURA FLO', N'250', NULL, 210.00, N'name 33, brand 20, mrp 3.3', '2026-07-05 13:15:21.487'),
    (N'F1BB1891-B8D6-4AB2-B0B4-000113DE899B', N'740FE183-B30B-4FC9-8F01-870B9424E43D', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'5891255', N'GLIPACURE M 50/500MG  TAB', N'GLIPACUREM50500MGTAB', 15.00, 13.16, 0.00, 0.00, 4.57, 32.73, N'GLIPACURE M', N'50', N'TAB', 197.15, N'name 15, brand 13, mrp 4.6', '2026-07-05 13:34:26.020'),
    (N'B968ED97-5459-4E0A-AF27-0001956C1643', N'F7B39B35-0EAD-45B2-B293-ADFE32E4E514', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'5894378', N'PROVISACC DIAMOND POW 500GM [VET]', N'PROVISACCDIAMONDPOW500GMVET', 18.46, 14.71, 0.00, 0.00, 0.17, 33.34, N'PROVISACC DIAMOND POW', N'500', NULL, 520.00, N'name 18, brand 15, mrp 0.2', '2026-07-05 13:15:20.350'),
    (N'6797AF7E-B7D7-4604-8776-0002E13B72C5', N'DED42E59-5AFA-46E2-AA0C-365D15555973', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'5877935', N'TRAPALIN TAB', N'TRAPALINTAB', 30.48, 16.67, 0.00, 10.00, 1.79, 58.94, N'TRAPALIN', NULL, N'TAB', 47.50, N'name 30, brand 17, form match, mrp 1.8', '2026-07-05 13:15:19.677'),
    (N'5D4C7F46-5B14-47CD-91AC-00038882900C', N'E292166D-993E-4BC6-92F5-F06A44FE8550', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'5876955', N'NERVINCE-M TAB', N'NERVINCEMTAB', 28.00, 13.89, 0.00, 0.00, 4.93, 46.82, N'NERVINCE M', NULL, N'TAB', 142.00, N'name 28, brand 14, mrp 4.9', '2026-07-05 13:15:20.167'),
    (N'0214B02E-E5AF-4CA8-856E-0003AF986126', N'63D0DB0B-EA05-4077-A5D3-2269313A4CF8', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'5883812', N'HAPPYHEEL CREAM 50GM', N'HAPPYHEELCREAM50GM', 16.00, 10.53, 0.00, 0.00, 2.17, 28.70, N'HAPPYHEEL', N'50', N'CREAM', 450.00, N'name 16, brand 11, mrp 2.2', '2026-07-05 13:15:20.340'),
    (N'30ECC56F-838C-4B30-8432-0003C618006F', N'2AF5550E-AC87-4432-A74C-BFFCA9A434A1', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'5881511', N'ALKOF C SYP 120ML', N'ALKOFCSYP120ML', 26.67, 20.00, 0.00, 10.00, 4.06, 60.73, N'ALKOF C', N'120', N'SYP', 105.00, N'name 27, brand 20, form match, mrp 4.1', '2026-07-05 13:34:25.577'),
    (N'6AD8D701-122C-4E84-9DDE-000510D00DF8', N'AAA787D0-6F8C-4EC5-BBD3-54695FC90F8B', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'5891724', N'LOZIVATE MF LOTION  30ML', N'LOZIVATEMFLOTION30ML', 15.14, 13.16, 0.00, 0.00, 4.42, 32.72, N'LOZIVATE MF', N'30', N'LOTION', 159.00, N'name 15, brand 13, mrp 4.4', '2026-07-05 13:15:21.263'),
    (N'0696D91B-C02C-4E3B-A577-000752BF729D', N'78E73FAC-FADC-4321-8207-7797C522B9FD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'5884230', N'NILAVEMBU KUDINEER 50GM (AVIS)', N'NILAVEMBUKUDINEER50GMAVIS', 33.33, 25.00, 0.00, 0.00, 1.01, 59.34, N'NILAVEMBU KUDINEER', N'50', NULL, 82.00, N'name 33, brand 25, mrp 1.0', '2026-07-05 13:15:20.657'),
    (N'057FAFB0-E036-4F2F-96B9-000A303EA99A', N'51C3B046-71DA-4E48-B3A9-D356382D454B', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'5873179', N'KNEE CAP (M) VISSCO', N'KNEECAPMVISSCO', 30.00, 19.12, 0.00, 0.00, 1.38, 50.50, N'KNEE M VISSCO', NULL, N'CAP', 425.00, N'name 30, brand 19, mrp 1.4', '2026-07-05 13:15:20.683');
GO

IF OBJECT_ID('dbo.product_normalization_dictionary') IS NOT NULL DROP TABLE [dbo].[product_normalization_dictionary];
GO
CREATE TABLE [dbo].[product_normalization_dictionary] (
    [entry_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NULL,
    [term] varchar(50) NOT NULL,
    [canonical] varchar(50) NULL,
    [kind] varchar(20) NOT NULL,
    [is_active] bit NOT NULL,
    [created_at] datetime NOT NULL,
    [created_by] uniqueidentifier NULL,
    [updated_at] datetime NULL,
    [updated_by] uniqueidentifier NULL,
    CONSTRAINT [PK_dbo_product_normalization_dictionary] PRIMARY KEY ([entry_id])
);
GO
INSERT INTO [dbo].[product_normalization_dictionary] ([entry_id], [tenant_id], [term], [canonical], [kind], [is_active], [created_at], [created_by], [updated_at], [updated_by]) VALUES
    (N'AB6E8A0C-1602-4B2B-A9BF-073A879B0E5F', NULL, N'SOLN', N'SOLN', N'DOSAGE_FORM', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    (N'F13315A8-9A91-4037-BBF3-0C6F40352A9D', NULL, N'MG/ML', N'MG/ML', N'UNIT', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    (N'9FA2F927-66B1-4106-AEEB-0D29F45DD328', NULL, N'CREAM', N'CREAM', N'DOSAGE_FORM', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    (N'9BC09E25-D4F8-4D72-9D06-0E46871522AD', NULL, N'IU', N'IU', N'UNIT', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    (N'C7FDEFE4-BD67-47B1-AD45-130F3059CBE7', NULL, N'OINTMENT', N'OINT', N'DOSAGE_FORM', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    (N'AF697A46-1509-4A67-8C5F-1CE4ED426B6E', NULL, N'TABLET', N'TAB', N'DOSAGE_FORM', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    (N'4005822C-FE30-474D-A3AA-204C83FE9DDE', NULL, N'LOTION', N'LOTION', N'DOSAGE_FORM', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    (N'A083F9C9-938C-4617-9A27-22D03CBFDD99', NULL, N'CAPSULES', N'CAP', N'DOSAGE_FORM', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    (N'69ADFD36-C9EA-4351-A38C-30C5446E3F48', NULL, N'SYRUP', N'SYP', N'DOSAGE_FORM', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    (N'A2514E3A-F4E5-495A-B417-4E12AE848100', NULL, N'CAP', N'CAP', N'DOSAGE_FORM', 1, '2026-07-05 13:06:41.000', NULL, '2026-07-05 17:37:42.700', NULL);
GO

IF OBJECT_ID('dbo.role_module_access') IS NOT NULL DROP TABLE [dbo].[role_module_access];
GO
CREATE TABLE [dbo].[role_module_access] (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [role_id] uniqueidentifier NOT NULL,
    [module_id] uniqueidentifier NOT NULL,
    [can_view] bit NULL,
    [can_create] bit NULL,
    [can_edit] bit NULL,
    [can_delete] bit NULL,
    [can_export] bit NULL,
    [is_active] bit NULL,
    CONSTRAINT [PK_dbo_role_module_access] PRIMARY KEY ([id])
);
GO
SET IDENTITY_INSERT [dbo].[role_module_access] ON;
INSERT INTO [dbo].[role_module_access] ([id], [role_id], [module_id], [can_view], [can_create], [can_edit], [can_delete], [can_export], [is_active]) VALUES
    (1, N'85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', N'F8D3A6DD-F47B-41C0-ACE7-0105218481A8', 1, 1, 1, 1, 1, 1),
    (2, N'85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', N'B655CFCB-9271-453F-945A-0234DC04F93E', 1, 1, 1, 1, 1, 1),
    (3, N'85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', N'41A344EB-3A24-4C53-849D-0E423D80C55F', 1, 1, 1, 1, 1, 1),
    (4, N'85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', N'4A303000-33EE-4C38-BE61-11A1606A7163', 1, 1, 1, 1, 1, 1),
    (5, N'85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', N'210843D0-8875-4F24-9619-1A9FE316695B', 1, 1, 1, 1, 1, 1),
    (6, N'85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', N'B059C357-0390-4CBA-A13B-460320A7EFBB', 1, 1, 1, 1, 1, 1),
    (7, N'85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', N'C7E67895-DD4C-4155-A23E-5458DE1FDF0A', 1, 1, 1, 1, 1, 1),
    (8, N'85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', N'482B4EE8-5D10-4DF4-B04B-6BF5988EE993', 1, 1, 1, 1, 1, 1),
    (9, N'85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', N'F7122D0E-5EF0-4835-938A-7BFE89DE8C32', 1, 1, 1, 1, 1, 1),
    (10, N'85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', N'B747540E-459A-4697-8E14-7EF12F1492D9', 1, 1, 1, 1, 1, 1);
SET IDENTITY_INSERT [dbo].[role_module_access] OFF;
GO

IF OBJECT_ID('dbo.roles') IS NOT NULL DROP TABLE [dbo].[roles];
GO
CREATE TABLE [dbo].[roles] (
    [role_id] uniqueidentifier NOT NULL,
    [role_name] varchar(50) NOT NULL,
    [description] varchar(500) NULL,
    [is_active] bit NOT NULL,
    CONSTRAINT [PK_dbo_roles] PRIMARY KEY ([role_id])
);
GO
INSERT INTO [dbo].[roles] ([role_id], [role_name], [description], [is_active]) VALUES
    (N'32D8CF99-3347-4F88-AD48-02341A793E0E', N'STORE_ADMIN', N'Store Administration', 1),
    (N'71FD12E9-118B-47AB-BE57-126E9C0BB53F', N'TENANT_ADMIN', N'Tenant Control', 1),
    (N'491C7D1F-AE97-4503-83A9-3929735145F9', N'Manager', N'Store Manager', 1),
    (N'FE004FB5-5473-4FA0-90D9-76221BA662D8', N'SuperAdmin', N'Platform Super Administrator', 1),
    (N'9E4B686B-5793-4614-83E5-96A9D18E7ADF', N'STORE_USER', N'Standard User', 1),
    (N'85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', N'SUPER_ADMIN', N'Platform Control', 1),
    (N'C79BE7A1-DECE-49BE-B24F-A4278FC6BCA7', N'STORE_MANAGER', N'Store Operations', 1),
    (N'D45CFFB6-CA97-4ADB-A218-B2CF3493BC81', N'Admin', N'Tenant Administrator', 1),
    (N'F6DAB5F8-F7ED-4F73-9F28-B911DC2805C3', N'User', N'Standard User', 1),
    (N'6F10C367-4613-4A66-BDFE-BB71D388C9C4', N'SYNC_OPERATOR', N'Sync Monitoring', 1);
GO

IF OBJECT_ID('dbo.store_agent_registry') IS NOT NULL DROP TABLE [dbo].[store_agent_registry];
GO
CREATE TABLE [dbo].[store_agent_registry] (
    [agent_id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [store_id] uniqueidentifier NOT NULL,
    [agent_version] varchar(50) NULL,
    [connection_type] varchar(50) NULL,
    [installed_at] datetime NULL,
    [last_heartbeat] datetime NULL,
    [connection_status] varchar(50) NULL,
    [is_active] bit NOT NULL,
    CONSTRAINT [PK_dbo_store_agent_registry] PRIMARY KEY ([agent_id])
);
GO
SET IDENTITY_INSERT [dbo].[store_agent_registry] ON;
INSERT INTO [dbo].[store_agent_registry] ([agent_id], [tenant_id], [store_id], [agent_version], [connection_type], [installed_at], [last_heartbeat], [connection_status], [is_active]) VALUES
    (1, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'1.0.0', N'LAN', '2026-06-21 17:59:58.077', '2026-07-06 20:01:31.563', N'ONLINE', 1),
    (2, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'1.0.0', N'LAN', '2026-06-23 18:31:28.650', '2026-07-06 20:01:40.643', N'ONLINE', 1),
    (3, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', N'1.0.0', N'LAN', '2026-06-23 19:30:03.960', '2026-07-06 20:01:35.047', N'ONLINE', 1),
    (4, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'3019101A-24A6-4045-AB7E-964046383EA2', N'1.0.0', N'LAN', '2026-06-23 19:31:53.853', '2026-07-06 20:01:33.503', N'ONLINE', 1),
    (5, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'1.0.0', N'LAN', '2026-06-23 19:33:13.323', '2026-07-06 20:01:33.497', N'ONLINE', 1);
SET IDENTITY_INSERT [dbo].[store_agent_registry] OFF;
GO

IF OBJECT_ID('dbo.store_connection_test_log') IS NOT NULL DROP TABLE [dbo].[store_connection_test_log];
GO
CREATE TABLE [dbo].[store_connection_test_log] (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [store_id] uniqueidentifier NOT NULL,
    [server_name] varchar(500) NULL,
    [database_name] varchar(200) NULL,
    [test_status] varchar(50) NOT NULL,
    [test_message] nvarchar(max) NULL,
    [tested_by] uniqueidentifier NULL,
    [tested_at] datetime NOT NULL,
    CONSTRAINT [PK_dbo_store_connection_test_log] PRIMARY KEY ([id])
);
GO

IF OBJECT_ID('dbo.store_onboarding_log') IS NOT NULL DROP TABLE [dbo].[store_onboarding_log];
GO
CREATE TABLE [dbo].[store_onboarding_log] (
    [onboarding_id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [store_id] uniqueidentifier NULL,
    [onboarding_status] varchar(50) NOT NULL,
    [started_by] uniqueidentifier NOT NULL,
    [started_at] datetime NOT NULL,
    [completed_at] datetime NULL,
    [remarks] nvarchar(max) NULL,
    CONSTRAINT [PK_dbo_store_onboarding_log] PRIMARY KEY ([onboarding_id])
);
GO

IF OBJECT_ID('dbo.store_sync_settings') IS NOT NULL DROP TABLE [dbo].[store_sync_settings];
GO
CREATE TABLE [dbo].[store_sync_settings] (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [store_id] uniqueidentifier NOT NULL,
    [sync_enabled] bit NOT NULL,
    [initial_sync_type] varchar(20) NOT NULL,
    [schedule_enabled] bit NOT NULL,
    [created_at] datetime NOT NULL,
    CONSTRAINT [PK_dbo_store_sync_settings] PRIMARY KEY ([id])
);
GO

IF OBJECT_ID('dbo.stores') IS NOT NULL DROP TABLE [dbo].[stores];
GO
CREATE TABLE [dbo].[stores] (
    [store_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [store_code] varchar(50) NOT NULL,
    [store_name] varchar(200) NOT NULL,
    [server_name] varchar(500) NULL,
    [database_name] varchar(200) NULL,
    [username] varchar(200) NULL,
    [password_encrypted] varbinary(max) NULL,
    [connection_type] varchar(50) NULL,
    [branch_codes] varchar(max) NULL,
    [last_sync_time] datetime NULL,
    [last_sync_status] varchar(50) NULL,
    [last_seen] datetime NULL,
    [connection_status] varchar(50) NULL,
    [heartbeat_ip] varchar(100) NULL,
    [is_active] bit NOT NULL,
    [created_at] datetime NOT NULL,
    [updated_at] datetime NULL,
    [gst_number] varchar(100) NULL,
    [drug_license_no] varchar(100) NULL,
    [address1] varchar(500) NULL,
    [address2] varchar(500) NULL,
    [city] varchar(100) NULL,
    [state] varchar(100) NULL,
    [country] varchar(100) NULL,
    [pincode] varchar(20) NULL,
    [contact_person] varchar(100) NULL,
    [contact_mobile] varchar(50) NULL,
    [contact_email] varchar(200) NULL,
    [store_abbreviation] varchar(20) NULL,
    [agent_version] varchar(50) NULL,
    [last_heartbeat] datetime NULL,
    [agent_installed_at] datetime NULL,
    [store_order] int NOT NULL,
    [agent_install_path] nvarchar(500) NULL,
    [agent_hostname] nvarchar(255) NULL,
    [agent_registered_at] datetime NULL,
    CONSTRAINT [PK_dbo_stores] PRIMARY KEY ([store_id])
);
GO
INSERT INTO [dbo].[stores] ([store_id], [tenant_id], [store_code], [store_name], [server_name], [database_name], [username], [password_encrypted], [connection_type], [branch_codes], [last_sync_time], [last_sync_status], [last_seen], [connection_status], [heartbeat_ip], [is_active], [created_at], [updated_at], [gst_number], [drug_license_no], [address1], [address2], [city], [state], [country], [pincode], [contact_person], [contact_mobile], [contact_email], [store_abbreviation], [agent_version], [last_heartbeat], [agent_installed_at], [store_order], [agent_install_path], [agent_hostname], [agent_registered_at]) VALUES
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'NMS', N'Nathan Medicals S', N'SERVER-S\SQLEXPRESS', N'Rshopaid', N'sa', 0x67414141414142714e5632324a4e564378674536436e6d52385f73754e4d4b73486f317a3573365f4f747773426970686e6739765a6e6d41634e35554a503445625f724b6e516f6764517250315731716a595736784d49725a556f3365326e5a67773d3d, N'LAN', N'1000135,1001286,1001379,1000668,1001374,1001263', NULL, NULL, NULL, NULL, NULL, 1, '2026-06-18 19:29:17.853', '2026-06-23 19:56:26.870', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'NMS', NULL, NULL, NULL, 5, N'D:\NexoraStoreAgent', N'SERVER-S', '2026-07-04 19:18:50.223'),
    (N'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'NMW', N'Nathan Medicals C[B]', N'DESKTOP-745PMO0\SQLEXPRESS', N'Nathanw', N'sa', 0x67414141414142714e5632324a4e564378674536436e6d52385f73754e4d4b73486f317a3573365f4f747773426970686e6739765a6e6d41634e35554a503445625f724b6e516f6764517250315731716a595736784d49725a556f3365326e5a67773d3d, N'LAN', N'', NULL, NULL, NULL, NULL, NULL, 1, '2026-06-18 19:29:17.850', '2026-06-23 19:56:40.990', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'NMW', NULL, NULL, NULL, 1, N'D:\NexoraStoreAgent', N'DESKTOP-745PMO0', '2026-07-05 13:27:26.493'),
    (N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'NMA', N'Nathan Medicals A', N'MSERVER-PC\SQLEXPRESS', N'RShopaidLive', N'sa', 0x67414141414142714e5632324a4e564378674536436e6d52385f73754e4d4b73486f317a3573365f4f747773426970686e6739765a6e6d41634e35554a503445625f724b6e516f6764517250315731716a595736784d49725a556f3365326e5a67773d3d, N'LAN', N'1000621,1000460,1000973,1000608,1001186,1001187,1001188', NULL, NULL, NULL, NULL, NULL, 1, '2026-06-18 19:29:17.863', '2026-06-25 19:04:23.597', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'NMA', NULL, NULL, NULL, 3, N'D:\NexoraStoreAgent', N'MSERVER-PC', '2026-07-04 17:55:12.363'),
    (N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'NMC', N'Nathan Medicals C', N'DESKTOP-LOCNRSU\SQLEXPRESS', N'Rshopaid', N'sa', 0x67414141414142714e5632324a4e564378674536436e6d52385f73754e4d4b73486f317a3573365f4f747773426970686e6739765a6e6d41634e35554a503445625f724b6e516f6764517250315731716a595736784d49725a556f3365326e5a67773d3d, N'LAN', N'1002700,1002701,1002702,1002699,1000996,1001118', NULL, NULL, NULL, NULL, NULL, 1, '2026-06-18 19:29:17.860', '2026-06-23 19:55:49.317', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'NMC', NULL, NULL, NULL, 2, N'D:\NexoraStoreAgent', N'CLIENT-3', '2026-07-06 16:46:59.320'),
    (N'3019101A-24A6-4045-AB7E-964046383EA2', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'NMG', N'Nathan Medicals G', N'KSERVER-PC\SQLEXPRESS', N'Shopaid', N'sa', 0x67414141414142714e5632324a4e564378674536436e6d52385f73754e4d4b73486f317a3573365f4f747773426970686e6739765a6e6d41634e35554a503445625f724b6e516f6764517250315731716a595736784d49725a556f3365326e5a67773d3d, N'LAN', N'721,720,437,745', NULL, NULL, NULL, NULL, NULL, 1, '2026-06-18 19:29:17.860', '2026-06-23 19:56:04.320', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'NMG', NULL, NULL, NULL, 4, N'D:\NexoraStoreAgent', N'NODE5-PC', '2026-07-06 16:46:53.393');
GO

IF OBJECT_ID('dbo.sync_approval_workflow') IS NOT NULL DROP TABLE [dbo].[sync_approval_workflow];
GO
CREATE TABLE [dbo].[sync_approval_workflow] (
    [workflow_id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [workflow_name] varchar(100) NOT NULL,
    [approval_required] bit NOT NULL,
    [approver_role] varchar(50) NOT NULL,
    [is_active] bit NOT NULL,
    CONSTRAINT [PK_dbo_sync_approval_workflow] PRIMARY KEY ([workflow_id])
);
GO

IF OBJECT_ID('dbo.sync_chunk_execution') IS NOT NULL DROP TABLE [dbo].[sync_chunk_execution];
GO
CREATE TABLE [dbo].[sync_chunk_execution] (
    [chunk_execution_id] bigint IDENTITY(1,1) NOT NULL,
    [execution_id] uniqueidentifier NOT NULL,
    [table_name] varchar(200) NOT NULL,
    [chunk_no] int NOT NULL,
    [chunk_status] varchar(50) NOT NULL,
    [rows_processed] bigint NOT NULL,
    [retry_count] int NOT NULL,
    [started_at] datetime NULL,
    [completed_at] datetime NULL,
    [error_message] nvarchar(max) NULL,
    CONSTRAINT [PK_dbo_sync_chunk_execution] PRIMARY KEY ([chunk_execution_id])
);
GO
SET IDENTITY_INSERT [dbo].[sync_chunk_execution] ON;
INSERT INTO [dbo].[sync_chunk_execution] ([chunk_execution_id], [execution_id], [table_name], [chunk_no], [chunk_status], [rows_processed], [retry_count], [started_at], [completed_at], [error_message]) VALUES
    (1, N'465FE679-034E-48AF-A50E-337C8D602F1F', N'RT_TEST', 1, N'ACK', 2, 0, '2026-06-21 16:59:25.437', '2026-06-21 16:59:25.557', NULL),
    (3, N'146EF276-2790-4E37-9763-0E69530D5093', N'Products', 1, N'FAILED', 0, 0, '2026-06-21 17:05:12.423', '2026-06-21 17:05:12.423', N'(''42S02'', "[42S02] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]Invalid object name ''sync.Products''. (208) (SQLExecDirectW)")'),
    (5, N'76A884ED-29A8-48C2-B136-BFE688E6DF55', N'Products', 1, N'FAILED', 0, 0, '2026-06-21 17:18:58.883', '2026-06-21 17:18:58.883', N'(''22007'', ''[22007] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]Conversion failed when converting date and/or time from character string. (241) (SQLExecute)'')'),
    (7, N'09FADD89-CE50-4C2D-A134-453927E4152B', N'Products', 1, N'FAILED', 0, 0, '2026-06-21 17:35:18.903', '2026-06-21 17:35:18.903', N'(''22007'', ''[22007] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]Conversion failed when converting date and/or time from character string. (241) (SQLExecute)'')'),
    (9, N'2D7C605C-CDC4-40E6-9C48-41D518B86C38', N'Products', 1, N'FAILED', 0, 0, '2026-06-21 17:41:08.067', '2026-06-21 17:41:08.067', N'(''22007'', ''[22007] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]Conversion failed when converting date and/or time from character string. (241) (SQLExecute)'')'),
    (11, N'911D8644-7F53-4E16-9C1F-466E6E61CE7E', N'Products', 1, N'FAILED', 0, 0, '2026-06-21 17:44:22.407', '2026-06-21 17:44:22.407', N'(''22007'', ''[22007] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]Conversion failed when converting date and/or time from character string. (241) (SQLExecDirectW)'')'),
    (13, N'AC1C4587-C9FF-4821-9FAA-A88AFC13245A', N'Products', 1, N'FAILED', 0, 0, '2026-06-21 17:45:58.733', '2026-06-21 17:45:58.733', N'(''22007'', ''[22007] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]Conversion failed when converting date and/or time from character string. (241) (SQLExecute)'')'),
    (14, N'B125A83B-F112-40DA-95D5-05CCF1D0FC3B', N'Products', 1, N'MERGED', 2, 0, '2026-06-21 17:59:58.230', '2026-06-21 17:59:58.363', NULL),
    (15, N'0790AA21-12C5-43E8-A16C-4329A9EAAC59', N'Products', 1, N'ACK', 1000, 0, '2026-06-21 18:07:03.263', '2026-06-21 18:07:03.647', NULL),
    (16, N'0790AA21-12C5-43E8-A16C-4329A9EAAC59', N'Products', 2, N'ACK', 1000, 0, '2026-06-21 18:07:03.700', '2026-06-21 18:07:04.067', NULL);
SET IDENTITY_INSERT [dbo].[sync_chunk_execution] OFF;
GO

IF OBJECT_ID('dbo.sync_chunk_rules') IS NOT NULL DROP TABLE [dbo].[sync_chunk_rules];
GO
CREATE TABLE [dbo].[sync_chunk_rules] (
    [rule_id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [chunk_size] int NOT NULL,
    [parallel_chunks] int NOT NULL,
    [is_active] bit NOT NULL,
    CONSTRAINT [PK_dbo_sync_chunk_rules] PRIMARY KEY ([rule_id])
);
GO

IF OBJECT_ID('dbo.sync_configuration') IS NOT NULL DROP TABLE [dbo].[sync_configuration];
GO
CREATE TABLE [dbo].[sync_configuration] (
    [config_id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [config_name] varchar(100) NOT NULL,
    [is_active] bit NOT NULL,
    [created_at] datetime NOT NULL,
    [created_by] uniqueidentifier NULL,
    [updated_at] datetime NULL,
    [updated_by] uniqueidentifier NULL,
    CONSTRAINT [PK_dbo_sync_configuration] PRIMARY KEY ([config_id])
);
GO

IF OBJECT_ID('dbo.sync_dashboard_snapshot') IS NOT NULL DROP TABLE [dbo].[sync_dashboard_snapshot];
GO
CREATE TABLE [dbo].[sync_dashboard_snapshot] (
    [snapshot_id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [total_stores] int NOT NULL,
    [online_stores] int NOT NULL,
    [offline_stores] int NOT NULL,
    [running_syncs] int NOT NULL,
    [failed_syncs] int NOT NULL,
    [pending_approvals] int NOT NULL,
    [today_sync_count] int NOT NULL,
    [data_processed_today] bigint NOT NULL,
    [snapshot_time] datetime NOT NULL,
    CONSTRAINT [PK_dbo_sync_dashboard_snapshot] PRIMARY KEY ([snapshot_id])
);
GO

IF OBJECT_ID('dbo.sync_execution') IS NOT NULL DROP TABLE [dbo].[sync_execution];
GO
CREATE TABLE [dbo].[sync_execution] (
    [execution_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [store_id] uniqueidentifier NOT NULL,
    [execution_type] varchar(50) NOT NULL,
    [sync_mode] varchar(50) NOT NULL,
    [execution_status] varchar(50) NOT NULL,
    [started_at] datetime NOT NULL,
    [completed_at] datetime NULL,
    [total_tables] int NOT NULL,
    [completed_tables] int NOT NULL,
    [failed_tables] int NOT NULL,
    [initiated_by] uniqueidentifier NULL,
    [created_by] uniqueidentifier NULL,
    CONSTRAINT [PK_dbo_sync_execution] PRIMARY KEY ([execution_id])
);
GO
INSERT INTO [dbo].[sync_execution] ([execution_id], [tenant_id], [store_id], [execution_type], [sync_mode], [execution_status], [started_at], [completed_at], [total_tables], [completed_tables], [failed_tables], [initiated_by], [created_by]) VALUES
    (N'15B0D63F-7B90-44C1-9229-01AD327EB5AC', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', N'FULL', N'FULL', N'COMPLETED', '2026-06-23 19:34:45.913', '2026-06-23 19:35:18.950', 9, 0, 0, NULL, NULL),
    (N'F563978B-63D9-4B9F-B8DF-03846492585E', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'FULL', N'FULL', N'COMPLETED', '2026-07-04 20:08:29.220', '2026-07-04 20:09:19.973', 0, 0, 0, NULL, NULL),
    (N'BDDCEC91-0844-4F6D-8095-040F00B24CCC', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'FULL', N'FULL', N'COMPLETED', '2026-06-23 19:23:02.187', '2026-06-23 19:24:32.157', 0, 0, 0, NULL, NULL),
    (N'B125A83B-F112-40DA-95D5-05CCF1D0FC3B', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'FULL', N'FULL', N'FAILED', '2026-06-21 17:59:58.217', '2026-06-21 18:16:17.000', 0, 0, 0, NULL, NULL),
    (N'C90BE353-01C3-42FC-BC74-0668A3779DB3', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'FULL', N'FULL', N'COMPLETED', '2026-06-23 19:34:57.000', '2026-06-25 16:24:42.070', 9, 0, 0, NULL, NULL),
    (N'16268982-48F7-49B5-8736-0686165E785D', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'FULL', N'FULL', N'FAILED', '2026-06-25 19:02:28.570', '2026-06-25 19:03:21.667', 0, 0, 0, NULL, NULL),
    (N'FE4CD7A6-6CBA-4752-A0E8-07211DFFF859', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', N'FULL', N'FULL', N'COMPLETED', '2026-07-05 20:38:35.423', '2026-07-05 20:39:07.327', 0, 0, 0, NULL, NULL),
    (N'D677CC7F-33C1-4CC6-8799-082C38CCB8EA', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'FULL', N'FULL', N'COMPLETED', '2026-07-04 19:38:11.463', '2026-07-04 19:39:17.433', 0, 0, 0, NULL, NULL),
    (N'2AD143AE-0AD8-44F8-AC4F-08E9C92480F7', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'FULL', N'FULL', N'CANCELLED', '2026-06-23 11:40:40.030', '2026-06-23 15:58:20.573', 9, 0, 0, NULL, NULL),
    (N'A50DB41D-2C32-4563-9F0A-0A72443D0D58', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'FULL', N'FULL', N'COMPLETED', '2026-06-26 12:10:44.870', '2026-06-26 12:12:04.873', 0, 0, 0, NULL, NULL);
GO

IF OBJECT_ID('dbo.sync_execution_audit') IS NOT NULL DROP TABLE [dbo].[sync_execution_audit];
GO
CREATE TABLE [dbo].[sync_execution_audit] (
    [audit_id] bigint IDENTITY(1,1) NOT NULL,
    [execution_id] uniqueidentifier NOT NULL,
    [action_name] varchar(200) NOT NULL,
    [action_time] datetime NOT NULL,
    [message] nvarchar(max) NULL,
    CONSTRAINT [PK_dbo_sync_execution_audit] PRIMARY KEY ([audit_id])
);
GO
SET IDENTITY_INSERT [dbo].[sync_execution_audit] ON;
INSERT INTO [dbo].[sync_execution_audit] ([audit_id], [execution_id], [action_name], [action_time], [message]) VALUES
    (1, N'465FE679-034E-48AF-A50E-337C8D602F1F', N'CREATED', '2026-06-21 16:59:25.267', N'Task created'),
    (2, N'465FE679-034E-48AF-A50E-337C8D602F1F', N'RUNNING', '2026-06-21 16:59:25.370', N'Task started'),
    (3, N'465FE679-034E-48AF-A50E-337C8D602F1F', N'CHUNK_MERGED', '2026-06-21 16:59:25.537', N'RT_TEST chunk 1 rows 2'),
    (4, N'465FE679-034E-48AF-A50E-337C8D602F1F', N'COMPLETED', '2026-06-21 16:59:25.610', N'Task completed'),
    (5, N'146EF276-2790-4E37-9763-0E69530D5093', N'RUNNING', '2026-06-21 17:05:10.290', N'Task started'),
    (6, N'146EF276-2790-4E37-9763-0E69530D5093', N'FAILED', '2026-06-21 17:05:12.457', N'500 Server Error: Internal Server Error for url: http://127.0.0.1:8000/api/sync/chunks/upload'),
    (7, N'76A884ED-29A8-48C2-B136-BFE688E6DF55', N'CREATED', '2026-06-21 17:18:36.200', N'Task created'),
    (8, N'76A884ED-29A8-48C2-B136-BFE688E6DF55', N'RUNNING', '2026-06-21 17:18:56.607', N'Task started'),
    (9, N'76A884ED-29A8-48C2-B136-BFE688E6DF55', N'FAILED', '2026-06-21 17:18:58.940', N'500 Server Error: Internal Server Error for url: http://127.0.0.1:8000/api/sync/chunks/upload'),
    (10, N'09FADD89-CE50-4C2D-A134-453927E4152B', N'CREATED', '2026-06-21 17:19:40.190', N'Task created');
SET IDENTITY_INSERT [dbo].[sync_execution_audit] OFF;
GO

IF OBJECT_ID('dbo.sync_execution_details') IS NOT NULL DROP TABLE [dbo].[sync_execution_details];
GO
CREATE TABLE [dbo].[sync_execution_details] (
    [detail_id] bigint IDENTITY(1,1) NOT NULL,
    [sync_id] bigint NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [store_id] uniqueidentifier NOT NULL,
    [table_name] varchar(200) NOT NULL,
    [chunk_no] int NOT NULL,
    [chunk_size] int NOT NULL,
    [rows_processed] bigint NOT NULL,
    [rows_failed] bigint NOT NULL,
    [started_at] datetime NULL,
    [completed_at] datetime NULL,
    [duration_seconds] int NULL,
    [status] varchar(50) NOT NULL,
    [error_message] nvarchar(max) NULL,
    [created_at] datetime NOT NULL,
    [execution_id] uniqueidentifier NULL,
    [sync_type] varchar(40) NULL,
    [rows_examined] bigint NULL,
    [rows_changed] bigint NULL,
    [rows_uploaded] bigint NULL,
    [rows_inserted] bigint NULL,
    [rows_updated] bigint NULL,
    [rows_skipped] bigint NULL,
    [source_total] bigint NULL,
    CONSTRAINT [PK_dbo_sync_execution_details] PRIMARY KEY ([detail_id])
);
GO
SET IDENTITY_INSERT [dbo].[sync_execution_details] ON;
INSERT INTO [dbo].[sync_execution_details] ([detail_id], [sync_id], [tenant_id], [store_id], [table_name], [chunk_no], [chunk_size], [rows_processed], [rows_failed], [started_at], [completed_at], [duration_seconds], [status], [error_message], [created_at], [execution_id], [sync_type], [rows_examined], [rows_changed], [rows_uploaded], [rows_inserted], [rows_updated], [rows_skipped], [source_total]) VALUES
    (4, NULL, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'Products', 0, 0, 54204, 0, '2026-06-21 20:11:53.863', '2026-06-21 20:12:17.227', NULL, N'RUNNING', NULL, '2026-06-21 20:11:53.863', N'87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 54204, 0, 54204, NULL, NULL),
    (5, NULL, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'Batches', 0, 0, 287552, 0, '2026-06-21 20:12:27.123', '2026-06-21 20:14:11.773', NULL, N'RUNNING', NULL, '2026-06-21 20:12:27.123', N'87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 287552, 0, 287552, NULL, NULL),
    (6, NULL, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'SaleInformation', 0, 0, 21043, 0, '2026-06-21 20:14:12.457', '2026-06-21 20:14:15.857', NULL, N'RUNNING', NULL, '2026-06-21 20:14:12.457', N'87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 21043, 13, 21030, NULL, NULL),
    (7, NULL, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'ProductSaleInformation', 0, 0, 43793, 0, '2026-06-21 20:14:18.660', '2026-06-21 20:14:37.447', NULL, N'RUNNING', NULL, '2026-06-21 20:14:18.660', N'87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 43793, 26, 43767, NULL, NULL),
    (8, NULL, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'PurchaseTrans', 0, 0, 15943, 0, '2026-06-21 20:14:38.330', '2026-06-21 20:14:42.257', NULL, N'RUNNING', NULL, '2026-06-21 20:14:38.330', N'87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 15943, 0, 15943, NULL, NULL),
    (9, NULL, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'ProductTrans', 0, 0, 31247, 0, '2026-06-21 20:14:43.537', '2026-06-21 20:14:52.487', NULL, N'RUNNING', NULL, '2026-06-21 20:14:43.537', N'87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 31247, 0, 31247, NULL, NULL),
    (10, NULL, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'SupplierProductMatch', 0, 0, 83026, 0, '2026-06-21 20:14:53.417', '2026-06-21 20:15:09.037', NULL, N'RUNNING', NULL, '2026-06-21 20:14:53.417', N'87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 83026, 0, 83026, NULL, NULL),
    (11, NULL, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'Suppliers', 0, 0, 970, 0, '2026-06-21 20:15:09.290', NULL, NULL, N'RUNNING', NULL, '2026-06-21 20:15:09.290', N'87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 970, 0, 970, NULL, NULL),
    (12, NULL, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'TAX', 0, 0, 20, 0, '2026-06-21 20:15:09.417', NULL, NULL, N'RUNNING', NULL, '2026-06-21 20:15:09.417', N'87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 20, 0, 20, NULL, NULL),
    (10011, NULL, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'Products', 0, 0, 54206, 0, '2026-06-22 19:10:57.287', '2026-06-22 19:11:27.220', NULL, N'RUNNING', NULL, '2026-06-22 19:10:57.287', N'F026EC67-6929-46B2-AB9C-2195006F2D27', N'UPSERT', 54206, 54206, 54206, 54206, 0, 0, 54206);
SET IDENTITY_INSERT [dbo].[sync_execution_details] OFF;
GO

IF OBJECT_ID('dbo.sync_execution_history') IS NOT NULL DROP TABLE [dbo].[sync_execution_history];
GO
CREATE TABLE [dbo].[sync_execution_history] (
    [sync_id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [store_id] uniqueidentifier NOT NULL,
    [sync_mode] varchar(50) NOT NULL,
    [sync_type] varchar(50) NULL,
    [started_at] datetime NOT NULL,
    [completed_at] datetime NULL,
    [duration_seconds] int NULL,
    [total_rows] bigint NOT NULL,
    [processed_rows] bigint NOT NULL,
    [failed_rows] bigint NOT NULL,
    [status] varchar(50) NOT NULL,
    [triggered_by] uniqueidentifier NULL,
    [error_message] nvarchar(max) NULL,
    [created_at] datetime NOT NULL,
    CONSTRAINT [PK_dbo_sync_execution_history] PRIMARY KEY ([sync_id])
);
GO

IF OBJECT_ID('dbo.sync_execution_lock') IS NOT NULL DROP TABLE [dbo].[sync_execution_lock];
GO
CREATE TABLE [dbo].[sync_execution_lock] (
    [lock_id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [store_id] uniqueidentifier NOT NULL,
    [table_name] varchar(200) NOT NULL,
    [lock_acquired_at] datetime NOT NULL,
    [lock_expires_at] datetime NOT NULL,
    [lock_status] varchar(50) NOT NULL,
    [acquired_by] uniqueidentifier NULL,
    [sync_id] uniqueidentifier NULL,
    CONSTRAINT [PK_dbo_sync_execution_lock] PRIMARY KEY ([lock_id])
);
GO

IF OBJECT_ID('dbo.sync_manual_trigger') IS NOT NULL DROP TABLE [dbo].[sync_manual_trigger];
GO
CREATE TABLE [dbo].[sync_manual_trigger] (
    [trigger_id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [store_id] uniqueidentifier NOT NULL,
    [trigger_type] varchar(50) NOT NULL,
    [requested_by] uniqueidentifier NOT NULL,
    [requested_at] datetime NOT NULL,
    [approval_status] varchar(50) NOT NULL,
    [approved_by] uniqueidentifier NULL,
    [approved_at] datetime NULL,
    CONSTRAINT [PK_dbo_sync_manual_trigger] PRIMARY KEY ([trigger_id])
);
GO

IF OBJECT_ID('dbo.sync_refresh_cycles') IS NOT NULL DROP TABLE [dbo].[sync_refresh_cycles];
GO
CREATE TABLE [dbo].[sync_refresh_cycles] (
    [cycle_id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [cycle_name] varchar(100) NOT NULL,
    [refresh_type] varchar(50) NOT NULL,
    [refresh_interval_minutes] int NOT NULL,
    [is_active] bit NOT NULL,
    CONSTRAINT [PK_dbo_sync_refresh_cycles] PRIMARY KEY ([cycle_id])
);
GO

IF OBJECT_ID('dbo.sync_retry_rules') IS NOT NULL DROP TABLE [dbo].[sync_retry_rules];
GO
CREATE TABLE [dbo].[sync_retry_rules] (
    [rule_id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [max_retry_count] int NOT NULL,
    [retry_interval_minutes] int NOT NULL,
    [is_active] bit NOT NULL,
    CONSTRAINT [PK_dbo_sync_retry_rules] PRIMARY KEY ([rule_id])
);
GO

IF OBJECT_ID('dbo.sync_schedule') IS NOT NULL DROP TABLE [dbo].[sync_schedule];
GO
CREATE TABLE [dbo].[sync_schedule] (
    [schedule_id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [schedule_name] varchar(100) NOT NULL,
    [schedule_type] varchar(50) NOT NULL,
    [start_time] datetime NOT NULL,
    [is_enabled] bit NOT NULL,
    [created_at] datetime NOT NULL,
    [store_id] uniqueidentifier NULL,
    [sync_mode] varchar(20) NOT NULL,
    [suspended_until] datetime NULL,
    [last_run_at] datetime NULL,
    [updated_at] datetime NULL,
    CONSTRAINT [PK_dbo_sync_schedule] PRIMARY KEY ([schedule_id])
);
GO
SET IDENTITY_INSERT [dbo].[sync_schedule] ON;
INSERT INTO [dbo].[sync_schedule] ([schedule_id], [tenant_id], [schedule_name], [schedule_type], [start_time], [is_enabled], [created_at], [store_id], [sync_mode], [suspended_until], [last_run_at], [updated_at]) VALUES
    (1, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'NMA Morning Sync', N'DAILY', '2000-01-01 18:15:00.000', 1, '2026-06-24 16:47:10.037', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'FULL', NULL, NULL, '2026-06-26 11:42:46.057'),
    (2, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'NMA Afternoon Sync', N'DAILY', '2000-01-01 13:00:00.000', 1, '2026-06-24 16:47:10.087', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'FULL', NULL, NULL, '2026-06-24 16:47:10.087'),
    (3, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'NMC Morning Sync', N'DAILY', '2000-01-01 18:17:00.000', 1, '2026-06-24 16:47:10.093', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'FULL', NULL, NULL, '2026-06-26 11:43:01.823'),
    (4, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'NMC Afternoon Sync', N'DAILY', '2000-01-01 13:02:00.000', 1, '2026-06-24 16:47:10.097', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'FULL', NULL, NULL, '2026-06-24 16:47:10.097'),
    (5, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'NMG Morning Sync', N'DAILY', '2000-01-01 18:19:00.000', 1, '2026-06-24 16:47:10.100', N'3019101A-24A6-4045-AB7E-964046383EA2', N'FULL', NULL, NULL, '2026-06-26 11:43:09.080'),
    (6, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'NMG Afternoon Sync', N'DAILY', '2000-01-01 13:04:00.000', 1, '2026-06-24 16:47:10.103', N'3019101A-24A6-4045-AB7E-964046383EA2', N'FULL', NULL, NULL, '2026-06-24 16:47:10.103'),
    (7, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'NMS Morning Sync', N'DAILY', '2000-01-01 18:21:00.000', 1, '2026-06-24 16:47:10.107', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'FULL', NULL, NULL, '2026-06-26 11:43:16.173'),
    (8, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'NMS Afternoon Sync', N'DAILY', '2000-01-01 13:06:00.000', 1, '2026-06-24 16:47:10.110', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'FULL', NULL, NULL, '2026-06-24 16:47:10.110'),
    (9, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'NMW Morning Sync', N'DAILY', '2000-01-01 18:23:00.000', 1, '2026-06-24 16:47:10.113', N'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', N'FULL', NULL, NULL, '2026-06-26 11:43:26.737'),
    (10, N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'NMW Afternoon Sync', N'DAILY', '2000-01-01 13:08:00.000', 1, '2026-06-24 16:47:10.120', N'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', N'FULL', NULL, NULL, '2026-06-24 16:47:10.120');
SET IDENTITY_INSERT [dbo].[sync_schedule] OFF;
GO

IF OBJECT_ID('dbo.sync_store_selection') IS NOT NULL DROP TABLE [dbo].[sync_store_selection];
GO
CREATE TABLE [dbo].[sync_store_selection] (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [config_id] bigint NOT NULL,
    [store_id] uniqueidentifier NOT NULL,
    [is_selected] bit NOT NULL,
    CONSTRAINT [PK_dbo_sync_store_selection] PRIMARY KEY ([id])
);
GO

IF OBJECT_ID('dbo.sync_table_registry') IS NOT NULL DROP TABLE [dbo].[sync_table_registry];
GO
CREATE TABLE [dbo].[sync_table_registry] (
    [table_id] bigint IDENTITY(1,1) NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [table_name] varchar(200) NOT NULL,
    [sync_order] int NOT NULL,
    [chunk_enabled] bit NOT NULL,
    [refresh_enabled] bit NOT NULL,
    [is_active] bit NOT NULL,
    CONSTRAINT [PK_dbo_sync_table_registry] PRIMARY KEY ([table_id])
);
GO
SET IDENTITY_INSERT [dbo].[sync_table_registry] ON;
INSERT INTO [dbo].[sync_table_registry] ([table_id], [tenant_id], [table_name], [sync_order], [chunk_enabled], [refresh_enabled], [is_active]) VALUES
    (1, N'00000000-0000-0000-0000-000000000000', N'3B_Table1', 999, 1, 1, 1),
    (2, N'00000000-0000-0000-0000-000000000000', N'3B_Table2', 999, 1, 1, 1),
    (3, N'00000000-0000-0000-0000-000000000000', N'3B_Table3', 999, 1, 1, 1),
    (4, N'00000000-0000-0000-0000-000000000000', N'3B_Table4', 999, 1, 1, 1),
    (5, N'00000000-0000-0000-0000-000000000000', N'3B_Table5', 999, 1, 1, 1),
    (6, N'00000000-0000-0000-0000-000000000000', N'3B_Table6', 999, 1, 1, 1),
    (7, N'00000000-0000-0000-0000-000000000000', N'3B_Table7', 999, 1, 1, 1),
    (8, N'00000000-0000-0000-0000-000000000000', N'3B_Table8', 999, 1, 1, 1),
    (9, N'00000000-0000-0000-0000-000000000000', N'3bsubmissioninfo', 999, 1, 1, 1),
    (10, N'00000000-0000-0000-0000-000000000000', N'AA', 999, 1, 1, 1);
SET IDENTITY_INSERT [dbo].[sync_table_registry] OFF;
GO

IF OBJECT_ID('dbo.tenants') IS NOT NULL DROP TABLE [dbo].[tenants];
GO
CREATE TABLE [dbo].[tenants] (
    [tenant_id] uniqueidentifier NOT NULL,
    [tenant_code] varchar(50) NOT NULL,
    [tenant_abbreviation] varchar(20) NOT NULL,
    [tenant_name] varchar(200) NOT NULL,
    [db_name] varchar(200) NOT NULL,
    [platform_version] varchar(20) NULL,
    [tenant_db_version] varchar(20) NULL,
    [contact_name] varchar(100) NULL,
    [contact_email] varchar(200) NULL,
    [contact_phone] varchar(50) NULL,
    [is_active] bit NOT NULL,
    [created_at] datetime NOT NULL,
    [created_by] uniqueidentifier NULL,
    [updated_at] datetime NULL,
    [updated_by] uniqueidentifier NULL,
    [website_url] varchar(500) NULL,
    CONSTRAINT [PK_dbo_tenants] PRIMARY KEY ([tenant_id])
);
GO
INSERT INTO [dbo].[tenants] ([tenant_id], [tenant_code], [tenant_abbreviation], [tenant_name], [db_name], [platform_version], [tenant_db_version], [contact_name], [contact_email], [contact_phone], [is_active], [created_at], [created_by], [updated_at], [updated_by], [website_url]) VALUES
    (N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'NATHAN', N'Nathan', N'Nathan Medicals ', N'NEXORA_PLATFORM', NULL, NULL, NULL, NULL, NULL, 1, '2026-06-18 19:21:40.837', NULL, NULL, NULL, NULL);
GO

IF OBJECT_ID('dbo.user_login_security') IS NOT NULL DROP TABLE [dbo].[user_login_security];
GO
CREATE TABLE [dbo].[user_login_security] (
    [user_id] uniqueidentifier NOT NULL,
    [failed_login_count] int NOT NULL,
    [is_locked] bit NOT NULL,
    [locked_until] datetime NULL,
    [force_password_change] bit NOT NULL,
    [last_failed_login] datetime NULL,
    [last_successful_login] datetime NULL,
    CONSTRAINT [PK_dbo_user_login_security] PRIMARY KEY ([user_id])
);
GO

IF OBJECT_ID('dbo.user_module_override') IS NOT NULL DROP TABLE [dbo].[user_module_override];
GO
CREATE TABLE [dbo].[user_module_override] (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [user_id] uniqueidentifier NOT NULL,
    [module_id] uniqueidentifier NOT NULL,
    [can_view] bit NULL,
    [can_create] bit NULL,
    [can_edit] bit NULL,
    [can_delete] bit NULL,
    [can_export] bit NULL,
    [is_active] bit NULL,
    CONSTRAINT [PK_dbo_user_module_override] PRIMARY KEY ([id])
);
GO

IF OBJECT_ID('dbo.user_store_roles') IS NOT NULL DROP TABLE [dbo].[user_store_roles];
GO
CREATE TABLE [dbo].[user_store_roles] (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [user_id] uniqueidentifier NOT NULL,
    [store_id] uniqueidentifier NOT NULL,
    [role_id] uniqueidentifier NOT NULL,
    [is_active] bit NOT NULL,
    CONSTRAINT [PK_dbo_user_store_roles] PRIMARY KEY ([id])
);
GO
SET IDENTITY_INSERT [dbo].[user_store_roles] ON;
INSERT INTO [dbo].[user_store_roles] ([id], [user_id], [store_id], [role_id], [is_active]) VALUES
    (1, N'4055B2C9-30E8-4062-9D52-666EF0769D4B', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', 1);
SET IDENTITY_INSERT [dbo].[user_store_roles] OFF;
GO

IF OBJECT_ID('dbo.users') IS NOT NULL DROP TABLE [dbo].[users];
GO
CREATE TABLE [dbo].[users] (
    [user_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NULL,
    [username] varchar(100) NOT NULL,
    [password_hash] varchar(500) NOT NULL,
    [first_name] varchar(100) NOT NULL,
    [last_name] varchar(100) NULL,
    [email] varchar(200) NULL,
    [mobile] varchar(50) NULL,
    [is_platform_user] bit NOT NULL,
    [is_active] bit NOT NULL,
    [last_login] datetime NULL,
    [created_at] datetime NOT NULL,
    [updated_at] datetime NULL,
    [failed_login_attempts] int NOT NULL,
    [locked_until] datetime NULL,
    [force_password_change] bit NOT NULL,
    [password_changed_at] datetime NULL,
    [created_by] uniqueidentifier NULL,
    [updated_by] uniqueidentifier NULL,
    [password_reset_token] varchar(200) NULL,
    [password_reset_expiry] datetime NULL,
    CONSTRAINT [PK_dbo_users] PRIMARY KEY ([user_id])
);
GO
INSERT INTO [dbo].[users] ([user_id], [tenant_id], [username], [password_hash], [first_name], [last_name], [email], [mobile], [is_platform_user], [is_active], [last_login], [created_at], [updated_at], [failed_login_attempts], [locked_until], [force_password_change], [password_changed_at], [created_by], [updated_by], [password_reset_token], [password_reset_expiry]) VALUES
    (N'4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, N'superadmin', N'$2b$12$EZZHtwfID05iPyKVuwQ/aee38JFcbbxvwmgWpcgT83oWyTKxW07RS', N'Super', N'Admin', NULL, NULL, 1, 1, '2026-06-18 19:53:32.570', '2026-06-18 14:38:59.737', '2026-06-18 19:48:40.253', 0, NULL, 0, '2026-06-18 19:48:40.253', NULL, NULL, NULL, NULL);
GO

IF OBJECT_ID('procurement.procurement_cycles') IS NOT NULL DROP TABLE [procurement].[procurement_cycles];
GO
CREATE TABLE [procurement].[procurement_cycles] (
    [cycle_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [name] varchar(200) NOT NULL,
    [description] varchar(1000) NULL,
    [status] varchar(50) NOT NULL,
    [start_date] date NULL,
    [end_date] date NULL,
    [store_id] uniqueidentifier NULL,
    [cycle_no] int NULL,
    [offline_mode] bit NOT NULL,
    [active_refresh_id] uniqueidentifier NULL,
    [closed_at] datetime NULL,
    [start_grn_number] varchar(50) NULL,
    [start_sale_bill_number] varchar(50) NULL,
    [end_grn_number] varchar(50) NULL,
    [end_sale_bill_number] varchar(50) NULL,
    [created_at] datetime NOT NULL,
    [created_by] uniqueidentifier NULL,
    [updated_at] datetime NULL,
    [updated_by] uniqueidentifier NULL,
    [is_deleted] bit NOT NULL,
    [deleted_at] datetime NULL,
    [deleted_by] uniqueidentifier NULL,
    CONSTRAINT [PK_procurement_procurement_cycles] PRIMARY KEY ([cycle_id])
);
GO
INSERT INTO [procurement].[procurement_cycles] ([cycle_id], [tenant_id], [name], [description], [status], [start_date], [end_date], [store_id], [cycle_no], [offline_mode], [active_refresh_id], [closed_at], [start_grn_number], [start_sale_bill_number], [end_grn_number], [end_sale_bill_number], [created_at], [created_by], [updated_at], [updated_by], [is_deleted], [deleted_at], [deleted_by]) VALUES
    (N'C5289020-BEC7-4E74-99EE-19455E7AF5E9', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'ISO Test B', NULL, N'Closed', NULL, NULL, N'D55F8A0D-C230-44EA-BF56-02F143B948BD', NULL, 0, N'B2C18431-173E-4636-B5CE-1764D92BF9BF', NULL, NULL, NULL, NULL, NULL, '2026-07-05 14:12:46.703', NULL, '2026-07-05 14:12:59.707', NULL, 1, NULL, NULL),
    (N'C6E89C04-55C5-44F8-8464-3E9559ED860E', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'Real Cycle 2026-07-02', NULL, N'Closed', NULL, NULL, N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', NULL, 0, N'47ACF89A-EC30-4201-A663-CA0DA179031D', '2026-07-04 20:11:04.670', N'17845', N'50235', N'17845', N'231675', '2026-07-02 17:34:13.517', N'4055B2C9-30E8-4062-9D52-666EF0769D4B', '2026-07-04 20:11:04.670', NULL, 0, NULL, NULL),
    (N'70AF68C3-BFBB-440E-80FB-421DEA1C1BC6', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'sunday test', NULL, N'ACTIVE', NULL, NULL, N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', NULL, 0, N'64977121-A59D-4FBF-B32A-36E4253AAF6E', NULL, NULL, NULL, NULL, NULL, '2026-07-05 15:06:52.647', NULL, '2026-07-05 15:07:04.800', NULL, 0, NULL, NULL),
    (N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'Real Cycle 2026-07-02 · 04-Jul-2026', NULL, N'ACTIVE', NULL, NULL, N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', NULL, 0, N'F2C197F8-8A16-4426-8DBC-08B0DAB4E25D', NULL, N'17845', N'231675', NULL, NULL, '2026-07-04 20:11:04.690', NULL, '2026-07-05 15:07:21.353', NULL, 0, NULL, NULL);
GO

IF OBJECT_ID('procurement.procurement_order_item_assignments') IS NOT NULL DROP TABLE [procurement].[procurement_order_item_assignments];
GO
CREATE TABLE [procurement].[procurement_order_item_assignments] (
    [assignment_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [cycle_id] uniqueidentifier NOT NULL,
    [refresh_id] uniqueidentifier NOT NULL,
    [order_item_id] uniqueidentifier NOT NULL,
    [store_id] uniqueidentifier NULL,
    [product_code] varchar(100) NULL,
    [supplier_code] varchar(100) NOT NULL,
    [assigned_qty] decimal(18,3) NULL,
    [assignment_status] varchar(30) NOT NULL,
    [remarks] varchar(300) NULL,
    [export_batch_number] varchar(50) NULL,
    [export_split_number] int NULL,
    [export_uid] varchar(100) NULL,
    [exported_at] datetime NULL,
    [exported_by] uniqueidentifier NULL,
    [received_qty] decimal(18,3) NULL,
    [grn_no] varchar(100) NULL,
    [supplier_bill_no] varchar(100) NULL,
    [created_at] datetime NOT NULL,
    [created_by] uniqueidentifier NULL,
    [updated_at] datetime NULL,
    [updated_by] uniqueidentifier NULL,
    [is_deleted] bit NOT NULL,
    [deleted_at] datetime NULL,
    [deleted_by] uniqueidentifier NULL,
    [remaining_qty] decimal(18,3) NULL,
    [last_grn_sync_at] datetime NULL,
    CONSTRAINT [PK_procurement_procurement_order_item_assignments] PRIMARY KEY ([assignment_id])
);
GO
INSERT INTO [procurement].[procurement_order_item_assignments] ([assignment_id], [tenant_id], [cycle_id], [refresh_id], [order_item_id], [store_id], [product_code], [supplier_code], [assigned_qty], [assignment_status], [remarks], [export_batch_number], [export_split_number], [export_uid], [exported_at], [exported_by], [received_qty], [grn_no], [supplier_bill_no], [created_at], [created_by], [updated_at], [updated_by], [is_deleted], [deleted_at], [deleted_by], [remaining_qty], [last_grn_sync_at]) VALUES
    (N'7ABF974D-B044-4391-907C-011863E79FC8', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C6E89C04-55C5-44F8-8464-3E9559ED860E', N'47ACF89A-EC30-4201-A663-CA0DA179031D', N'5348162B-B286-4EFC-9133-071246EFA4C3', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'5894618', N'LIFE', 1.000, N'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:34:57.800', N'4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    (N'543270CA-C93E-48B4-9D20-019D302B2B4F', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C6E89C04-55C5-44F8-8464-3E9559ED860E', N'47ACF89A-EC30-4201-A663-CA0DA179031D', N'F1049D89-7DEE-4F54-9F59-BC27291F93AE', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'24747', N'117', 30.000, N'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:34:50.367', N'4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    (N'A8F9324B-C9EB-461B-A2C2-01E42E3C94F1', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C6E89C04-55C5-44F8-8464-3E9559ED860E', N'47ACF89A-EC30-4201-A663-CA0DA179031D', N'FCFE99D4-9F46-4B25-9EF3-7F48EDF0F4C6', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'5852448', N'117', 13.000, N'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:34:50.610', N'4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    (N'1B2D02DF-8546-41C1-904A-01EF3F7CA702', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C6E89C04-55C5-44F8-8464-3E9559ED860E', N'47ACF89A-EC30-4201-A663-CA0DA179031D', N'868B7A39-A662-4173-B04D-17B125C0C498', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'5870517', N'PALEPU', 1.000, N'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:34:59.327', N'4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    (N'47074A8D-D600-46DC-8869-02889AEE5E2A', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C6E89C04-55C5-44F8-8464-3E9559ED860E', N'47ACF89A-EC30-4201-A663-CA0DA179031D', N'5B66B8A5-F074-4A44-ADF6-1D426C4A5763', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'5878014', N'426', 60.000, N'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:34:55.910', N'4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    (N'11ADA3BE-D96C-439C-A981-02AB297CAAC1', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C6E89C04-55C5-44F8-8464-3E9559ED860E', N'47ACF89A-EC30-4201-A663-CA0DA179031D', N'E33D7B16-FAD9-4846-AAF4-8A817E7C9B6D', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'5883802', N'438', 1.000, N'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:34:59.160', N'4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    (N'862E775E-313C-43F6-8609-02C8F1AB3AC2', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C6E89C04-55C5-44F8-8464-3E9559ED860E', N'47ACF89A-EC30-4201-A663-CA0DA179031D', N'33051BAF-EED2-42E7-A707-599EE68C08F7', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'26065', N'120', 60.000, N'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:34:52.203', N'4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    (N'B146AAD6-4481-4435-B1B7-0328C5CC8F85', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C6E89C04-55C5-44F8-8464-3E9559ED860E', N'47ACF89A-EC30-4201-A663-CA0DA179031D', N'CFFB5C43-F917-4C43-8068-8CBDD35C64DE', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'4407', N'15', 40.000, N'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:34:52.823', N'4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    (N'26260681-E925-4803-8EFE-042C00F32F09', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C6E89C04-55C5-44F8-8464-3E9559ED860E', N'47ACF89A-EC30-4201-A663-CA0DA179031D', N'91D8479A-342D-412C-9048-630258F790B5', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'5882197', N'567', 3.000, N'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:35:01.520', N'4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    (N'72D008BA-CD66-4555-87EE-043F8CA293E1', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C6E89C04-55C5-44F8-8464-3E9559ED860E', N'47ACF89A-EC30-4201-A663-CA0DA179031D', N'EE426966-2E92-4661-9508-A30049EEDCDA', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'5888110', N'153', 4.000, N'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:35:01.830', N'4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL);
GO

IF OBJECT_ID('procurement.procurement_order_items') IS NOT NULL DROP TABLE [procurement].[procurement_order_items];
GO
CREATE TABLE [procurement].[procurement_order_items] (
    [order_item_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [cycle_id] uniqueidentifier NOT NULL,
    [refresh_id] uniqueidentifier NOT NULL,
    [store_id] uniqueidentifier NULL,
    [product_id] uniqueidentifier NOT NULL,
    [product_code] varchar(100) NULL,
    [final_qty] decimal(18,3) NULL,
    [assigned_qty] decimal(18,3) NULL,
    [remaining_qty] decimal(18,3) NULL,
    [action_mode] varchar(30) NULL,
    [manual_override] bit NULL,
    [override_reason] varchar(300) NULL,
    [item_status] varchar(20) NOT NULL,
    [created_at] datetime NOT NULL,
    [created_by] uniqueidentifier NULL,
    [updated_at] datetime NULL,
    [updated_by] uniqueidentifier NULL,
    [is_deleted] bit NOT NULL,
    [deleted_at] datetime NULL,
    [deleted_by] uniqueidentifier NULL,
    [suggested_qty] decimal(18,3) NULL,
    [skip_reason] varchar(300) NULL,
    [reviewed_by] uniqueidentifier NULL,
    [reviewed_at] datetime NULL,
    [received_qty] decimal(18,3) NULL,
    [is_manual] bit NOT NULL,
    [pending_status] varchar(20) NULL,
    CONSTRAINT [PK_procurement_procurement_order_items] PRIMARY KEY ([order_item_id])
);
GO
INSERT INTO [procurement].[procurement_order_items] ([order_item_id], [tenant_id], [cycle_id], [refresh_id], [store_id], [product_id], [product_code], [final_qty], [assigned_qty], [remaining_qty], [action_mode], [manual_override], [override_reason], [item_status], [created_at], [created_by], [updated_at], [updated_by], [is_deleted], [deleted_at], [deleted_by], [suggested_qty], [skip_reason], [reviewed_by], [reviewed_at], [received_qty], [is_manual], [pending_status]) VALUES
    (N'F321F46A-2464-4984-8596-000BAE0E31B1', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'905087CF-CA8D-4237-B4FB-94D213F1D503', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'3C85B5D9-EE0E-4BC5-8E96-0EAEAD68534D', N'10731', 60.000, 0.000, 60.000, NULL, NULL, NULL, N'draft', '2026-07-05 14:18:05.490', NULL, NULL, NULL, 0, NULL, NULL, 60.000, NULL, NULL, NULL, NULL, 0, NULL),
    (N'A6D0277B-2B93-4C16-B3DD-001016DFFB26', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'905087CF-CA8D-4237-B4FB-94D213F1D503', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'CACB9109-A93C-4E90-998F-5BEC413EEF39', N'5890539', 1.000, 0.000, 1.000, NULL, NULL, NULL, N'draft', '2026-07-05 14:18:05.490', NULL, NULL, NULL, 0, NULL, NULL, 1.000, NULL, NULL, NULL, NULL, 0, NULL),
    (N'A9EE15D7-68F4-4E7C-A8D0-00182A9A5127', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'40C9BD82-7531-45FF-BB1D-4D2AE8E67CE1', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'FE4B3C7E-87C6-4006-9789-A22BC447189F', N'5891002', 10.000, 0.000, 10.000, NULL, NULL, NULL, N'draft', '2026-07-05 15:06:41.117', NULL, NULL, NULL, 0, NULL, NULL, 10.000, NULL, NULL, NULL, NULL, 0, NULL),
    (N'6EBC6629-82B4-4FD0-9503-00196D7D1CAF', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'40C9BD82-7531-45FF-BB1D-4D2AE8E67CE1', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'94A29A36-284B-42B5-88AE-27415106E780', N'5871400', 2.000, 0.000, 2.000, NULL, NULL, NULL, N'draft', '2026-07-05 15:06:41.117', NULL, NULL, NULL, 0, NULL, NULL, 2.000, NULL, NULL, NULL, NULL, 0, NULL),
    (N'B71F935D-5C8B-4763-A2D8-001B5365AE16', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'40C9BD82-7531-45FF-BB1D-4D2AE8E67CE1', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'3234027A-1AAE-4842-9E68-765C60F3E3C1', N'5894229', 1.000, 0.000, 1.000, NULL, NULL, NULL, N'draft', '2026-07-05 15:06:41.117', NULL, NULL, NULL, 0, NULL, NULL, 1.000, NULL, NULL, NULL, NULL, 0, NULL),
    (N'B6D3A4EF-06F0-4D6B-9C14-003047A3FB77', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'14FD2327-950E-4B1B-9057-75A0342A2DBD', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'76239A8D-36D3-4C6B-B645-ACF0F5969548', N'2300', 10.000, 0.000, 10.000, NULL, NULL, NULL, N'draft', '2026-07-05 15:04:38.980', NULL, NULL, NULL, 0, NULL, NULL, 10.000, NULL, NULL, NULL, NULL, 0, NULL),
    (N'0781FB8C-9B85-4838-AFC2-0034AD75D0F1', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'F2C197F8-8A16-4426-8DBC-08B0DAB4E25D', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'A582259F-78EB-4CE7-A1AE-298EE7B37C53', N'21394', 2.000, 0.000, 2.000, NULL, NULL, NULL, N'draft', '2026-07-05 15:07:21.383', NULL, NULL, NULL, 0, NULL, NULL, 2.000, NULL, NULL, NULL, NULL, 0, NULL),
    (N'BEFE284C-BDEF-467F-8DF9-003B0437E9CB', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'F2C197F8-8A16-4426-8DBC-08B0DAB4E25D', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'53EC69F6-3494-4131-91CC-F77991EE0F1E', N'12994', 3.000, 0.000, 3.000, NULL, NULL, NULL, N'draft', '2026-07-05 15:07:21.383', NULL, NULL, NULL, 0, NULL, NULL, 3.000, NULL, NULL, NULL, NULL, 0, NULL),
    (N'984AF4DF-D932-4703-91A6-0045BFE2504E', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C6E89C04-55C5-44F8-8464-3E9559ED860E', N'47ACF89A-EC30-4201-A663-CA0DA179031D', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'3DB4C61F-3F94-4DA1-844B-BCD28B41F136', N'5888582', 30.000, 30.000, 30.000, NULL, NULL, NULL, N'pending', '2026-07-02 17:34:21.183', N'4055B2C9-30E8-4062-9D52-666EF0769D4B', '2026-07-04 20:11:04.497', NULL, 0, NULL, NULL, 30.000, NULL, NULL, '2026-07-04 20:11:04.497', 0.000, 0, N'cleared'),
    (N'AECBFE51-5077-4C7B-9D90-004DBAF8BAB5', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'40C9BD82-7531-45FF-BB1D-4D2AE8E67CE1', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'B0975B6A-9B7E-440B-B853-39B684231DE5', N'5858436', 40.000, 0.000, 40.000, NULL, NULL, NULL, N'draft', '2026-07-05 15:06:41.117', NULL, NULL, NULL, 0, NULL, NULL, 40.000, NULL, NULL, NULL, NULL, 0, NULL);
GO

IF OBJECT_ID('procurement.procurement_refreshes') IS NOT NULL DROP TABLE [procurement].[procurement_refreshes];
GO
CREATE TABLE [procurement].[procurement_refreshes] (
    [refresh_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [cycle_id] uniqueidentifier NOT NULL,
    [store_id] uniqueidentifier NULL,
    [snapshot_name] varchar(200) NOT NULL,
    [snapshot_status] varchar(50) NOT NULL,
    [refresh_no] int NULL,
    [rolling_days] int NULL,
    [min_days] decimal(18,2) NULL,
    [max_days] decimal(18,2) NULL,
    [previous_refresh_id] uniqueidentifier NULL,
    [snapshot_grn_number] varchar(50) NULL,
    [snapshot_sale_bill_number] varchar(50) NULL,
    [sync_execution_id] uniqueidentifier NULL,
    [generated_product_count] int NULL,
    [generation_started_at] datetime NULL,
    [generation_completed_at] datetime NULL,
    [remarks] varchar(500) NULL,
    [last_snapshot_on] datetime NULL,
    [last_snapshot_by] uniqueidentifier NULL,
    [created_at] datetime NOT NULL,
    [created_by] uniqueidentifier NULL,
    [updated_at] datetime NULL,
    [updated_by] uniqueidentifier NULL,
    [is_deleted] bit NOT NULL,
    [deleted_at] datetime NULL,
    [deleted_by] uniqueidentifier NULL,
    [last_grn_number] varchar(50) NULL,
    [grn_completed_at] datetime NULL,
    CONSTRAINT [PK_procurement_procurement_refreshes] PRIMARY KEY ([refresh_id])
);
GO
INSERT INTO [procurement].[procurement_refreshes] ([refresh_id], [tenant_id], [cycle_id], [store_id], [snapshot_name], [snapshot_status], [refresh_no], [rolling_days], [min_days], [max_days], [previous_refresh_id], [snapshot_grn_number], [snapshot_sale_bill_number], [sync_execution_id], [generated_product_count], [generation_started_at], [generation_completed_at], [remarks], [last_snapshot_on], [last_snapshot_by], [created_at], [created_by], [updated_at], [updated_by], [is_deleted], [deleted_at], [deleted_by], [last_grn_number], [grn_completed_at]) VALUES
    (N'F2C197F8-8A16-4426-8DBC-08B0DAB4E25D', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'Refresh', N'Ready', NULL, 90, 13.00, 18.00, N'40C9BD82-7531-45FF-BB1D-4D2AE8E67CE1', NULL, NULL, NULL, 1357, '2026-07-05 15:07:20.093', '2026-07-05 15:07:21.353', NULL, NULL, NULL, '2026-07-05 15:07:20.070', NULL, '2026-07-05 15:07:21.353', NULL, 0, NULL, NULL, NULL, NULL),
    (N'B2C18431-173E-4636-B5CE-1764D92BF9BF', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C5289020-BEC7-4E74-99EE-19455E7AF5E9', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'ISO B', N'Ready', NULL, 90, 7.00, 21.00, NULL, NULL, NULL, NULL, 45909, '2026-07-05 14:12:46.757', '2026-07-05 14:12:59.707', NULL, NULL, NULL, '2026-07-05 14:12:46.740', NULL, '2026-07-05 14:12:59.707', NULL, 1, NULL, NULL, NULL, NULL),
    (N'64977121-A59D-4FBF-B32A-36E4253AAF6E', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'70AF68C3-BFBB-440E-80FB-421DEA1C1BC6', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'Refresh', N'Ready', NULL, 90, 13.00, 18.00, NULL, NULL, NULL, NULL, 724, '2026-07-05 15:07:03.453', '2026-07-05 15:07:04.800', NULL, NULL, NULL, '2026-07-05 15:07:03.420', NULL, '2026-07-05 15:07:04.800', NULL, 0, NULL, NULL, NULL, NULL),
    (N'40C9BD82-7531-45FF-BB1D-4D2AE8E67CE1', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'Trimmed VPL', N'Archived', NULL, 90, 7.00, 21.00, N'14FD2327-950E-4B1B-9057-75A0342A2DBD', NULL, NULL, NULL, 989, '2026-07-05 15:06:39.943', '2026-07-05 15:06:41.093', NULL, NULL, NULL, '2026-07-05 15:06:39.893', NULL, '2026-07-05 15:07:21.760', NULL, 0, NULL, NULL, NULL, NULL),
    (N'F2C5C224-FD68-435D-8B77-54989EA3D4C8', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'Repro Refresh', N'Archived', NULL, 90, 7.00, 21.00, NULL, NULL, NULL, NULL, 32712, '2026-07-05 14:01:44.370', '2026-07-05 14:01:56.400', NULL, NULL, NULL, '2026-07-05 14:01:44.300', NULL, '2026-07-05 14:18:05.670', NULL, 0, NULL, NULL, NULL, NULL),
    (N'14FD2327-950E-4B1B-9057-75A0342A2DBD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'Refresh', N'Archived', NULL, 90, 13.00, 18.00, N'905087CF-CA8D-4237-B4FB-94D213F1D503', NULL, NULL, NULL, 32712, '2026-07-05 15:04:27.263', '2026-07-05 15:04:38.760', NULL, NULL, NULL, '2026-07-05 15:04:27.230', NULL, '2026-07-05 15:06:41.220', NULL, 0, NULL, NULL, NULL, NULL),
    (N'905087CF-CA8D-4237-B4FB-94D213F1D503', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'Refresh', N'Archived', NULL, 90, 13.00, 15.00, N'F2C5C224-FD68-435D-8B77-54989EA3D4C8', NULL, NULL, NULL, 32712, '2026-07-05 14:17:54.030', '2026-07-05 14:18:05.260', NULL, NULL, NULL, '2026-07-05 14:17:53.997', NULL, '2026-07-05 15:04:39.153', NULL, 0, NULL, NULL, NULL, NULL),
    (N'47ACF89A-EC30-4201-A663-CA0DA179031D', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C6E89C04-55C5-44F8-8464-3E9559ED860E', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'Refresh 1', N'Ready', NULL, 90, 13.00, 18.00, NULL, N'17845', N'50235', NULL, 32682, '2026-07-02 17:34:13.573', '2026-07-02 17:34:21.020', NULL, NULL, NULL, '2026-07-02 17:34:13.553', N'4055B2C9-30E8-4062-9D52-666EF0769D4B', '2026-07-02 17:34:21.020', NULL, 0, NULL, NULL, NULL, NULL);
GO

IF OBJECT_ID('procurement.procurement_virtual_products') IS NOT NULL DROP TABLE [procurement].[procurement_virtual_products];
GO
CREATE TABLE [procurement].[procurement_virtual_products] (
    [virtual_product_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [cycle_id] uniqueidentifier NOT NULL,
    [refresh_id] uniqueidentifier NOT NULL,
    [product_id] uniqueidentifier NOT NULL,
    [product_code] varchar(100) NULL,
    [product_name] varchar(300) NULL,
    [manufacturer_id] uniqueidentifier NULL,
    [category_id] uniqueidentifier NULL,
    [schedule_type] varchar(50) NULL,
    [unit] varchar(50) NULL,
    [is_active] bit NOT NULL,
    [snapshot_version] int NOT NULL,
    [mrp] decimal(18,4) NULL,
    [ptr_cost] decimal(18,4) NULL,
    [pack] varchar(50) NULL,
    [unit_description] varchar(100) NULL,
    [sub_location] varchar(100) NULL,
    [monthly_sales_qty] decimal(18,3) NULL,
    [tx_count] int NULL,
    [max_day_sale_qty] decimal(18,3) NULL,
    [max_bill_qty] decimal(18,3) NULL,
    [days_since_last_sale] int NULL,
    [days_since_last_purchase] int NULL,
    [days_cover] decimal(18,3) NULL,
    [movement_class] varchar(30) NULL,
    [stock_status] varchar(30) NULL,
    [offer_buy_qty] decimal(18,3) NULL,
    [offer_free_qty] decimal(18,3) NULL,
    [offer_last_date] date NULL,
    [order_type] varchar(30) NULL,
    [is_auto_accept] bit NULL,
    [warning_flag] bit NULL,
    [warning_reason] varchar(200) NULL,
    [committed_qty] decimal(18,3) NULL,
    [remaining_procurement_qty] decimal(18,3) NULL,
    [required_qty] decimal(18,3) NULL,
    [suggested_qty] decimal(18,3) NULL,
    [target_days] decimal(18,2) NULL,
    [target_stock_qty] decimal(18,3) NULL,
    [raw_required_qty] decimal(18,3) NULL,
    [final_required_qty] decimal(18,3) NULL,
    [procurement_action] varchar(50) NULL,
    [trigger_reason] varchar(100) NULL,
    [effective_available_qty] decimal(18,3) NULL,
    [pending_used_qty] decimal(18,3) NULL,
    [created_at] datetime NOT NULL,
    [updated_at] datetime NULL,
    [current_stock_qty] decimal(18,3) NULL,
    [available_stock_qty] decimal(18,3) NULL,
    [pending_purchase_qty] decimal(18,3) NULL,
    [pending_sales_qty] decimal(18,3) NULL,
    [last_purchase_date] date NULL,
    [last_purchase_qty] decimal(18,3) NULL,
    [last_purchase_rate] decimal(18,4) NULL,
    [last_sale_date] date NULL,
    [last_sale_qty] decimal(18,3) NULL,
    [avg_daily_sales] decimal(18,4) NULL,
    [avg_monthly_sales] decimal(18,4) NULL,
    [expiry_qty] decimal(18,3) NULL,
    [near_expiry_qty] decimal(18,3) NULL,
    [supplier_count] int NULL,
    [preferred_supplier_id] uniqueidentifier NULL,
    [snapshot_refreshed_on] datetime NULL,
    [reason_code] varchar(50) NULL,
    [reason_text] varchar(500) NULL,
    [window_sales_qty] decimal(18,3) NULL,
    [billing_frequency] int NULL,
    CONSTRAINT [PK_procurement_procurement_virtual_products] PRIMARY KEY ([virtual_product_id])
);
GO
INSERT INTO [procurement].[procurement_virtual_products] ([virtual_product_id], [tenant_id], [cycle_id], [refresh_id], [product_id], [product_code], [product_name], [manufacturer_id], [category_id], [schedule_type], [unit], [is_active], [snapshot_version], [mrp], [ptr_cost], [pack], [unit_description], [sub_location], [monthly_sales_qty], [tx_count], [max_day_sale_qty], [max_bill_qty], [days_since_last_sale], [days_since_last_purchase], [days_cover], [movement_class], [stock_status], [offer_buy_qty], [offer_free_qty], [offer_last_date], [order_type], [is_auto_accept], [warning_flag], [warning_reason], [committed_qty], [remaining_procurement_qty], [required_qty], [suggested_qty], [target_days], [target_stock_qty], [raw_required_qty], [final_required_qty], [procurement_action], [trigger_reason], [effective_available_qty], [pending_used_qty], [created_at], [updated_at], [current_stock_qty], [available_stock_qty], [pending_purchase_qty], [pending_sales_qty], [last_purchase_date], [last_purchase_qty], [last_purchase_rate], [last_sale_date], [last_sale_qty], [avg_daily_sales], [avg_monthly_sales], [expiry_qty], [near_expiry_qty], [supplier_count], [preferred_supplier_id], [snapshot_refreshed_on], [reason_code], [reason_text], [window_sales_qty], [billing_frequency]) VALUES
    (N'5DB66897-2BE5-4947-A21B-00001AF10EA7', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C6E89C04-55C5-44F8-8464-3E9559ED860E', N'47ACF89A-EC30-4201-A663-CA0DA179031D', N'ECBE2AE9-D781-473A-8CA6-01E9C8492BE2', N'5886868', N'VIZIGLY SOAP  75GM', NULL, NULL, NULL, N'SOAP', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, 0.000, NULL, NULL, 0.000, N'NONMOVING', N'OUT', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, N'EXCLUDE', NULL, 0.000, 0.000, '2026-07-02 17:34:19.673', NULL, 0.000, 0.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0000, NULL, NULL, NULL, NULL, NULL, NULL, N'EXCLUDED_NOT_SELLING', N'Excluded: no eligible sales in the rolling window.', 0.000, 0),
    (N'FB320F53-0661-454D-9941-000025624CD9', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'905087CF-CA8D-4237-B4FB-94D213F1D503', N'9F98CAE4-90C1-4633-B135-3E0F36C267EB', N'5861014', N'FLOXSAFE 400 TAB', NULL, NULL, NULL, N'TAB', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, 0.000, NULL, NULL, 0.000, N'NONMOVING', N'OUT', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, N'EXCLUDE', NULL, 0.000, 0.000, '2026-07-05 14:18:00.177', NULL, 0.000, 0.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0000, NULL, NULL, NULL, NULL, NULL, NULL, N'EXCLUDED_NOT_SELLING', N'Excluded: no eligible sales in the rolling window.', 0.000, 0),
    (N'4ACDED02-BB4C-41A4-8EE2-0000950D4CCB', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'F2C5C224-FD68-435D-8B77-54989EA3D4C8', N'59BF207C-BB45-4E6C-AD08-2CFBDBB0E4F3', N'5888337', N'DIGERAFT XT SYP 200ML', NULL, NULL, NULL, N'SYP', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 1.000, 1.000, NULL, NULL, 90.000, N'SLOW', N'OVERSTOCK', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, N'EXCLUDE', NULL, 1.000, 0.000, '2026-07-05 14:01:55.510', NULL, 1.000, 1.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0111, NULL, NULL, NULL, NULL, NULL, NULL, N'EXCLUDED_ADEQUATE_COVER', N'Excluded: 90.0d cover >= 7d minimum.', 1.000, 1),
    (N'B9D42BCE-678E-4A4F-92AC-0000EF9F144A', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C5289020-BEC7-4E74-99EE-19455E7AF5E9', N'B2C18431-173E-4636-B5CE-1764D92BF9BF', N'1058E668-2E4C-4F93-B78D-949B1813F922', N'18770', N'TRICHUP OIL 200ML', NULL, NULL, NULL, N'LOT', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 1.000, 1.000, NULL, NULL, 90.000, N'SLOW', N'OVERSTOCK', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, N'EXCLUDE', NULL, 1.000, 0.000, '2026-07-05 14:12:54.533', NULL, 1.000, 1.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0111, NULL, NULL, NULL, NULL, NULL, NULL, N'EXCLUDED_ADEQUATE_COVER', N'Excluded: 90.0d cover >= 7d minimum.', 1.000, 1),
    (N'A27F8B36-DA0F-41E7-AE2E-000203196C94', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'905087CF-CA8D-4237-B4FB-94D213F1D503', N'5D9E7781-BDE0-48C6-85A7-B0DFB4FCFC84', N'15480', N'HELLO BABY FEED BOT 250ML (PREMIUM)', NULL, NULL, NULL, N'CON', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 2.000, 1.000, NULL, NULL, 54.000, N'SLOW', N'OVERSTOCK', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, N'EXCLUDE', NULL, 3.000, 0.000, '2026-07-05 14:17:57.673', NULL, 3.000, 3.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0556, NULL, NULL, NULL, NULL, NULL, NULL, N'EXCLUDED_ADEQUATE_COVER', N'Excluded: 54.0d cover >= 13d minimum.', 5.000, 5),
    (N'83A82529-40F6-4D8D-8046-000204BCEA36', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'F2C5C224-FD68-435D-8B77-54989EA3D4C8', N'5E23690E-2074-41A8-A70D-7727B976EE0D', N'5875692', N'VIVEL  SOAP 51GM RS.10', NULL, NULL, NULL, N'SOAP', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, 0.000, NULL, NULL, 0.000, N'NONMOVING', N'OUT', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, N'EXCLUDE', NULL, 0.000, 0.000, '2026-07-05 14:01:53.980', NULL, 0.000, 0.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0000, NULL, NULL, NULL, NULL, NULL, NULL, N'EXCLUDED_NOT_SELLING', N'Excluded: no eligible sales in the rolling window.', 0.000, 0),
    (N'8BB41ACF-5B6F-4C74-91F2-000227619EDE', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C5289020-BEC7-4E74-99EE-19455E7AF5E9', N'B2C18431-173E-4636-B5CE-1764D92BF9BF', N'B632265B-F79B-43BC-857A-25CC435E0A07', N'5880832', N'VIM LIQ 750ML', NULL, NULL, NULL, N'SOAP', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, 0.000, NULL, NULL, 0.000, N'NONMOVING', N'OUT', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, N'EXCLUDE', NULL, 0.000, 0.000, '2026-07-05 14:12:58.890', NULL, 0.000, 0.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0000, NULL, NULL, NULL, NULL, NULL, NULL, N'EXCLUDED_NOT_SELLING', N'Excluded: no eligible sales in the rolling window.', 0.000, 0),
    (N'E5333D46-1EA7-4C17-A66D-00025428AD71', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'98207326-B23E-4F91-A299-E018FAC8EA1B', N'14FD2327-950E-4B1B-9057-75A0342A2DBD', N'69E66B2B-252E-474F-807E-B377471F8961', N'5862631', N'ANORELIEF CREAM  30GM', NULL, NULL, NULL, N'OIN', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 1.000, 1.000, NULL, NULL, 30.000, N'SLOW', N'OVERSTOCK', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, N'EXCLUDE', NULL, 1.000, 0.000, '2026-07-05 15:04:35.500', NULL, 1.000, 1.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0333, NULL, NULL, NULL, NULL, NULL, NULL, N'EXCLUDED_ADEQUATE_COVER', N'Excluded: 30.0d cover >= 13d minimum.', 3.000, 3),
    (N'644DED45-E448-4ABB-8084-0002744A52D2', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C6E89C04-55C5-44F8-8464-3E9559ED860E', N'47ACF89A-EC30-4201-A663-CA0DA179031D', N'7D85621C-2CBE-4A91-8D64-B9CF93C92D6F', N'5894382', N'KS B/S [SPARK]  220ML', NULL, NULL, NULL, N'PACK', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 1.000, 1.000, NULL, NULL, 180.000, N'SLOW', N'OVERSTOCK', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, N'EXCLUDE', NULL, 2.000, 0.000, '2026-07-02 17:34:20.960', NULL, 2.000, 2.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0111, NULL, NULL, NULL, NULL, NULL, NULL, N'EXCLUDED_ADEQUATE_COVER', N'Excluded: 180.0d cover >= 13d minimum.', 1.000, 1),
    (N'931720FE-9D0C-4591-A3A6-0002B2636303', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'C5289020-BEC7-4E74-99EE-19455E7AF5E9', N'B2C18431-173E-4636-B5CE-1764D92BF9BF', N'2AE286C1-5267-44AF-A968-95F8820FE898', N'5866044', N'VIMINOX FORTE TAB', NULL, NULL, NULL, N'TAB', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, 0.000, NULL, NULL, 0.000, N'NONMOVING', N'OUT', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, N'EXCLUDE', NULL, 0.000, 0.000, '2026-07-05 14:12:57.317', NULL, 0.000, 0.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0000, NULL, NULL, NULL, NULL, NULL, NULL, N'EXCLUDED_NOT_SELLING', N'Excluded: no eligible sales in the rolling window.', 0.000, 0);
GO

IF OBJECT_ID('procurement.supplier_excel_mapping') IS NOT NULL DROP TABLE [procurement].[supplier_excel_mapping];
GO
CREATE TABLE [procurement].[supplier_excel_mapping] (
    [mapping_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [store_id] uniqueidentifier NOT NULL,
    [supplier_code] varchar(50) NOT NULL,
    [supplier_column_name] nvarchar(150) NOT NULL,
    [column_name] nvarchar(100) NOT NULL,
    [is_active] bit NOT NULL,
    [created_by] varchar(100) NULL,
    [created_at] datetime NOT NULL,
    CONSTRAINT [PK_procurement_supplier_excel_mapping] PRIMARY KEY ([mapping_id])
);
GO
INSERT INTO [procurement].[supplier_excel_mapping] ([mapping_id], [tenant_id], [store_id], [supplier_code], [supplier_column_name], [column_name], [is_active], [created_by], [created_at]) VALUES
    (N'3AB53F5A-08B5-4D38-A256-04E377A1E805', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', N'1356', N'Product Code', N'supplierproductcode', 1, NULL, '2026-07-04 16:24:41.043'),
    (N'C2C298C8-B0A7-459A-A20B-05560F4B92AD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'1356', N'Pack', N'packing', 1, NULL, '2026-07-04 16:24:41.043'),
    (N'A4ED3F87-B8BA-4D14-ACC9-073620F22C20', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'754', N'item_name', N'SupplierProductName', 1, NULL, '2026-07-04 16:24:41.043'),
    (N'B01F9558-1AA5-4490-BBAF-0CCD61AAD46B', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'754', N'qty', N'stock', 1, NULL, '2026-07-04 16:24:41.043'),
    (N'0515EA35-3938-4211-BE01-0D3A07E82795', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'640', N'Pack', N'packing', 1, NULL, '2026-07-04 16:24:41.043'),
    (N'DA71E929-4847-45FC-B40F-0D93D0DE7BEB', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', N'1391', N'stock', N'stock', 1, NULL, '2026-07-04 16:24:41.043'),
    (N'E5A09623-4FCE-4143-93D4-12AFE24F6FFB', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'1356', N'stock', N'stock', 1, NULL, '2026-07-04 16:24:41.043'),
    (N'AE8297C1-AF0B-4567-9077-1F684896B732', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'691', N'free', N'free', 1, NULL, '2026-07-04 16:24:41.043'),
    (N'2F473743-F603-4552-9C19-22A71DA25DBE', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', N'102', N'Total Stock', N'stock', 1, NULL, '2026-07-04 16:24:41.043'),
    (N'FFDAC20E-BDED-4ADB-9FA3-26F686161CD5', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'AM', N'MRP', N'mrp', 1, NULL, '2026-07-04 16:24:41.043');
GO

IF OBJECT_ID('procurement.supplier_stock') IS NOT NULL DROP TABLE [procurement].[supplier_stock];
GO
CREATE TABLE [procurement].[supplier_stock] (
    [supplier_stock_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NOT NULL,
    [store_id] uniqueidentifier NOT NULL,
    [supplier_code] varchar(50) NOT NULL,
    [supplier_product_code] varchar(50) NULL,
    [supplier_product_name] varchar(200) NULL,
    [product_code] varchar(50) NULL,
    [available_stock] float NULL,
    [ptr] decimal(18,2) NULL,
    [mrp] decimal(18,2) NULL,
    [discount] varchar(50) NULL,
    [packing] varchar(50) NULL,
    [free] int NULL,
    [minimum_qty] int NULL,
    [scheme] int NULL,
    [transaction_date] datetime NULL,
    [source] varchar(20) NOT NULL,
    [is_active] bit NOT NULL,
    [imported_by] varchar(100) NULL,
    [imported_at] datetime NOT NULL,
    CONSTRAINT [PK_procurement_supplier_stock] PRIMARY KEY ([supplier_stock_id])
);
GO
INSERT INTO [procurement].[supplier_stock] ([supplier_stock_id], [tenant_id], [store_id], [supplier_code], [supplier_product_code], [supplier_product_name], [product_code], [available_stock], [ptr], [mrp], [discount], [packing], [free], [minimum_qty], [scheme], [transaction_date], [source], [is_active], [imported_by], [imported_at]) VALUES
    (N'152A7B8E-24F6-4D3E-A491-00024D021520', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'640', N'3403', N'ZOMELIS MET 50/500 TAB @ (185.11)', N'5855635', 172.0, 203.62, NULL, NULL, N'15''S', 0, NULL, 0, NULL, N'legacy', 1, N'legacy-import', '2026-07-04 16:24:40.483'),
    (N'FB539ECE-1181-4DA2-BD30-000404150EED', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', N'1356', N'73608', N'TELCURE CH 40MG TAB', NULL, 4.0, 216.56, NULL, N'10', N'15''S', 0, NULL, 0, NULL, N'legacy', 1, N'legacy-import', '2026-07-04 16:24:40.323'),
    (N'810E0D90-D071-4E6A-A97F-0006AC3CC344', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'754', N'I01815', N'AMLONG H TAB', N'23391', 80.0, NULL, NULL, N'16% MICRO CARSYON 1', N'15''S', NULL, 40, NULL, NULL, N'legacy', 1, N'legacy-import', '2026-07-04 16:24:40.743'),
    (N'E012F385-EA23-4CFB-9AD1-00076FE825BA', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', N'102', N'10111', N'OZOVAS-F TAB', N'25810', 1.0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'legacy', 1, N'legacy-import', '2026-07-04 16:24:39.617'),
    (N'CEC22934-610A-48CD-BCE0-0007C542728A', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', N'1391', N'2152', N'MOISTUREX CREAM 100GM (300.00)', N'5849688', 40.0, NULL, NULL, N'10', NULL, 0, NULL, 0, NULL, N'legacy', 1, N'legacy-import', '2026-07-04 16:24:40.410'),
    (N'30D26221-1F2F-4829-A80C-000C49CA454B', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', N'1391', N'2111', N'MEDERMA ADV PLUS 10GM (MIN 3) (8%)', NULL, 51.0, NULL, NULL, N'8', NULL, 0, NULL, 0, NULL, N'legacy', 1, N'legacy-import', '2026-07-04 16:24:40.410'),
    (N'87E8D9EF-6D4C-4E43-99A0-0010C28D327C', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', N'1391', N'2448', N'SAAZ DS TAB (192.90)', N'19336', 60.0, NULL, NULL, N'12', NULL, 0, NULL, 0, NULL, N'legacy', 1, N'legacy-import', '2026-07-04 16:24:40.420'),
    (N'BF78CE9C-8D3B-4C04-A4D3-001490BA39E4', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'3019101A-24A6-4045-AB7E-964046383EA2', N'99', N'22130', N'TONACT ASP 75', N'22130', 24.0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'legacy', 1, N'legacy-import', '2026-07-04 16:24:40.897'),
    (N'E5160211-A4FA-4201-AB73-0014C7CCFEEB', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'AM', N'2968', N'AMODEP AT TAB ', N'19844', 769.0, NULL, NULL, NULL, N'15''S', NULL, NULL, NULL, NULL, N'legacy', 1, N'legacy-import', '2026-07-04 16:24:40.923'),
    (N'D0A75674-3180-4401-B8EC-001A97A9DA17', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', N'1356', N'4068', N'LIPONORM F  (102.18)', N'5858207', 20.0, 112.00, NULL, N'8', N'15''S', 0, NULL, 0, NULL, N'legacy', 1, N'legacy-import', '2026-07-04 16:24:40.230');
GO

IF OBJECT_ID('sync.Batches') IS NOT NULL DROP TABLE [sync].[Batches];
GO
CREATE TABLE [sync].[Batches] (
    [store_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NULL,
    [BatchCode] int NOT NULL,
    [ProductCode] int NULL,
    [Stock] float NULL,
    [MRP] float NULL,
    [ExpiryDate] datetime NULL,
    [ItemCost] float NULL,
    [PurchasePrice] float NULL,
    [SaleUnit] float NULL,
    [GrnDate] datetime NULL,
    [LastReceivedDate] datetime NULL,
    [LastSaleDate] datetime NULL,
    [SalesTaxCode] int NULL,
    [SupplierCode] varchar(15) NULL,
    [Rate1] float NULL,
    [ReservedStock] float NULL,
    [FreeStock] float NULL,
    [CountedStock] float NULL,
    [StockDiscrepancy] float NULL,
    [StockCorrection] int NULL,
    [PurchaseUnit] float NULL,
    [RetailPrice] float NULL,
    [Margin] float NULL,
    [ManufacturingDate] datetime NULL,
    [InvoiceDate] datetime NULL,
    [InvoiceNumber] varchar(30) NULL,
    [GrnNumber] int NULL,
    [LocationId] int NULL,
    [SubLocation] varchar(50) NULL,
    [RackCode] int NULL,
    [IsLocked] bit NULL,
    [BatchLockType] int NULL,
    [OriginalRate] float NULL,
    [OriginalMRP] float NULL,
    [SyncID] int NULL,
    [row_hash] varchar(64) NULL,
    CONSTRAINT [PK_sync_Batches] PRIMARY KEY ([store_id], [BatchCode])
);
GO
INSERT INTO [sync].[Batches] ([store_id], [tenant_id], [BatchCode], [ProductCode], [Stock], [MRP], [ExpiryDate], [ItemCost], [PurchasePrice], [SaleUnit], [GrnDate], [LastReceivedDate], [LastSaleDate], [SalesTaxCode], [SupplierCode], [Rate1], [ReservedStock], [FreeStock], [CountedStock], [StockDiscrepancy], [StockCorrection], [PurchaseUnit], [RetailPrice], [Margin], [ManufacturingDate], [InvoiceDate], [InvoiceNumber], [GrnNumber], [LocationId], [SubLocation], [RackCode], [IsLocked], [BatchLockType], [OriginalRate], [OriginalMRP], [SyncID], [row_hash]) VALUES
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 9386, 10768, 0.0, 8.4, '2009-03-31 00:00:00.000', 7.18, 7.18, 10.0, NULL, NULL, NULL, 30, NULL, 8.4, 0.0, 0.0, NULL, NULL, 0, 10.0, NULL, NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, 0, 0, NULL, 0.0, NULL, N'be89969215f30c350ac92315402614327725346e77f17b4ed931e635d46e4eb2'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 22895, 25012, 0.0, 4.25, NULL, 2.88, 2.88, 1.0, NULL, NULL, NULL, 36, NULL, 4.25, 0.0, 0.0, NULL, NULL, 0, 1.0, 0.0, 0.0, NULL, NULL, NULL, 0, 1, N'', NULL, 0, 0, NULL, 0.0, 0, N'a801fdac493f57b227dd1776244aabdb0119cdd5811382bee16ebb1575dfd390'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 23625, 5, 0.0, 0.0, NULL, 0.0, 0.0, 1.0, NULL, NULL, NULL, 30, NULL, 0.0, 0.0, 0.0, NULL, NULL, 0, 1.0, NULL, NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, 0, 0, NULL, 0.0, NULL, N'5465bcceaf69314e33cf378945aae08873fac43888324e015e47f88798f6a3d0'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 23627, 7, 0.0, 0.0, NULL, 0.0, 0.0, 1.0, NULL, NULL, NULL, 30, NULL, 0.0, 0.0, 0.0, NULL, NULL, 0, 1.0, NULL, NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, 0, 0, NULL, 0.0, NULL, N'7587ac1d1df3b71d284ad5ede469357fa107a72368bd179125594243847635fa'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 23632, 12, 0.0, 0.0, NULL, 0.0, 0.0, 1.0, NULL, NULL, NULL, 30, NULL, 0.0, 0.0, 0.0, NULL, NULL, 0, 1.0, NULL, NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, 0, 0, NULL, 0.0, NULL, N'8677c086e78291135c6ce34d82e0def4f9aea96cb66c2b697793f08e2df214b9'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 23640, 20, 0.0, 0.0, NULL, 0.0, 0.0, 1.0, NULL, NULL, NULL, 30, NULL, 0.0, 0.0, 0.0, NULL, NULL, 0, 1.0, NULL, NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, 0, 0, NULL, 0.0, NULL, N'26493acf1d1fd432ebf768cd9dc1f86e079c2e1bd1b818835a5f7721f80d5e47'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 23641, 21, 0.0, 0.0, NULL, 0.0, 0.0, 1.0, NULL, NULL, NULL, 30, NULL, 0.0, 0.0, 0.0, NULL, NULL, 0, 1.0, NULL, NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, 0, 0, NULL, 0.0, NULL, N'a8403237df4d09765d7b6f2c26f7f6267c193abd99888e95516f824206847116'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 23656, 37, 0.0, 0.0, NULL, 0.0, 0.0, 1.0, NULL, NULL, NULL, 30, NULL, 0.0, 0.0, 0.0, NULL, NULL, 0, 1.0, NULL, NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, 0, 0, NULL, 0.0, NULL, N'488034dc28e4f18e2b3057ee308cf1cc875c2f8458b8dff599f35de089d96e0d'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 23660, 41, 0.0, 19.8, '2007-03-31 00:00:00.000', 17.93415, 16.23, 10.0, NULL, NULL, NULL, 36, NULL, 19.8, 0.0, 0.0, NULL, NULL, 0, 10.0, 0.0, 0.0, NULL, NULL, NULL, 0, 1, N'', NULL, 0, 0, NULL, 0.0, 0, N'8781fb4ce997e2a4b50270128a3fe76051759a5badddba25d31c3b52fd4dc33b'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 23666, 47, 0.0, 0.0, NULL, 0.0, 0.0, 1.0, NULL, NULL, NULL, 30, NULL, 0.0, 0.0, 0.0, NULL, NULL, 0, 1.0, NULL, NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, 0, 0, NULL, 0.0, NULL, N'a5dcd31b4c560a099e0dbffc25e5bc8ebacbe5bfa62d0a4e011790698a84cd13');
GO

IF OBJECT_ID('sync.CategoryMaster') IS NOT NULL DROP TABLE [sync].[CategoryMaster];
GO
CREATE TABLE [sync].[CategoryMaster] (
    [store_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NULL,
    [CategoryCode] varchar(50) NOT NULL,
    [Description] varchar(100) NULL,
    [IsActive] bit NOT NULL,
    [row_hash] varchar(64) NULL,
    CONSTRAINT [PK_sync_CategoryMaster] PRIMARY KEY ([store_id], [CategoryCode])
);
GO
INSERT INTO [sync].[CategoryMaster] ([store_id], [tenant_id], [CategoryCode], [Description], [IsActive], [row_hash]) VALUES
    (N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N' 1', N'VET', 1, N'9749410821ef8f2d51efd7f75994f766661300dd4a8b52fdb6c1392c2c8a6287');
GO

IF OBJECT_ID('sync.Products') IS NOT NULL DROP TABLE [sync].[Products];
GO
CREATE TABLE [sync].[Products] (
    [store_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NULL,
    [AllowFractions] bit NULL,
    [AllowNegativeStock] bit NULL,
    [CategoryCode] varchar(50) NULL,
    [CreatedbyUser] varchar(50) NULL,
    [CreationDate] datetime NULL,
    [DivisionCode] varchar(15) NULL,
    [ExpectedMargin] float NULL,
    [FreeQuantity] float NULL,
    [isActive] tinyint NULL,
    [ItemCost] float NULL,
    [ManufacturerCode] varchar(15) NULL,
    [Margin] float NULL,
    [MaximumStockLevel] float NULL,
    [MinimumStockLevel] float NULL,
    [ModifiedbyUser] varchar(50) NULL,
    [ModifiedDate] datetime NULL,
    [MRP] float NULL,
    [OrderDate] datetime NULL,
    [OrderTime] datetime NULL,
    [ProductCode] int NOT NULL,
    [ProductName] varchar(250) NULL,
    [ProductType] int NULL,
    [PurchasePrice] float NULL,
    [PurchaseTaxCode] int NULL,
    [PurchaseUnit] float NULL,
    [Remarks] varchar(100) NULL,
    [ReorderLevel] float NULL,
    [SalePrice] float NULL,
    [SalesTaxCode] int NULL,
    [SaleUnit] float NULL,
    [ScheduleCode] int NULL,
    [SubCategory] varchar(50) NULL,
    [SubLocation] varchar(50) NULL,
    [SupplierCode] varchar(15) NULL,
    [TaxId] int NULL,
    [TotalStock] float NULL,
    [UnitDescription] varchar(200) NULL,
    [DefaultDiscountPercentage] float NULL,
    [ProductLevelDiscount] bit NULL,
    [DiscountPerAllowInBill] float NULL,
    [ProductDiscountEligibility] bit NULL,
    [row_hash] varchar(64) NULL,
    CONSTRAINT [PK_sync_Products] PRIMARY KEY ([store_id], [ProductCode])
);
GO
INSERT INTO [sync].[Products] ([store_id], [tenant_id], [AllowFractions], [AllowNegativeStock], [CategoryCode], [CreatedbyUser], [CreationDate], [DivisionCode], [ExpectedMargin], [FreeQuantity], [isActive], [ItemCost], [ManufacturerCode], [Margin], [MaximumStockLevel], [MinimumStockLevel], [ModifiedbyUser], [ModifiedDate], [MRP], [OrderDate], [OrderTime], [ProductCode], [ProductName], [ProductType], [PurchasePrice], [PurchaseTaxCode], [PurchaseUnit], [Remarks], [ReorderLevel], [SalePrice], [SalesTaxCode], [SaleUnit], [ScheduleCode], [SubCategory], [SubLocation], [SupplierCode], [TaxId], [TotalStock], [UnitDescription], [DefaultDiscountPercentage], [ProductLevelDiscount], [DiscountPerAllowInBill], [ProductDiscountEligibility], [row_hash]) VALUES
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, N'', NULL, '2006-08-01 00:00:00.000', N'UNIVE3', NULL, 0.0, 1, 37.0, N'UNIVE3', 0.0, 0.0, 0.0, N'JANA', '2025-09-22 07:19:08.000', 45.0, NULL, NULL, 2, N'ZENIM CAPS', 1, 37.0, 36, 10.0, N'', NULL, 45.0, 36, 10.0, 0, N'', NULL, N'292', 1, 0.0, N'CAP', 3.0, 1, 10.0, NULL, N'26ea984224924770a3c9bbd4e0280e60249ef22da56888c27c9fd1123bd2556d'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, N'', NULL, '2006-08-01 00:00:00.000', N'AKUMS', NULL, 0.0, 1, 0.0, N'AKUMS', 19.19, 0.0, 0.0, N'JANA', '2025-09-22 07:19:08.000', 0.0, NULL, NULL, 3, N'DOLOROFF AP tab', 1, 0.0, 36, 10.0, N'', NULL, 0.0, 36, 10.0, 0, N'', NULL, N'119', 1, 0.0, N'TAB', 3.0, 1, 10.0, NULL, N'5a8c95c70703be3ea4a48f47483f4654fbdda2c2e456b088564901eb83a01a3c'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, N'', NULL, '2006-08-01 00:00:00.000', N'NOVAR', NULL, 0.0, 1, 81.6, N'NOVAR', 25.0, 0.0, 0.0, N'JANA', '2025-09-22 07:19:08.000', 120.25, '2015-09-03 00:00:00.000', '2015-09-03 09:47:32.000', 4, N'VOVERAN SR 75', 1, 85.89, 36, 10.0, N'', NULL, 120.25, 36, 10.0, 1, N'', N'V035', N'292', 1, 10.0, N'TAB', 10.0, 1, 15.0, 1, N'8f6ad76b7248cd7b8b1c83674e74bf29801088783c68c9456ec1b9d176ce7578'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, N'', NULL, '2006-08-01 00:00:00.000', N'TORRE1', NULL, 0.0, 1, 7.91, N'TORRE1', 21.65, 0.0, 0.0, N'JANA', '2025-09-22 07:19:08.000', 10.09, '2015-05-11 00:00:00.000', '2015-05-11 10:09:33.000', 6, N'UROFLOX 400', 1, 8.15, 36, 10.0, N'', NULL, 10.09, 36, 10.0, 1, N'', NULL, N'292', 1, 0.0, N'TAB', 10.0, 1, 18.0, NULL, N'7b95903a315acd2b4bdef33ce1813458306ff836e6273aa7d7df531ea39705c7'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, N'', NULL, '2006-08-01 00:00:00.000', N'SHA15', NULL, 0.0, 1, 41.51, N'SHA15', 20.01, 0.0, 0.0, N'JANA', '2025-09-22 07:19:08.000', 57.35, '2016-05-24 00:00:00.000', '2016-05-24 13:59:26.000', 8, N'VALPARIN 200 TAB', 1, 43.69, 36, 15.0, N'', NULL, 57.35, 36, 15.0, 1, N'', N'V002', N'292', 1, 60.0, N'TAB', 10.0, 1, 18.0, NULL, N'511124035495138190f4a21886414376c180a98400e02b706160fe631fb25b0d'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, N'', NULL, '2006-08-01 00:00:00.000', N'SUN P', NULL, 0.0, 1, 80.08, N'SUN P', 40.34, 0.0, 0.0, N'JANA', '2025-09-22 07:19:08.000', 118.0, '2016-08-05 00:00:00.000', '2016-08-05 11:16:56.000', 9, N'TROPAN 2.5', 1, 84.29, 36, 10.0, N'', NULL, 118.0, 36, 10.0, 1, N'', N'T074', N'107', 1, 20.0, N'TAB', 10.0, 1, 18.0, NULL, N'4ecde2959f1143fc917cf925b745ed853e2774827469e2d24838a222e2e73cd1'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, N'', NULL, '2006-08-01 00:00:00.000', N'KHAND', NULL, 0.0, 1, 10.38, N'KHAND', 19.98, 0.0, 0.0, N'JANA', '2025-09-22 07:19:08.000', 13.62, '2015-12-24 00:00:00.000', '2015-12-24 16:40:57.000', 10, N'VERMISOL 50MG', 1, 10.38, 36, 1.0, N'', NULL, 13.62, 36, 1.0, 0, N'', NULL, N'120', 1, 0.0, N'TAB', 3.0, 1, 10.0, NULL, N'9c638515087e8cc568400263b744238dbf060266775ca9bffc613125fe50b9ae'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, N'', NULL, '2006-08-01 00:00:00.000', N'SHA212', NULL, 0.0, 1, 54.39, N'SHA212', 25.0, 0.0, 0.0, N'VIJAYAKUMAR', '2026-06-22 00:00:00.000', 79.63, '2015-06-01 00:00:00.000', '2015-06-01 10:26:42.000', 11, N'STORVAS 10', 1, 60.67, 36, 15.0, N'', NULL, 79.63, 36, 15.0, 1, N'', N'S040', N'292', 1, 102.0, N'TAB', 10.0, 1, 15.0, NULL, N'3d44609f892dead9e3aa19e34584ed54b6c6c26e13ca1b174a4c412315312b9c'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, N'', NULL, '2006-08-01 00:00:00.000', N'SHA230', NULL, 0.0, 1, 14.69, N'SHA230', 19.98, 0.0, 0.0, N'JANA', '2025-09-22 07:19:08.000', 20.51, '2015-01-17 00:00:00.000', '2015-01-17 11:42:14.000', 13, N'SYSCAN 150', 1, 15.63, 36, 1.0, N'', NULL, 20.51, 36, 1.0, 0, N'', N'S050', N'292', 1, 10.0, N'CAP', 10.0, 1, 18.0, NULL, N'e3e5e16a481bcd3ac0e07077be8a261ae8f6c94863b7a31990b170c88fe7fa2b'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, N'', NULL, '2006-08-01 00:00:00.000', N'SUN P', NULL, 0.0, 1, 22.95, N'SUN P', 19.99, 0.0, 0.0, N'JANA', '2025-09-22 07:19:08.000', 33.82, '2014-09-12 00:00:00.000', '2014-09-12 14:06:28.000', 14, N'SIZODON 1', 1, 24.16, 36, 10.0, N'', NULL, 33.82, 36, 10.0, 1, N'', N'S019', N'107', 1, 20.0, N'TAB', 10.0, 1, 18.0, NULL, N'b1a52cebada5fdde450c3d43a6d699816ca09ca61be571e5a0882c9e3535c29d');
GO

IF OBJECT_ID('sync.ProductSaleInformation') IS NOT NULL DROP TABLE [sync].[ProductSaleInformation];
GO
CREATE TABLE [sync].[ProductSaleInformation] (
    [store_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NULL,
    [ID] bigint NOT NULL,
    [ProductCode] int NULL,
    [Quantity] float NULL,
    [TransactionDate] datetime NOT NULL,
    [SeriesTransID] int NULL,
    [TransactionValidity] int NULL,
    [DontConsiderInOrder] bit NULL,
    [Bnumber] varchar(50) NOT NULL,
    [SeriesName] char(10) NULL,
    [MRP] float NULL,
    [PurchasePrice] float NULL,
    [DiscountPercentage] float NULL,
    [LastAdjustmentDate] datetime NULL,
    [BillNumber] int NOT NULL,
    [Expirydate] datetime NULL,
    [Batchdescription] varchar(25) NULL,
    [Rate1] float NULL,
    [CostOfSales] float NULL,
    [Batchcode] int NULL,
    [Transactiontime] datetime NULL,
    [ReferenceNumber] varchar(50) NULL,
    [ReferenceDate] datetime NULL,
    [Freequantity] float NULL,
    [Rate] float NULL,
    [Itemcost] float NULL,
    [Transactionamount] float NULL,
    [Discountamount] float NULL,
    [Taxamount] float NULL,
    [Cashdiscount] real NULL,
    [Adjustmenttype] int NULL,
    [ReasonId] int NULL,
    [StockNotAffected] bit NULL,
    [Username] varchar(50) NULL,
    [Locationid] int NULL,
    [IsTaxInclusive] bit NULL,
    [IsBatchLocked] bit NULL,
    [row_hash] varchar(64) NULL,
    CONSTRAINT [PK_sync_ProductSaleInformation] PRIMARY KEY ([store_id], [ID])
);
GO
INSERT INTO [sync].[ProductSaleInformation] ([store_id], [tenant_id], [ID], [ProductCode], [Quantity], [TransactionDate], [SeriesTransID], [TransactionValidity], [DontConsiderInOrder], [Bnumber], [SeriesName], [MRP], [PurchasePrice], [DiscountPercentage], [LastAdjustmentDate], [BillNumber], [Expirydate], [Batchdescription], [Rate1], [CostOfSales], [Batchcode], [Transactiontime], [ReferenceNumber], [ReferenceDate], [Freequantity], [Rate], [Itemcost], [Transactionamount], [Discountamount], [Taxamount], [Cashdiscount], [Adjustmenttype], [ReasonId], [StockNotAffected], [Username], [Locationid], [IsTaxInclusive], [IsBatchLocked], [row_hash]) VALUES
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522355, 5872880, 2.0, '2026-01-06 00:00:00.000', 1, 0, 0, N'C01129001', N'C         ', 48.0, 8.8, 10.0, NULL, 129001, '2028-04-30 00:00:00.000', N'504', 45.0, 1.7600000000000002, 1418668, '2026-01-06 07:39:29.000', NULL, NULL, 0.0, 48.0, 8.8, 8.2286, 0.96, 0.2057, 0.0, 0, NULL, 0, N'JOY', 1, 1, 0, N'3f869a9caeb09f054985d5bc11a4188493b6e8cee4141cc560f8ddd2bb0dbcf8'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522356, 5883743, 2.0, '2026-01-06 00:00:00.000', 1, 0, 0, N'C01129001', N'C         ', 75.51, 28.95, 10.0, NULL, 129001, '2027-08-31 00:00:00.000', N'2903', 75.51, 19.3, 1422370, '2026-01-06 07:39:29.000', NULL, NULL, 0.0, 75.51, 28.95, 43.1486, 5.03, 1.0787, 0.0, 0, NULL, 0, N'JOY', 1, 1, 0, N'883cb6e7b57c9da4151f727a56c94972ca6c13d7e0a52ca29bf1916e74b928b3'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522357, 5863490, 2.0, '2026-01-06 00:00:00.000', 1, 0, 0, N'C01129001', N'C         ', 6.0, 3.62, 0.0, NULL, 129001, '2026-11-30 00:00:00.000', N'433', 6.0, 5.34, 1415012, '2026-01-06 07:39:29.000', NULL, NULL, 0.0, 6.0, 2.67, 11.4286, 0.0, 0.2857, 0.0, 0, NULL, 0, N'JOY', 1, 1, 0, N'671f04fcff621776c562024a36ad35ea050017cbe93b6b25ab8e0018cbd923c4'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522358, 5864112, 1.0, '2026-01-06 00:00:00.000', 1, 0, 0, N'C01129002', N'C         ', 146.41, 104.57, 10.0, NULL, 129002, '2026-12-31 00:00:00.000', N'A0DFY011-', 137.25, 98.3, 1422927, '2026-01-06 07:41:22.000', NULL, NULL, 0.0, 146.41, 98.3, 125.4943, 14.64, 3.1374, 0.0, 0, NULL, 0, N'JOY', 1, 1, 0, N'ab93f5a1d37e14c2a98d992da67f6d31dd36ded5aea3ad0857d7775fcbf99928'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522359, 23126, 15.0, '2026-01-06 00:00:00.000', 1, 0, 0, N'C01129003', N'C         ', 46.85, 33.46, 10.0, NULL, 129003, '2027-07-31 00:00:00.000', N'G75Y021-', 43.92, 31.45, 1420218, '2026-01-06 07:44:40.000', NULL, NULL, 0.0, 46.85, 31.45, 40.1571, 4.69, 1.0039, 0.0, 0, NULL, 0, N'JOY', 1, 1, 0, N'0ed99e5d948972561c503ea1d9414b06dda7bf2278dc7dbaaba6c9c2c7e4ce51'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522360, 5856645, 10.0, '2026-01-06 00:00:00.000', 1, 0, 0, N'C01129003', N'C         ', 62.22, 47.41, 10.0, NULL, 129003, '2027-09-30 00:00:00.000', N'E15Y013', 62.22, 44.57, 1423309, '2026-01-06 07:44:40.000', NULL, NULL, 0.0, 62.22, 44.57, 53.3314, 6.22, 1.3333, 0.0, 0, NULL, 0, N'JOY', 1, 1, 0, N'de86ed409d75658034609da2e6a7e9a8d66ef6b5ec1d9b01e84b8d3f43a6452a'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522361, 5878963, 1.0, '2026-01-06 00:00:00.000', 1, 0, 0, N'C01129003', N'C         ', 22.0, 14.59, 0.0, NULL, 129003, '2029-12-31 00:00:00.000', N'001', 22.0, 14.59, 1419210, '2026-01-06 07:44:40.000', NULL, NULL, 0.0, 22.0, 14.59, 20.9524, 0.0, 0.5238, 0.0, 0, NULL, 0, N'JOY', 1, 1, 0, N'e97ffc502c1190965f8d6a0a7d8b02ebd96b2b0b6dd1ff41ce2aea7550a2b22a'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522362, 5877333, 1.0, '2026-01-06 00:00:00.000', 1, 0, 0, N'C01129004', N'C         ', 93.0, 68.57, 5.0, NULL, 129004, '2028-10-31 00:00:00.000', N'023', 93.0, 68.57, 1419208, '2026-01-06 07:46:48.000', NULL, NULL, 0.0, 93.0, 68.57, 84.1429, 4.65, 2.1036, 0.0, 0, NULL, 0, N'JOY', 1, 1, 0, N'44d33b9cea4c8feb1b77edb08d162dbdcdaf4216d4f275909405e71e7b0d5668'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522363, 21914, 1.0, '2026-01-06 00:00:00.000', 1, 0, 0, N'C01129004', N'C         ', 105.0, 92.59, 0.0, NULL, 129004, '2026-11-30 00:00:00.000', N'A11', 105.0, 90.74, 1422106, '2026-01-06 07:46:48.000', NULL, NULL, 0.0, 105.0, 90.74, 100.0, 0.0, 2.5, 0.0, 0, NULL, 0, N'JOY', 1, 1, 0, N'357c5005becdef462745b5626a0fe81b4242bf2fe6fbb13b451e260436e945b0'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522364, 5849937, 1.0, '2026-01-06 00:00:00.000', 1, 0, 0, N'C01129004', N'C         ', 125.0, 91.32, 0.0, NULL, 129004, '2027-10-31 00:00:00.000', N'4A5', 111.23, 84.01, 1398270, '2026-01-06 07:46:48.000', NULL, NULL, 0.0, 125.0, 84.01, 119.0476, 0.0, 2.9762, 0.0, 0, NULL, 0, N'JOY', 1, 1, 0, N'88739985b3cbe59ec12fa59ed87ac0823585004a73debee892e1dd1bca9e2b95');
GO

IF OBJECT_ID('sync.ProductTrans') IS NOT NULL DROP TABLE [sync].[ProductTrans];
GO
CREATE TABLE [sync].[ProductTrans] (
    [store_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NULL,
    [ProductCode] int NOT NULL,
    [SaleQuantity] float NULL,
    [StockInHand] float NULL,
    [PurchaseQuantity] float NULL,
    [AdjustmentQuantity] float NULL,
    [LastBillDate] datetime NULL,
    [LastGrnDate] datetime NULL,
    [MonthOfStatistics] datetime NOT NULL,
    [TransferInQuantity] float NULL,
    [TransferOutQuantity] float NULL,
    [OpeningStock] float NULL,
    [OpeningStockValue] float NULL,
    [PurchaseValue] float NULL,
    [PurchaseReturnQuantity] float NULL,
    [SaleValue] float NULL,
    [SaleReturnQuantity] float NULL,
    [AdjustmentValue] float NULL,
    [StockValueAtCostPrice] float NULL,
    [StockValueAtSalePrice] float NULL,
    [CostOfSales] float NULL,
    [SaleTransactionCount] int NULL,
    [PurchaseTransactionCount] int NULL,
    [Syncid] int NULL,
    [row_hash] varchar(64) NULL,
    CONSTRAINT [PK_sync_ProductTrans] PRIMARY KEY ([store_id], [ProductCode], [MonthOfStatistics])
);
GO
INSERT INTO [sync].[ProductTrans] ([store_id], [tenant_id], [ProductCode], [SaleQuantity], [StockInHand], [PurchaseQuantity], [AdjustmentQuantity], [LastBillDate], [LastGrnDate], [MonthOfStatistics], [TransferInQuantity], [TransferOutQuantity], [OpeningStock], [OpeningStockValue], [PurchaseValue], [PurchaseReturnQuantity], [SaleValue], [SaleReturnQuantity], [AdjustmentValue], [StockValueAtCostPrice], [StockValueAtSalePrice], [CostOfSales], [SaleTransactionCount], [PurchaseTransactionCount], [Syncid], [row_hash]) VALUES
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 4, 0.0, 15.0, 0.0, 0.0, '2026-01-17 00:00:00.000', '2026-01-20 00:00:00.000', '2026-02-01 00:00:00.000', 0.0, 0.0, 15.0, 122.39999999999999, 0.0, 0.0, 0.0, 0.0, 0.0, 122.39999999999999, 169.9919, 0.0, 0, 0, NULL, N'b6f4e564880d8d6a2c66f5b6496cafc1c109e6fd5db9422c9a9bbdbfd7a344ba'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 4, 6.0, 9.0, 0.0, 0.0, '2026-03-07 00:00:00.000', '2026-01-20 00:00:00.000', '2026-03-01 00:00:00.000', 0.0, 0.0, 15.0, 122.39999999999999, 0.0, 0.0, 57.9754, 0.0, 0.0, 73.44, 100.2067, 48.96, 1, 0, 0, N'8ceecdcf153b04cefa40c5159a57d7a51652d631a5c0da5f92950f4fb7e54688'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 4, 0.0, 9.0, 0.0, 0.0, '2026-03-07 00:00:00.000', '2026-01-20 00:00:00.000', '2026-04-01 00:00:00.000', 0.0, 0.0, 9.0, 73.44, 0.0, 0.0, 0.0, 0.0, 0.0, 73.44, 100.2067, 0.0, 0, 0, NULL, N'1e21a6beaa844eae6c1de51f16e72733f6b41080b180ae0b44a503c03e8bba2f'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 4, 19.0, 10.0, 20.0, 0.0, '2026-05-24 00:00:00.000', '2026-05-26 00:00:00.000', '2026-05-01 00:00:00.000', 0.0, 0.0, 9.0, 73.44, 163.2, 0.0, 193.25740000000002, 0.0, 0.0, 81.6, 120.25, 155.04, 2, 2, 0, N'3e72b9972a87de97d3785394f6316122332efeef8bcce1f27afe5f048aa2a3f0'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 4, 0.0, 10.0, 0.0, 0.0, '2026-05-24 00:00:00.000', '2026-05-26 00:00:00.000', '2026-06-01 00:00:00.000', 0.0, 0.0, 10.0, 81.6, 0.0, 0.0, 0.0, 0.0, 0.0, 81.6, 120.25, 0.0, 0, 0, NULL, N'1f68030ed02e9196270e153020d8de2ad2d0e40367c277b14747e9afe3008fad'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 4, 0.0, 10.0, 0.0, 0.0, '2026-05-24 00:00:00.000', '2026-05-26 00:00:00.000', '2026-07-01 00:00:00.000', 0.0, 0.0, 10.0, 81.6, 0.0, 0.0, 0.0, 0.0, 0.0, 81.6, 120.25, 0.0, 0, 0, NULL, N'73745a965f212195fc1fcdbd0b461d5f49634cbbedaafc0c5fa9d29acaed48a9'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 8, 0.0, 14.0, 0.0, 0.0, '2025-12-08 00:00:00.000', '2025-09-06 00:00:00.000', '2026-02-01 00:00:00.000', 0.0, 0.0, 14.0, 38.752, 0.0, 0.0, 0.0, 0.0, 0.0, 38.752, 54.3822, 0.0, 0, 0, NULL, N'e21d12b34ee23ea2be1d36cd95ab37cccadf6d6a5c46d06aa4b94b7ffe1d1803'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 8, 2.0, 12.0, 0.0, 0.0, '2026-03-03 00:00:00.000', '2025-09-06 00:00:00.000', '2026-03-01 00:00:00.000', 0.0, 0.0, 14.0, 38.752, 0.0, 0.0, 6.992, 0.0, 0.0, 33.216, 46.6133, 5.536, 1, 0, 0, N'3be096b16dcbed4add8cbdf273efb251f111c895d43f2e0fb3f9ec32337be8dd'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 8, 0.0, 12.0, 0.0, 0.0, '2026-03-03 00:00:00.000', '2025-09-06 00:00:00.000', '2026-04-01 00:00:00.000', 0.0, 0.0, 12.0, 33.216, 0.0, 0.0, 0.0, 0.0, 0.0, 33.216, 46.6133, 0.0, 0, 0, NULL, N'92401319436d166e76980146c1cd353f67a9e9fa1af9a4a66412c751e1edc3ff'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 8, 42.0, 45.0, 75.0, 0.0, '2026-05-14 00:00:00.000', '2026-05-15 00:00:00.000', '2026-05-01 00:00:00.000', 0.0, 0.0, 12.0, 33.216, 207.53, 0.0, 146.832, 0.0, 0.0, 124.52999999999999, 183.54, 116.23599999999999, 2, 2, 0, N'fe83aa08dba04c38865b3112142f2e84f033f6ae682c9eff848273018ac38bf4');
GO

IF OBJECT_ID('sync.PurchaseTrans') IS NOT NULL DROP TABLE [sync].[PurchaseTrans];
GO
CREATE TABLE [sync].[PurchaseTrans] (
    [store_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NULL,
    [ID] int NOT NULL,
    [ProductCode] int NULL,
    [stockreceived] float NULL,
    [FreeQty] float NULL,
    [ProductDiscPercent] float NULL,
    [itemcost] float NULL,
    [purchaseprice] float NULL,
    [mrp] float NULL,
    [grndate] datetime NOT NULL,
    [InvoiceSeries] char(4) NULL,
    [Grnnumber] int NULL,
    [SaleUnit] float NULL,
    [BatchCode] int NULL,
    [TaxAmount] float NULL,
    [DiscountAmount] float NULL,
    [Margin] float NULL,
    [MarginOnCost] float NULL,
    [MarginOnSale] float NULL,
    [ManufacturerCode] varchar(15) NULL,
    [Username] varchar(50) NULL,
    [LocationId] int NULL,
    [row_hash] varchar(64) NULL,
    [SupplierCode] varchar(15) NULL,
    CONSTRAINT [PK_sync_PurchaseTrans] PRIMARY KEY ([store_id], [ID])
);
GO
INSERT INTO [sync].[PurchaseTrans] ([store_id], [tenant_id], [ID], [ProductCode], [stockreceived], [FreeQty], [ProductDiscPercent], [itemcost], [purchaseprice], [mrp], [grndate], [InvoiceSeries], [Grnnumber], [SaleUnit], [BatchCode], [TaxAmount], [DiscountAmount], [Margin], [MarginOnCost], [MarginOnSale], [ManufacturerCode], [Username], [LocationId], [row_hash], [SupplierCode]) VALUES
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779663, 5883521, 1.0, 0.0, 2.0, 456.78, 466.1, 625.0, '2024-04-27 00:00:00.000', N'IV  ', 802, 1.0, 1313049, 82.22, 9.322, 12.0, 13.64, 12.0, NULL, N'PRADEEP', 1, N'6d579cdb1f179145f54798b4426dcbf28b9fd30140d137958f51aae9d60105dc', N'109'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779664, 5870000, 2.0, 0.0, 5.0, 279.58, 294.29, 412.0, '2024-04-27 00:00:00.000', N'IV  ', 802, 15.0, 1300114, 33.55, 29.429, 20.0, 25.0, 20.0, N'BERGE', N'PRADEEP', 1, N'ed3a4788bb45cf1bd8956dfa8ff220a5e3bff37bfac9d6b3eef4ac8516cdf485', N'109'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779665, 5883982, 1.0, 0.0, 5.0, 128.25, 135.0, 189.0, '2024-04-27 00:00:00.000', N'IV  ', 802, 10.0, 1306262, 15.39, 6.75, 20.0, 25.0, 20.0, N'ALKEM', N'PRADEEP', 1, N'f555cfe807bda3d3a67f844c9d8ca5abb263b39b345e28f9433aa5a7d10b02f3', N'109'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779666, 5865185, 1.0, 0.0, 5.0, 539.09, 567.46, 837.0, '2024-04-27 00:00:00.000', N'IV  ', 802, 1.0, 1312827, 97.03, 28.373, 20.0, 25.0, 20.0, N'IPCA 1', N'PRADEEP', 1, N'0174bb04ac36c15e3e77d65e7b88ce71abce468646802b71d8df53e2fe948831', N'109'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779667, 14176, 1.0, 0.0, 0.0, 125.53, 132.14, 185.0, '2024-04-27 00:00:00.000', N'IV  ', 803, 1.0, 1313875, 15.07, 0.0, 20.0, 25.0, 20.0, N'SHA103', N'PRADEEP', 1, N'7633c32f35f9fa63deaa6571db74ec7f31e595511cc8cf92583dc7b9cd1f18e9', N'107'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779668, 5880896, 1.0, 0.0, 0.0, 205.85, 218.99, 300.0, '2024-04-27 00:00:00.000', N'IV  ', 804, 1.0, 1312811, 24.7, 0.0, 18.24, 22.31, 18.24, N'DERMA', N'PRADEEP', 1, N'1ed612a04fc0222e46a38f92ef0b6e2808d015a45fc20591106bd0643075d17c', N'SMMA'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779669, 5866811, 3.0, 0.0, 0.0, 120.86, 128.57, 180.0, '2024-04-27 00:00:00.000', N'IV  ', 804, 10.0, 1304844, 14.5, 0.0, 20.0, 25.0, 20.0, N'12345', N'PRADEEP', 1, N'7a07b3e92a95b8c08380d9a529a64d5777d604c1ef51fb93884c9841bd6d1130', N'SMMA'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779670, 5883916, 3.0, 0.0, 0.0, 126.9, 135.0, 189.0, '2024-04-27 00:00:00.000', N'IV  ', 804, 15.0, 1310154, 15.23, 0.0, 20.0, 25.0, 20.0, N'LIA', N'PRADEEP', 1, N'd90f04b430a572d5b81e359336e5499b09ab8f40711e820e0a3a6d0a7960b897', N'SMMA'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779671, 22180, 1.0, 0.0, 0.0, 151.92, 161.62, 226.27, '2024-04-27 00:00:00.000', N'IV  ', 804, 10.0, 1313876, 18.23, 0.0, 20.0, 25.0, 20.0, N'SERDI1', N'PRADEEP', 1, N'6948322297848af00e26bf0642ca700b4a80dd8cea98e5f0601a8bb715094ad7', N'SMMA'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779672, 5875467, 1.0, 0.0, 0.0, 70.17, 74.65, 104.5, '2024-04-27 00:00:00.000', N'IV  ', 805, 10.0, 1306275, 8.42, 0.0, 19.99, 24.99, 19.99, N'EAST 1', N'PRADEEP', 1, N'f1310c7eeea93f907897641ebe914d52b935d8b521b893c1355e58978fe2bb56', N'SMMA');
GO

IF OBJECT_ID('sync.SaleInformation') IS NOT NULL DROP TABLE [sync].[SaleInformation];
GO
CREATE TABLE [sync].[SaleInformation] (
    [store_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NULL,
    [BillDate] datetime NOT NULL,
    [BillNumber] int NOT NULL,
    [BNumber] varchar(50) NOT NULL,
    [BillAmount] float NULL,
    [CustomerName] varchar(120) NULL,
    [DeliverySalesRep] int NULL,
    [Billtime] datetime NULL,
    [CustomerCode] varchar(50) NULL,
    [row_hash] varchar(64) NULL,
    CONSTRAINT [PK_sync_SaleInformation] PRIMARY KEY ([store_id], [BillDate], [BNumber])
);
GO
INSERT INTO [sync].[SaleInformation] ([store_id], [tenant_id], [BillDate], [BillNumber], [BNumber], [BillAmount], [CustomerName], [DeliverySalesRep], [Billtime], [CustomerCode], [row_hash]) VALUES
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129001, N'C01129001', 66.0, N'mithun  ', 78, '2026-01-06 07:39:29.000', N'0', N'e9461a8b569bb70f251d82b4eb94d3e06c7cbde0d72433740613f77b29583186'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129002, N'C01129002', 132.0, N'r  revathy  ', 78, '2026-01-06 07:41:22.000', N'0', N'60f9563b65be47eddb83c6e14a8716a5785920d22230a908fc07d521e7f55bb7'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129003, N'C01129003', 120.0, N'ravi    ', 78, '2026-01-06 07:44:40.000', N'0', N'0e0695f7d66ce3bd463c0b463712b718cd79535e26e9fb8484d7f2ac2dfb7773'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129004, N'C01129004', 318.0, N'gopi  ', 78, '2026-01-06 07:46:48.000', N'0', N'b658657faaeeed1eeb9a6b51ad8b00084b708407f459aac73c4d7d38dc25de57'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129005, N'C01129005', 581.0, N'ravi     ', 78, '2026-01-06 07:56:18.000', N'0', N'5845e46f346d862b5b884974c28ff92fe903f7c73386ba6f5ba9843edf41696d'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129006, N'C01129006', 177.0, N'selvaraj', 78, '2026-01-06 08:08:01.000', N'0', N'3c37c4d63586bec1ec11973facdb9f207491c6cb349cd24cdb617449c5c390dd'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129007, N'C01129007', 57.0, N'priya  ', 78, '2026-01-06 08:10:52.000', N'0', N'5f356710855926f7a101f3529de5e6f9435c31fbfa650441193c2a09a57988af'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129008, N'C01129008', 127.0, N'kerthish ', 78, '2026-01-06 08:17:21.000', N'0', N'b964907f5c4017f44d5e57edaeafe62ea8eead8159a9e8a9718e5121e2459b6a'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129009, N'C01129009', 725.0, N'nithiya  ', 78, '2026-01-06 08:21:27.000', N'0', N'8e076bc8fec749a4f1b142c5f85834b34c4389b529946c912873c0ef459f072f'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129010, N'C01129010', 526.0, N'guna   ', 78, '2026-01-06 08:24:27.000', N'0', N'9482d62503571bdd3e77b6506666624cfc5804a9449f24e85a5a278d7023bcf2');
GO

IF OBJECT_ID('sync.SalesRep') IS NOT NULL DROP TABLE [sync].[SalesRep];
GO
CREATE TABLE [sync].[SalesRep] (
    [store_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NULL,
    [Salesmancode] int NOT NULL,
    [Salesmanname] varchar(30) NOT NULL,
    [row_hash] varchar(64) NULL,
    [isActive] bit NULL,
    CONSTRAINT [PK_sync_SalesRep] PRIMARY KEY ([store_id], [Salesmancode])
);
GO
INSERT INTO [sync].[SalesRep] ([store_id], [tenant_id], [Salesmancode], [Salesmanname], [row_hash], [isActive]) VALUES
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 1, N'NEW', N'27cd9ba0be075120db9cf3125cbe2496904cf6151d6267ca2ec88c661ae2e41f', 1),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 2, N'~PUNITHA', N'367b9b523c22e303181966909653743f9150dc21e9bb5a7fbe7a27a622b94be4', 0),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3, N'SALMAN', N'b340bd35a1bc39f8143b5b03aea7671d1fd8aef9e5b851dcc151494e3b7d584a', 1),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 4, N'~M.SHANKAR', N'619a4eac01f35395d4a93b510b88859672e67e01005521e836d2d246b15f26ba', 0),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 5, N'~MASTHAN ', N'c5d40ecdd3f961851f7bc336244e24d48ec18c0ecdb26787251bc2cce0e6cf21', 0),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 6, N'~ANEESH', N'369a69a9f9baaaa281283e9e7e82f4eddd4a7e58e0aa2370c92758e9354a9115', 0),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 7, N'~GOPAL', N'6d1275679b0fa4dc8d97c3cfcb19770fa83541d4f7a9d88434177a9c50c99f8f', 0),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 8, N'~PONVENTHAN', N'4a772086c43fe41aa21a7ca19e62ec5229dd80fe4a35ac6a256d4ed5c8ce5bee', 0),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 9, N'~GOKUL', N'c2357dba5108dc12309a23e2a0a58ceb2044b567237a0dcef4fa3e6f2f2e1283', 0),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 10, N'~MOHANAPRIYAN', N'c647628042870dcb26153643437602e532c6b8709eb447e7d728fe8d18b7bde7', 0);
GO

IF OBJECT_ID('sync.SupplierProductMatch') IS NOT NULL DROP TABLE [sync].[SupplierProductMatch];
GO
CREATE TABLE [sync].[SupplierProductMatch] (
    [store_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NULL,
    [SupplierCode] varchar(15) NOT NULL,
    [SupplierProductCode] varchar(50) NOT NULL,
    [SupplierProductName] varchar(250) NULL,
    [ProductCode] int NULL,
    [UserName] varchar(50) NULL,
    [LastModifiedDate] datetime NULL,
    [IsActive] bit NULL,
    [row_hash] varchar(64) NULL,
    CONSTRAINT [PK_sync_SupplierProductMatch] PRIMARY KEY ([store_id], [SupplierCode], [SupplierProductCode])
);
GO
INSERT INTO [sync].[SupplierProductMatch] ([store_id], [tenant_id], [SupplierCode], [SupplierProductCode], [SupplierProductName], [ProductCode], [UserName], [LastModifiedDate], [IsActive], [row_hash]) VALUES
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'1015', N'10003', N'RIVOTRIL 5MG TAB', 2195, NULL, NULL, NULL, N'62a305e653e7e3bb8d2549362cc873f60bd937d9ff20db29bf3a67f1b106a471'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'1015', N'10011', N'DILZEM 30MG TAB  ', 2789, NULL, NULL, NULL, N'8c2fc2a1ad7ec6eaee465ea8955f3f65d8b690147a3ea555bc11871403a3ea40'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'1015', N'10016', N'QUADRIDERM 10GM CREAM  ', 5105, NULL, NULL, NULL, N'db0c2d1a079baeb77ac5999853abef6f53c3ae1ccd7e2473f870479af061977c'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'1015', N'10024', N'SILVEREX 10GM  ', 20808, NULL, NULL, NULL, N'935dc60ae89ca5276e0585293f1018080d3ddb6b9086a79e611d803db8ebb35e'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'1015', N'10033', N'SPORIDEX REDIMEX 250MG SYRUP  ', 26106, NULL, NULL, NULL, N'9fab47b48210b2047c648c59fce26521f57248fa027718cbd0b591a411e90589'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'1015', N'10037', N'WIKORYL SY  ', 3536, NULL, NULL, NULL, N'ebafd93b0bb88e73ecde7b693ed3863c13138b1d973fc643869bbfe8b986615a'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'1015', N'10040', N'ANDIAL TAB  ', 770, NULL, NULL, NULL, N'1b007064ddba037154d92ab590eab852ef8a3c9a8a104b3c9ad83622b256b59a'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'1015', N'10044', N'FEPANIL 125MG SYRUP  ', 4785, NULL, NULL, NULL, N'dc504353b410055d0bb37a0aadbb57996756a3e3d586367b1d8eb577a75fc20f'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'1015', N'10045', N'FEPANIL 650MG TAB  ', 2577, NULL, NULL, NULL, N'e8b1e591ad48604c5fff51918f3df6cef952594ecff3a5d2a6d0ae0f9443ef6e'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'1015', N'10046', N'FEPANIL 500MG TAB  ', 6405, NULL, NULL, NULL, N'65933ce0b7dbd6a8f1621dc9880f0363ed2ab98a95659842631753a0135d3388');
GO

IF OBJECT_ID('sync.Suppliers') IS NOT NULL DROP TABLE [sync].[Suppliers];
GO
CREATE TABLE [sync].[Suppliers] (
    [store_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NULL,
    [suppliercode] varchar(15) NOT NULL,
    [suppliername] varchar(200) NOT NULL,
    [mobilenumber] varchar(50) NULL,
    [email] varchar(40) NULL,
    [isActive] bit NULL,
    [row_hash] varchar(64) NULL,
    [Abbreviation] varchar(5) NULL,
    [Address1] varchar(250) NULL,
    [Address2] varchar(250) NULL,
    [Address3] varchar(250) NULL,
    [State] varchar(50) NULL,
    [Pincode] varchar(15) NULL,
    [Tngstnumber] varchar(50) NULL,
    [GSTNumber] varchar(15) NULL,
    CONSTRAINT [PK_sync_Suppliers] PRIMARY KEY ([store_id], [suppliercode])
);
GO
INSERT INTO [sync].[Suppliers] ([store_id], [tenant_id], [suppliercode], [suppliername], [mobilenumber], [email], [isActive], [row_hash], [Abbreviation], [Address1], [Address2], [Address3], [State], [Pincode], [Tngstnumber], [GSTNumber]) VALUES
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'.', N'RAJ PHARMACEUTICALS', N'9443349355', N'', 1, N'642c3dfe9a5376bf44b7f77e3bbeb003af3759c8fdc0a9a82e49d8d92c9de281', N'', N'5/17 UMA NAGAR SARADHA COLLEG ROAD SALEM-7', N'', N'', NULL, N'636007', N'', NULL),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'001', N'S.K. AGENCY', NULL, NULL, 1, N'd85fae34f09839d418281215338abbe73aa3068af6287d54c2c6a19e3984dd26', NULL, N'', N'', N'', NULL, N'', NULL, NULL),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'006', N'SHARADHA MEDICALS (GUGAI)', NULL, NULL, 1, N'b6c6f4359a180972b674e1261c7cab159fa24efa05d9451ca99e0150b5375d4a', NULL, N'450, TRICHY MAINROAD, GUGAI, SALEM', N'', N'', NULL, N'636006', NULL, NULL),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'012', N'SHARADHA MEDICALS', N'9994477499', NULL, 1, N'56a07128a5349a13bbf7960ed234c201bcee73eda9294f7e27b2c9e79ca80bc7', NULL, N'8/C-1 OMALUR MAIN ROAD                               FOUR ROADS SALEM-9', N'', N'', NULL, N'636009', N'', NULL),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'0123', N'SRREE SENTHIL AGENCIES', N'', N'', 1, N'bb309f8e5c9dec60701ce88dd864742911870ba6f7ae63fed04d5a94f18f181e', N'', N'VASANTHA BAVAN NR, PERIYAR ST,', N'', N'', N'1', N'638001', N'', N'33ABJPC6328F1Z0'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'10', N'SRI MAHA TRADERS', N'9095520702', NULL, 1, N'9e220387065208e791e8af6c6432ed03d9d6914a2214ac21dbd4d82e799b7130', NULL, N'H.O.12/183-PERUMPARAPPU V.KARUKAMPALAYAM POST SIVAGIRI-638109', NULL, NULL, NULL, NULL, NULL, NULL),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'100', N'MADHV TRADERS', NULL, NULL, 1, N'680ad11622b53f3fbb24240bba0f95d6366270f2e6fdd5a0b5b0753c6428f6bb', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'1000', N'VISWANATHAM STORES', N'', NULL, 1, N'4cf30ff72569fa0b69bf81cf7a1d491e9997c6ee5a262479c3834d6696695aee', NULL, N'289,MAINROAD,SHEVAPET, SALEM-2.', N'', N'', NULL, N'636002', N'', NULL),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'10005', N'SRI SENTHIL STORES', N'9842956477', NULL, 1, N'74429619656ae5a96c2e2ddec2a34fc2af70d6330ef92bea0aaaf1793016ff69', NULL, N'C-3,CHOKAN KAADU, MAIN ROAD,SHEVAPET-SALEM -636002', N'', N'', NULL, N'636002', N'', NULL),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'1001', N'JAYA SHREE PHARMAA', N'9943952888', NULL, 1, N'19de8526d76fae824c8962c55f719f6f9d4ece2cf33fdd2a60a0ed2dea63d894', NULL, N'22/16A,KANDAR HOSTEL ROAD, NAMAKKAL .', N'', N'', NULL, N'', N'', NULL);
GO

IF OBJECT_ID('sync.Suppliertrans') IS NOT NULL DROP TABLE [sync].[Suppliertrans];
GO
CREATE TABLE [sync].[Suppliertrans] (
    [store_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NULL,
    [Suppliercode] varchar(15) NOT NULL,
    [MonthOfStatistics] datetime NOT NULL,
    [Transactionid] int NULL,
    [Purchasevaluetoday] float NULL,
    [Purchasevalueuptopreviousday] float NULL,
    [Purchasevalueuptopreviousmonth] float NULL,
    [Taxpaiduptopreviousmonth] float NULL,
    [Lastbill] varchar(20) NULL,
    [Openingbalance] float NULL,
    [Closingbalance] float NOT NULL,
    [Salevalue] float NULL,
    [LastGRNDate] datetime NULL,
    [PurchaseCount] int NULL,
    [UnAdjustedReturnCount] int NULL,
    [SupplierDCCount] int NULL,
    [NoOfPendingCreditDebitNote] int NULL,
    [PendingCreditDebitNoteValue] float NULL,
    [NoOfPendingCheques] int NULL,
    [NoOfPendingInvoices] int NOT NULL,
    [PendingAcknowledgementQty] float NULL,
    [PendingAcknowledgementValue] float NULL,
    [row_hash] varchar(64) NULL,
    CONSTRAINT [PK_sync_Suppliertrans] PRIMARY KEY ([store_id], [Suppliercode], [MonthOfStatistics])
);
GO
INSERT INTO [sync].[Suppliertrans] ([store_id], [tenant_id], [Suppliercode], [MonthOfStatistics], [Transactionid], [Purchasevaluetoday], [Purchasevalueuptopreviousday], [Purchasevalueuptopreviousmonth], [Taxpaiduptopreviousmonth], [Lastbill], [Openingbalance], [Closingbalance], [Salevalue], [LastGRNDate], [PurchaseCount], [UnAdjustedReturnCount], [SupplierDCCount], [NoOfPendingCreditDebitNote], [PendingCreditDebitNoteValue], [NoOfPendingCheques], [NoOfPendingInvoices], [PendingAcknowledgementQty], [PendingAcknowledgementValue], [row_hash]) VALUES
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'.', '2024-04-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, N'50081a280b0b8fdfe37738a14328d24df735145ef3d299440482709192572ce9'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'.', '2024-05-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, N'608bec6b18b0a95cbb9d5b02b542cc01e9a610148a25d0e44a0e9f7f64992507'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'.', '2024-06-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, N'e31fa6736bff1c68b7105db282d6a3430107d18cae086f0a1bf103b0e6569d40'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'.', '2024-07-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, N'7bd48f17a5fea96f0d04d3d9a970a85e16b3e818c44eb4495a4bd173c599e512'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'.', '2024-08-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, N'545734a94024199debfd8374f3bf1e422c0071aef08fad68ba82bace463b599e'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'.', '2024-09-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, N'080cc1853e4232eacd84bb2e9b656cbbdae41c20d24d2da84f60de3c691c4d05'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'.', '2024-10-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, N'12e107925b6c71a193f3dd6c1ee780935855c767d3c885239e822955ad117abb'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'.', '2024-11-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, N'4c7fd7fbf9ca246126b95fd60bcc8b2f80a95c74e742b7b49df9cbc0d9ca5aff'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'.', '2024-12-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, N'e7794434a0fc672cb0a64f56cc9517e16de4c9cb01f2834ae049118e63b39a6c'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', N'.', '2025-01-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, N'86b4e959f6c2c03f0946b8e9eb09f5a6fef11c238ade05f17899cb28365a951a');
GO

IF OBJECT_ID('sync.sync_column_mapping') IS NOT NULL DROP TABLE [sync].[sync_column_mapping];
GO
CREATE TABLE [sync].[sync_column_mapping] (
    [mapping_id] uniqueidentifier NOT NULL,
    [sync_table_id] uniqueidentifier NOT NULL,
    [table_name] varchar(128) NOT NULL,
    [column_name] varchar(128) NOT NULL,
    [data_type] varchar(100) NULL,
    [is_selected] bit NOT NULL,
    [is_pk] bit NOT NULL,
    [is_hash] bit NOT NULL,
    [is_watermark] bit NOT NULL,
    [column_order] int NOT NULL,
    [created_at] datetime NOT NULL,
    CONSTRAINT [PK_sync_sync_column_mapping] PRIMARY KEY ([mapping_id])
);
GO
INSERT INTO [sync].[sync_column_mapping] ([mapping_id], [sync_table_id], [table_name], [column_name], [data_type], [is_selected], [is_pk], [is_hash], [is_watermark], [column_order], [created_at]) VALUES
    (N'22E446D6-661F-4D07-BECF-004B491740FF', N'03419296-12CB-4D9E-88E6-1A3C3E9AB4CA', N'SalesRep', N'Salesmancode', N'int', 1, 1, 1, 0, 1, '2026-06-25 18:10:11.837'),
    (N'A59D80EE-1C0E-43D3-8D3E-007C9C46A8E2', N'D192DC62-B6C6-4346-AC57-C66C857CA22B', N'SaleInformation', N'BillNumber', N'int', 1, 0, 1, 0, 2, '2026-06-20 19:48:58.967'),
    (N'A26F1097-89B7-41AB-A861-0154FB869F05', N'AB0E2EB2-0F7C-4DB7-82C7-64D9A7C28D65', N'Suppliertrans', N'Taxpaiduptopreviousday', N'float', 0, 0, 0, 0, 8, '2026-06-25 18:13:23.160'),
    (N'D089C4ED-CC83-45FD-B3B3-02472A3FAC8D', N'37193197-252C-4D8F-AA42-12F2EF0982CE', N'PurchaseTrans', N'InvoiceSeries', N'char', 1, 0, 1, 0, 36, '2026-06-20 19:48:58.967'),
    (N'28648B74-1FC8-4339-B3D2-0249C873CA13', N'FB9F14B0-A914-460D-910E-29D867148CE4', N'Suppliers', N'suppliername', N'nvarchar', 1, 0, 1, 0, 2, '2026-06-20 19:48:58.967'),
    (N'CBF26E52-9FD6-4025-8C73-02B3920F029E', N'FB9F14B0-A914-460D-910E-29D867148CE4', N'Suppliers', N'Pincode', N'varchar', 1, 0, 0, 0, 10, '2026-06-25 18:17:45.147'),
    (N'019CCF4F-F82C-4DF3-83FD-02F7C869A12B', N'E62CE414-0247-4AB3-B03C-BCB3B30FFA99', N'ProductSaleInformation', N'SeriesTransID', N'int', 1, 0, 1, 0, 5, '2026-06-20 19:48:58.967'),
    (N'880AA278-8291-48ED-9C78-04CEFC2276ED', N'D192DC62-B6C6-4346-AC57-C66C857CA22B', N'SaleInformation', N'CustomerCode', N'varchar', 1, 0, 1, 0, 8, '2026-06-20 19:48:58.967'),
    (N'805CF9BC-9DF4-4495-BB9F-06924B2D40BF', N'57E8BE86-979C-467C-B0B2-7D83AAE14CB4', N'products', N'isActive', N'tinyint', 1, 0, 1, 0, 9, '2026-06-20 19:48:58.967'),
    (N'690EE886-A880-4AB2-8894-071969CCBD9D', N'57E8BE86-979C-467C-B0B2-7D83AAE14CB4', N'products', N'OrderDate', N'datetime', 1, 0, 0, 0, 18, '2026-06-20 19:48:58.967');
GO

IF OBJECT_ID('sync.sync_schema_catalog') IS NOT NULL DROP TABLE [sync].[sync_schema_catalog];
GO
CREATE TABLE [sync].[sync_schema_catalog] (
    [catalog_id] uniqueidentifier NOT NULL,
    [schema_name] varchar(128) NOT NULL,
    [table_name] varchar(128) NOT NULL,
    [column_name] varchar(128) NOT NULL,
    [data_type] varchar(100) NOT NULL,
    [max_length] int NULL,
    [precision_value] int NULL,
    [scale_value] int NULL,
    [is_nullable] bit NOT NULL,
    [is_identity] bit NOT NULL,
    [is_primary_key] bit NOT NULL,
    [ordinal_position] int NOT NULL,
    [first_discovered_store_id] uniqueidentifier NULL,
    [first_discovered_at] datetime NOT NULL,
    [last_discovered_at] datetime NOT NULL,
    [is_active] bit NOT NULL,
    CONSTRAINT [PK_sync_sync_schema_catalog] PRIMARY KEY ([catalog_id])
);
GO
INSERT INTO [sync].[sync_schema_catalog] ([catalog_id], [schema_name], [table_name], [column_name], [data_type], [max_length], [precision_value], [scale_value], [is_nullable], [is_identity], [is_primary_key], [ordinal_position], [first_discovered_store_id], [first_discovered_at], [last_discovered_at], [is_active]) VALUES
    (N'79B8B352-4A99-41C5-800C-0000D078F702', N'dbo', N'product130123', N'MaximumStockLevel', N'float', 8, 53, 0, 1, 0, 0, 22, N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '2026-06-23 18:56:56.443', '2026-07-04 19:42:12.987', 1),
    (N'BC8BB584-1D45-4730-A0F5-0001A89B3F49', N'dbo', N'Ins_MproformaSaleInformation', N'DeliverySalesRep', N'int', 4, 10, 0, 1, 0, 0, 79, N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-20 16:08:57.053', '2026-07-04 19:42:12.987', 1),
    (N'130FA43E-19F8-41C7-8DEA-0001C723F013', N'dbo', N'SUBMISSIONINFO', N'SenderID', N'varchar', 50, 0, 0, 1, 0, 0, 10, N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-20 16:09:11.593', '2026-07-04 19:42:12.987', 1),
    (N'A6E4BD0C-B021-473E-ADF2-000309A47CCF', N'dbo', N'BarcodePrintSettings', N'PaperLeftmargin', N'float', 8, 53, 0, 1, 0, 0, 6, N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-20 16:08:32.117', '2026-07-04 19:42:12.987', 1),
    (N'6DF74ADF-DCF3-4205-BE29-0003581D99FE', N'dbo', N'PriceRevisionDetail', N'OldRate', N'float', 8, 53, 0, 1, 0, 0, 12, N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-20 16:09:04.200', '2026-07-04 19:42:12.987', 1),
    (N'16E5E1E6-ADD5-4C3D-9EE0-0004853A36A5', N'dbo', N'WSServiceOutletConfig', N'ModifiedOn', N'datetime', 8, 23, 3, 1, 0, 0, 10, N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-20 16:09:18.190', '2026-07-04 19:42:12.987', 1),
    (N'9255E1FE-9B51-42C0-B9DD-00051953FCE0', N'dbo', N'dvw_SPendingPayments', N'TransactionTime', N'datetime', NULL, NULL, NULL, 1, 0, 0, 20, N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-20 16:08:51.667', '2026-06-20 16:31:49.960', 1),
    (N'538955CA-50D1-45D8-A2FD-0005BF04E855', N'dbo', N'suppliers_260525', N'CreatedAtStoreCode', N'int', 4, 10, 0, 1, 0, 0, 148, N'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '2026-06-23 18:56:56.443', '2026-07-04 18:15:17.733', 1),
    (N'B81D7E0C-C487-4A31-9FC9-00066B1F4427', N'dbo', N'dvw_SaleInformation_STK', N'Deliverytype', N'int', NULL, 10, 0, 1, 0, 0, 33, N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-20 16:08:50.527', '2026-06-20 16:31:49.960', 1),
    (N'24DBC477-3BFD-4975-AD87-000690689EDE', N'dbo', N'dvw_CPaymentAdjustmentforApproval', N'ReceiptDate', N'datetime', NULL, NULL, NULL, 0, 0, 0, 6, N'109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-20 16:08:41.260', '2026-06-20 16:31:49.960', 1);
GO

IF OBJECT_ID('sync.sync_table_master') IS NOT NULL DROP TABLE [sync].[sync_table_master];
GO
CREATE TABLE [sync].[sync_table_master] (
    [sync_table_id] uniqueidentifier NOT NULL,
    [table_name] varchar(128) NOT NULL,
    [is_active] bit NOT NULL,
    [sync_mode] varchar(50) NOT NULL,
    [watermark_column] varchar(128) NULL,
    [window_days] int NULL,
    [window_months] int NULL,
    [custom_where] nvarchar(1000) NULL,
    [sync_order] int NOT NULL,
    [created_at] datetime NOT NULL,
    CONSTRAINT [PK_sync_sync_table_master] PRIMARY KEY ([sync_table_id])
);
GO
INSERT INTO [sync].[sync_table_master] ([sync_table_id], [table_name], [is_active], [sync_mode], [watermark_column], [window_days], [window_months], [custom_where], [sync_order], [created_at]) VALUES
    (N'37193197-252C-4D8F-AA42-12F2EF0982CE', N'PurchaseTrans', 1, N'ROLLING_WINDOW', N'GrnDate', 800, NULL, NULL, 5, '2026-06-19 17:26:24.783'),
    (N'03419296-12CB-4D9E-88E6-1A3C3E9AB4CA', N'SalesRep', 1, N'UPSERT', NULL, NULL, NULL, NULL, 0, '2026-06-25 18:09:58.117'),
    (N'30DBE7F6-4931-4815-82EA-1A878DFC9AFE', N'CategoryMaster', 1, N'UPSERT', NULL, NULL, NULL, NULL, 0, '2026-06-25 18:19:38.467'),
    (N'FB9F14B0-A914-460D-910E-29D867148CE4', N'Suppliers', 1, N'UPSERT', NULL, NULL, NULL, NULL, 8, '2026-06-19 17:26:24.783'),
    (N'AB0E2EB2-0F7C-4DB7-82C7-64D9A7C28D65', N'Suppliertrans', 1, N'UPSERT', NULL, NULL, NULL, NULL, 0, '2026-06-25 18:12:35.080'),
    (N'57E8BE86-979C-467C-B0B2-7D83AAE14CB4', N'Products', 1, N'UPSERT', NULL, NULL, NULL, NULL, 1, '2026-06-19 17:26:24.783'),
    (N'17E0FF14-65E2-4326-A0AA-86D26A6F0CCF', N'SupplierProductMatch', 1, N'UPSERT', NULL, NULL, NULL, NULL, 7, '2026-06-19 17:26:24.783'),
    (N'7B5CAD8D-0F3B-49E2-BB83-B2C5D741AB75', N'ProductTrans', 1, N'ROLLING_WINDOW', N'MonthOfStatistics', 180, NULL, NULL, 6, '2026-06-19 17:26:24.783'),
    (N'329BA141-4E4D-4534-A323-BBD97A0F97E9', N'Batches', 1, N'UPSERT', NULL, NULL, NULL, NULL, 2, '2026-06-19 17:26:24.783'),
    (N'E62CE414-0247-4AB3-B03C-BCB3B30FFA99', N'ProductSaleInformation', 1, N'ROLLING_WINDOW', N'TransactionDate', 180, NULL, NULL, 4, '2026-06-19 17:26:24.783');
GO

IF OBJECT_ID('sync.sync_table_progress') IS NOT NULL DROP TABLE [sync].[sync_table_progress];
GO
CREATE TABLE [sync].[sync_table_progress] (
    [execution_id] uniqueidentifier NOT NULL,
    [table_name] varchar(128) NOT NULL,
    [sync_type] varchar(40) NULL,
    [total_rows] bigint NOT NULL,
    [rows_sent] bigint NOT NULL,
    [chunks_sent] int NOT NULL,
    [updated_at] datetime NOT NULL,
    CONSTRAINT [PK_sync_sync_table_progress] PRIMARY KEY ([execution_id], [table_name])
);
GO
INSERT INTO [sync].[sync_table_progress] ([execution_id], [table_name], [sync_type], [total_rows], [rows_sent], [chunks_sent], [updated_at]) VALUES
    (N'F563978B-63D9-4B9F-B8DF-03846492585E', N'Products', N'UPSERT', 9, 9, 1, '2026-07-04 20:08:47.367'),
    (N'C90BE353-01C3-42FC-BC74-0668A3779DB3', N'Batches', N'UPSERT', 200681, 200681, 201, '2026-06-25 16:22:30.537'),
    (N'C90BE353-01C3-42FC-BC74-0668A3779DB3', N'Products', N'UPSERT', 51328, 51328, 52, '2026-06-25 16:19:52.473'),
    (N'C90BE353-01C3-42FC-BC74-0668A3779DB3', N'ProductSaleInformation', N'ROLLING_WINDOW', 55418, 55418, 56, '2026-06-25 16:23:31.807'),
    (N'C90BE353-01C3-42FC-BC74-0668A3779DB3', N'ProductTrans', N'ROLLING_WINDOW', 24122, 24122, 25, '2026-06-25 16:24:01.390'),
    (N'C90BE353-01C3-42FC-BC74-0668A3779DB3', N'PurchaseTrans', N'ROLLING_WINDOW', 17433, 17433, 18, '2026-06-25 16:23:43.827'),
    (N'C90BE353-01C3-42FC-BC74-0668A3779DB3', N'SaleInformation', N'ROLLING_WINDOW', 26289, 26289, 27, '2026-06-25 16:22:45.360'),
    (N'C90BE353-01C3-42FC-BC74-0668A3779DB3', N'SupplierProductMatch', N'UPSERT', 79127, 79127, 80, '2026-06-25 16:24:40.210'),
    (N'C90BE353-01C3-42FC-BC74-0668A3779DB3', N'Suppliers', N'UPSERT', 749, 749, 1, '2026-06-25 16:24:41.080'),
    (N'C90BE353-01C3-42FC-BC74-0668A3779DB3', N'TAX', N'UPSERT', 20, 20, 1, '2026-06-25 16:24:41.640');
GO

IF OBJECT_ID('sync.TAX') IS NOT NULL DROP TABLE [sync].[TAX];
GO
CREATE TABLE [sync].[TAX] (
    [store_id] uniqueidentifier NOT NULL,
    [tenant_id] uniqueidentifier NULL,
    [taxcode] int NOT NULL,
    [description] varchar(50) NULL,
    [row_hash] varchar(64) NULL,
    CONSTRAINT [PK_sync_TAX] PRIMARY KEY ([store_id], [taxcode])
);
GO
INSERT INTO [sync].[TAX] ([store_id], [tenant_id], [taxcode], [description], [row_hash]) VALUES
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 28, N'4%', N'c9b427d87c72943a1cadbf6237ac78cbae0328e3fdecc973e2623f0a2b5d75ce'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 29, N'12.5%', N'e028e5d30b40c5cf3726f4456c8eeebc0d416ae55fe730305c97afdbf21a23e1'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 30, N'NOTAX', N'5e7566271859fb3b526aeabce737bfefcf00bf6fb508ef1c078073bbe1cede15'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 31, N'14.50%', N'8d0f0e649c2ded32531e3549234e59abad5d6f24587f9536e1622825b17f120c'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 32, N'5.00%', N'c001676199e34b2b4ad8846cf8ec599b7aa652928b68d90f4877f8f4778def61'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 33, N'IT14.50%', N'a0a7bf126e362782e70bdf53c7e0d7a896a8c4c839e654cf4213740ae461af35'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 34, N'IT5.00%', N'2f7df5a37e33026e997bf64d2c40a506f717c0fe2cfa17c023003606ebc9ed17'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 35, N'Exempted', N'849edd2161c81ca6181e1105979b69e4f5c5dd3039b9fa2817234e945269128f'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 36, N'5 % GST', N'b59e249dd454d8feabe62a4b05e840ec4dfc3eaa9a0df9d6579e6338031eb40a'),
    (N'D55F8A0D-C230-44EA-BF56-02F143B948BD', N'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 37, N'12 % GST', N'78293f4d49951ccfdd6d0f79715614ac8f175a88477bf3b361f82c16225e5afa');
GO

IF OBJECT_ID('sync.V2_TEST') IS NOT NULL DROP TABLE [sync].[V2_TEST];
GO
CREATE TABLE [sync].[V2_TEST] (
    [id] int NOT NULL,
    [name] varchar(50) NULL,
    [mrp] decimal(10,2) NULL,
    CONSTRAINT [PK_sync_V2_TEST] PRIMARY KEY ([id])
);
GO

/* Done. 61 tables, 369 rows total. */
