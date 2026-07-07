SET NAMES utf8mb4;
SET SESSION sql_mode = CONCAT(@@sql_mode, ',NO_BACKSLASH_ESCAPES,NO_AUTO_VALUE_ON_ZERO');
CREATE DATABASE IF NOT EXISTS nexora_platform;
CREATE DATABASE IF NOT EXISTS nexora_procurement;
CREATE DATABASE IF NOT EXISTS nexora_sync;
USE nexora_platform;

DROP TABLE IF EXISTS nexora_platform.`agent_heartbeat_log`;
CREATE TABLE nexora_platform.`agent_heartbeat_log` (
    `id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `store_id` char(36) NOT NULL,
    `heartbeat_time` datetime(3) NOT NULL,
    `ip_address` varchar(100) NULL,
    `agent_version` varchar(50) NULL,
    PRIMARY KEY (`id`)
);
INSERT INTO nexora_platform.`agent_heartbeat_log` (`id`, `tenant_id`, `store_id`, `heartbeat_time`, `ip_address`, `agent_version`) VALUES
    (1, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 17:59:58.093', '10.0.0.5', '1.0.0'),
    (2, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 17:59:58.170', NULL, NULL),
    (3, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 18:08:40.560', '192.168.10.80', '1.0.0'),
    (4, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 18:08:40.590', '192.168.10.80', '1.0.0'),
    (5, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 18:09:10.603', '192.168.10.80', '1.0.0'),
    (6, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 18:09:40.720', '192.168.10.80', '1.0.0'),
    (7, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 18:10:10.817', '192.168.10.80', '1.0.0'),
    (8, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 18:10:40.897', '192.168.10.80', '1.0.0'),
    (9, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 18:11:10.913', '192.168.10.80', '1.0.0'),
    (10, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-21 18:11:40.973', '192.168.10.80', '1.0.0');
DROP TABLE IF EXISTS nexora_platform.`agent_version_catalog`;
CREATE TABLE nexora_platform.`agent_version_catalog` (
    `version_id` bigint AUTO_INCREMENT NOT NULL,
    `version_no` varchar(50) NOT NULL,
    `release_date` datetime(3) NOT NULL,
    `release_notes` longtext NULL,
    `is_active` tinyint(1) NOT NULL,
    PRIMARY KEY (`version_id`)
);
DROP TABLE IF EXISTS nexora_platform.`global_audit_log`;
CREATE TABLE nexora_platform.`global_audit_log` (
    `audit_id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NULL,
    `store_id` char(36) NULL,
    `user_id` char(36) NULL,
    `module_name` varchar(100) NULL,
    `action_name` varchar(100) NULL,
    `old_value` longtext NULL,
    `new_value` longtext NULL,
    `created_at` datetime(3) NOT NULL,
    PRIMARY KEY (`audit_id`)
);
DROP TABLE IF EXISTS nexora_platform.`modules`;
CREATE TABLE nexora_platform.`modules` (
    `module_id` char(36) NOT NULL,
    `module_code` varchar(50) NOT NULL,
    `module_name` varchar(100) NOT NULL,
    `description` varchar(500) NULL,
    `is_active` tinyint(1) NOT NULL,
    PRIMARY KEY (`module_id`)
);
INSERT INTO nexora_platform.`modules` (`module_id`, `module_code`, `module_name`, `description`, `is_active`) VALUES
    ('F8D3A6DD-F47B-41C0-ACE7-0105218481A8', 'PROCUREMENT', 'Procurement', 'Procurement Management', 1),
    ('B655CFCB-9271-453F-945A-0234DC04F93E', 'ROLES', 'Roles', 'Role Management', 1),
    ('41A344EB-3A24-4C53-849D-0E423D80C55F', 'SYNC_MONITOR', 'Sync Monitor', 'Synchronization Monitoring', 1),
    ('4A303000-33EE-4C38-BE61-11A1606A7163', 'SETTINGS', 'Settings', 'Platform Settings', 1),
    ('210843D0-8875-4F24-9619-1A9FE316695B', 'MODULES', 'Modules', 'Module Management', 1),
    ('27A99D55-6799-41C4-A9A2-1D66427236D9', 'PRODUCT_MAPPING', 'Product Mapping', 'Cross-store product mapping engine', 1),
    ('B059C357-0390-4CBA-A13B-460320A7EFBB', 'SUPPLIER', 'Supplier', 'Supplier Management', 1),
    ('C7E67895-DD4C-4155-A23E-5458DE1FDF0A', 'SYNC_JOBS', 'Sync Jobs', 'Synchronization Jobs', 1),
    ('482B4EE8-5D10-4DF4-B04B-6BF5988EE993', 'SYNC', 'Sync', 'Store Synchronization', 1),
    ('F7122D0E-5EF0-4835-938A-7BFE89DE8C32', 'USERS', 'Users', 'User Management', 1);
DROP TABLE IF EXISTS nexora_platform.`platform_settings`;
CREATE TABLE nexora_platform.`platform_settings` (
    `setting_id` bigint AUTO_INCREMENT NOT NULL,
    `setting_key` varchar(100) NOT NULL,
    `setting_value` longtext NULL,
    `description` varchar(500) NULL,
    `is_active` tinyint(1) NULL,
    PRIMARY KEY (`setting_id`)
);
INSERT INTO nexora_platform.`platform_settings` (`setting_id`, `setting_key`, `setting_value`, `description`, `is_active`) VALUES
    (1, 'THEME', 'DARK', 'Default Application Theme', 1),
    (2, 'PASSWORD_EXPIRY_DAYS', '90', 'Password Expiry Policy', 1),
    (3, 'SESSION_TIMEOUT', '30', 'Session Timeout In Minutes', 1);
DROP TABLE IF EXISTS nexora_platform.`product_mapping`;
CREATE TABLE nexora_platform.`product_mapping` (
    `mapping_id` char(36) NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `run_id` char(36) NOT NULL,
    `source_store_id` char(36) NOT NULL,
    `source_product_code` varchar(50) NOT NULL,
    `source_product_name` varchar(400) NOT NULL,
    `source_normalized_name` varchar(400) NULL,
    `target_store_id` char(36) NOT NULL,
    `target_product_code` varchar(50) NULL,
    `target_product_name` varchar(400) NULL,
    `match_method` varchar(20) NULL,
    `match_phase` int NULL,
    `confidence` decimal(5,2) NOT NULL,
    `status` varchar(20) NOT NULL,
    `brand` varchar(200) NULL,
    `strength` varchar(50) NULL,
    `unit` varchar(20) NULL,
    `dosage_form` varchar(30) NULL,
    `pack_size` varchar(30) NULL,
    `mrp` decimal(18,2) NULL,
    `created_at` datetime(3) NOT NULL,
    `created_by` char(36) NULL,
    `updated_at` datetime(3) NULL,
    `updated_by` char(36) NULL,
    `is_deleted` tinyint(1) NOT NULL,
    `deleted_at` datetime(3) NULL,
    `deleted_by` char(36) NULL,
    PRIMARY KEY (`mapping_id`)
);
INSERT INTO nexora_platform.`product_mapping` (`mapping_id`, `tenant_id`, `run_id`, `source_store_id`, `source_product_code`, `source_product_name`, `source_normalized_name`, `target_store_id`, `target_product_code`, `target_product_name`, `match_method`, `match_phase`, `confidence`, `status`, `brand`, `strength`, `unit`, `dosage_form`, `pack_size`, `mrp`, `created_at`, `created_by`, `updated_at`, `updated_by`, `is_deleted`, `deleted_at`, `deleted_by`) VALUES
    ('AB7860EE-8556-4191-85DA-000121A1FBD3', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'DF82C426-7929-4C99-BC25-C2C3C8133D53', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '5857082', 'CAPTAR 40MG', 'CAPTAR40MG', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '5893948', 'CAPTAR TAB', 'SUPPLIER', 1, 100.00, 'AUTO', 'CAPTAR', '40', 'MG', NULL, NULL, 77.90, '2026-07-05 13:34:21.157', NULL, NULL, NULL, 0, NULL, NULL),
    ('D58AE5CF-C4F8-4804-A216-0002521FE939', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'E6E1FCC6-D06A-4BA9-A211-397C7C68EFB0', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', '5873904', 'RHEZA ASP 75MG CAPS 10''S', 'RHEZAASP75MGCAPS10S', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', NULL, NULL, NULL, 7, 0.00, 'PENDING', 'RHEZA ASP', '75', 'MG', 'CAP', '10', 53.50, '2026-07-05 13:10:35.630', NULL, NULL, NULL, 1, '2026-07-05 13:15:14.310', NULL),
    ('43B37EA3-40CC-42B6-8F83-00027C6B9F4B', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'DF82C426-7929-4C99-BC25-C2C3C8133D53', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '5889345', 'ASWINI HIRAN STRONG OIL', 'ASWINIHIRANSTRONGOIL', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '5883278', 'ASWINI HAND SANITIZER 50ML', 'FUZZY', 7, 42.83, 'PENDING', 'ASWINI HIRAN STRONG OIL', NULL, NULL, NULL, NULL, 180.00, '2026-07-05 13:34:23.660', NULL, NULL, NULL, 0, NULL, NULL),
    ('1D582931-0AF0-4A14-A9F2-000330BBBA7C', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'A882A66E-9B8C-4CF6-84CD-5B0F679BE4ED', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', '19939', 'BIOCET*TAB', 'BIOCETTAB', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '5850740', 'BIOCAINE  TAB', 'FUZZY', 7, 62.70, 'PENDING', 'BIOCET', NULL, NULL, 'TAB', NULL, 25.00, '2026-07-05 13:15:16.410', NULL, NULL, NULL, 0, NULL, NULL),
    ('96B5AF43-5774-42DB-A114-0003E22FA5F2', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'A882A66E-9B8C-4CF6-84CD-5B0F679BE4ED', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', '5869871', 'MYLAMIN PLUS INJ 2ML', 'MYLAMINPLUSINJ2ML', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '5887817', 'MYLAMIN GOLD   CAP', 'FUZZY', 7, 39.79, 'PENDING', 'MYLAMIN PLUS', '2', 'ML', 'INJ', NULL, 25.30, '2026-07-05 13:15:16.737', NULL, NULL, NULL, 0, NULL, NULL),
    ('2D1058C0-0C7C-4680-B04D-00051566137F', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'A882A66E-9B8C-4CF6-84CD-5B0F679BE4ED', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', '13501', 'ARJIT LINIMENT 30ML', 'ARJITLINIMENT30ML', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '5881766', 'ARJIT CAP', 'FUZZY', 7, 32.98, 'PENDING', 'ARJIT LINIMENT', '30', 'ML', NULL, NULL, 57.00, '2026-07-05 13:15:16.370', NULL, NULL, NULL, 0, NULL, NULL),
    ('5207DADD-CCC9-43C0-A932-00059CF25BF7', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'E6E1FCC6-D06A-4BA9-A211-397C7C68EFB0', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', '5857905', 'CAROL SACHET', 'CAROLSACHET', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '5885923', 'CARODYL 100MG  TAB [VET]', 'FUZZY', 7, 43.41, 'PENDING', 'CAROL', NULL, NULL, 'SACHET', NULL, 30.00, '2026-07-05 13:10:34.887', NULL, NULL, NULL, 1, '2026-07-05 13:15:14.310', NULL),
    ('A3071B26-A8FC-452D-87E9-0005EC8A6D9B', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'DF82C426-7929-4C99-BC25-C2C3C8133D53', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '5884128', 'TELMIDUCE CL', 'TELMIDUCECL', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '5886906', 'TELMIDUCE CL  TAB', 'STRUCTURED', 4, 96.00, 'AUTO', 'TELMIDUCE CL', NULL, NULL, NULL, NULL, 100.00, '2026-07-05 13:34:22.620', NULL, NULL, NULL, 0, NULL, NULL),
    ('981262B8-198A-4254-ABEE-0006DCD2A9C3', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'E6E1FCC6-D06A-4BA9-A211-397C7C68EFB0', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', '571', 'DAFLON 500', 'DAFLON500', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '571', 'DAFLON 500', 'SUPPLIER', 1, 100.00, 'AUTO', 'DAFLON', '500', NULL, NULL, NULL, 188.73, '2026-07-05 13:10:30.300', NULL, NULL, NULL, 0, NULL, NULL),
    ('87AFB502-7A10-4354-A5FF-0006F9CB5CDB', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'E6E1FCC6-D06A-4BA9-A211-397C7C68EFB0', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', '5864088', 'ALKASTON-B6 ORAL SUL 200ML', 'ALKASTONB6ORALSUL200ML', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '5864088', 'ALKASTON B6 SYP 200ML', 'SUPPLIER', 1, 100.00, 'AUTO', 'ALKASTON B', '6', NULL, NULL, NULL, 252.20, '2026-07-05 13:10:32.993', NULL, NULL, NULL, 0, NULL, NULL);
DROP TABLE IF EXISTS nexora_platform.`product_mapping_audit`;
CREATE TABLE nexora_platform.`product_mapping_audit` (
    `audit_id` char(36) NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `mapping_id` char(36) NULL,
    `run_id` char(36) NULL,
    `action` varchar(20) NOT NULL,
    `old_status` varchar(20) NULL,
    `new_status` varchar(20) NULL,
    `actor_user_id` char(36) NULL,
    `detail` varchar(1000) NULL,
    `created_at` datetime(3) NOT NULL,
    PRIMARY KEY (`audit_id`)
);
INSERT INTO nexora_platform.`product_mapping_audit` (`audit_id`, `tenant_id`, `mapping_id`, `run_id`, `action`, `old_status`, `new_status`, `actor_user_id`, `detail`, `created_at`) VALUES
    ('57952EA5-B036-49A7-80CF-0000D4054E9C', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'B257DA8B-93BE-474C-BEDD-C67C65CDC5B1', 'A882A66E-9B8C-4CF6-84CD-5B0F679BE4ED', 'RUN', NULL, 'PENDING', NULL, 'no-match @ 0.0', '2026-07-05 13:15:22.450'),
    ('2B587C31-9EDE-48EF-BBE4-0000FC004DC3', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'EB7F0325-4E9D-4512-A6F8-17D3D6720366', 'A882A66E-9B8C-4CF6-84CD-5B0F679BE4ED', 'RUN', NULL, 'PENDING', NULL, 'FUZZY @ 56.11', '2026-07-05 13:15:22.540'),
    ('190D7D6D-DA51-40C2-AA5A-0000FD0E03A4', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'E31CE24A-6518-4E37-A39F-ECE9303361C4', 'A882A66E-9B8C-4CF6-84CD-5B0F679BE4ED', 'RUN', NULL, 'PENDING', NULL, 'no-match @ 0.0', '2026-07-05 13:15:22.747'),
    ('63D2D2BF-996A-4F52-8F0B-000143990409', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '945E7E11-A4BE-488F-9F02-C8D939F2BCB1', 'E6E1FCC6-D06A-4BA9-A211-397C7C68EFB0', 'RUN', NULL, 'PENDING', NULL, 'no-match @ 0.0', '2026-07-05 13:10:44.507'),
    ('5E82FEE3-BBF7-4575-A933-0001B494831A', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '64D0CB56-6780-4B03-BFA9-8E59FAE1723C', 'E6E1FCC6-D06A-4BA9-A211-397C7C68EFB0', 'AUTO_MATCH', NULL, 'AUTO', NULL, 'EXACT @ 99.0', '2026-07-05 13:10:43.747'),
    ('EB6C8B27-D045-422F-835A-0001F8D022B6', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '7A94FAA6-84AF-493D-AD30-921093809A87', 'E6E1FCC6-D06A-4BA9-A211-397C7C68EFB0', 'AUTO_MATCH', NULL, 'AUTO', NULL, 'EXACT @ 99.0', '2026-07-05 13:10:43.810'),
    ('2951657C-5139-4B38-8CF3-0001FE8A742D', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '8BF1AC92-EDC2-42D0-9342-D779EF88F6A3', 'E6E1FCC6-D06A-4BA9-A211-397C7C68EFB0', 'AUTO_MATCH', NULL, 'AUTO', NULL, 'EXACT @ 99.0', '2026-07-05 13:10:43.703'),
    ('35F41AE4-4736-4DD4-9E3C-00036BC7C73E', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2BEDE559-83A2-47B5-8976-448AC1425F37', 'DF82C426-7929-4C99-BC25-C2C3C8133D53', 'AUTO_MATCH', NULL, 'AUTO', NULL, 'STRUCTURED @ 96.0', '2026-07-05 13:34:27.760'),
    ('F0632A04-7839-4E05-BBBC-000378DA051E', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'E4507C13-6517-4379-B47F-2BBAB6D28B6D', 'A882A66E-9B8C-4CF6-84CD-5B0F679BE4ED', 'RUN', NULL, 'PENDING', NULL, 'FUZZY @ 45.22', '2026-07-05 13:15:23.480'),
    ('952A104A-1ABA-4FCC-B84B-0004E9F4089D', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '9D57A50B-FF7F-4DD5-ACCB-4DA0EA6CC410', 'DF82C426-7929-4C99-BC25-C2C3C8133D53', 'AUTO_MATCH', NULL, 'AUTO', NULL, 'SUPPLIER @ 100.0', '2026-07-05 13:34:27.230');
DROP TABLE IF EXISTS nexora_platform.`product_mapping_candidate`;
CREATE TABLE nexora_platform.`product_mapping_candidate` (
    `candidate_id` char(36) NOT NULL,
    `mapping_id` char(36) NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `target_product_code` varchar(50) NOT NULL,
    `target_product_name` varchar(400) NOT NULL,
    `target_normalized_name` varchar(400) NULL,
    `name_score` decimal(5,2) NOT NULL,
    `brand_score` decimal(5,2) NOT NULL,
    `strength_score` decimal(5,2) NOT NULL,
    `form_score` decimal(5,2) NOT NULL,
    `mrp_score` decimal(5,2) NOT NULL,
    `total_score` decimal(5,2) NOT NULL,
    `brand` varchar(200) NULL,
    `strength` varchar(50) NULL,
    `dosage_form` varchar(30) NULL,
    `mrp` decimal(18,2) NULL,
    `reason` varchar(500) NULL,
    `created_at` datetime(3) NOT NULL,
    PRIMARY KEY (`candidate_id`)
);
INSERT INTO nexora_platform.`product_mapping_candidate` (`candidate_id`, `mapping_id`, `tenant_id`, `target_product_code`, `target_product_name`, `target_normalized_name`, `name_score`, `brand_score`, `strength_score`, `form_score`, `mrp_score`, `total_score`, `brand`, `strength`, `dosage_form`, `mrp`, `reason`, `created_at`) VALUES
    ('30D5363D-4E62-41DD-B632-0001021C3C84', 'E5660F9D-41ED-4D64-BFA0-2FA7545FC7EC', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '5882793', 'LUVLAP FEEDING BOT [NATURA FLO] 250ML', 'LUVLAPFEEDINGBOTNATURAFLO250ML', 32.59, 20.00, 0.00, 0.00, 3.33, 55.92, 'LUVLAP FEEDING BOT NATURA FLO', '250', NULL, 210.00, 'name 33, brand 20, mrp 3.3', '2026-07-05 13:15:21.487'),
    ('F1BB1891-B8D6-4AB2-B0B4-000113DE899B', '740FE183-B30B-4FC9-8F01-870B9424E43D', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '5891255', 'GLIPACURE M 50/500MG  TAB', 'GLIPACUREM50500MGTAB', 15.00, 13.16, 0.00, 0.00, 4.57, 32.73, 'GLIPACURE M', '50', 'TAB', 197.15, 'name 15, brand 13, mrp 4.6', '2026-07-05 13:34:26.020'),
    ('B968ED97-5459-4E0A-AF27-0001956C1643', 'F7B39B35-0EAD-45B2-B293-ADFE32E4E514', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '5894378', 'PROVISACC DIAMOND POW 500GM [VET]', 'PROVISACCDIAMONDPOW500GMVET', 18.46, 14.71, 0.00, 0.00, 0.17, 33.34, 'PROVISACC DIAMOND POW', '500', NULL, 520.00, 'name 18, brand 15, mrp 0.2', '2026-07-05 13:15:20.350'),
    ('6797AF7E-B7D7-4604-8776-0002E13B72C5', 'DED42E59-5AFA-46E2-AA0C-365D15555973', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '5877935', 'TRAPALIN TAB', 'TRAPALINTAB', 30.48, 16.67, 0.00, 10.00, 1.79, 58.94, 'TRAPALIN', NULL, 'TAB', 47.50, 'name 30, brand 17, form match, mrp 1.8', '2026-07-05 13:15:19.677'),
    ('5D4C7F46-5B14-47CD-91AC-00038882900C', 'E292166D-993E-4BC6-92F5-F06A44FE8550', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '5876955', 'NERVINCE-M TAB', 'NERVINCEMTAB', 28.00, 13.89, 0.00, 0.00, 4.93, 46.82, 'NERVINCE M', NULL, 'TAB', 142.00, 'name 28, brand 14, mrp 4.9', '2026-07-05 13:15:20.167'),
    ('0214B02E-E5AF-4CA8-856E-0003AF986126', '63D0DB0B-EA05-4077-A5D3-2269313A4CF8', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '5883812', 'HAPPYHEEL CREAM 50GM', 'HAPPYHEELCREAM50GM', 16.00, 10.53, 0.00, 0.00, 2.17, 28.70, 'HAPPYHEEL', '50', 'CREAM', 450.00, 'name 16, brand 11, mrp 2.2', '2026-07-05 13:15:20.340'),
    ('30ECC56F-838C-4B30-8432-0003C618006F', '2AF5550E-AC87-4432-A74C-BFFCA9A434A1', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '5881511', 'ALKOF C SYP 120ML', 'ALKOFCSYP120ML', 26.67, 20.00, 0.00, 10.00, 4.06, 60.73, 'ALKOF C', '120', 'SYP', 105.00, 'name 27, brand 20, form match, mrp 4.1', '2026-07-05 13:34:25.577'),
    ('6AD8D701-122C-4E84-9DDE-000510D00DF8', 'AAA787D0-6F8C-4EC5-BBD3-54695FC90F8B', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '5891724', 'LOZIVATE MF LOTION  30ML', 'LOZIVATEMFLOTION30ML', 15.14, 13.16, 0.00, 0.00, 4.42, 32.72, 'LOZIVATE MF', '30', 'LOTION', 159.00, 'name 15, brand 13, mrp 4.4', '2026-07-05 13:15:21.263'),
    ('0696D91B-C02C-4E3B-A577-000752BF729D', '78E73FAC-FADC-4321-8207-7797C522B9FD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '5884230', 'NILAVEMBU KUDINEER 50GM (AVIS)', 'NILAVEMBUKUDINEER50GMAVIS', 33.33, 25.00, 0.00, 0.00, 1.01, 59.34, 'NILAVEMBU KUDINEER', '50', NULL, 82.00, 'name 33, brand 25, mrp 1.0', '2026-07-05 13:15:20.657'),
    ('057FAFB0-E036-4F2F-96B9-000A303EA99A', '51C3B046-71DA-4E48-B3A9-D356382D454B', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '5873179', 'KNEE CAP (M) VISSCO', 'KNEECAPMVISSCO', 30.00, 19.12, 0.00, 0.00, 1.38, 50.50, 'KNEE M VISSCO', NULL, 'CAP', 425.00, 'name 30, brand 19, mrp 1.4', '2026-07-05 13:15:20.683');
DROP TABLE IF EXISTS nexora_platform.`product_normalization_dictionary`;
CREATE TABLE nexora_platform.`product_normalization_dictionary` (
    `entry_id` char(36) NOT NULL,
    `tenant_id` char(36) NULL,
    `term` varchar(50) NOT NULL,
    `canonical` varchar(50) NULL,
    `kind` varchar(20) NOT NULL,
    `is_active` tinyint(1) NOT NULL,
    `created_at` datetime(3) NOT NULL,
    `created_by` char(36) NULL,
    `updated_at` datetime(3) NULL,
    `updated_by` char(36) NULL,
    PRIMARY KEY (`entry_id`)
);
INSERT INTO nexora_platform.`product_normalization_dictionary` (`entry_id`, `tenant_id`, `term`, `canonical`, `kind`, `is_active`, `created_at`, `created_by`, `updated_at`, `updated_by`) VALUES
    ('AB6E8A0C-1602-4B2B-A9BF-073A879B0E5F', NULL, 'SOLN', 'SOLN', 'DOSAGE_FORM', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    ('F13315A8-9A91-4037-BBF3-0C6F40352A9D', NULL, 'MG/ML', 'MG/ML', 'UNIT', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    ('9FA2F927-66B1-4106-AEEB-0D29F45DD328', NULL, 'CREAM', 'CREAM', 'DOSAGE_FORM', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    ('9BC09E25-D4F8-4D72-9D06-0E46871522AD', NULL, 'IU', 'IU', 'UNIT', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    ('C7FDEFE4-BD67-47B1-AD45-130F3059CBE7', NULL, 'OINTMENT', 'OINT', 'DOSAGE_FORM', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    ('AF697A46-1509-4A67-8C5F-1CE4ED426B6E', NULL, 'TABLET', 'TAB', 'DOSAGE_FORM', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    ('4005822C-FE30-474D-A3AA-204C83FE9DDE', NULL, 'LOTION', 'LOTION', 'DOSAGE_FORM', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    ('A083F9C9-938C-4617-9A27-22D03CBFDD99', NULL, 'CAPSULES', 'CAP', 'DOSAGE_FORM', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    ('69ADFD36-C9EA-4351-A38C-30C5446E3F48', NULL, 'SYRUP', 'SYP', 'DOSAGE_FORM', 1, '2026-07-05 13:06:41.000', NULL, NULL, NULL),
    ('A2514E3A-F4E5-495A-B417-4E12AE848100', NULL, 'CAP', 'CAP', 'DOSAGE_FORM', 1, '2026-07-05 13:06:41.000', NULL, '2026-07-05 17:37:42.700', NULL);
DROP TABLE IF EXISTS nexora_platform.`role_module_access`;
CREATE TABLE nexora_platform.`role_module_access` (
    `id` bigint AUTO_INCREMENT NOT NULL,
    `role_id` char(36) NOT NULL,
    `module_id` char(36) NOT NULL,
    `can_view` tinyint(1) NULL,
    `can_create` tinyint(1) NULL,
    `can_edit` tinyint(1) NULL,
    `can_delete` tinyint(1) NULL,
    `can_export` tinyint(1) NULL,
    `is_active` tinyint(1) NULL,
    PRIMARY KEY (`id`)
);
INSERT INTO nexora_platform.`role_module_access` (`id`, `role_id`, `module_id`, `can_view`, `can_create`, `can_edit`, `can_delete`, `can_export`, `is_active`) VALUES
    (1, '85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', 'F8D3A6DD-F47B-41C0-ACE7-0105218481A8', 1, 1, 1, 1, 1, 1),
    (2, '85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', 'B655CFCB-9271-453F-945A-0234DC04F93E', 1, 1, 1, 1, 1, 1),
    (3, '85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', '41A344EB-3A24-4C53-849D-0E423D80C55F', 1, 1, 1, 1, 1, 1),
    (4, '85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', '4A303000-33EE-4C38-BE61-11A1606A7163', 1, 1, 1, 1, 1, 1),
    (5, '85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', '210843D0-8875-4F24-9619-1A9FE316695B', 1, 1, 1, 1, 1, 1),
    (6, '85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', 'B059C357-0390-4CBA-A13B-460320A7EFBB', 1, 1, 1, 1, 1, 1),
    (7, '85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', 'C7E67895-DD4C-4155-A23E-5458DE1FDF0A', 1, 1, 1, 1, 1, 1),
    (8, '85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', '482B4EE8-5D10-4DF4-B04B-6BF5988EE993', 1, 1, 1, 1, 1, 1),
    (9, '85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', 'F7122D0E-5EF0-4835-938A-7BFE89DE8C32', 1, 1, 1, 1, 1, 1),
    (10, '85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', 'B747540E-459A-4697-8E14-7EF12F1492D9', 1, 1, 1, 1, 1, 1);
DROP TABLE IF EXISTS nexora_platform.`roles`;
CREATE TABLE nexora_platform.`roles` (
    `role_id` char(36) NOT NULL,
    `role_name` varchar(50) NOT NULL,
    `description` varchar(500) NULL,
    `is_active` tinyint(1) NOT NULL,
    PRIMARY KEY (`role_id`)
);
INSERT INTO nexora_platform.`roles` (`role_id`, `role_name`, `description`, `is_active`) VALUES
    ('32D8CF99-3347-4F88-AD48-02341A793E0E', 'STORE_ADMIN', 'Store Administration', 1),
    ('71FD12E9-118B-47AB-BE57-126E9C0BB53F', 'TENANT_ADMIN', 'Tenant Control', 1),
    ('491C7D1F-AE97-4503-83A9-3929735145F9', 'Manager', 'Store Manager', 1),
    ('FE004FB5-5473-4FA0-90D9-76221BA662D8', 'SuperAdmin', 'Platform Super Administrator', 1),
    ('9E4B686B-5793-4614-83E5-96A9D18E7ADF', 'STORE_USER', 'Standard User', 1),
    ('85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', 'SUPER_ADMIN', 'Platform Control', 1),
    ('C79BE7A1-DECE-49BE-B24F-A4278FC6BCA7', 'STORE_MANAGER', 'Store Operations', 1),
    ('D45CFFB6-CA97-4ADB-A218-B2CF3493BC81', 'Admin', 'Tenant Administrator', 1),
    ('F6DAB5F8-F7ED-4F73-9F28-B911DC2805C3', 'User', 'Standard User', 1),
    ('6F10C367-4613-4A66-BDFE-BB71D388C9C4', 'SYNC_OPERATOR', 'Sync Monitoring', 1);
DROP TABLE IF EXISTS nexora_platform.`store_agent_registry`;
CREATE TABLE nexora_platform.`store_agent_registry` (
    `agent_id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `store_id` char(36) NOT NULL,
    `agent_version` varchar(50) NULL,
    `connection_type` varchar(50) NULL,
    `installed_at` datetime(3) NULL,
    `last_heartbeat` datetime(3) NULL,
    `connection_status` varchar(50) NULL,
    `is_active` tinyint(1) NOT NULL,
    PRIMARY KEY (`agent_id`)
);
INSERT INTO nexora_platform.`store_agent_registry` (`agent_id`, `tenant_id`, `store_id`, `agent_version`, `connection_type`, `installed_at`, `last_heartbeat`, `connection_status`, `is_active`) VALUES
    (1, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '1.0.0', 'LAN', '2026-06-21 17:59:58.077', '2026-07-06 20:01:31.563', 'ONLINE', 1),
    (2, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '1.0.0', 'LAN', '2026-06-23 18:31:28.650', '2026-07-06 20:01:40.643', 'ONLINE', 1),
    (3, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', '1.0.0', 'LAN', '2026-06-23 19:30:03.960', '2026-07-06 20:01:35.047', 'ONLINE', 1),
    (4, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '3019101A-24A6-4045-AB7E-964046383EA2', '1.0.0', 'LAN', '2026-06-23 19:31:53.853', '2026-07-06 20:01:33.503', 'ONLINE', 1),
    (5, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', '1.0.0', 'LAN', '2026-06-23 19:33:13.323', '2026-07-06 20:01:33.497', 'ONLINE', 1);
DROP TABLE IF EXISTS nexora_platform.`store_connection_test_log`;
CREATE TABLE nexora_platform.`store_connection_test_log` (
    `id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `store_id` char(36) NOT NULL,
    `server_name` varchar(500) NULL,
    `database_name` varchar(200) NULL,
    `test_status` varchar(50) NOT NULL,
    `test_message` longtext NULL,
    `tested_by` char(36) NULL,
    `tested_at` datetime(3) NOT NULL,
    PRIMARY KEY (`id`)
);
DROP TABLE IF EXISTS nexora_platform.`store_onboarding_log`;
CREATE TABLE nexora_platform.`store_onboarding_log` (
    `onboarding_id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `store_id` char(36) NULL,
    `onboarding_status` varchar(50) NOT NULL,
    `started_by` char(36) NOT NULL,
    `started_at` datetime(3) NOT NULL,
    `completed_at` datetime(3) NULL,
    `remarks` longtext NULL,
    PRIMARY KEY (`onboarding_id`)
);
DROP TABLE IF EXISTS nexora_platform.`store_sync_settings`;
CREATE TABLE nexora_platform.`store_sync_settings` (
    `id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `store_id` char(36) NOT NULL,
    `sync_enabled` tinyint(1) NOT NULL,
    `initial_sync_type` varchar(20) NOT NULL,
    `schedule_enabled` tinyint(1) NOT NULL,
    `created_at` datetime(3) NOT NULL,
    PRIMARY KEY (`id`)
);
DROP TABLE IF EXISTS nexora_platform.`stores`;
CREATE TABLE nexora_platform.`stores` (
    `store_id` char(36) NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `store_code` varchar(50) NOT NULL,
    `store_name` varchar(200) NOT NULL,
    `server_name` varchar(500) NULL,
    `database_name` varchar(200) NULL,
    `username` varchar(200) NULL,
    `password_encrypted` longblob NULL,
    `connection_type` varchar(50) NULL,
    `branch_codes` longtext NULL,
    `last_sync_time` datetime(3) NULL,
    `last_sync_status` varchar(50) NULL,
    `last_seen` datetime(3) NULL,
    `connection_status` varchar(50) NULL,
    `heartbeat_ip` varchar(100) NULL,
    `is_active` tinyint(1) NOT NULL,
    `created_at` datetime(3) NOT NULL,
    `updated_at` datetime(3) NULL,
    `gst_number` varchar(100) NULL,
    `drug_license_no` varchar(100) NULL,
    `address1` varchar(500) NULL,
    `address2` varchar(500) NULL,
    `city` varchar(100) NULL,
    `state` varchar(100) NULL,
    `country` varchar(100) NULL,
    `pincode` varchar(20) NULL,
    `contact_person` varchar(100) NULL,
    `contact_mobile` varchar(50) NULL,
    `contact_email` varchar(200) NULL,
    `store_abbreviation` varchar(20) NULL,
    `agent_version` varchar(50) NULL,
    `last_heartbeat` datetime(3) NULL,
    `agent_installed_at` datetime(3) NULL,
    `store_order` int NOT NULL,
    `agent_install_path` varchar(500) NULL,
    `agent_hostname` varchar(255) NULL,
    `agent_registered_at` datetime(3) NULL,
    PRIMARY KEY (`store_id`)
);
INSERT INTO nexora_platform.`stores` (`store_id`, `tenant_id`, `store_code`, `store_name`, `server_name`, `database_name`, `username`, `password_encrypted`, `connection_type`, `branch_codes`, `last_sync_time`, `last_sync_status`, `last_seen`, `connection_status`, `heartbeat_ip`, `is_active`, `created_at`, `updated_at`, `gst_number`, `drug_license_no`, `address1`, `address2`, `city`, `state`, `country`, `pincode`, `contact_person`, `contact_mobile`, `contact_email`, `store_abbreviation`, `agent_version`, `last_heartbeat`, `agent_installed_at`, `store_order`, `agent_install_path`, `agent_hostname`, `agent_registered_at`) VALUES
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'NMS', 'Nathan Medicals S', 'SERVER-S\SQLEXPRESS', 'Rshopaid', 'sa', 0x67414141414142714e5632324a4e564378674536436e6d52385f73754e4d4b73486f317a3573365f4f747773426970686e6739765a6e6d41634e35554a503445625f724b6e516f6764517250315731716a595736784d49725a556f3365326e5a67773d3d, 'LAN', '1000135,1001286,1001379,1000668,1001374,1001263', NULL, NULL, NULL, NULL, NULL, 1, '2026-06-18 19:29:17.853', '2026-06-23 19:56:26.870', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'NMS', NULL, NULL, NULL, 5, 'D:\NexoraStoreAgent', 'SERVER-S', '2026-07-04 19:18:50.223'),
    ('DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'NMW', 'Nathan Medicals C[B]', 'DESKTOP-745PMO0\SQLEXPRESS', 'Nathanw', 'sa', 0x67414141414142714e5632324a4e564378674536436e6d52385f73754e4d4b73486f317a3573365f4f747773426970686e6739765a6e6d41634e35554a503445625f724b6e516f6764517250315731716a595736784d49725a556f3365326e5a67773d3d, 'LAN', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-06-18 19:29:17.850', '2026-06-23 19:56:40.990', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'NMW', NULL, NULL, NULL, 1, 'D:\NexoraStoreAgent', 'DESKTOP-745PMO0', '2026-07-05 13:27:26.493'),
    ('109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'NMA', 'Nathan Medicals A', 'MSERVER-PC\SQLEXPRESS', 'RShopaidLive', 'sa', 0x67414141414142714e5632324a4e564378674536436e6d52385f73754e4d4b73486f317a3573365f4f747773426970686e6739765a6e6d41634e35554a503445625f724b6e516f6764517250315731716a595736784d49725a556f3365326e5a67773d3d, 'LAN', '1000621,1000460,1000973,1000608,1001186,1001187,1001188', NULL, NULL, NULL, NULL, NULL, 1, '2026-06-18 19:29:17.863', '2026-06-25 19:04:23.597', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'NMA', NULL, NULL, NULL, 3, 'D:\NexoraStoreAgent', 'MSERVER-PC', '2026-07-04 17:55:12.363'),
    ('FCBE8B35-B1A1-463E-80C6-73161CDC8F32', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'NMC', 'Nathan Medicals C', 'DESKTOP-LOCNRSU\SQLEXPRESS', 'Rshopaid', 'sa', 0x67414141414142714e5632324a4e564378674536436e6d52385f73754e4d4b73486f317a3573365f4f747773426970686e6739765a6e6d41634e35554a503445625f724b6e516f6764517250315731716a595736784d49725a556f3365326e5a67773d3d, 'LAN', '1002700,1002701,1002702,1002699,1000996,1001118', NULL, NULL, NULL, NULL, NULL, 1, '2026-06-18 19:29:17.860', '2026-06-23 19:55:49.317', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'NMC', NULL, NULL, NULL, 2, 'D:\NexoraStoreAgent', 'CLIENT-3', '2026-07-06 16:46:59.320'),
    ('3019101A-24A6-4045-AB7E-964046383EA2', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'NMG', 'Nathan Medicals G', 'KSERVER-PC\SQLEXPRESS', 'Shopaid', 'sa', 0x67414141414142714e5632324a4e564378674536436e6d52385f73754e4d4b73486f317a3573365f4f747773426970686e6739765a6e6d41634e35554a503445625f724b6e516f6764517250315731716a595736784d49725a556f3365326e5a67773d3d, 'LAN', '721,720,437,745', NULL, NULL, NULL, NULL, NULL, 1, '2026-06-18 19:29:17.860', '2026-06-23 19:56:04.320', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'NMG', NULL, NULL, NULL, 4, 'D:\NexoraStoreAgent', 'NODE5-PC', '2026-07-06 16:46:53.393');
DROP TABLE IF EXISTS nexora_platform.`sync_approval_workflow`;
CREATE TABLE nexora_platform.`sync_approval_workflow` (
    `workflow_id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `workflow_name` varchar(100) NOT NULL,
    `approval_required` tinyint(1) NOT NULL,
    `approver_role` varchar(50) NOT NULL,
    `is_active` tinyint(1) NOT NULL,
    PRIMARY KEY (`workflow_id`)
);
DROP TABLE IF EXISTS nexora_platform.`sync_chunk_execution`;
CREATE TABLE nexora_platform.`sync_chunk_execution` (
    `chunk_execution_id` bigint AUTO_INCREMENT NOT NULL,
    `execution_id` char(36) NOT NULL,
    `table_name` varchar(200) NOT NULL,
    `chunk_no` int NOT NULL,
    `chunk_status` varchar(50) NOT NULL,
    `rows_processed` bigint NOT NULL,
    `retry_count` int NOT NULL,
    `started_at` datetime(3) NULL,
    `completed_at` datetime(3) NULL,
    `error_message` longtext NULL,
    PRIMARY KEY (`chunk_execution_id`)
);
INSERT INTO nexora_platform.`sync_chunk_execution` (`chunk_execution_id`, `execution_id`, `table_name`, `chunk_no`, `chunk_status`, `rows_processed`, `retry_count`, `started_at`, `completed_at`, `error_message`) VALUES
    (1, '465FE679-034E-48AF-A50E-337C8D602F1F', 'RT_TEST', 1, 'ACK', 2, 0, '2026-06-21 16:59:25.437', '2026-06-21 16:59:25.557', NULL),
    (3, '146EF276-2790-4E37-9763-0E69530D5093', 'Products', 1, 'FAILED', 0, 0, '2026-06-21 17:05:12.423', '2026-06-21 17:05:12.423', '(''42S02'', "[42S02] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]Invalid object name ''sync.Products''. (208) (SQLExecDirectW)")'),
    (5, '76A884ED-29A8-48C2-B136-BFE688E6DF55', 'Products', 1, 'FAILED', 0, 0, '2026-06-21 17:18:58.883', '2026-06-21 17:18:58.883', '(''22007'', ''[22007] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]Conversion failed when converting date and/or time from character string. (241) (SQLExecute)'')'),
    (7, '09FADD89-CE50-4C2D-A134-453927E4152B', 'Products', 1, 'FAILED', 0, 0, '2026-06-21 17:35:18.903', '2026-06-21 17:35:18.903', '(''22007'', ''[22007] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]Conversion failed when converting date and/or time from character string. (241) (SQLExecute)'')'),
    (9, '2D7C605C-CDC4-40E6-9C48-41D518B86C38', 'Products', 1, 'FAILED', 0, 0, '2026-06-21 17:41:08.067', '2026-06-21 17:41:08.067', '(''22007'', ''[22007] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]Conversion failed when converting date and/or time from character string. (241) (SQLExecute)'')'),
    (11, '911D8644-7F53-4E16-9C1F-466E6E61CE7E', 'Products', 1, 'FAILED', 0, 0, '2026-06-21 17:44:22.407', '2026-06-21 17:44:22.407', '(''22007'', ''[22007] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]Conversion failed when converting date and/or time from character string. (241) (SQLExecDirectW)'')'),
    (13, 'AC1C4587-C9FF-4821-9FAA-A88AFC13245A', 'Products', 1, 'FAILED', 0, 0, '2026-06-21 17:45:58.733', '2026-06-21 17:45:58.733', '(''22007'', ''[22007] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]Conversion failed when converting date and/or time from character string. (241) (SQLExecute)'')'),
    (14, 'B125A83B-F112-40DA-95D5-05CCF1D0FC3B', 'Products', 1, 'MERGED', 2, 0, '2026-06-21 17:59:58.230', '2026-06-21 17:59:58.363', NULL),
    (15, '0790AA21-12C5-43E8-A16C-4329A9EAAC59', 'Products', 1, 'ACK', 1000, 0, '2026-06-21 18:07:03.263', '2026-06-21 18:07:03.647', NULL),
    (16, '0790AA21-12C5-43E8-A16C-4329A9EAAC59', 'Products', 2, 'ACK', 1000, 0, '2026-06-21 18:07:03.700', '2026-06-21 18:07:04.067', NULL);
DROP TABLE IF EXISTS nexora_platform.`sync_chunk_rules`;
CREATE TABLE nexora_platform.`sync_chunk_rules` (
    `rule_id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `chunk_size` int NOT NULL,
    `parallel_chunks` int NOT NULL,
    `is_active` tinyint(1) NOT NULL,
    PRIMARY KEY (`rule_id`)
);
DROP TABLE IF EXISTS nexora_platform.`sync_configuration`;
CREATE TABLE nexora_platform.`sync_configuration` (
    `config_id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `config_name` varchar(100) NOT NULL,
    `is_active` tinyint(1) NOT NULL,
    `created_at` datetime(3) NOT NULL,
    `created_by` char(36) NULL,
    `updated_at` datetime(3) NULL,
    `updated_by` char(36) NULL,
    PRIMARY KEY (`config_id`)
);
DROP TABLE IF EXISTS nexora_platform.`sync_dashboard_snapshot`;
CREATE TABLE nexora_platform.`sync_dashboard_snapshot` (
    `snapshot_id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `total_stores` int NOT NULL,
    `online_stores` int NOT NULL,
    `offline_stores` int NOT NULL,
    `running_syncs` int NOT NULL,
    `failed_syncs` int NOT NULL,
    `pending_approvals` int NOT NULL,
    `today_sync_count` int NOT NULL,
    `data_processed_today` bigint NOT NULL,
    `snapshot_time` datetime(3) NOT NULL,
    PRIMARY KEY (`snapshot_id`)
);
DROP TABLE IF EXISTS nexora_platform.`sync_execution`;
CREATE TABLE nexora_platform.`sync_execution` (
    `execution_id` char(36) NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `store_id` char(36) NOT NULL,
    `execution_type` varchar(50) NOT NULL,
    `sync_mode` varchar(50) NOT NULL,
    `execution_status` varchar(50) NOT NULL,
    `started_at` datetime(3) NOT NULL,
    `completed_at` datetime(3) NULL,
    `total_tables` int NOT NULL,
    `completed_tables` int NOT NULL,
    `failed_tables` int NOT NULL,
    `initiated_by` char(36) NULL,
    `created_by` char(36) NULL,
    PRIMARY KEY (`execution_id`)
);
INSERT INTO nexora_platform.`sync_execution` (`execution_id`, `tenant_id`, `store_id`, `execution_type`, `sync_mode`, `execution_status`, `started_at`, `completed_at`, `total_tables`, `completed_tables`, `failed_tables`, `initiated_by`, `created_by`) VALUES
    ('15B0D63F-7B90-44C1-9229-01AD327EB5AC', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', 'FULL', 'FULL', 'COMPLETED', '2026-06-23 19:34:45.913', '2026-06-23 19:35:18.950', 9, 0, 0, NULL, NULL),
    ('F563978B-63D9-4B9F-B8DF-03846492585E', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', 'FULL', 'FULL', 'COMPLETED', '2026-07-04 20:08:29.220', '2026-07-04 20:09:19.973', 0, 0, 0, NULL, NULL),
    ('BDDCEC91-0844-4F6D-8095-040F00B24CCC', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', 'FULL', 'FULL', 'COMPLETED', '2026-06-23 19:23:02.187', '2026-06-23 19:24:32.157', 0, 0, 0, NULL, NULL),
    ('B125A83B-F112-40DA-95D5-05CCF1D0FC3B', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'FULL', 'FULL', 'FAILED', '2026-06-21 17:59:58.217', '2026-06-21 18:16:17.000', 0, 0, 0, NULL, NULL),
    ('C90BE353-01C3-42FC-BC74-0668A3779DB3', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', 'FULL', 'FULL', 'COMPLETED', '2026-06-23 19:34:57.000', '2026-06-25 16:24:42.070', 9, 0, 0, NULL, NULL),
    ('16268982-48F7-49B5-8736-0686165E785D', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', 'FULL', 'FULL', 'FAILED', '2026-06-25 19:02:28.570', '2026-06-25 19:03:21.667', 0, 0, 0, NULL, NULL),
    ('FE4CD7A6-6CBA-4752-A0E8-07211DFFF859', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', 'FULL', 'FULL', 'COMPLETED', '2026-07-05 20:38:35.423', '2026-07-05 20:39:07.327', 0, 0, 0, NULL, NULL),
    ('D677CC7F-33C1-4CC6-8799-082C38CCB8EA', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', 'FULL', 'FULL', 'COMPLETED', '2026-07-04 19:38:11.463', '2026-07-04 19:39:17.433', 0, 0, 0, NULL, NULL),
    ('2AD143AE-0AD8-44F8-AC4F-08E9C92480F7', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'FULL', 'FULL', 'CANCELLED', '2026-06-23 11:40:40.030', '2026-06-23 15:58:20.573', 9, 0, 0, NULL, NULL),
    ('A50DB41D-2C32-4563-9F0A-0A72443D0D58', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', 'FULL', 'FULL', 'COMPLETED', '2026-06-26 12:10:44.870', '2026-06-26 12:12:04.873', 0, 0, 0, NULL, NULL);
DROP TABLE IF EXISTS nexora_platform.`sync_execution_audit`;
CREATE TABLE nexora_platform.`sync_execution_audit` (
    `audit_id` bigint AUTO_INCREMENT NOT NULL,
    `execution_id` char(36) NOT NULL,
    `action_name` varchar(200) NOT NULL,
    `action_time` datetime(3) NOT NULL,
    `message` longtext NULL,
    PRIMARY KEY (`audit_id`)
);
INSERT INTO nexora_platform.`sync_execution_audit` (`audit_id`, `execution_id`, `action_name`, `action_time`, `message`) VALUES
    (1, '465FE679-034E-48AF-A50E-337C8D602F1F', 'CREATED', '2026-06-21 16:59:25.267', 'Task created'),
    (2, '465FE679-034E-48AF-A50E-337C8D602F1F', 'RUNNING', '2026-06-21 16:59:25.370', 'Task started'),
    (3, '465FE679-034E-48AF-A50E-337C8D602F1F', 'CHUNK_MERGED', '2026-06-21 16:59:25.537', 'RT_TEST chunk 1 rows 2'),
    (4, '465FE679-034E-48AF-A50E-337C8D602F1F', 'COMPLETED', '2026-06-21 16:59:25.610', 'Task completed'),
    (5, '146EF276-2790-4E37-9763-0E69530D5093', 'RUNNING', '2026-06-21 17:05:10.290', 'Task started'),
    (6, '146EF276-2790-4E37-9763-0E69530D5093', 'FAILED', '2026-06-21 17:05:12.457', '500 Server Error: Internal Server Error for url: http://127.0.0.1:8000/api/sync/chunks/upload'),
    (7, '76A884ED-29A8-48C2-B136-BFE688E6DF55', 'CREATED', '2026-06-21 17:18:36.200', 'Task created'),
    (8, '76A884ED-29A8-48C2-B136-BFE688E6DF55', 'RUNNING', '2026-06-21 17:18:56.607', 'Task started'),
    (9, '76A884ED-29A8-48C2-B136-BFE688E6DF55', 'FAILED', '2026-06-21 17:18:58.940', '500 Server Error: Internal Server Error for url: http://127.0.0.1:8000/api/sync/chunks/upload'),
    (10, '09FADD89-CE50-4C2D-A134-453927E4152B', 'CREATED', '2026-06-21 17:19:40.190', 'Task created');
DROP TABLE IF EXISTS nexora_platform.`sync_execution_details`;
CREATE TABLE nexora_platform.`sync_execution_details` (
    `detail_id` bigint AUTO_INCREMENT NOT NULL,
    `sync_id` bigint NULL,
    `tenant_id` char(36) NOT NULL,
    `store_id` char(36) NOT NULL,
    `table_name` varchar(200) NOT NULL,
    `chunk_no` int NOT NULL,
    `chunk_size` int NOT NULL,
    `rows_processed` bigint NOT NULL,
    `rows_failed` bigint NOT NULL,
    `started_at` datetime(3) NULL,
    `completed_at` datetime(3) NULL,
    `duration_seconds` int NULL,
    `status` varchar(50) NOT NULL,
    `error_message` longtext NULL,
    `created_at` datetime(3) NOT NULL,
    `execution_id` char(36) NULL,
    `sync_type` varchar(40) NULL,
    `rows_examined` bigint NULL,
    `rows_changed` bigint NULL,
    `rows_uploaded` bigint NULL,
    `rows_inserted` bigint NULL,
    `rows_updated` bigint NULL,
    `rows_skipped` bigint NULL,
    `source_total` bigint NULL,
    PRIMARY KEY (`detail_id`)
);
INSERT INTO nexora_platform.`sync_execution_details` (`detail_id`, `sync_id`, `tenant_id`, `store_id`, `table_name`, `chunk_no`, `chunk_size`, `rows_processed`, `rows_failed`, `started_at`, `completed_at`, `duration_seconds`, `status`, `error_message`, `created_at`, `execution_id`, `sync_type`, `rows_examined`, `rows_changed`, `rows_uploaded`, `rows_inserted`, `rows_updated`, `rows_skipped`, `source_total`) VALUES
    (4, NULL, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'Products', 0, 0, 54204, 0, '2026-06-21 20:11:53.863', '2026-06-21 20:12:17.227', NULL, 'RUNNING', NULL, '2026-06-21 20:11:53.863', '87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 54204, 0, 54204, NULL, NULL),
    (5, NULL, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'Batches', 0, 0, 287552, 0, '2026-06-21 20:12:27.123', '2026-06-21 20:14:11.773', NULL, 'RUNNING', NULL, '2026-06-21 20:12:27.123', '87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 287552, 0, 287552, NULL, NULL),
    (6, NULL, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'SaleInformation', 0, 0, 21043, 0, '2026-06-21 20:14:12.457', '2026-06-21 20:14:15.857', NULL, 'RUNNING', NULL, '2026-06-21 20:14:12.457', '87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 21043, 13, 21030, NULL, NULL),
    (7, NULL, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'ProductSaleInformation', 0, 0, 43793, 0, '2026-06-21 20:14:18.660', '2026-06-21 20:14:37.447', NULL, 'RUNNING', NULL, '2026-06-21 20:14:18.660', '87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 43793, 26, 43767, NULL, NULL),
    (8, NULL, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'PurchaseTrans', 0, 0, 15943, 0, '2026-06-21 20:14:38.330', '2026-06-21 20:14:42.257', NULL, 'RUNNING', NULL, '2026-06-21 20:14:38.330', '87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 15943, 0, 15943, NULL, NULL),
    (9, NULL, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'ProductTrans', 0, 0, 31247, 0, '2026-06-21 20:14:43.537', '2026-06-21 20:14:52.487', NULL, 'RUNNING', NULL, '2026-06-21 20:14:43.537', '87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 31247, 0, 31247, NULL, NULL),
    (10, NULL, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'SupplierProductMatch', 0, 0, 83026, 0, '2026-06-21 20:14:53.417', '2026-06-21 20:15:09.037', NULL, 'RUNNING', NULL, '2026-06-21 20:14:53.417', '87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 83026, 0, 83026, NULL, NULL),
    (11, NULL, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'Suppliers', 0, 0, 970, 0, '2026-06-21 20:15:09.290', NULL, NULL, 'RUNNING', NULL, '2026-06-21 20:15:09.290', '87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 970, 0, 970, NULL, NULL),
    (12, NULL, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'TAX', 0, 0, 20, 0, '2026-06-21 20:15:09.417', NULL, NULL, 'RUNNING', NULL, '2026-06-21 20:15:09.417', '87544FC4-872E-4000-B11F-0B3B2E69644F', NULL, NULL, NULL, 20, 0, 20, NULL, NULL),
    (10011, NULL, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'Products', 0, 0, 54206, 0, '2026-06-22 19:10:57.287', '2026-06-22 19:11:27.220', NULL, 'RUNNING', NULL, '2026-06-22 19:10:57.287', 'F026EC67-6929-46B2-AB9C-2195006F2D27', 'UPSERT', 54206, 54206, 54206, 54206, 0, 0, 54206);
DROP TABLE IF EXISTS nexora_platform.`sync_execution_history`;
CREATE TABLE nexora_platform.`sync_execution_history` (
    `sync_id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `store_id` char(36) NOT NULL,
    `sync_mode` varchar(50) NOT NULL,
    `sync_type` varchar(50) NULL,
    `started_at` datetime(3) NOT NULL,
    `completed_at` datetime(3) NULL,
    `duration_seconds` int NULL,
    `total_rows` bigint NOT NULL,
    `processed_rows` bigint NOT NULL,
    `failed_rows` bigint NOT NULL,
    `status` varchar(50) NOT NULL,
    `triggered_by` char(36) NULL,
    `error_message` longtext NULL,
    `created_at` datetime(3) NOT NULL,
    PRIMARY KEY (`sync_id`)
);
DROP TABLE IF EXISTS nexora_platform.`sync_execution_lock`;
CREATE TABLE nexora_platform.`sync_execution_lock` (
    `lock_id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `store_id` char(36) NOT NULL,
    `table_name` varchar(200) NOT NULL,
    `lock_acquired_at` datetime(3) NOT NULL,
    `lock_expires_at` datetime(3) NOT NULL,
    `lock_status` varchar(50) NOT NULL,
    `acquired_by` char(36) NULL,
    `sync_id` char(36) NULL,
    PRIMARY KEY (`lock_id`)
);
DROP TABLE IF EXISTS nexora_platform.`sync_manual_trigger`;
CREATE TABLE nexora_platform.`sync_manual_trigger` (
    `trigger_id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `store_id` char(36) NOT NULL,
    `trigger_type` varchar(50) NOT NULL,
    `requested_by` char(36) NOT NULL,
    `requested_at` datetime(3) NOT NULL,
    `approval_status` varchar(50) NOT NULL,
    `approved_by` char(36) NULL,
    `approved_at` datetime(3) NULL,
    PRIMARY KEY (`trigger_id`)
);
DROP TABLE IF EXISTS nexora_platform.`sync_refresh_cycles`;
CREATE TABLE nexora_platform.`sync_refresh_cycles` (
    `cycle_id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `cycle_name` varchar(100) NOT NULL,
    `refresh_type` varchar(50) NOT NULL,
    `refresh_interval_minutes` int NOT NULL,
    `is_active` tinyint(1) NOT NULL,
    PRIMARY KEY (`cycle_id`)
);
DROP TABLE IF EXISTS nexora_platform.`sync_retry_rules`;
CREATE TABLE nexora_platform.`sync_retry_rules` (
    `rule_id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `max_retry_count` int NOT NULL,
    `retry_interval_minutes` int NOT NULL,
    `is_active` tinyint(1) NOT NULL,
    PRIMARY KEY (`rule_id`)
);
DROP TABLE IF EXISTS nexora_platform.`sync_schedule`;
CREATE TABLE nexora_platform.`sync_schedule` (
    `schedule_id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `schedule_name` varchar(100) NOT NULL,
    `schedule_type` varchar(50) NOT NULL,
    `start_time` datetime(3) NOT NULL,
    `is_enabled` tinyint(1) NOT NULL,
    `created_at` datetime(3) NOT NULL,
    `store_id` char(36) NULL,
    `sync_mode` varchar(20) NOT NULL,
    `suspended_until` datetime(3) NULL,
    `last_run_at` datetime(3) NULL,
    `updated_at` datetime(3) NULL,
    PRIMARY KEY (`schedule_id`)
);
INSERT INTO nexora_platform.`sync_schedule` (`schedule_id`, `tenant_id`, `schedule_name`, `schedule_type`, `start_time`, `is_enabled`, `created_at`, `store_id`, `sync_mode`, `suspended_until`, `last_run_at`, `updated_at`) VALUES
    (1, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'NMA Morning Sync', 'DAILY', '2000-01-01 18:15:00.000', 1, '2026-06-24 16:47:10.037', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'FULL', NULL, NULL, '2026-06-26 11:42:46.057'),
    (2, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'NMA Afternoon Sync', 'DAILY', '2000-01-01 13:00:00.000', 1, '2026-06-24 16:47:10.087', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'FULL', NULL, NULL, '2026-06-24 16:47:10.087'),
    (3, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'NMC Morning Sync', 'DAILY', '2000-01-01 18:17:00.000', 1, '2026-06-24 16:47:10.093', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', 'FULL', NULL, NULL, '2026-06-26 11:43:01.823'),
    (4, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'NMC Afternoon Sync', 'DAILY', '2000-01-01 13:02:00.000', 1, '2026-06-24 16:47:10.097', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', 'FULL', NULL, NULL, '2026-06-24 16:47:10.097'),
    (5, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'NMG Morning Sync', 'DAILY', '2000-01-01 18:19:00.000', 1, '2026-06-24 16:47:10.100', '3019101A-24A6-4045-AB7E-964046383EA2', 'FULL', NULL, NULL, '2026-06-26 11:43:09.080'),
    (6, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'NMG Afternoon Sync', 'DAILY', '2000-01-01 13:04:00.000', 1, '2026-06-24 16:47:10.103', '3019101A-24A6-4045-AB7E-964046383EA2', 'FULL', NULL, NULL, '2026-06-24 16:47:10.103'),
    (7, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'NMS Morning Sync', 'DAILY', '2000-01-01 18:21:00.000', 1, '2026-06-24 16:47:10.107', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', 'FULL', NULL, NULL, '2026-06-26 11:43:16.173'),
    (8, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'NMS Afternoon Sync', 'DAILY', '2000-01-01 13:06:00.000', 1, '2026-06-24 16:47:10.110', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', 'FULL', NULL, NULL, '2026-06-24 16:47:10.110'),
    (9, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'NMW Morning Sync', 'DAILY', '2000-01-01 18:23:00.000', 1, '2026-06-24 16:47:10.113', 'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', 'FULL', NULL, NULL, '2026-06-26 11:43:26.737'),
    (10, 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'NMW Afternoon Sync', 'DAILY', '2000-01-01 13:08:00.000', 1, '2026-06-24 16:47:10.120', 'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', 'FULL', NULL, NULL, '2026-06-24 16:47:10.120');
DROP TABLE IF EXISTS nexora_platform.`sync_store_selection`;
CREATE TABLE nexora_platform.`sync_store_selection` (
    `id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `config_id` bigint NOT NULL,
    `store_id` char(36) NOT NULL,
    `is_selected` tinyint(1) NOT NULL,
    PRIMARY KEY (`id`)
);
DROP TABLE IF EXISTS nexora_platform.`sync_table_registry`;
CREATE TABLE nexora_platform.`sync_table_registry` (
    `table_id` bigint AUTO_INCREMENT NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `table_name` varchar(200) NOT NULL,
    `sync_order` int NOT NULL,
    `chunk_enabled` tinyint(1) NOT NULL,
    `refresh_enabled` tinyint(1) NOT NULL,
    `is_active` tinyint(1) NOT NULL,
    PRIMARY KEY (`table_id`)
);
INSERT INTO nexora_platform.`sync_table_registry` (`table_id`, `tenant_id`, `table_name`, `sync_order`, `chunk_enabled`, `refresh_enabled`, `is_active`) VALUES
    (1, '00000000-0000-0000-0000-000000000000', '3B_Table1', 999, 1, 1, 1),
    (2, '00000000-0000-0000-0000-000000000000', '3B_Table2', 999, 1, 1, 1),
    (3, '00000000-0000-0000-0000-000000000000', '3B_Table3', 999, 1, 1, 1),
    (4, '00000000-0000-0000-0000-000000000000', '3B_Table4', 999, 1, 1, 1),
    (5, '00000000-0000-0000-0000-000000000000', '3B_Table5', 999, 1, 1, 1),
    (6, '00000000-0000-0000-0000-000000000000', '3B_Table6', 999, 1, 1, 1),
    (7, '00000000-0000-0000-0000-000000000000', '3B_Table7', 999, 1, 1, 1),
    (8, '00000000-0000-0000-0000-000000000000', '3B_Table8', 999, 1, 1, 1),
    (9, '00000000-0000-0000-0000-000000000000', '3bsubmissioninfo', 999, 1, 1, 1),
    (10, '00000000-0000-0000-0000-000000000000', 'AA', 999, 1, 1, 1);
DROP TABLE IF EXISTS nexora_platform.`tenants`;
CREATE TABLE nexora_platform.`tenants` (
    `tenant_id` char(36) NOT NULL,
    `tenant_code` varchar(50) NOT NULL,
    `tenant_abbreviation` varchar(20) NOT NULL,
    `tenant_name` varchar(200) NOT NULL,
    `db_name` varchar(200) NOT NULL,
    `platform_version` varchar(20) NULL,
    `tenant_db_version` varchar(20) NULL,
    `contact_name` varchar(100) NULL,
    `contact_email` varchar(200) NULL,
    `contact_phone` varchar(50) NULL,
    `is_active` tinyint(1) NOT NULL,
    `created_at` datetime(3) NOT NULL,
    `created_by` char(36) NULL,
    `updated_at` datetime(3) NULL,
    `updated_by` char(36) NULL,
    `website_url` varchar(500) NULL,
    PRIMARY KEY (`tenant_id`)
);
INSERT INTO nexora_platform.`tenants` (`tenant_id`, `tenant_code`, `tenant_abbreviation`, `tenant_name`, `db_name`, `platform_version`, `tenant_db_version`, `contact_name`, `contact_email`, `contact_phone`, `is_active`, `created_at`, `created_by`, `updated_at`, `updated_by`, `website_url`) VALUES
    ('A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'NATHAN', 'Nathan', 'Nathan Medicals ', 'NEXORA_PLATFORM', NULL, NULL, NULL, NULL, NULL, 1, '2026-06-18 19:21:40.837', NULL, NULL, NULL, NULL);
DROP TABLE IF EXISTS nexora_platform.`user_login_security`;
CREATE TABLE nexora_platform.`user_login_security` (
    `user_id` char(36) NOT NULL,
    `failed_login_count` int NOT NULL,
    `is_locked` tinyint(1) NOT NULL,
    `locked_until` datetime(3) NULL,
    `force_password_change` tinyint(1) NOT NULL,
    `last_failed_login` datetime(3) NULL,
    `last_successful_login` datetime(3) NULL,
    PRIMARY KEY (`user_id`)
);
DROP TABLE IF EXISTS nexora_platform.`user_module_override`;
CREATE TABLE nexora_platform.`user_module_override` (
    `id` bigint AUTO_INCREMENT NOT NULL,
    `user_id` char(36) NOT NULL,
    `module_id` char(36) NOT NULL,
    `can_view` tinyint(1) NULL,
    `can_create` tinyint(1) NULL,
    `can_edit` tinyint(1) NULL,
    `can_delete` tinyint(1) NULL,
    `can_export` tinyint(1) NULL,
    `is_active` tinyint(1) NULL,
    PRIMARY KEY (`id`)
);
DROP TABLE IF EXISTS nexora_platform.`user_store_roles`;
CREATE TABLE nexora_platform.`user_store_roles` (
    `id` bigint AUTO_INCREMENT NOT NULL,
    `user_id` char(36) NOT NULL,
    `store_id` char(36) NOT NULL,
    `role_id` char(36) NOT NULL,
    `is_active` tinyint(1) NOT NULL,
    PRIMARY KEY (`id`)
);
INSERT INTO nexora_platform.`user_store_roles` (`id`, `user_id`, `store_id`, `role_id`, `is_active`) VALUES
    (1, '4055B2C9-30E8-4062-9D52-666EF0769D4B', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '85BD267C-B7C6-4FA9-A2CA-A11EEC6624E7', 1);
DROP TABLE IF EXISTS nexora_platform.`users`;
CREATE TABLE nexora_platform.`users` (
    `user_id` char(36) NOT NULL,
    `tenant_id` char(36) NULL,
    `username` varchar(100) NOT NULL,
    `password_hash` varchar(500) NOT NULL,
    `first_name` varchar(100) NOT NULL,
    `last_name` varchar(100) NULL,
    `email` varchar(200) NULL,
    `mobile` varchar(50) NULL,
    `is_platform_user` tinyint(1) NOT NULL,
    `is_active` tinyint(1) NOT NULL,
    `last_login` datetime(3) NULL,
    `created_at` datetime(3) NOT NULL,
    `updated_at` datetime(3) NULL,
    `failed_login_attempts` int NOT NULL,
    `locked_until` datetime(3) NULL,
    `force_password_change` tinyint(1) NOT NULL,
    `password_changed_at` datetime(3) NULL,
    `created_by` char(36) NULL,
    `updated_by` char(36) NULL,
    `password_reset_token` varchar(200) NULL,
    `password_reset_expiry` datetime(3) NULL,
    PRIMARY KEY (`user_id`)
);
INSERT INTO nexora_platform.`users` (`user_id`, `tenant_id`, `username`, `password_hash`, `first_name`, `last_name`, `email`, `mobile`, `is_platform_user`, `is_active`, `last_login`, `created_at`, `updated_at`, `failed_login_attempts`, `locked_until`, `force_password_change`, `password_changed_at`, `created_by`, `updated_by`, `password_reset_token`, `password_reset_expiry`) VALUES
    ('4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, 'superadmin', '$2b$12$EZZHtwfID05iPyKVuwQ/aee38JFcbbxvwmgWpcgT83oWyTKxW07RS', 'Super', 'Admin', NULL, NULL, 1, 1, '2026-06-18 19:53:32.570', '2026-06-18 14:38:59.737', '2026-06-18 19:48:40.253', 0, NULL, 0, '2026-06-18 19:48:40.253', NULL, NULL, NULL, NULL);
DROP TABLE IF EXISTS nexora_procurement.`procurement_cycles`;
CREATE TABLE nexora_procurement.`procurement_cycles` (
    `cycle_id` char(36) NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `name` varchar(200) NOT NULL,
    `description` varchar(1000) NULL,
    `status` varchar(50) NOT NULL,
    `start_date` date NULL,
    `end_date` date NULL,
    `store_id` char(36) NULL,
    `cycle_no` int NULL,
    `offline_mode` tinyint(1) NOT NULL,
    `active_refresh_id` char(36) NULL,
    `closed_at` datetime(3) NULL,
    `start_grn_number` varchar(50) NULL,
    `start_sale_bill_number` varchar(50) NULL,
    `end_grn_number` varchar(50) NULL,
    `end_sale_bill_number` varchar(50) NULL,
    `created_at` datetime(3) NOT NULL,
    `created_by` char(36) NULL,
    `updated_at` datetime(3) NULL,
    `updated_by` char(36) NULL,
    `is_deleted` tinyint(1) NOT NULL,
    `deleted_at` datetime(3) NULL,
    `deleted_by` char(36) NULL,
    PRIMARY KEY (`cycle_id`)
);
INSERT INTO nexora_procurement.`procurement_cycles` (`cycle_id`, `tenant_id`, `name`, `description`, `status`, `start_date`, `end_date`, `store_id`, `cycle_no`, `offline_mode`, `active_refresh_id`, `closed_at`, `start_grn_number`, `start_sale_bill_number`, `end_grn_number`, `end_sale_bill_number`, `created_at`, `created_by`, `updated_at`, `updated_by`, `is_deleted`, `deleted_at`, `deleted_by`) VALUES
    ('C5289020-BEC7-4E74-99EE-19455E7AF5E9', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'ISO Test B', NULL, 'Closed', NULL, NULL, 'D55F8A0D-C230-44EA-BF56-02F143B948BD', NULL, 0, 'B2C18431-173E-4636-B5CE-1764D92BF9BF', NULL, NULL, NULL, NULL, NULL, '2026-07-05 14:12:46.703', NULL, '2026-07-05 14:12:59.707', NULL, 1, NULL, NULL),
    ('C6E89C04-55C5-44F8-8464-3E9559ED860E', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'Real Cycle 2026-07-02', NULL, 'Closed', NULL, NULL, 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', NULL, 0, '47ACF89A-EC30-4201-A663-CA0DA179031D', '2026-07-04 20:11:04.670', '17845', '50235', '17845', '231675', '2026-07-02 17:34:13.517', '4055B2C9-30E8-4062-9D52-666EF0769D4B', '2026-07-04 20:11:04.670', NULL, 0, NULL, NULL),
    ('70AF68C3-BFBB-440E-80FB-421DEA1C1BC6', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'sunday test', NULL, 'ACTIVE', NULL, NULL, '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', NULL, 0, '64977121-A59D-4FBF-B32A-36E4253AAF6E', NULL, NULL, NULL, NULL, NULL, '2026-07-05 15:06:52.647', NULL, '2026-07-05 15:07:04.800', NULL, 0, NULL, NULL),
    ('98207326-B23E-4F91-A299-E018FAC8EA1B', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'Real Cycle 2026-07-02 · 04-Jul-2026', NULL, 'ACTIVE', NULL, NULL, 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', NULL, 0, 'F2C197F8-8A16-4426-8DBC-08B0DAB4E25D', NULL, '17845', '231675', NULL, NULL, '2026-07-04 20:11:04.690', NULL, '2026-07-05 15:07:21.353', NULL, 0, NULL, NULL);
DROP TABLE IF EXISTS nexora_procurement.`procurement_order_item_assignments`;
CREATE TABLE nexora_procurement.`procurement_order_item_assignments` (
    `assignment_id` char(36) NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `cycle_id` char(36) NOT NULL,
    `refresh_id` char(36) NOT NULL,
    `order_item_id` char(36) NOT NULL,
    `store_id` char(36) NULL,
    `product_code` varchar(100) NULL,
    `supplier_code` varchar(100) NOT NULL,
    `assigned_qty` decimal(18,3) NULL,
    `assignment_status` varchar(30) NOT NULL,
    `remarks` varchar(300) NULL,
    `export_batch_number` varchar(50) NULL,
    `export_split_number` int NULL,
    `export_uid` varchar(100) NULL,
    `exported_at` datetime(3) NULL,
    `exported_by` char(36) NULL,
    `received_qty` decimal(18,3) NULL,
    `grn_no` varchar(100) NULL,
    `supplier_bill_no` varchar(100) NULL,
    `created_at` datetime(3) NOT NULL,
    `created_by` char(36) NULL,
    `updated_at` datetime(3) NULL,
    `updated_by` char(36) NULL,
    `is_deleted` tinyint(1) NOT NULL,
    `deleted_at` datetime(3) NULL,
    `deleted_by` char(36) NULL,
    `remaining_qty` decimal(18,3) NULL,
    `last_grn_sync_at` datetime(3) NULL,
    PRIMARY KEY (`assignment_id`)
);
INSERT INTO nexora_procurement.`procurement_order_item_assignments` (`assignment_id`, `tenant_id`, `cycle_id`, `refresh_id`, `order_item_id`, `store_id`, `product_code`, `supplier_code`, `assigned_qty`, `assignment_status`, `remarks`, `export_batch_number`, `export_split_number`, `export_uid`, `exported_at`, `exported_by`, `received_qty`, `grn_no`, `supplier_bill_no`, `created_at`, `created_by`, `updated_at`, `updated_by`, `is_deleted`, `deleted_at`, `deleted_by`, `remaining_qty`, `last_grn_sync_at`) VALUES
    ('7ABF974D-B044-4391-907C-011863E79FC8', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C6E89C04-55C5-44F8-8464-3E9559ED860E', '47ACF89A-EC30-4201-A663-CA0DA179031D', '5348162B-B286-4EFC-9133-071246EFA4C3', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '5894618', 'LIFE', 1.000, 'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:34:57.800', '4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    ('543270CA-C93E-48B4-9D20-019D302B2B4F', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C6E89C04-55C5-44F8-8464-3E9559ED860E', '47ACF89A-EC30-4201-A663-CA0DA179031D', 'F1049D89-7DEE-4F54-9F59-BC27291F93AE', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '24747', '117', 30.000, 'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:34:50.367', '4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    ('A8F9324B-C9EB-461B-A2C2-01E42E3C94F1', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C6E89C04-55C5-44F8-8464-3E9559ED860E', '47ACF89A-EC30-4201-A663-CA0DA179031D', 'FCFE99D4-9F46-4B25-9EF3-7F48EDF0F4C6', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '5852448', '117', 13.000, 'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:34:50.610', '4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    ('1B2D02DF-8546-41C1-904A-01EF3F7CA702', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C6E89C04-55C5-44F8-8464-3E9559ED860E', '47ACF89A-EC30-4201-A663-CA0DA179031D', '868B7A39-A662-4173-B04D-17B125C0C498', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '5870517', 'PALEPU', 1.000, 'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:34:59.327', '4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    ('47074A8D-D600-46DC-8869-02889AEE5E2A', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C6E89C04-55C5-44F8-8464-3E9559ED860E', '47ACF89A-EC30-4201-A663-CA0DA179031D', '5B66B8A5-F074-4A44-ADF6-1D426C4A5763', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '5878014', '426', 60.000, 'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:34:55.910', '4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    ('11ADA3BE-D96C-439C-A981-02AB297CAAC1', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C6E89C04-55C5-44F8-8464-3E9559ED860E', '47ACF89A-EC30-4201-A663-CA0DA179031D', 'E33D7B16-FAD9-4846-AAF4-8A817E7C9B6D', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '5883802', '438', 1.000, 'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:34:59.160', '4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    ('862E775E-313C-43F6-8609-02C8F1AB3AC2', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C6E89C04-55C5-44F8-8464-3E9559ED860E', '47ACF89A-EC30-4201-A663-CA0DA179031D', '33051BAF-EED2-42E7-A707-599EE68C08F7', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '26065', '120', 60.000, 'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:34:52.203', '4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    ('B146AAD6-4481-4435-B1B7-0328C5CC8F85', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C6E89C04-55C5-44F8-8464-3E9559ED860E', '47ACF89A-EC30-4201-A663-CA0DA179031D', 'CFFB5C43-F917-4C43-8068-8CBDD35C64DE', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '4407', '15', 40.000, 'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:34:52.823', '4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    ('26260681-E925-4803-8EFE-042C00F32F09', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C6E89C04-55C5-44F8-8464-3E9559ED860E', '47ACF89A-EC30-4201-A663-CA0DA179031D', '91D8479A-342D-412C-9048-630258F790B5', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '5882197', '567', 3.000, 'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:35:01.520', '4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL),
    ('72D008BA-CD66-4555-87EE-043F8CA293E1', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C6E89C04-55C5-44F8-8464-3E9559ED860E', '47ACF89A-EC30-4201-A663-CA0DA179031D', 'EE426966-2E92-4661-9508-A30049EEDCDA', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '5888110', '153', 4.000, 'draft', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-07-02 17:35:01.830', '4055B2C9-30E8-4062-9D52-666EF0769D4B', NULL, NULL, 0, NULL, NULL, NULL, NULL);
DROP TABLE IF EXISTS nexora_procurement.`procurement_order_items`;
CREATE TABLE nexora_procurement.`procurement_order_items` (
    `order_item_id` char(36) NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `cycle_id` char(36) NOT NULL,
    `refresh_id` char(36) NOT NULL,
    `store_id` char(36) NULL,
    `product_id` char(36) NOT NULL,
    `product_code` varchar(100) NULL,
    `final_qty` decimal(18,3) NULL,
    `assigned_qty` decimal(18,3) NULL,
    `remaining_qty` decimal(18,3) NULL,
    `action_mode` varchar(30) NULL,
    `manual_override` tinyint(1) NULL,
    `override_reason` varchar(300) NULL,
    `item_status` varchar(20) NOT NULL,
    `created_at` datetime(3) NOT NULL,
    `created_by` char(36) NULL,
    `updated_at` datetime(3) NULL,
    `updated_by` char(36) NULL,
    `is_deleted` tinyint(1) NOT NULL,
    `deleted_at` datetime(3) NULL,
    `deleted_by` char(36) NULL,
    `suggested_qty` decimal(18,3) NULL,
    `skip_reason` varchar(300) NULL,
    `reviewed_by` char(36) NULL,
    `reviewed_at` datetime(3) NULL,
    `received_qty` decimal(18,3) NULL,
    `is_manual` tinyint(1) NOT NULL,
    `pending_status` varchar(20) NULL,
    PRIMARY KEY (`order_item_id`)
);
INSERT INTO nexora_procurement.`procurement_order_items` (`order_item_id`, `tenant_id`, `cycle_id`, `refresh_id`, `store_id`, `product_id`, `product_code`, `final_qty`, `assigned_qty`, `remaining_qty`, `action_mode`, `manual_override`, `override_reason`, `item_status`, `created_at`, `created_by`, `updated_at`, `updated_by`, `is_deleted`, `deleted_at`, `deleted_by`, `suggested_qty`, `skip_reason`, `reviewed_by`, `reviewed_at`, `received_qty`, `is_manual`, `pending_status`) VALUES
    ('F321F46A-2464-4984-8596-000BAE0E31B1', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', '905087CF-CA8D-4237-B4FB-94D213F1D503', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '3C85B5D9-EE0E-4BC5-8E96-0EAEAD68534D', '10731', 60.000, 0.000, 60.000, NULL, NULL, NULL, 'draft', '2026-07-05 14:18:05.490', NULL, NULL, NULL, 0, NULL, NULL, 60.000, NULL, NULL, NULL, NULL, 0, NULL),
    ('A6D0277B-2B93-4C16-B3DD-001016DFFB26', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', '905087CF-CA8D-4237-B4FB-94D213F1D503', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', 'CACB9109-A93C-4E90-998F-5BEC413EEF39', '5890539', 1.000, 0.000, 1.000, NULL, NULL, NULL, 'draft', '2026-07-05 14:18:05.490', NULL, NULL, NULL, 0, NULL, NULL, 1.000, NULL, NULL, NULL, NULL, 0, NULL),
    ('A9EE15D7-68F4-4E7C-A8D0-00182A9A5127', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', '40C9BD82-7531-45FF-BB1D-4D2AE8E67CE1', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', 'FE4B3C7E-87C6-4006-9789-A22BC447189F', '5891002', 10.000, 0.000, 10.000, NULL, NULL, NULL, 'draft', '2026-07-05 15:06:41.117', NULL, NULL, NULL, 0, NULL, NULL, 10.000, NULL, NULL, NULL, NULL, 0, NULL),
    ('6EBC6629-82B4-4FD0-9503-00196D7D1CAF', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', '40C9BD82-7531-45FF-BB1D-4D2AE8E67CE1', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '94A29A36-284B-42B5-88AE-27415106E780', '5871400', 2.000, 0.000, 2.000, NULL, NULL, NULL, 'draft', '2026-07-05 15:06:41.117', NULL, NULL, NULL, 0, NULL, NULL, 2.000, NULL, NULL, NULL, NULL, 0, NULL),
    ('B71F935D-5C8B-4763-A2D8-001B5365AE16', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', '40C9BD82-7531-45FF-BB1D-4D2AE8E67CE1', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '3234027A-1AAE-4842-9E68-765C60F3E3C1', '5894229', 1.000, 0.000, 1.000, NULL, NULL, NULL, 'draft', '2026-07-05 15:06:41.117', NULL, NULL, NULL, 0, NULL, NULL, 1.000, NULL, NULL, NULL, NULL, 0, NULL),
    ('B6D3A4EF-06F0-4D6B-9C14-003047A3FB77', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', '14FD2327-950E-4B1B-9057-75A0342A2DBD', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '76239A8D-36D3-4C6B-B645-ACF0F5969548', '2300', 10.000, 0.000, 10.000, NULL, NULL, NULL, 'draft', '2026-07-05 15:04:38.980', NULL, NULL, NULL, 0, NULL, NULL, 10.000, NULL, NULL, NULL, NULL, 0, NULL),
    ('0781FB8C-9B85-4838-AFC2-0034AD75D0F1', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', 'F2C197F8-8A16-4426-8DBC-08B0DAB4E25D', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', 'A582259F-78EB-4CE7-A1AE-298EE7B37C53', '21394', 2.000, 0.000, 2.000, NULL, NULL, NULL, 'draft', '2026-07-05 15:07:21.383', NULL, NULL, NULL, 0, NULL, NULL, 2.000, NULL, NULL, NULL, NULL, 0, NULL),
    ('BEFE284C-BDEF-467F-8DF9-003B0437E9CB', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', 'F2C197F8-8A16-4426-8DBC-08B0DAB4E25D', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '53EC69F6-3494-4131-91CC-F77991EE0F1E', '12994', 3.000, 0.000, 3.000, NULL, NULL, NULL, 'draft', '2026-07-05 15:07:21.383', NULL, NULL, NULL, 0, NULL, NULL, 3.000, NULL, NULL, NULL, NULL, 0, NULL),
    ('984AF4DF-D932-4703-91A6-0045BFE2504E', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C6E89C04-55C5-44F8-8464-3E9559ED860E', '47ACF89A-EC30-4201-A663-CA0DA179031D', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '3DB4C61F-3F94-4DA1-844B-BCD28B41F136', '5888582', 30.000, 30.000, 30.000, NULL, NULL, NULL, 'pending', '2026-07-02 17:34:21.183', '4055B2C9-30E8-4062-9D52-666EF0769D4B', '2026-07-04 20:11:04.497', NULL, 0, NULL, NULL, 30.000, NULL, NULL, '2026-07-04 20:11:04.497', 0.000, 0, 'cleared'),
    ('AECBFE51-5077-4C7B-9D90-004DBAF8BAB5', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', '40C9BD82-7531-45FF-BB1D-4D2AE8E67CE1', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', 'B0975B6A-9B7E-440B-B853-39B684231DE5', '5858436', 40.000, 0.000, 40.000, NULL, NULL, NULL, 'draft', '2026-07-05 15:06:41.117', NULL, NULL, NULL, 0, NULL, NULL, 40.000, NULL, NULL, NULL, NULL, 0, NULL);
DROP TABLE IF EXISTS nexora_procurement.`procurement_refreshes`;
CREATE TABLE nexora_procurement.`procurement_refreshes` (
    `refresh_id` char(36) NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `cycle_id` char(36) NOT NULL,
    `store_id` char(36) NULL,
    `snapshot_name` varchar(200) NOT NULL,
    `snapshot_status` varchar(50) NOT NULL,
    `refresh_no` int NULL,
    `rolling_days` int NULL,
    `min_days` decimal(18,2) NULL,
    `max_days` decimal(18,2) NULL,
    `previous_refresh_id` char(36) NULL,
    `snapshot_grn_number` varchar(50) NULL,
    `snapshot_sale_bill_number` varchar(50) NULL,
    `sync_execution_id` char(36) NULL,
    `generated_product_count` int NULL,
    `generation_started_at` datetime(3) NULL,
    `generation_completed_at` datetime(3) NULL,
    `remarks` varchar(500) NULL,
    `last_snapshot_on` datetime(3) NULL,
    `last_snapshot_by` char(36) NULL,
    `created_at` datetime(3) NOT NULL,
    `created_by` char(36) NULL,
    `updated_at` datetime(3) NULL,
    `updated_by` char(36) NULL,
    `is_deleted` tinyint(1) NOT NULL,
    `deleted_at` datetime(3) NULL,
    `deleted_by` char(36) NULL,
    `last_grn_number` varchar(50) NULL,
    `grn_completed_at` datetime(3) NULL,
    PRIMARY KEY (`refresh_id`)
);
INSERT INTO nexora_procurement.`procurement_refreshes` (`refresh_id`, `tenant_id`, `cycle_id`, `store_id`, `snapshot_name`, `snapshot_status`, `refresh_no`, `rolling_days`, `min_days`, `max_days`, `previous_refresh_id`, `snapshot_grn_number`, `snapshot_sale_bill_number`, `sync_execution_id`, `generated_product_count`, `generation_started_at`, `generation_completed_at`, `remarks`, `last_snapshot_on`, `last_snapshot_by`, `created_at`, `created_by`, `updated_at`, `updated_by`, `is_deleted`, `deleted_at`, `deleted_by`, `last_grn_number`, `grn_completed_at`) VALUES
    ('F2C197F8-8A16-4426-8DBC-08B0DAB4E25D', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', 'Refresh', 'Ready', NULL, 90, 13.00, 18.00, '40C9BD82-7531-45FF-BB1D-4D2AE8E67CE1', NULL, NULL, NULL, 1357, '2026-07-05 15:07:20.093', '2026-07-05 15:07:21.353', NULL, NULL, NULL, '2026-07-05 15:07:20.070', NULL, '2026-07-05 15:07:21.353', NULL, 0, NULL, NULL, NULL, NULL),
    ('B2C18431-173E-4636-B5CE-1764D92BF9BF', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C5289020-BEC7-4E74-99EE-19455E7AF5E9', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', 'ISO B', 'Ready', NULL, 90, 7.00, 21.00, NULL, NULL, NULL, NULL, 45909, '2026-07-05 14:12:46.757', '2026-07-05 14:12:59.707', NULL, NULL, NULL, '2026-07-05 14:12:46.740', NULL, '2026-07-05 14:12:59.707', NULL, 1, NULL, NULL, NULL, NULL),
    ('64977121-A59D-4FBF-B32A-36E4253AAF6E', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '70AF68C3-BFBB-440E-80FB-421DEA1C1BC6', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'Refresh', 'Ready', NULL, 90, 13.00, 18.00, NULL, NULL, NULL, NULL, 724, '2026-07-05 15:07:03.453', '2026-07-05 15:07:04.800', NULL, NULL, NULL, '2026-07-05 15:07:03.420', NULL, '2026-07-05 15:07:04.800', NULL, 0, NULL, NULL, NULL, NULL),
    ('40C9BD82-7531-45FF-BB1D-4D2AE8E67CE1', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', 'Trimmed VPL', 'Archived', NULL, 90, 7.00, 21.00, '14FD2327-950E-4B1B-9057-75A0342A2DBD', NULL, NULL, NULL, 989, '2026-07-05 15:06:39.943', '2026-07-05 15:06:41.093', NULL, NULL, NULL, '2026-07-05 15:06:39.893', NULL, '2026-07-05 15:07:21.760', NULL, 0, NULL, NULL, NULL, NULL),
    ('F2C5C224-FD68-435D-8B77-54989EA3D4C8', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', 'Repro Refresh', 'Archived', NULL, 90, 7.00, 21.00, NULL, NULL, NULL, NULL, 32712, '2026-07-05 14:01:44.370', '2026-07-05 14:01:56.400', NULL, NULL, NULL, '2026-07-05 14:01:44.300', NULL, '2026-07-05 14:18:05.670', NULL, 0, NULL, NULL, NULL, NULL),
    ('14FD2327-950E-4B1B-9057-75A0342A2DBD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', 'Refresh', 'Archived', NULL, 90, 13.00, 18.00, '905087CF-CA8D-4237-B4FB-94D213F1D503', NULL, NULL, NULL, 32712, '2026-07-05 15:04:27.263', '2026-07-05 15:04:38.760', NULL, NULL, NULL, '2026-07-05 15:04:27.230', NULL, '2026-07-05 15:06:41.220', NULL, 0, NULL, NULL, NULL, NULL),
    ('905087CF-CA8D-4237-B4FB-94D213F1D503', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', 'Refresh', 'Archived', NULL, 90, 13.00, 15.00, 'F2C5C224-FD68-435D-8B77-54989EA3D4C8', NULL, NULL, NULL, 32712, '2026-07-05 14:17:54.030', '2026-07-05 14:18:05.260', NULL, NULL, NULL, '2026-07-05 14:17:53.997', NULL, '2026-07-05 15:04:39.153', NULL, 0, NULL, NULL, NULL, NULL),
    ('47ACF89A-EC30-4201-A663-CA0DA179031D', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C6E89C04-55C5-44F8-8464-3E9559ED860E', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', 'Refresh 1', 'Ready', NULL, 90, 13.00, 18.00, NULL, '17845', '50235', NULL, 32682, '2026-07-02 17:34:13.573', '2026-07-02 17:34:21.020', NULL, NULL, NULL, '2026-07-02 17:34:13.553', '4055B2C9-30E8-4062-9D52-666EF0769D4B', '2026-07-02 17:34:21.020', NULL, 0, NULL, NULL, NULL, NULL);
DROP TABLE IF EXISTS nexora_procurement.`procurement_virtual_products`;
CREATE TABLE nexora_procurement.`procurement_virtual_products` (
    `virtual_product_id` char(36) NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `cycle_id` char(36) NOT NULL,
    `refresh_id` char(36) NOT NULL,
    `product_id` char(36) NOT NULL,
    `product_code` varchar(100) NULL,
    `product_name` varchar(300) NULL,
    `manufacturer_id` char(36) NULL,
    `category_id` char(36) NULL,
    `schedule_type` varchar(50) NULL,
    `unit` varchar(50) NULL,
    `is_active` tinyint(1) NOT NULL,
    `snapshot_version` int NOT NULL,
    `mrp` decimal(18,4) NULL,
    `ptr_cost` decimal(18,4) NULL,
    `pack` varchar(50) NULL,
    `unit_description` varchar(100) NULL,
    `sub_location` varchar(100) NULL,
    `monthly_sales_qty` decimal(18,3) NULL,
    `tx_count` int NULL,
    `max_day_sale_qty` decimal(18,3) NULL,
    `max_bill_qty` decimal(18,3) NULL,
    `days_since_last_sale` int NULL,
    `days_since_last_purchase` int NULL,
    `days_cover` decimal(18,3) NULL,
    `movement_class` varchar(30) NULL,
    `stock_status` varchar(30) NULL,
    `offer_buy_qty` decimal(18,3) NULL,
    `offer_free_qty` decimal(18,3) NULL,
    `offer_last_date` date NULL,
    `order_type` varchar(30) NULL,
    `is_auto_accept` tinyint(1) NULL,
    `warning_flag` tinyint(1) NULL,
    `warning_reason` varchar(200) NULL,
    `committed_qty` decimal(18,3) NULL,
    `remaining_procurement_qty` decimal(18,3) NULL,
    `required_qty` decimal(18,3) NULL,
    `suggested_qty` decimal(18,3) NULL,
    `target_days` decimal(18,2) NULL,
    `target_stock_qty` decimal(18,3) NULL,
    `raw_required_qty` decimal(18,3) NULL,
    `final_required_qty` decimal(18,3) NULL,
    `procurement_action` varchar(50) NULL,
    `trigger_reason` varchar(100) NULL,
    `effective_available_qty` decimal(18,3) NULL,
    `pending_used_qty` decimal(18,3) NULL,
    `created_at` datetime(3) NOT NULL,
    `updated_at` datetime(3) NULL,
    `current_stock_qty` decimal(18,3) NULL,
    `available_stock_qty` decimal(18,3) NULL,
    `pending_purchase_qty` decimal(18,3) NULL,
    `pending_sales_qty` decimal(18,3) NULL,
    `last_purchase_date` date NULL,
    `last_purchase_qty` decimal(18,3) NULL,
    `last_purchase_rate` decimal(18,4) NULL,
    `last_sale_date` date NULL,
    `last_sale_qty` decimal(18,3) NULL,
    `avg_daily_sales` decimal(18,4) NULL,
    `avg_monthly_sales` decimal(18,4) NULL,
    `expiry_qty` decimal(18,3) NULL,
    `near_expiry_qty` decimal(18,3) NULL,
    `supplier_count` int NULL,
    `preferred_supplier_id` char(36) NULL,
    `snapshot_refreshed_on` datetime(3) NULL,
    `reason_code` varchar(50) NULL,
    `reason_text` varchar(500) NULL,
    `window_sales_qty` decimal(18,3) NULL,
    `billing_frequency` int NULL,
    PRIMARY KEY (`virtual_product_id`)
);
INSERT INTO nexora_procurement.`procurement_virtual_products` (`virtual_product_id`, `tenant_id`, `cycle_id`, `refresh_id`, `product_id`, `product_code`, `product_name`, `manufacturer_id`, `category_id`, `schedule_type`, `unit`, `is_active`, `snapshot_version`, `mrp`, `ptr_cost`, `pack`, `unit_description`, `sub_location`, `monthly_sales_qty`, `tx_count`, `max_day_sale_qty`, `max_bill_qty`, `days_since_last_sale`, `days_since_last_purchase`, `days_cover`, `movement_class`, `stock_status`, `offer_buy_qty`, `offer_free_qty`, `offer_last_date`, `order_type`, `is_auto_accept`, `warning_flag`, `warning_reason`, `committed_qty`, `remaining_procurement_qty`, `required_qty`, `suggested_qty`, `target_days`, `target_stock_qty`, `raw_required_qty`, `final_required_qty`, `procurement_action`, `trigger_reason`, `effective_available_qty`, `pending_used_qty`, `created_at`, `updated_at`, `current_stock_qty`, `available_stock_qty`, `pending_purchase_qty`, `pending_sales_qty`, `last_purchase_date`, `last_purchase_qty`, `last_purchase_rate`, `last_sale_date`, `last_sale_qty`, `avg_daily_sales`, `avg_monthly_sales`, `expiry_qty`, `near_expiry_qty`, `supplier_count`, `preferred_supplier_id`, `snapshot_refreshed_on`, `reason_code`, `reason_text`, `window_sales_qty`, `billing_frequency`) VALUES
    ('5DB66897-2BE5-4947-A21B-00001AF10EA7', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C6E89C04-55C5-44F8-8464-3E9559ED860E', '47ACF89A-EC30-4201-A663-CA0DA179031D', 'ECBE2AE9-D781-473A-8CA6-01E9C8492BE2', '5886868', 'VIZIGLY SOAP  75GM', NULL, NULL, NULL, 'SOAP', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, 0.000, NULL, NULL, 0.000, 'NONMOVING', 'OUT', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, 'EXCLUDE', NULL, 0.000, 0.000, '2026-07-02 17:34:19.673', NULL, 0.000, 0.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0000, NULL, NULL, NULL, NULL, NULL, NULL, 'EXCLUDED_NOT_SELLING', 'Excluded: no eligible sales in the rolling window.', 0.000, 0),
    ('FB320F53-0661-454D-9941-000025624CD9', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', '905087CF-CA8D-4237-B4FB-94D213F1D503', '9F98CAE4-90C1-4633-B135-3E0F36C267EB', '5861014', 'FLOXSAFE 400 TAB', NULL, NULL, NULL, 'TAB', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, 0.000, NULL, NULL, 0.000, 'NONMOVING', 'OUT', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, 'EXCLUDE', NULL, 0.000, 0.000, '2026-07-05 14:18:00.177', NULL, 0.000, 0.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0000, NULL, NULL, NULL, NULL, NULL, NULL, 'EXCLUDED_NOT_SELLING', 'Excluded: no eligible sales in the rolling window.', 0.000, 0),
    ('4ACDED02-BB4C-41A4-8EE2-0000950D4CCB', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', 'F2C5C224-FD68-435D-8B77-54989EA3D4C8', '59BF207C-BB45-4E6C-AD08-2CFBDBB0E4F3', '5888337', 'DIGERAFT XT SYP 200ML', NULL, NULL, NULL, 'SYP', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 1.000, 1.000, NULL, NULL, 90.000, 'SLOW', 'OVERSTOCK', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, 'EXCLUDE', NULL, 1.000, 0.000, '2026-07-05 14:01:55.510', NULL, 1.000, 1.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0111, NULL, NULL, NULL, NULL, NULL, NULL, 'EXCLUDED_ADEQUATE_COVER', 'Excluded: 90.0d cover >= 7d minimum.', 1.000, 1),
    ('B9D42BCE-678E-4A4F-92AC-0000EF9F144A', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C5289020-BEC7-4E74-99EE-19455E7AF5E9', 'B2C18431-173E-4636-B5CE-1764D92BF9BF', '1058E668-2E4C-4F93-B78D-949B1813F922', '18770', 'TRICHUP OIL 200ML', NULL, NULL, NULL, 'LOT', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 1.000, 1.000, NULL, NULL, 90.000, 'SLOW', 'OVERSTOCK', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, 'EXCLUDE', NULL, 1.000, 0.000, '2026-07-05 14:12:54.533', NULL, 1.000, 1.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0111, NULL, NULL, NULL, NULL, NULL, NULL, 'EXCLUDED_ADEQUATE_COVER', 'Excluded: 90.0d cover >= 7d minimum.', 1.000, 1),
    ('A27F8B36-DA0F-41E7-AE2E-000203196C94', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', '905087CF-CA8D-4237-B4FB-94D213F1D503', '5D9E7781-BDE0-48C6-85A7-B0DFB4FCFC84', '15480', 'HELLO BABY FEED BOT 250ML (PREMIUM)', NULL, NULL, NULL, 'CON', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 2.000, 1.000, NULL, NULL, 54.000, 'SLOW', 'OVERSTOCK', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, 'EXCLUDE', NULL, 3.000, 0.000, '2026-07-05 14:17:57.673', NULL, 3.000, 3.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0556, NULL, NULL, NULL, NULL, NULL, NULL, 'EXCLUDED_ADEQUATE_COVER', 'Excluded: 54.0d cover >= 13d minimum.', 5.000, 5),
    ('83A82529-40F6-4D8D-8046-000204BCEA36', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', 'F2C5C224-FD68-435D-8B77-54989EA3D4C8', '5E23690E-2074-41A8-A70D-7727B976EE0D', '5875692', 'VIVEL  SOAP 51GM RS.10', NULL, NULL, NULL, 'SOAP', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, 0.000, NULL, NULL, 0.000, 'NONMOVING', 'OUT', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, 'EXCLUDE', NULL, 0.000, 0.000, '2026-07-05 14:01:53.980', NULL, 0.000, 0.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0000, NULL, NULL, NULL, NULL, NULL, NULL, 'EXCLUDED_NOT_SELLING', 'Excluded: no eligible sales in the rolling window.', 0.000, 0),
    ('8BB41ACF-5B6F-4C74-91F2-000227619EDE', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C5289020-BEC7-4E74-99EE-19455E7AF5E9', 'B2C18431-173E-4636-B5CE-1764D92BF9BF', 'B632265B-F79B-43BC-857A-25CC435E0A07', '5880832', 'VIM LIQ 750ML', NULL, NULL, NULL, 'SOAP', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, 0.000, NULL, NULL, 0.000, 'NONMOVING', 'OUT', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, 'EXCLUDE', NULL, 0.000, 0.000, '2026-07-05 14:12:58.890', NULL, 0.000, 0.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0000, NULL, NULL, NULL, NULL, NULL, NULL, 'EXCLUDED_NOT_SELLING', 'Excluded: no eligible sales in the rolling window.', 0.000, 0),
    ('E5333D46-1EA7-4C17-A66D-00025428AD71', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '98207326-B23E-4F91-A299-E018FAC8EA1B', '14FD2327-950E-4B1B-9057-75A0342A2DBD', '69E66B2B-252E-474F-807E-B377471F8961', '5862631', 'ANORELIEF CREAM  30GM', NULL, NULL, NULL, 'OIN', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 1.000, 1.000, NULL, NULL, 30.000, 'SLOW', 'OVERSTOCK', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, 'EXCLUDE', NULL, 1.000, 0.000, '2026-07-05 15:04:35.500', NULL, 1.000, 1.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0333, NULL, NULL, NULL, NULL, NULL, NULL, 'EXCLUDED_ADEQUATE_COVER', 'Excluded: 30.0d cover >= 13d minimum.', 3.000, 3),
    ('644DED45-E448-4ABB-8084-0002744A52D2', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C6E89C04-55C5-44F8-8464-3E9559ED860E', '47ACF89A-EC30-4201-A663-CA0DA179031D', '7D85621C-2CBE-4A91-8D64-B9CF93C92D6F', '5894382', 'KS B/S [SPARK]  220ML', NULL, NULL, NULL, 'PACK', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 1.000, 1.000, NULL, NULL, 180.000, 'SLOW', 'OVERSTOCK', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, 'EXCLUDE', NULL, 2.000, 0.000, '2026-07-02 17:34:20.960', NULL, 2.000, 2.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0111, NULL, NULL, NULL, NULL, NULL, NULL, 'EXCLUDED_ADEQUATE_COVER', 'Excluded: 180.0d cover >= 13d minimum.', 1.000, 1),
    ('931720FE-9D0C-4591-A3A6-0002B2636303', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'C5289020-BEC7-4E74-99EE-19455E7AF5E9', 'B2C18431-173E-4636-B5CE-1764D92BF9BF', '2AE286C1-5267-44AF-A968-95F8820FE898', '5866044', 'VIMINOX FORTE TAB', NULL, NULL, NULL, 'TAB', 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, 0.000, NULL, NULL, 0.000, 'NONMOVING', 'OUT', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0.000, NULL, NULL, NULL, 0.000, 'EXCLUDE', NULL, 0.000, 0.000, '2026-07-05 14:12:57.317', NULL, 0.000, 0.000, 0.000, 0.000, NULL, NULL, NULL, NULL, NULL, 0.0000, NULL, NULL, NULL, NULL, NULL, NULL, 'EXCLUDED_NOT_SELLING', 'Excluded: no eligible sales in the rolling window.', 0.000, 0);
DROP TABLE IF EXISTS nexora_procurement.`supplier_excel_mapping`;
CREATE TABLE nexora_procurement.`supplier_excel_mapping` (
    `mapping_id` char(36) NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `store_id` char(36) NOT NULL,
    `supplier_code` varchar(50) NOT NULL,
    `supplier_column_name` varchar(150) NOT NULL,
    `column_name` varchar(100) NOT NULL,
    `is_active` tinyint(1) NOT NULL,
    `created_by` varchar(100) NULL,
    `created_at` datetime(3) NOT NULL,
    PRIMARY KEY (`mapping_id`)
);
INSERT INTO nexora_procurement.`supplier_excel_mapping` (`mapping_id`, `tenant_id`, `store_id`, `supplier_code`, `supplier_column_name`, `column_name`, `is_active`, `created_by`, `created_at`) VALUES
    ('3AB53F5A-08B5-4D38-A256-04E377A1E805', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', '1356', 'Product Code', 'supplierproductcode', 1, NULL, '2026-07-04 16:24:41.043'),
    ('C2C298C8-B0A7-459A-A20B-05560F4B92AD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '1356', 'Pack', 'packing', 1, NULL, '2026-07-04 16:24:41.043'),
    ('A4ED3F87-B8BA-4D14-ACC9-073620F22C20', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '754', 'item_name', 'SupplierProductName', 1, NULL, '2026-07-04 16:24:41.043'),
    ('B01F9558-1AA5-4490-BBAF-0CCD61AAD46B', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '754', 'qty', 'stock', 1, NULL, '2026-07-04 16:24:41.043'),
    ('0515EA35-3938-4211-BE01-0D3A07E82795', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '640', 'Pack', 'packing', 1, NULL, '2026-07-04 16:24:41.043'),
    ('DA71E929-4847-45FC-B40F-0D93D0DE7BEB', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', '1391', 'stock', 'stock', 1, NULL, '2026-07-04 16:24:41.043'),
    ('E5A09623-4FCE-4143-93D4-12AFE24F6FFB', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '1356', 'stock', 'stock', 1, NULL, '2026-07-04 16:24:41.043'),
    ('AE8297C1-AF0B-4567-9077-1F684896B732', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', '691', 'free', 'free', 1, NULL, '2026-07-04 16:24:41.043'),
    ('2F473743-F603-4552-9C19-22A71DA25DBE', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '102', 'Total Stock', 'stock', 1, NULL, '2026-07-04 16:24:41.043'),
    ('FFDAC20E-BDED-4ADB-9FA3-26F686161CD5', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', 'AM', 'MRP', 'mrp', 1, NULL, '2026-07-04 16:24:41.043');
DROP TABLE IF EXISTS nexora_procurement.`supplier_stock`;
CREATE TABLE nexora_procurement.`supplier_stock` (
    `supplier_stock_id` char(36) NOT NULL,
    `tenant_id` char(36) NOT NULL,
    `store_id` char(36) NOT NULL,
    `supplier_code` varchar(50) NOT NULL,
    `supplier_product_code` varchar(50) NULL,
    `supplier_product_name` varchar(200) NULL,
    `product_code` varchar(50) NULL,
    `available_stock` double NULL,
    `ptr` decimal(18,2) NULL,
    `mrp` decimal(18,2) NULL,
    `discount` varchar(50) NULL,
    `packing` varchar(50) NULL,
    `free` int NULL,
    `minimum_qty` int NULL,
    `scheme` int NULL,
    `transaction_date` datetime(3) NULL,
    `source` varchar(20) NOT NULL,
    `is_active` tinyint(1) NOT NULL,
    `imported_by` varchar(100) NULL,
    `imported_at` datetime(3) NOT NULL,
    PRIMARY KEY (`supplier_stock_id`)
);
INSERT INTO nexora_procurement.`supplier_stock` (`supplier_stock_id`, `tenant_id`, `store_id`, `supplier_code`, `supplier_product_code`, `supplier_product_name`, `product_code`, `available_stock`, `ptr`, `mrp`, `discount`, `packing`, `free`, `minimum_qty`, `scheme`, `transaction_date`, `source`, `is_active`, `imported_by`, `imported_at`) VALUES
    ('152A7B8E-24F6-4D3E-A491-00024D021520', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '640', '3403', 'ZOMELIS MET 50/500 TAB @ (185.11)', '5855635', 172.0, 203.62, NULL, NULL, '15''S', 0, NULL, 0, NULL, 'legacy', 1, 'legacy-import', '2026-07-04 16:24:40.483'),
    ('FB539ECE-1181-4DA2-BD30-000404150EED', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', '1356', '73608', 'TELCURE CH 40MG TAB', NULL, 4.0, 216.56, NULL, '10', '15''S', 0, NULL, 0, NULL, 'legacy', 1, 'legacy-import', '2026-07-04 16:24:40.323'),
    ('810E0D90-D071-4E6A-A97F-0006AC3CC344', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '754', 'I01815', 'AMLONG H TAB', '23391', 80.0, NULL, NULL, '16% MICRO CARSYON 1', '15''S', NULL, 40, NULL, NULL, 'legacy', 1, 'legacy-import', '2026-07-04 16:24:40.743'),
    ('E012F385-EA23-4CFB-9AD1-00076FE825BA', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', '102', '10111', 'OZOVAS-F TAB', '25810', 1.0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'legacy', 1, 'legacy-import', '2026-07-04 16:24:39.617'),
    ('CEC22934-610A-48CD-BCE0-0007C542728A', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', '1391', '2152', 'MOISTUREX CREAM 100GM (300.00)', '5849688', 40.0, NULL, NULL, '10', NULL, 0, NULL, 0, NULL, 'legacy', 1, 'legacy-import', '2026-07-04 16:24:40.410'),
    ('30D26221-1F2F-4829-A80C-000C49CA454B', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', '1391', '2111', 'MEDERMA ADV PLUS 10GM (MIN 3) (8%)', NULL, 51.0, NULL, NULL, '8', NULL, 0, NULL, 0, NULL, 'legacy', 1, 'legacy-import', '2026-07-04 16:24:40.410'),
    ('87E8D9EF-6D4C-4E43-99A0-0010C28D327C', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', '1391', '2448', 'SAAZ DS TAB (192.90)', '19336', 60.0, NULL, NULL, '12', NULL, 0, NULL, 0, NULL, 'legacy', 1, 'legacy-import', '2026-07-04 16:24:40.420'),
    ('BF78CE9C-8D3B-4C04-A4D3-001490BA39E4', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '3019101A-24A6-4045-AB7E-964046383EA2', '99', '22130', 'TONACT ASP 75', '22130', 24.0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'legacy', 1, 'legacy-import', '2026-07-04 16:24:40.897'),
    ('E5160211-A4FA-4201-AB73-0014C7CCFEEB', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'D55F8A0D-C230-44EA-BF56-02F143B948BD', 'AM', '2968', 'AMODEP AT TAB ', '19844', 769.0, NULL, NULL, NULL, '15''S', NULL, NULL, NULL, NULL, 'legacy', 1, 'legacy-import', '2026-07-04 16:24:40.923'),
    ('D0A75674-3180-4401-B8EC-001A97A9DA17', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 'DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0', '1356', '4068', 'LIPONORM F  (102.18)', '5858207', 20.0, 112.00, NULL, '8', '15''S', 0, NULL, 0, NULL, 'legacy', 1, 'legacy-import', '2026-07-04 16:24:40.230');
DROP TABLE IF EXISTS nexora_sync.`Batches`;
CREATE TABLE nexora_sync.`Batches` (
    `store_id` char(36) NOT NULL,
    `tenant_id` char(36) NULL,
    `BatchCode` int NOT NULL,
    `ProductCode` int NULL,
    `Stock` double NULL,
    `MRP` double NULL,
    `ExpiryDate` datetime(3) NULL,
    `ItemCost` double NULL,
    `PurchasePrice` double NULL,
    `SaleUnit` double NULL,
    `GrnDate` datetime(3) NULL,
    `LastReceivedDate` datetime(3) NULL,
    `LastSaleDate` datetime(3) NULL,
    `SalesTaxCode` int NULL,
    `SupplierCode` varchar(15) NULL,
    `Rate1` double NULL,
    `ReservedStock` double NULL,
    `FreeStock` double NULL,
    `CountedStock` double NULL,
    `StockDiscrepancy` double NULL,
    `StockCorrection` int NULL,
    `PurchaseUnit` double NULL,
    `RetailPrice` double NULL,
    `Margin` double NULL,
    `ManufacturingDate` datetime(3) NULL,
    `InvoiceDate` datetime(3) NULL,
    `InvoiceNumber` varchar(30) NULL,
    `GrnNumber` int NULL,
    `LocationId` int NULL,
    `SubLocation` varchar(50) NULL,
    `RackCode` int NULL,
    `IsLocked` tinyint(1) NULL,
    `BatchLockType` int NULL,
    `OriginalRate` double NULL,
    `OriginalMRP` double NULL,
    `SyncID` int NULL,
    `row_hash` varchar(64) NULL,
    PRIMARY KEY (`store_id`, `BatchCode`)
);
INSERT INTO nexora_sync.`Batches` (`store_id`, `tenant_id`, `BatchCode`, `ProductCode`, `Stock`, `MRP`, `ExpiryDate`, `ItemCost`, `PurchasePrice`, `SaleUnit`, `GrnDate`, `LastReceivedDate`, `LastSaleDate`, `SalesTaxCode`, `SupplierCode`, `Rate1`, `ReservedStock`, `FreeStock`, `CountedStock`, `StockDiscrepancy`, `StockCorrection`, `PurchaseUnit`, `RetailPrice`, `Margin`, `ManufacturingDate`, `InvoiceDate`, `InvoiceNumber`, `GrnNumber`, `LocationId`, `SubLocation`, `RackCode`, `IsLocked`, `BatchLockType`, `OriginalRate`, `OriginalMRP`, `SyncID`, `row_hash`) VALUES
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 9386, 10768, 0.0, 8.4, '2009-03-31 00:00:00.000', 7.18, 7.18, 10.0, NULL, NULL, NULL, 30, NULL, 8.4, 0.0, 0.0, NULL, NULL, 0, 10.0, NULL, NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, 0, 0, NULL, 0.0, NULL, 'be89969215f30c350ac92315402614327725346e77f17b4ed931e635d46e4eb2'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 22895, 25012, 0.0, 4.25, NULL, 2.88, 2.88, 1.0, NULL, NULL, NULL, 36, NULL, 4.25, 0.0, 0.0, NULL, NULL, 0, 1.0, 0.0, 0.0, NULL, NULL, NULL, 0, 1, '', NULL, 0, 0, NULL, 0.0, 0, 'a801fdac493f57b227dd1776244aabdb0119cdd5811382bee16ebb1575dfd390'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 23625, 5, 0.0, 0.0, NULL, 0.0, 0.0, 1.0, NULL, NULL, NULL, 30, NULL, 0.0, 0.0, 0.0, NULL, NULL, 0, 1.0, NULL, NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, 0, 0, NULL, 0.0, NULL, '5465bcceaf69314e33cf378945aae08873fac43888324e015e47f88798f6a3d0'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 23627, 7, 0.0, 0.0, NULL, 0.0, 0.0, 1.0, NULL, NULL, NULL, 30, NULL, 0.0, 0.0, 0.0, NULL, NULL, 0, 1.0, NULL, NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, 0, 0, NULL, 0.0, NULL, '7587ac1d1df3b71d284ad5ede469357fa107a72368bd179125594243847635fa'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 23632, 12, 0.0, 0.0, NULL, 0.0, 0.0, 1.0, NULL, NULL, NULL, 30, NULL, 0.0, 0.0, 0.0, NULL, NULL, 0, 1.0, NULL, NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, 0, 0, NULL, 0.0, NULL, '8677c086e78291135c6ce34d82e0def4f9aea96cb66c2b697793f08e2df214b9'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 23640, 20, 0.0, 0.0, NULL, 0.0, 0.0, 1.0, NULL, NULL, NULL, 30, NULL, 0.0, 0.0, 0.0, NULL, NULL, 0, 1.0, NULL, NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, 0, 0, NULL, 0.0, NULL, '26493acf1d1fd432ebf768cd9dc1f86e079c2e1bd1b818835a5f7721f80d5e47'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 23641, 21, 0.0, 0.0, NULL, 0.0, 0.0, 1.0, NULL, NULL, NULL, 30, NULL, 0.0, 0.0, 0.0, NULL, NULL, 0, 1.0, NULL, NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, 0, 0, NULL, 0.0, NULL, 'a8403237df4d09765d7b6f2c26f7f6267c193abd99888e95516f824206847116'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 23656, 37, 0.0, 0.0, NULL, 0.0, 0.0, 1.0, NULL, NULL, NULL, 30, NULL, 0.0, 0.0, 0.0, NULL, NULL, 0, 1.0, NULL, NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, 0, 0, NULL, 0.0, NULL, '488034dc28e4f18e2b3057ee308cf1cc875c2f8458b8dff599f35de089d96e0d'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 23660, 41, 0.0, 19.8, '2007-03-31 00:00:00.000', 17.93415, 16.23, 10.0, NULL, NULL, NULL, 36, NULL, 19.8, 0.0, 0.0, NULL, NULL, 0, 10.0, 0.0, 0.0, NULL, NULL, NULL, 0, 1, '', NULL, 0, 0, NULL, 0.0, 0, '8781fb4ce997e2a4b50270128a3fe76051759a5badddba25d31c3b52fd4dc33b'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 23666, 47, 0.0, 0.0, NULL, 0.0, 0.0, 1.0, NULL, NULL, NULL, 30, NULL, 0.0, 0.0, 0.0, NULL, NULL, 0, 1.0, NULL, NULL, NULL, NULL, NULL, NULL, 1, NULL, NULL, 0, 0, NULL, 0.0, NULL, 'a5dcd31b4c560a099e0dbffc25e5bc8ebacbe5bfa62d0a4e011790698a84cd13');
DROP TABLE IF EXISTS nexora_sync.`CategoryMaster`;
CREATE TABLE nexora_sync.`CategoryMaster` (
    `store_id` char(36) NOT NULL,
    `tenant_id` char(36) NULL,
    `CategoryCode` varchar(50) NOT NULL,
    `Description` varchar(100) NULL,
    `IsActive` tinyint(1) NOT NULL,
    `row_hash` varchar(64) NULL,
    PRIMARY KEY (`store_id`, `CategoryCode`)
);
INSERT INTO nexora_sync.`CategoryMaster` (`store_id`, `tenant_id`, `CategoryCode`, `Description`, `IsActive`, `row_hash`) VALUES
    ('109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', ' 1', 'VET', 1, '9749410821ef8f2d51efd7f75994f766661300dd4a8b52fdb6c1392c2c8a6287');
DROP TABLE IF EXISTS nexora_sync.`Products`;
CREATE TABLE nexora_sync.`Products` (
    `store_id` char(36) NOT NULL,
    `tenant_id` char(36) NULL,
    `AllowFractions` tinyint(1) NULL,
    `AllowNegativeStock` tinyint(1) NULL,
    `CategoryCode` varchar(50) NULL,
    `CreatedbyUser` varchar(50) NULL,
    `CreationDate` datetime(3) NULL,
    `DivisionCode` varchar(15) NULL,
    `ExpectedMargin` double NULL,
    `FreeQuantity` double NULL,
    `isActive` tinyint NULL,
    `ItemCost` double NULL,
    `ManufacturerCode` varchar(15) NULL,
    `Margin` double NULL,
    `MaximumStockLevel` double NULL,
    `MinimumStockLevel` double NULL,
    `ModifiedbyUser` varchar(50) NULL,
    `ModifiedDate` datetime(3) NULL,
    `MRP` double NULL,
    `OrderDate` datetime(3) NULL,
    `OrderTime` datetime(3) NULL,
    `ProductCode` int NOT NULL,
    `ProductName` varchar(250) NULL,
    `ProductType` int NULL,
    `PurchasePrice` double NULL,
    `PurchaseTaxCode` int NULL,
    `PurchaseUnit` double NULL,
    `Remarks` varchar(100) NULL,
    `ReorderLevel` double NULL,
    `SalePrice` double NULL,
    `SalesTaxCode` int NULL,
    `SaleUnit` double NULL,
    `ScheduleCode` int NULL,
    `SubCategory` varchar(50) NULL,
    `SubLocation` varchar(50) NULL,
    `SupplierCode` varchar(15) NULL,
    `TaxId` int NULL,
    `TotalStock` double NULL,
    `UnitDescription` varchar(200) NULL,
    `DefaultDiscountPercentage` double NULL,
    `ProductLevelDiscount` tinyint(1) NULL,
    `DiscountPerAllowInBill` double NULL,
    `ProductDiscountEligibility` tinyint(1) NULL,
    `row_hash` varchar(64) NULL,
    PRIMARY KEY (`store_id`, `ProductCode`)
);
INSERT INTO nexora_sync.`Products` (`store_id`, `tenant_id`, `AllowFractions`, `AllowNegativeStock`, `CategoryCode`, `CreatedbyUser`, `CreationDate`, `DivisionCode`, `ExpectedMargin`, `FreeQuantity`, `isActive`, `ItemCost`, `ManufacturerCode`, `Margin`, `MaximumStockLevel`, `MinimumStockLevel`, `ModifiedbyUser`, `ModifiedDate`, `MRP`, `OrderDate`, `OrderTime`, `ProductCode`, `ProductName`, `ProductType`, `PurchasePrice`, `PurchaseTaxCode`, `PurchaseUnit`, `Remarks`, `ReorderLevel`, `SalePrice`, `SalesTaxCode`, `SaleUnit`, `ScheduleCode`, `SubCategory`, `SubLocation`, `SupplierCode`, `TaxId`, `TotalStock`, `UnitDescription`, `DefaultDiscountPercentage`, `ProductLevelDiscount`, `DiscountPerAllowInBill`, `ProductDiscountEligibility`, `row_hash`) VALUES
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, '', NULL, '2006-08-01 00:00:00.000', 'UNIVE3', NULL, 0.0, 1, 37.0, 'UNIVE3', 0.0, 0.0, 0.0, 'JANA', '2025-09-22 07:19:08.000', 45.0, NULL, NULL, 2, 'ZENIM CAPS', 1, 37.0, 36, 10.0, '', NULL, 45.0, 36, 10.0, 0, '', NULL, '292', 1, 0.0, 'CAP', 3.0, 1, 10.0, NULL, '26ea984224924770a3c9bbd4e0280e60249ef22da56888c27c9fd1123bd2556d'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, '', NULL, '2006-08-01 00:00:00.000', 'AKUMS', NULL, 0.0, 1, 0.0, 'AKUMS', 19.19, 0.0, 0.0, 'JANA', '2025-09-22 07:19:08.000', 0.0, NULL, NULL, 3, 'DOLOROFF AP tab', 1, 0.0, 36, 10.0, '', NULL, 0.0, 36, 10.0, 0, '', NULL, '119', 1, 0.0, 'TAB', 3.0, 1, 10.0, NULL, '5a8c95c70703be3ea4a48f47483f4654fbdda2c2e456b088564901eb83a01a3c'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, '', NULL, '2006-08-01 00:00:00.000', 'NOVAR', NULL, 0.0, 1, 81.6, 'NOVAR', 25.0, 0.0, 0.0, 'JANA', '2025-09-22 07:19:08.000', 120.25, '2015-09-03 00:00:00.000', '2015-09-03 09:47:32.000', 4, 'VOVERAN SR 75', 1, 85.89, 36, 10.0, '', NULL, 120.25, 36, 10.0, 1, '', 'V035', '292', 1, 10.0, 'TAB', 10.0, 1, 15.0, 1, '8f6ad76b7248cd7b8b1c83674e74bf29801088783c68c9456ec1b9d176ce7578'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, '', NULL, '2006-08-01 00:00:00.000', 'TORRE1', NULL, 0.0, 1, 7.91, 'TORRE1', 21.65, 0.0, 0.0, 'JANA', '2025-09-22 07:19:08.000', 10.09, '2015-05-11 00:00:00.000', '2015-05-11 10:09:33.000', 6, 'UROFLOX 400', 1, 8.15, 36, 10.0, '', NULL, 10.09, 36, 10.0, 1, '', NULL, '292', 1, 0.0, 'TAB', 10.0, 1, 18.0, NULL, '7b95903a315acd2b4bdef33ce1813458306ff836e6273aa7d7df531ea39705c7'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, '', NULL, '2006-08-01 00:00:00.000', 'SHA15', NULL, 0.0, 1, 41.51, 'SHA15', 20.01, 0.0, 0.0, 'JANA', '2025-09-22 07:19:08.000', 57.35, '2016-05-24 00:00:00.000', '2016-05-24 13:59:26.000', 8, 'VALPARIN 200 TAB', 1, 43.69, 36, 15.0, '', NULL, 57.35, 36, 15.0, 1, '', 'V002', '292', 1, 60.0, 'TAB', 10.0, 1, 18.0, NULL, '511124035495138190f4a21886414376c180a98400e02b706160fe631fb25b0d'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, '', NULL, '2006-08-01 00:00:00.000', 'SUN P', NULL, 0.0, 1, 80.08, 'SUN P', 40.34, 0.0, 0.0, 'JANA', '2025-09-22 07:19:08.000', 118.0, '2016-08-05 00:00:00.000', '2016-08-05 11:16:56.000', 9, 'TROPAN 2.5', 1, 84.29, 36, 10.0, '', NULL, 118.0, 36, 10.0, 1, '', 'T074', '107', 1, 20.0, 'TAB', 10.0, 1, 18.0, NULL, '4ecde2959f1143fc917cf925b745ed853e2774827469e2d24838a222e2e73cd1'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, '', NULL, '2006-08-01 00:00:00.000', 'KHAND', NULL, 0.0, 1, 10.38, 'KHAND', 19.98, 0.0, 0.0, 'JANA', '2025-09-22 07:19:08.000', 13.62, '2015-12-24 00:00:00.000', '2015-12-24 16:40:57.000', 10, 'VERMISOL 50MG', 1, 10.38, 36, 1.0, '', NULL, 13.62, 36, 1.0, 0, '', NULL, '120', 1, 0.0, 'TAB', 3.0, 1, 10.0, NULL, '9c638515087e8cc568400263b744238dbf060266775ca9bffc613125fe50b9ae'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, '', NULL, '2006-08-01 00:00:00.000', 'SHA212', NULL, 0.0, 1, 54.39, 'SHA212', 25.0, 0.0, 0.0, 'VIJAYAKUMAR', '2026-06-22 00:00:00.000', 79.63, '2015-06-01 00:00:00.000', '2015-06-01 10:26:42.000', 11, 'STORVAS 10', 1, 60.67, 36, 15.0, '', NULL, 79.63, 36, 15.0, 1, '', 'S040', '292', 1, 102.0, 'TAB', 10.0, 1, 15.0, NULL, '3d44609f892dead9e3aa19e34584ed54b6c6c26e13ca1b174a4c412315312b9c'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, '', NULL, '2006-08-01 00:00:00.000', 'SHA230', NULL, 0.0, 1, 14.69, 'SHA230', 19.98, 0.0, 0.0, 'JANA', '2025-09-22 07:19:08.000', 20.51, '2015-01-17 00:00:00.000', '2015-01-17 11:42:14.000', 13, 'SYSCAN 150', 1, 15.63, 36, 1.0, '', NULL, 20.51, 36, 1.0, 0, '', 'S050', '292', 1, 10.0, 'CAP', 10.0, 1, 18.0, NULL, 'e3e5e16a481bcd3ac0e07077be8a261ae8f6c94863b7a31990b170c88fe7fa2b'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 0, 0, '', NULL, '2006-08-01 00:00:00.000', 'SUN P', NULL, 0.0, 1, 22.95, 'SUN P', 19.99, 0.0, 0.0, 'JANA', '2025-09-22 07:19:08.000', 33.82, '2014-09-12 00:00:00.000', '2014-09-12 14:06:28.000', 14, 'SIZODON 1', 1, 24.16, 36, 10.0, '', NULL, 33.82, 36, 10.0, 1, '', 'S019', '107', 1, 20.0, 'TAB', 10.0, 1, 18.0, NULL, 'b1a52cebada5fdde450c3d43a6d699816ca09ca61be571e5a0882c9e3535c29d');
DROP TABLE IF EXISTS nexora_sync.`ProductSaleInformation`;
CREATE TABLE nexora_sync.`ProductSaleInformation` (
    `store_id` char(36) NOT NULL,
    `tenant_id` char(36) NULL,
    `ID` bigint NOT NULL,
    `ProductCode` int NULL,
    `Quantity` double NULL,
    `TransactionDate` datetime(3) NOT NULL,
    `SeriesTransID` int NULL,
    `TransactionValidity` int NULL,
    `DontConsiderInOrder` tinyint(1) NULL,
    `Bnumber` varchar(50) NOT NULL,
    `SeriesName` char(10) NULL,
    `MRP` double NULL,
    `PurchasePrice` double NULL,
    `DiscountPercentage` double NULL,
    `LastAdjustmentDate` datetime(3) NULL,
    `BillNumber` int NOT NULL,
    `Expirydate` datetime(3) NULL,
    `Batchdescription` varchar(25) NULL,
    `Rate1` double NULL,
    `CostOfSales` double NULL,
    `Batchcode` int NULL,
    `Transactiontime` datetime(3) NULL,
    `ReferenceNumber` varchar(50) NULL,
    `ReferenceDate` datetime(3) NULL,
    `Freequantity` double NULL,
    `Rate` double NULL,
    `Itemcost` double NULL,
    `Transactionamount` double NULL,
    `Discountamount` double NULL,
    `Taxamount` double NULL,
    `Cashdiscount` double NULL,
    `Adjustmenttype` int NULL,
    `ReasonId` int NULL,
    `StockNotAffected` tinyint(1) NULL,
    `Username` varchar(50) NULL,
    `Locationid` int NULL,
    `IsTaxInclusive` tinyint(1) NULL,
    `IsBatchLocked` tinyint(1) NULL,
    `row_hash` varchar(64) NULL,
    PRIMARY KEY (`store_id`, `ID`)
);
INSERT INTO nexora_sync.`ProductSaleInformation` (`store_id`, `tenant_id`, `ID`, `ProductCode`, `Quantity`, `TransactionDate`, `SeriesTransID`, `TransactionValidity`, `DontConsiderInOrder`, `Bnumber`, `SeriesName`, `MRP`, `PurchasePrice`, `DiscountPercentage`, `LastAdjustmentDate`, `BillNumber`, `Expirydate`, `Batchdescription`, `Rate1`, `CostOfSales`, `Batchcode`, `Transactiontime`, `ReferenceNumber`, `ReferenceDate`, `Freequantity`, `Rate`, `Itemcost`, `Transactionamount`, `Discountamount`, `Taxamount`, `Cashdiscount`, `Adjustmenttype`, `ReasonId`, `StockNotAffected`, `Username`, `Locationid`, `IsTaxInclusive`, `IsBatchLocked`, `row_hash`) VALUES
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522355, 5872880, 2.0, '2026-01-06 00:00:00.000', 1, 0, 0, 'C01129001', 'C         ', 48.0, 8.8, 10.0, NULL, 129001, '2028-04-30 00:00:00.000', '504', 45.0, 1.7600000000000002, 1418668, '2026-01-06 07:39:29.000', NULL, NULL, 0.0, 48.0, 8.8, 8.2286, 0.96, 0.2057, 0.0, 0, NULL, 0, 'JOY', 1, 1, 0, '3f869a9caeb09f054985d5bc11a4188493b6e8cee4141cc560f8ddd2bb0dbcf8'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522356, 5883743, 2.0, '2026-01-06 00:00:00.000', 1, 0, 0, 'C01129001', 'C         ', 75.51, 28.95, 10.0, NULL, 129001, '2027-08-31 00:00:00.000', '2903', 75.51, 19.3, 1422370, '2026-01-06 07:39:29.000', NULL, NULL, 0.0, 75.51, 28.95, 43.1486, 5.03, 1.0787, 0.0, 0, NULL, 0, 'JOY', 1, 1, 0, '883cb6e7b57c9da4151f727a56c94972ca6c13d7e0a52ca29bf1916e74b928b3'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522357, 5863490, 2.0, '2026-01-06 00:00:00.000', 1, 0, 0, 'C01129001', 'C         ', 6.0, 3.62, 0.0, NULL, 129001, '2026-11-30 00:00:00.000', '433', 6.0, 5.34, 1415012, '2026-01-06 07:39:29.000', NULL, NULL, 0.0, 6.0, 2.67, 11.4286, 0.0, 0.2857, 0.0, 0, NULL, 0, 'JOY', 1, 1, 0, '671f04fcff621776c562024a36ad35ea050017cbe93b6b25ab8e0018cbd923c4'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522358, 5864112, 1.0, '2026-01-06 00:00:00.000', 1, 0, 0, 'C01129002', 'C         ', 146.41, 104.57, 10.0, NULL, 129002, '2026-12-31 00:00:00.000', 'A0DFY011-', 137.25, 98.3, 1422927, '2026-01-06 07:41:22.000', NULL, NULL, 0.0, 146.41, 98.3, 125.4943, 14.64, 3.1374, 0.0, 0, NULL, 0, 'JOY', 1, 1, 0, 'ab93f5a1d37e14c2a98d992da67f6d31dd36ded5aea3ad0857d7775fcbf99928'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522359, 23126, 15.0, '2026-01-06 00:00:00.000', 1, 0, 0, 'C01129003', 'C         ', 46.85, 33.46, 10.0, NULL, 129003, '2027-07-31 00:00:00.000', 'G75Y021-', 43.92, 31.45, 1420218, '2026-01-06 07:44:40.000', NULL, NULL, 0.0, 46.85, 31.45, 40.1571, 4.69, 1.0039, 0.0, 0, NULL, 0, 'JOY', 1, 1, 0, '0ed99e5d948972561c503ea1d9414b06dda7bf2278dc7dbaaba6c9c2c7e4ce51'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522360, 5856645, 10.0, '2026-01-06 00:00:00.000', 1, 0, 0, 'C01129003', 'C         ', 62.22, 47.41, 10.0, NULL, 129003, '2027-09-30 00:00:00.000', 'E15Y013', 62.22, 44.57, 1423309, '2026-01-06 07:44:40.000', NULL, NULL, 0.0, 62.22, 44.57, 53.3314, 6.22, 1.3333, 0.0, 0, NULL, 0, 'JOY', 1, 1, 0, 'de86ed409d75658034609da2e6a7e9a8d66ef6b5ec1d9b01e84b8d3f43a6452a'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522361, 5878963, 1.0, '2026-01-06 00:00:00.000', 1, 0, 0, 'C01129003', 'C         ', 22.0, 14.59, 0.0, NULL, 129003, '2029-12-31 00:00:00.000', '001', 22.0, 14.59, 1419210, '2026-01-06 07:44:40.000', NULL, NULL, 0.0, 22.0, 14.59, 20.9524, 0.0, 0.5238, 0.0, 0, NULL, 0, 'JOY', 1, 1, 0, 'e97ffc502c1190965f8d6a0a7d8b02ebd96b2b0b6dd1ff41ce2aea7550a2b22a'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522362, 5877333, 1.0, '2026-01-06 00:00:00.000', 1, 0, 0, 'C01129004', 'C         ', 93.0, 68.57, 5.0, NULL, 129004, '2028-10-31 00:00:00.000', '023', 93.0, 68.57, 1419208, '2026-01-06 07:46:48.000', NULL, NULL, 0.0, 93.0, 68.57, 84.1429, 4.65, 2.1036, 0.0, 0, NULL, 0, 'JOY', 1, 1, 0, '44d33b9cea4c8feb1b77edb08d162dbdcdaf4216d4f275909405e71e7b0d5668'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522363, 21914, 1.0, '2026-01-06 00:00:00.000', 1, 0, 0, 'C01129004', 'C         ', 105.0, 92.59, 0.0, NULL, 129004, '2026-11-30 00:00:00.000', 'A11', 105.0, 90.74, 1422106, '2026-01-06 07:46:48.000', NULL, NULL, 0.0, 105.0, 90.74, 100.0, 0.0, 2.5, 0.0, 0, NULL, 0, 'JOY', 1, 1, 0, '357c5005becdef462745b5626a0fe81b4242bf2fe6fbb13b451e260436e945b0'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3522364, 5849937, 1.0, '2026-01-06 00:00:00.000', 1, 0, 0, 'C01129004', 'C         ', 125.0, 91.32, 0.0, NULL, 129004, '2027-10-31 00:00:00.000', '4A5', 111.23, 84.01, 1398270, '2026-01-06 07:46:48.000', NULL, NULL, 0.0, 125.0, 84.01, 119.0476, 0.0, 2.9762, 0.0, 0, NULL, 0, 'JOY', 1, 1, 0, '88739985b3cbe59ec12fa59ed87ac0823585004a73debee892e1dd1bca9e2b95');
DROP TABLE IF EXISTS nexora_sync.`ProductTrans`;
CREATE TABLE nexora_sync.`ProductTrans` (
    `store_id` char(36) NOT NULL,
    `tenant_id` char(36) NULL,
    `ProductCode` int NOT NULL,
    `SaleQuantity` double NULL,
    `StockInHand` double NULL,
    `PurchaseQuantity` double NULL,
    `AdjustmentQuantity` double NULL,
    `LastBillDate` datetime(3) NULL,
    `LastGrnDate` datetime(3) NULL,
    `MonthOfStatistics` datetime(3) NOT NULL,
    `TransferInQuantity` double NULL,
    `TransferOutQuantity` double NULL,
    `OpeningStock` double NULL,
    `OpeningStockValue` double NULL,
    `PurchaseValue` double NULL,
    `PurchaseReturnQuantity` double NULL,
    `SaleValue` double NULL,
    `SaleReturnQuantity` double NULL,
    `AdjustmentValue` double NULL,
    `StockValueAtCostPrice` double NULL,
    `StockValueAtSalePrice` double NULL,
    `CostOfSales` double NULL,
    `SaleTransactionCount` int NULL,
    `PurchaseTransactionCount` int NULL,
    `Syncid` int NULL,
    `row_hash` varchar(64) NULL,
    PRIMARY KEY (`store_id`, `ProductCode`, `MonthOfStatistics`)
);
INSERT INTO nexora_sync.`ProductTrans` (`store_id`, `tenant_id`, `ProductCode`, `SaleQuantity`, `StockInHand`, `PurchaseQuantity`, `AdjustmentQuantity`, `LastBillDate`, `LastGrnDate`, `MonthOfStatistics`, `TransferInQuantity`, `TransferOutQuantity`, `OpeningStock`, `OpeningStockValue`, `PurchaseValue`, `PurchaseReturnQuantity`, `SaleValue`, `SaleReturnQuantity`, `AdjustmentValue`, `StockValueAtCostPrice`, `StockValueAtSalePrice`, `CostOfSales`, `SaleTransactionCount`, `PurchaseTransactionCount`, `Syncid`, `row_hash`) VALUES
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 4, 0.0, 15.0, 0.0, 0.0, '2026-01-17 00:00:00.000', '2026-01-20 00:00:00.000', '2026-02-01 00:00:00.000', 0.0, 0.0, 15.0, 122.39999999999999, 0.0, 0.0, 0.0, 0.0, 0.0, 122.39999999999999, 169.9919, 0.0, 0, 0, NULL, 'b6f4e564880d8d6a2c66f5b6496cafc1c109e6fd5db9422c9a9bbdbfd7a344ba'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 4, 6.0, 9.0, 0.0, 0.0, '2026-03-07 00:00:00.000', '2026-01-20 00:00:00.000', '2026-03-01 00:00:00.000', 0.0, 0.0, 15.0, 122.39999999999999, 0.0, 0.0, 57.9754, 0.0, 0.0, 73.44, 100.2067, 48.96, 1, 0, 0, '8ceecdcf153b04cefa40c5159a57d7a51652d631a5c0da5f92950f4fb7e54688'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 4, 0.0, 9.0, 0.0, 0.0, '2026-03-07 00:00:00.000', '2026-01-20 00:00:00.000', '2026-04-01 00:00:00.000', 0.0, 0.0, 9.0, 73.44, 0.0, 0.0, 0.0, 0.0, 0.0, 73.44, 100.2067, 0.0, 0, 0, NULL, '1e21a6beaa844eae6c1de51f16e72733f6b41080b180ae0b44a503c03e8bba2f'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 4, 19.0, 10.0, 20.0, 0.0, '2026-05-24 00:00:00.000', '2026-05-26 00:00:00.000', '2026-05-01 00:00:00.000', 0.0, 0.0, 9.0, 73.44, 163.2, 0.0, 193.25740000000002, 0.0, 0.0, 81.6, 120.25, 155.04, 2, 2, 0, '3e72b9972a87de97d3785394f6316122332efeef8bcce1f27afe5f048aa2a3f0'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 4, 0.0, 10.0, 0.0, 0.0, '2026-05-24 00:00:00.000', '2026-05-26 00:00:00.000', '2026-06-01 00:00:00.000', 0.0, 0.0, 10.0, 81.6, 0.0, 0.0, 0.0, 0.0, 0.0, 81.6, 120.25, 0.0, 0, 0, NULL, '1f68030ed02e9196270e153020d8de2ad2d0e40367c277b14747e9afe3008fad'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 4, 0.0, 10.0, 0.0, 0.0, '2026-05-24 00:00:00.000', '2026-05-26 00:00:00.000', '2026-07-01 00:00:00.000', 0.0, 0.0, 10.0, 81.6, 0.0, 0.0, 0.0, 0.0, 0.0, 81.6, 120.25, 0.0, 0, 0, NULL, '73745a965f212195fc1fcdbd0b461d5f49634cbbedaafc0c5fa9d29acaed48a9'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 8, 0.0, 14.0, 0.0, 0.0, '2025-12-08 00:00:00.000', '2025-09-06 00:00:00.000', '2026-02-01 00:00:00.000', 0.0, 0.0, 14.0, 38.752, 0.0, 0.0, 0.0, 0.0, 0.0, 38.752, 54.3822, 0.0, 0, 0, NULL, 'e21d12b34ee23ea2be1d36cd95ab37cccadf6d6a5c46d06aa4b94b7ffe1d1803'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 8, 2.0, 12.0, 0.0, 0.0, '2026-03-03 00:00:00.000', '2025-09-06 00:00:00.000', '2026-03-01 00:00:00.000', 0.0, 0.0, 14.0, 38.752, 0.0, 0.0, 6.992, 0.0, 0.0, 33.216, 46.6133, 5.536, 1, 0, 0, '3be096b16dcbed4add8cbdf273efb251f111c895d43f2e0fb3f9ec32337be8dd'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 8, 0.0, 12.0, 0.0, 0.0, '2026-03-03 00:00:00.000', '2025-09-06 00:00:00.000', '2026-04-01 00:00:00.000', 0.0, 0.0, 12.0, 33.216, 0.0, 0.0, 0.0, 0.0, 0.0, 33.216, 46.6133, 0.0, 0, 0, NULL, '92401319436d166e76980146c1cd353f67a9e9fa1af9a4a66412c751e1edc3ff'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 8, 42.0, 45.0, 75.0, 0.0, '2026-05-14 00:00:00.000', '2026-05-15 00:00:00.000', '2026-05-01 00:00:00.000', 0.0, 0.0, 12.0, 33.216, 207.53, 0.0, 146.832, 0.0, 0.0, 124.52999999999999, 183.54, 116.23599999999999, 2, 2, 0, 'fe83aa08dba04c38865b3112142f2e84f033f6ae682c9eff848273018ac38bf4');
DROP TABLE IF EXISTS nexora_sync.`PurchaseTrans`;
CREATE TABLE nexora_sync.`PurchaseTrans` (
    `store_id` char(36) NOT NULL,
    `tenant_id` char(36) NULL,
    `ID` int NOT NULL,
    `ProductCode` int NULL,
    `stockreceived` double NULL,
    `FreeQty` double NULL,
    `ProductDiscPercent` double NULL,
    `itemcost` double NULL,
    `purchaseprice` double NULL,
    `mrp` double NULL,
    `grndate` datetime(3) NOT NULL,
    `InvoiceSeries` char(4) NULL,
    `Grnnumber` int NULL,
    `SaleUnit` double NULL,
    `BatchCode` int NULL,
    `TaxAmount` double NULL,
    `DiscountAmount` double NULL,
    `Margin` double NULL,
    `MarginOnCost` double NULL,
    `MarginOnSale` double NULL,
    `ManufacturerCode` varchar(15) NULL,
    `Username` varchar(50) NULL,
    `LocationId` int NULL,
    `row_hash` varchar(64) NULL,
    `SupplierCode` varchar(15) NULL,
    PRIMARY KEY (`store_id`, `ID`)
);
INSERT INTO nexora_sync.`PurchaseTrans` (`store_id`, `tenant_id`, `ID`, `ProductCode`, `stockreceived`, `FreeQty`, `ProductDiscPercent`, `itemcost`, `purchaseprice`, `mrp`, `grndate`, `InvoiceSeries`, `Grnnumber`, `SaleUnit`, `BatchCode`, `TaxAmount`, `DiscountAmount`, `Margin`, `MarginOnCost`, `MarginOnSale`, `ManufacturerCode`, `Username`, `LocationId`, `row_hash`, `SupplierCode`) VALUES
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779663, 5883521, 1.0, 0.0, 2.0, 456.78, 466.1, 625.0, '2024-04-27 00:00:00.000', 'IV  ', 802, 1.0, 1313049, 82.22, 9.322, 12.0, 13.64, 12.0, NULL, 'PRADEEP', 1, '6d579cdb1f179145f54798b4426dcbf28b9fd30140d137958f51aae9d60105dc', '109'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779664, 5870000, 2.0, 0.0, 5.0, 279.58, 294.29, 412.0, '2024-04-27 00:00:00.000', 'IV  ', 802, 15.0, 1300114, 33.55, 29.429, 20.0, 25.0, 20.0, 'BERGE', 'PRADEEP', 1, 'ed3a4788bb45cf1bd8956dfa8ff220a5e3bff37bfac9d6b3eef4ac8516cdf485', '109'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779665, 5883982, 1.0, 0.0, 5.0, 128.25, 135.0, 189.0, '2024-04-27 00:00:00.000', 'IV  ', 802, 10.0, 1306262, 15.39, 6.75, 20.0, 25.0, 20.0, 'ALKEM', 'PRADEEP', 1, 'f555cfe807bda3d3a67f844c9d8ca5abb263b39b345e28f9433aa5a7d10b02f3', '109'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779666, 5865185, 1.0, 0.0, 5.0, 539.09, 567.46, 837.0, '2024-04-27 00:00:00.000', 'IV  ', 802, 1.0, 1312827, 97.03, 28.373, 20.0, 25.0, 20.0, 'IPCA 1', 'PRADEEP', 1, '0174bb04ac36c15e3e77d65e7b88ce71abce468646802b71d8df53e2fe948831', '109'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779667, 14176, 1.0, 0.0, 0.0, 125.53, 132.14, 185.0, '2024-04-27 00:00:00.000', 'IV  ', 803, 1.0, 1313875, 15.07, 0.0, 20.0, 25.0, 20.0, 'SHA103', 'PRADEEP', 1, '7633c32f35f9fa63deaa6571db74ec7f31e595511cc8cf92583dc7b9cd1f18e9', '107'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779668, 5880896, 1.0, 0.0, 0.0, 205.85, 218.99, 300.0, '2024-04-27 00:00:00.000', 'IV  ', 804, 1.0, 1312811, 24.7, 0.0, 18.24, 22.31, 18.24, 'DERMA', 'PRADEEP', 1, '1ed612a04fc0222e46a38f92ef0b6e2808d015a45fc20591106bd0643075d17c', 'SMMA'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779669, 5866811, 3.0, 0.0, 0.0, 120.86, 128.57, 180.0, '2024-04-27 00:00:00.000', 'IV  ', 804, 10.0, 1304844, 14.5, 0.0, 20.0, 25.0, 20.0, '12345', 'PRADEEP', 1, '7a07b3e92a95b8c08380d9a529a64d5777d604c1ef51fb93884c9841bd6d1130', 'SMMA'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779670, 5883916, 3.0, 0.0, 0.0, 126.9, 135.0, 189.0, '2024-04-27 00:00:00.000', 'IV  ', 804, 15.0, 1310154, 15.23, 0.0, 20.0, 25.0, 20.0, 'LIA', 'PRADEEP', 1, 'd90f04b430a572d5b81e359336e5499b09ab8f40711e820e0a3a6d0a7960b897', 'SMMA'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779671, 22180, 1.0, 0.0, 0.0, 151.92, 161.62, 226.27, '2024-04-27 00:00:00.000', 'IV  ', 804, 10.0, 1313876, 18.23, 0.0, 20.0, 25.0, 20.0, 'SERDI1', 'PRADEEP', 1, '6948322297848af00e26bf0642ca700b4a80dd8cea98e5f0601a8bb715094ad7', 'SMMA'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 779672, 5875467, 1.0, 0.0, 0.0, 70.17, 74.65, 104.5, '2024-04-27 00:00:00.000', 'IV  ', 805, 10.0, 1306275, 8.42, 0.0, 19.99, 24.99, 19.99, 'EAST 1', 'PRADEEP', 1, 'f1310c7eeea93f907897641ebe914d52b935d8b521b893c1355e58978fe2bb56', 'SMMA');
DROP TABLE IF EXISTS nexora_sync.`SaleInformation`;
CREATE TABLE nexora_sync.`SaleInformation` (
    `store_id` char(36) NOT NULL,
    `tenant_id` char(36) NULL,
    `BillDate` datetime(3) NOT NULL,
    `BillNumber` int NOT NULL,
    `BNumber` varchar(50) NOT NULL,
    `BillAmount` double NULL,
    `CustomerName` varchar(120) NULL,
    `DeliverySalesRep` int NULL,
    `Billtime` datetime(3) NULL,
    `CustomerCode` varchar(50) NULL,
    `row_hash` varchar(64) NULL,
    PRIMARY KEY (`store_id`, `BillDate`, `BNumber`)
);
INSERT INTO nexora_sync.`SaleInformation` (`store_id`, `tenant_id`, `BillDate`, `BillNumber`, `BNumber`, `BillAmount`, `CustomerName`, `DeliverySalesRep`, `Billtime`, `CustomerCode`, `row_hash`) VALUES
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129001, 'C01129001', 66.0, 'mithun  ', 78, '2026-01-06 07:39:29.000', '0', 'e9461a8b569bb70f251d82b4eb94d3e06c7cbde0d72433740613f77b29583186'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129002, 'C01129002', 132.0, 'r  revathy  ', 78, '2026-01-06 07:41:22.000', '0', '60f9563b65be47eddb83c6e14a8716a5785920d22230a908fc07d521e7f55bb7'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129003, 'C01129003', 120.0, 'ravi    ', 78, '2026-01-06 07:44:40.000', '0', '0e0695f7d66ce3bd463c0b463712b718cd79535e26e9fb8484d7f2ac2dfb7773'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129004, 'C01129004', 318.0, 'gopi  ', 78, '2026-01-06 07:46:48.000', '0', 'b658657faaeeed1eeb9a6b51ad8b00084b708407f459aac73c4d7d38dc25de57'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129005, 'C01129005', 581.0, 'ravi     ', 78, '2026-01-06 07:56:18.000', '0', '5845e46f346d862b5b884974c28ff92fe903f7c73386ba6f5ba9843edf41696d'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129006, 'C01129006', 177.0, 'selvaraj', 78, '2026-01-06 08:08:01.000', '0', '3c37c4d63586bec1ec11973facdb9f207491c6cb349cd24cdb617449c5c390dd'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129007, 'C01129007', 57.0, 'priya  ', 78, '2026-01-06 08:10:52.000', '0', '5f356710855926f7a101f3529de5e6f9435c31fbfa650441193c2a09a57988af'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129008, 'C01129008', 127.0, 'kerthish ', 78, '2026-01-06 08:17:21.000', '0', 'b964907f5c4017f44d5e57edaeafe62ea8eead8159a9e8a9718e5121e2459b6a'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129009, 'C01129009', 725.0, 'nithiya  ', 78, '2026-01-06 08:21:27.000', '0', '8e076bc8fec749a4f1b142c5f85834b34c4389b529946c912873c0ef459f072f'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '2026-01-06 00:00:00.000', 129010, 'C01129010', 526.0, 'guna   ', 78, '2026-01-06 08:24:27.000', '0', '9482d62503571bdd3e77b6506666624cfc5804a9449f24e85a5a278d7023bcf2');
DROP TABLE IF EXISTS nexora_sync.`SalesRep`;
CREATE TABLE nexora_sync.`SalesRep` (
    `store_id` char(36) NOT NULL,
    `tenant_id` char(36) NULL,
    `Salesmancode` int NOT NULL,
    `Salesmanname` varchar(30) NOT NULL,
    `row_hash` varchar(64) NULL,
    `isActive` tinyint(1) NULL,
    PRIMARY KEY (`store_id`, `Salesmancode`)
);
INSERT INTO nexora_sync.`SalesRep` (`store_id`, `tenant_id`, `Salesmancode`, `Salesmanname`, `row_hash`, `isActive`) VALUES
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 1, 'NEW', '27cd9ba0be075120db9cf3125cbe2496904cf6151d6267ca2ec88c661ae2e41f', 1),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 2, '~PUNITHA', '367b9b523c22e303181966909653743f9150dc21e9bb5a7fbe7a27a622b94be4', 0),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 3, 'SALMAN', 'b340bd35a1bc39f8143b5b03aea7671d1fd8aef9e5b851dcc151494e3b7d584a', 1),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 4, '~M.SHANKAR', '619a4eac01f35395d4a93b510b88859672e67e01005521e836d2d246b15f26ba', 0),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 5, '~MASTHAN ', 'c5d40ecdd3f961851f7bc336244e24d48ec18c0ecdb26787251bc2cce0e6cf21', 0),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 6, '~ANEESH', '369a69a9f9baaaa281283e9e7e82f4eddd4a7e58e0aa2370c92758e9354a9115', 0),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 7, '~GOPAL', '6d1275679b0fa4dc8d97c3cfcb19770fa83541d4f7a9d88434177a9c50c99f8f', 0),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 8, '~PONVENTHAN', '4a772086c43fe41aa21a7ca19e62ec5229dd80fe4a35ac6a256d4ed5c8ce5bee', 0),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 9, '~GOKUL', 'c2357dba5108dc12309a23e2a0a58ceb2044b567237a0dcef4fa3e6f2f2e1283', 0),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 10, '~MOHANAPRIYAN', 'c647628042870dcb26153643437602e532c6b8709eb447e7d728fe8d18b7bde7', 0);
DROP TABLE IF EXISTS nexora_sync.`SupplierProductMatch`;
CREATE TABLE nexora_sync.`SupplierProductMatch` (
    `store_id` char(36) NOT NULL,
    `tenant_id` char(36) NULL,
    `SupplierCode` varchar(15) NOT NULL,
    `SupplierProductCode` varchar(50) NOT NULL,
    `SupplierProductName` varchar(250) NULL,
    `ProductCode` int NULL,
    `UserName` varchar(50) NULL,
    `LastModifiedDate` datetime(3) NULL,
    `IsActive` tinyint(1) NULL,
    `row_hash` varchar(64) NULL,
    PRIMARY KEY (`store_id`, `SupplierCode`, `SupplierProductCode`)
);
INSERT INTO nexora_sync.`SupplierProductMatch` (`store_id`, `tenant_id`, `SupplierCode`, `SupplierProductCode`, `SupplierProductName`, `ProductCode`, `UserName`, `LastModifiedDate`, `IsActive`, `row_hash`) VALUES
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '1015', '10003', 'RIVOTRIL 5MG TAB', 2195, NULL, NULL, NULL, '62a305e653e7e3bb8d2549362cc873f60bd937d9ff20db29bf3a67f1b106a471'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '1015', '10011', 'DILZEM 30MG TAB  ', 2789, NULL, NULL, NULL, '8c2fc2a1ad7ec6eaee465ea8955f3f65d8b690147a3ea555bc11871403a3ea40'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '1015', '10016', 'QUADRIDERM 10GM CREAM  ', 5105, NULL, NULL, NULL, 'db0c2d1a079baeb77ac5999853abef6f53c3ae1ccd7e2473f870479af061977c'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '1015', '10024', 'SILVEREX 10GM  ', 20808, NULL, NULL, NULL, '935dc60ae89ca5276e0585293f1018080d3ddb6b9086a79e611d803db8ebb35e'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '1015', '10033', 'SPORIDEX REDIMEX 250MG SYRUP  ', 26106, NULL, NULL, NULL, '9fab47b48210b2047c648c59fce26521f57248fa027718cbd0b591a411e90589'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '1015', '10037', 'WIKORYL SY  ', 3536, NULL, NULL, NULL, 'ebafd93b0bb88e73ecde7b693ed3863c13138b1d973fc643869bbfe8b986615a'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '1015', '10040', 'ANDIAL TAB  ', 770, NULL, NULL, NULL, '1b007064ddba037154d92ab590eab852ef8a3c9a8a104b3c9ad83622b256b59a'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '1015', '10044', 'FEPANIL 125MG SYRUP  ', 4785, NULL, NULL, NULL, 'dc504353b410055d0bb37a0aadbb57996756a3e3d586367b1d8eb577a75fc20f'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '1015', '10045', 'FEPANIL 650MG TAB  ', 2577, NULL, NULL, NULL, 'e8b1e591ad48604c5fff51918f3df6cef952594ecff3a5d2a6d0ae0f9443ef6e'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '1015', '10046', 'FEPANIL 500MG TAB  ', 6405, NULL, NULL, NULL, '65933ce0b7dbd6a8f1621dc9880f0363ed2ab98a95659842631753a0135d3388');
DROP TABLE IF EXISTS nexora_sync.`Suppliers`;
CREATE TABLE nexora_sync.`Suppliers` (
    `store_id` char(36) NOT NULL,
    `tenant_id` char(36) NULL,
    `suppliercode` varchar(15) NOT NULL,
    `suppliername` varchar(200) NOT NULL,
    `mobilenumber` varchar(50) NULL,
    `email` varchar(40) NULL,
    `isActive` tinyint(1) NULL,
    `row_hash` varchar(64) NULL,
    `Abbreviation` varchar(5) NULL,
    `Address1` varchar(250) NULL,
    `Address2` varchar(250) NULL,
    `Address3` varchar(250) NULL,
    `State` varchar(50) NULL,
    `Pincode` varchar(15) NULL,
    `Tngstnumber` varchar(50) NULL,
    `GSTNumber` varchar(15) NULL,
    PRIMARY KEY (`store_id`, `suppliercode`)
);
INSERT INTO nexora_sync.`Suppliers` (`store_id`, `tenant_id`, `suppliercode`, `suppliername`, `mobilenumber`, `email`, `isActive`, `row_hash`, `Abbreviation`, `Address1`, `Address2`, `Address3`, `State`, `Pincode`, `Tngstnumber`, `GSTNumber`) VALUES
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '.', 'RAJ PHARMACEUTICALS', '9443349355', '', 1, '642c3dfe9a5376bf44b7f77e3bbeb003af3759c8fdc0a9a82e49d8d92c9de281', '', '5/17 UMA NAGAR SARADHA COLLEG ROAD SALEM-7', '', '', NULL, '636007', '', NULL),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '001', 'S.K. AGENCY', NULL, NULL, 1, 'd85fae34f09839d418281215338abbe73aa3068af6287d54c2c6a19e3984dd26', NULL, '', '', '', NULL, '', NULL, NULL),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '006', 'SHARADHA MEDICALS (GUGAI)', NULL, NULL, 1, 'b6c6f4359a180972b674e1261c7cab159fa24efa05d9451ca99e0150b5375d4a', NULL, '450, TRICHY MAINROAD, GUGAI, SALEM', '', '', NULL, '636006', NULL, NULL),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '012', 'SHARADHA MEDICALS', '9994477499', NULL, 1, '56a07128a5349a13bbf7960ed234c201bcee73eda9294f7e27b2c9e79ca80bc7', NULL, '8/C-1 OMALUR MAIN ROAD                               FOUR ROADS SALEM-9', '', '', NULL, '636009', '', NULL),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '0123', 'SRREE SENTHIL AGENCIES', '', '', 1, 'bb309f8e5c9dec60701ce88dd864742911870ba6f7ae63fed04d5a94f18f181e', '', 'VASANTHA BAVAN NR, PERIYAR ST,', '', '', '1', '638001', '', '33ABJPC6328F1Z0'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '10', 'SRI MAHA TRADERS', '9095520702', NULL, 1, '9e220387065208e791e8af6c6432ed03d9d6914a2214ac21dbd4d82e799b7130', NULL, 'H.O.12/183-PERUMPARAPPU V.KARUKAMPALAYAM POST SIVAGIRI-638109', NULL, NULL, NULL, NULL, NULL, NULL),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '100', 'MADHV TRADERS', NULL, NULL, 1, '680ad11622b53f3fbb24240bba0f95d6366270f2e6fdd5a0b5b0753c6428f6bb', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '1000', 'VISWANATHAM STORES', '', NULL, 1, '4cf30ff72569fa0b69bf81cf7a1d491e9997c6ee5a262479c3834d6696695aee', NULL, '289,MAINROAD,SHEVAPET, SALEM-2.', '', '', NULL, '636002', '', NULL),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '10005', 'SRI SENTHIL STORES', '9842956477', NULL, 1, '74429619656ae5a96c2e2ddec2a34fc2af70d6330ef92bea0aaaf1793016ff69', NULL, 'C-3,CHOKAN KAADU, MAIN ROAD,SHEVAPET-SALEM -636002', '', '', NULL, '636002', '', NULL),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '1001', 'JAYA SHREE PHARMAA', '9943952888', NULL, 1, '19de8526d76fae824c8962c55f719f6f9d4ece2cf33fdd2a60a0ed2dea63d894', NULL, '22/16A,KANDAR HOSTEL ROAD, NAMAKKAL .', '', '', NULL, '', '', NULL);
DROP TABLE IF EXISTS nexora_sync.`Suppliertrans`;
CREATE TABLE nexora_sync.`Suppliertrans` (
    `store_id` char(36) NOT NULL,
    `tenant_id` char(36) NULL,
    `Suppliercode` varchar(15) NOT NULL,
    `MonthOfStatistics` datetime(3) NOT NULL,
    `Transactionid` int NULL,
    `Purchasevaluetoday` double NULL,
    `Purchasevalueuptopreviousday` double NULL,
    `Purchasevalueuptopreviousmonth` double NULL,
    `Taxpaiduptopreviousmonth` double NULL,
    `Lastbill` varchar(20) NULL,
    `Openingbalance` double NULL,
    `Closingbalance` double NOT NULL,
    `Salevalue` double NULL,
    `LastGRNDate` datetime(3) NULL,
    `PurchaseCount` int NULL,
    `UnAdjustedReturnCount` int NULL,
    `SupplierDCCount` int NULL,
    `NoOfPendingCreditDebitNote` int NULL,
    `PendingCreditDebitNoteValue` double NULL,
    `NoOfPendingCheques` int NULL,
    `NoOfPendingInvoices` int NOT NULL,
    `PendingAcknowledgementQty` double NULL,
    `PendingAcknowledgementValue` double NULL,
    `row_hash` varchar(64) NULL,
    PRIMARY KEY (`store_id`, `Suppliercode`, `MonthOfStatistics`)
);
INSERT INTO nexora_sync.`Suppliertrans` (`store_id`, `tenant_id`, `Suppliercode`, `MonthOfStatistics`, `Transactionid`, `Purchasevaluetoday`, `Purchasevalueuptopreviousday`, `Purchasevalueuptopreviousmonth`, `Taxpaiduptopreviousmonth`, `Lastbill`, `Openingbalance`, `Closingbalance`, `Salevalue`, `LastGRNDate`, `PurchaseCount`, `UnAdjustedReturnCount`, `SupplierDCCount`, `NoOfPendingCreditDebitNote`, `PendingCreditDebitNoteValue`, `NoOfPendingCheques`, `NoOfPendingInvoices`, `PendingAcknowledgementQty`, `PendingAcknowledgementValue`, `row_hash`) VALUES
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '.', '2024-04-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, '50081a280b0b8fdfe37738a14328d24df735145ef3d299440482709192572ce9'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '.', '2024-05-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, '608bec6b18b0a95cbb9d5b02b542cc01e9a610148a25d0e44a0e9f7f64992507'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '.', '2024-06-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, 'e31fa6736bff1c68b7105db282d6a3430107d18cae086f0a1bf103b0e6569d40'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '.', '2024-07-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, '7bd48f17a5fea96f0d04d3d9a970a85e16b3e818c44eb4495a4bd173c599e512'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '.', '2024-08-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, '545734a94024199debfd8374f3bf1e422c0071aef08fad68ba82bace463b599e'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '.', '2024-09-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, '080cc1853e4232eacd84bb2e9b656cbbdae41c20d24d2da84f60de3c691c4d05'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '.', '2024-10-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, '12e107925b6c71a193f3dd6c1ee780935855c767d3c885239e822955ad117abb'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '.', '2024-11-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, '4c7fd7fbf9ca246126b95fd60bcc8b2f80a95c74e742b7b49df9cbc0d9ca5aff'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '.', '2024-12-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, 'e7794434a0fc672cb0a64f56cc9517e16de4c9cb01f2834ae049118e63b39a6c'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', '.', '2025-01-01 00:00:00.000', NULL, 0.0, 0.0, 0.0, 0.0, NULL, 0.0, 0.0, NULL, NULL, NULL, 0, 0, 0, 0.0, 0, 0, 0.0, 0.0, '86b4e959f6c2c03f0946b8e9eb09f5a6fef11c238ade05f17899cb28365a951a');
DROP TABLE IF EXISTS nexora_sync.`sync_column_mapping`;
CREATE TABLE nexora_sync.`sync_column_mapping` (
    `mapping_id` char(36) NOT NULL,
    `sync_table_id` char(36) NOT NULL,
    `table_name` varchar(128) NOT NULL,
    `column_name` varchar(128) NOT NULL,
    `data_type` varchar(100) NULL,
    `is_selected` tinyint(1) NOT NULL,
    `is_pk` tinyint(1) NOT NULL,
    `is_hash` tinyint(1) NOT NULL,
    `is_watermark` tinyint(1) NOT NULL,
    `column_order` int NOT NULL,
    `created_at` datetime(3) NOT NULL,
    PRIMARY KEY (`mapping_id`)
);
INSERT INTO nexora_sync.`sync_column_mapping` (`mapping_id`, `sync_table_id`, `table_name`, `column_name`, `data_type`, `is_selected`, `is_pk`, `is_hash`, `is_watermark`, `column_order`, `created_at`) VALUES
    ('22E446D6-661F-4D07-BECF-004B491740FF', '03419296-12CB-4D9E-88E6-1A3C3E9AB4CA', 'SalesRep', 'Salesmancode', 'int', 1, 1, 1, 0, 1, '2026-06-25 18:10:11.837'),
    ('A59D80EE-1C0E-43D3-8D3E-007C9C46A8E2', 'D192DC62-B6C6-4346-AC57-C66C857CA22B', 'SaleInformation', 'BillNumber', 'int', 1, 0, 1, 0, 2, '2026-06-20 19:48:58.967'),
    ('A26F1097-89B7-41AB-A861-0154FB869F05', 'AB0E2EB2-0F7C-4DB7-82C7-64D9A7C28D65', 'Suppliertrans', 'Taxpaiduptopreviousday', 'float', 0, 0, 0, 0, 8, '2026-06-25 18:13:23.160'),
    ('D089C4ED-CC83-45FD-B3B3-02472A3FAC8D', '37193197-252C-4D8F-AA42-12F2EF0982CE', 'PurchaseTrans', 'InvoiceSeries', 'char', 1, 0, 1, 0, 36, '2026-06-20 19:48:58.967'),
    ('28648B74-1FC8-4339-B3D2-0249C873CA13', 'FB9F14B0-A914-460D-910E-29D867148CE4', 'Suppliers', 'suppliername', 'nvarchar', 1, 0, 1, 0, 2, '2026-06-20 19:48:58.967'),
    ('CBF26E52-9FD6-4025-8C73-02B3920F029E', 'FB9F14B0-A914-460D-910E-29D867148CE4', 'Suppliers', 'Pincode', 'varchar', 1, 0, 0, 0, 10, '2026-06-25 18:17:45.147'),
    ('019CCF4F-F82C-4DF3-83FD-02F7C869A12B', 'E62CE414-0247-4AB3-B03C-BCB3B30FFA99', 'ProductSaleInformation', 'SeriesTransID', 'int', 1, 0, 1, 0, 5, '2026-06-20 19:48:58.967'),
    ('880AA278-8291-48ED-9C78-04CEFC2276ED', 'D192DC62-B6C6-4346-AC57-C66C857CA22B', 'SaleInformation', 'CustomerCode', 'varchar', 1, 0, 1, 0, 8, '2026-06-20 19:48:58.967'),
    ('805CF9BC-9DF4-4495-BB9F-06924B2D40BF', '57E8BE86-979C-467C-B0B2-7D83AAE14CB4', 'products', 'isActive', 'tinyint', 1, 0, 1, 0, 9, '2026-06-20 19:48:58.967'),
    ('690EE886-A880-4AB2-8894-071969CCBD9D', '57E8BE86-979C-467C-B0B2-7D83AAE14CB4', 'products', 'OrderDate', 'datetime', 1, 0, 0, 0, 18, '2026-06-20 19:48:58.967');
DROP TABLE IF EXISTS nexora_sync.`sync_schema_catalog`;
CREATE TABLE nexora_sync.`sync_schema_catalog` (
    `catalog_id` char(36) NOT NULL,
    `schema_name` varchar(128) NOT NULL,
    `table_name` varchar(128) NOT NULL,
    `column_name` varchar(128) NOT NULL,
    `data_type` varchar(100) NOT NULL,
    `max_length` int NULL,
    `precision_value` int NULL,
    `scale_value` int NULL,
    `is_nullable` tinyint(1) NOT NULL,
    `is_identity` tinyint(1) NOT NULL,
    `is_primary_key` tinyint(1) NOT NULL,
    `ordinal_position` int NOT NULL,
    `first_discovered_store_id` char(36) NULL,
    `first_discovered_at` datetime(3) NOT NULL,
    `last_discovered_at` datetime(3) NOT NULL,
    `is_active` tinyint(1) NOT NULL,
    PRIMARY KEY (`catalog_id`)
);
INSERT INTO nexora_sync.`sync_schema_catalog` (`catalog_id`, `schema_name`, `table_name`, `column_name`, `data_type`, `max_length`, `precision_value`, `scale_value`, `is_nullable`, `is_identity`, `is_primary_key`, `ordinal_position`, `first_discovered_store_id`, `first_discovered_at`, `last_discovered_at`, `is_active`) VALUES
    ('79B8B352-4A99-41C5-800C-0000D078F702', 'dbo', 'product130123', 'MaximumStockLevel', 'float', 8, 53, 0, 1, 0, 0, 22, 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '2026-06-23 18:56:56.443', '2026-07-04 19:42:12.987', 1),
    ('BC8BB584-1D45-4730-A0F5-0001A89B3F49', 'dbo', 'Ins_MproformaSaleInformation', 'DeliverySalesRep', 'int', 4, 10, 0, 1, 0, 0, 79, '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-20 16:08:57.053', '2026-07-04 19:42:12.987', 1),
    ('130FA43E-19F8-41C7-8DEA-0001C723F013', 'dbo', 'SUBMISSIONINFO', 'SenderID', 'varchar', 50, 0, 0, 1, 0, 0, 10, '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-20 16:09:11.593', '2026-07-04 19:42:12.987', 1),
    ('A6E4BD0C-B021-473E-ADF2-000309A47CCF', 'dbo', 'BarcodePrintSettings', 'PaperLeftmargin', 'float', 8, 53, 0, 1, 0, 0, 6, '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-20 16:08:32.117', '2026-07-04 19:42:12.987', 1),
    ('6DF74ADF-DCF3-4205-BE29-0003581D99FE', 'dbo', 'PriceRevisionDetail', 'OldRate', 'float', 8, 53, 0, 1, 0, 0, 12, '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-20 16:09:04.200', '2026-07-04 19:42:12.987', 1),
    ('16E5E1E6-ADD5-4C3D-9EE0-0004853A36A5', 'dbo', 'WSServiceOutletConfig', 'ModifiedOn', 'datetime', 8, 23, 3, 1, 0, 0, 10, '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-20 16:09:18.190', '2026-07-04 19:42:12.987', 1),
    ('9255E1FE-9B51-42C0-B9DD-00051953FCE0', 'dbo', 'dvw_SPendingPayments', 'TransactionTime', 'datetime', NULL, NULL, NULL, 1, 0, 0, 20, '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-20 16:08:51.667', '2026-06-20 16:31:49.960', 1),
    ('538955CA-50D1-45D8-A2FD-0005BF04E855', 'dbo', 'suppliers_260525', 'CreatedAtStoreCode', 'int', 4, 10, 0, 1, 0, 0, 148, 'FCBE8B35-B1A1-463E-80C6-73161CDC8F32', '2026-06-23 18:56:56.443', '2026-07-04 18:15:17.733', 1),
    ('B81D7E0C-C487-4A31-9FC9-00066B1F4427', 'dbo', 'dvw_SaleInformation_STK', 'Deliverytype', 'int', NULL, 10, 0, 1, 0, 0, 33, '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-20 16:08:50.527', '2026-06-20 16:31:49.960', 1),
    ('24DBC477-3BFD-4975-AD87-000690689EDE', 'dbo', 'dvw_CPaymentAdjustmentforApproval', 'ReceiptDate', 'datetime', NULL, NULL, NULL, 0, 0, 0, 6, '109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1', '2026-06-20 16:08:41.260', '2026-06-20 16:31:49.960', 1);
DROP TABLE IF EXISTS nexora_sync.`sync_table_master`;
CREATE TABLE nexora_sync.`sync_table_master` (
    `sync_table_id` char(36) NOT NULL,
    `table_name` varchar(128) NOT NULL,
    `is_active` tinyint(1) NOT NULL,
    `sync_mode` varchar(50) NOT NULL,
    `watermark_column` varchar(128) NULL,
    `window_days` int NULL,
    `window_months` int NULL,
    `custom_where` varchar(1000) NULL,
    `sync_order` int NOT NULL,
    `created_at` datetime(3) NOT NULL,
    PRIMARY KEY (`sync_table_id`)
);
INSERT INTO nexora_sync.`sync_table_master` (`sync_table_id`, `table_name`, `is_active`, `sync_mode`, `watermark_column`, `window_days`, `window_months`, `custom_where`, `sync_order`, `created_at`) VALUES
    ('37193197-252C-4D8F-AA42-12F2EF0982CE', 'PurchaseTrans', 1, 'ROLLING_WINDOW', 'GrnDate', 800, NULL, NULL, 5, '2026-06-19 17:26:24.783'),
    ('03419296-12CB-4D9E-88E6-1A3C3E9AB4CA', 'SalesRep', 1, 'UPSERT', NULL, NULL, NULL, NULL, 0, '2026-06-25 18:09:58.117'),
    ('30DBE7F6-4931-4815-82EA-1A878DFC9AFE', 'CategoryMaster', 1, 'UPSERT', NULL, NULL, NULL, NULL, 0, '2026-06-25 18:19:38.467'),
    ('FB9F14B0-A914-460D-910E-29D867148CE4', 'Suppliers', 1, 'UPSERT', NULL, NULL, NULL, NULL, 8, '2026-06-19 17:26:24.783'),
    ('AB0E2EB2-0F7C-4DB7-82C7-64D9A7C28D65', 'Suppliertrans', 1, 'UPSERT', NULL, NULL, NULL, NULL, 0, '2026-06-25 18:12:35.080'),
    ('57E8BE86-979C-467C-B0B2-7D83AAE14CB4', 'Products', 1, 'UPSERT', NULL, NULL, NULL, NULL, 1, '2026-06-19 17:26:24.783'),
    ('17E0FF14-65E2-4326-A0AA-86D26A6F0CCF', 'SupplierProductMatch', 1, 'UPSERT', NULL, NULL, NULL, NULL, 7, '2026-06-19 17:26:24.783'),
    ('7B5CAD8D-0F3B-49E2-BB83-B2C5D741AB75', 'ProductTrans', 1, 'ROLLING_WINDOW', 'MonthOfStatistics', 180, NULL, NULL, 6, '2026-06-19 17:26:24.783'),
    ('329BA141-4E4D-4534-A323-BBD97A0F97E9', 'Batches', 1, 'UPSERT', NULL, NULL, NULL, NULL, 2, '2026-06-19 17:26:24.783'),
    ('E62CE414-0247-4AB3-B03C-BCB3B30FFA99', 'ProductSaleInformation', 1, 'ROLLING_WINDOW', 'TransactionDate', 180, NULL, NULL, 4, '2026-06-19 17:26:24.783');
DROP TABLE IF EXISTS nexora_sync.`sync_table_progress`;
CREATE TABLE nexora_sync.`sync_table_progress` (
    `execution_id` char(36) NOT NULL,
    `table_name` varchar(128) NOT NULL,
    `sync_type` varchar(40) NULL,
    `total_rows` bigint NOT NULL,
    `rows_sent` bigint NOT NULL,
    `chunks_sent` int NOT NULL,
    `updated_at` datetime(3) NOT NULL,
    PRIMARY KEY (`execution_id`, `table_name`)
);
INSERT INTO nexora_sync.`sync_table_progress` (`execution_id`, `table_name`, `sync_type`, `total_rows`, `rows_sent`, `chunks_sent`, `updated_at`) VALUES
    ('F563978B-63D9-4B9F-B8DF-03846492585E', 'Products', 'UPSERT', 9, 9, 1, '2026-07-04 20:08:47.367'),
    ('C90BE353-01C3-42FC-BC74-0668A3779DB3', 'Batches', 'UPSERT', 200681, 200681, 201, '2026-06-25 16:22:30.537'),
    ('C90BE353-01C3-42FC-BC74-0668A3779DB3', 'Products', 'UPSERT', 51328, 51328, 52, '2026-06-25 16:19:52.473'),
    ('C90BE353-01C3-42FC-BC74-0668A3779DB3', 'ProductSaleInformation', 'ROLLING_WINDOW', 55418, 55418, 56, '2026-06-25 16:23:31.807'),
    ('C90BE353-01C3-42FC-BC74-0668A3779DB3', 'ProductTrans', 'ROLLING_WINDOW', 24122, 24122, 25, '2026-06-25 16:24:01.390'),
    ('C90BE353-01C3-42FC-BC74-0668A3779DB3', 'PurchaseTrans', 'ROLLING_WINDOW', 17433, 17433, 18, '2026-06-25 16:23:43.827'),
    ('C90BE353-01C3-42FC-BC74-0668A3779DB3', 'SaleInformation', 'ROLLING_WINDOW', 26289, 26289, 27, '2026-06-25 16:22:45.360'),
    ('C90BE353-01C3-42FC-BC74-0668A3779DB3', 'SupplierProductMatch', 'UPSERT', 79127, 79127, 80, '2026-06-25 16:24:40.210'),
    ('C90BE353-01C3-42FC-BC74-0668A3779DB3', 'Suppliers', 'UPSERT', 749, 749, 1, '2026-06-25 16:24:41.080'),
    ('C90BE353-01C3-42FC-BC74-0668A3779DB3', 'TAX', 'UPSERT', 20, 20, 1, '2026-06-25 16:24:41.640');
DROP TABLE IF EXISTS nexora_sync.`TAX`;
CREATE TABLE nexora_sync.`TAX` (
    `store_id` char(36) NOT NULL,
    `tenant_id` char(36) NULL,
    `taxcode` int NOT NULL,
    `description` varchar(50) NULL,
    `row_hash` varchar(64) NULL,
    PRIMARY KEY (`store_id`, `taxcode`)
);
INSERT INTO nexora_sync.`TAX` (`store_id`, `tenant_id`, `taxcode`, `description`, `row_hash`) VALUES
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 28, '4%', 'c9b427d87c72943a1cadbf6237ac78cbae0328e3fdecc973e2623f0a2b5d75ce'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 29, '12.5%', 'e028e5d30b40c5cf3726f4456c8eeebc0d416ae55fe730305c97afdbf21a23e1'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 30, 'NOTAX', '5e7566271859fb3b526aeabce737bfefcf00bf6fb508ef1c078073bbe1cede15'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 31, '14.50%', '8d0f0e649c2ded32531e3549234e59abad5d6f24587f9536e1622825b17f120c'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 32, '5.00%', 'c001676199e34b2b4ad8846cf8ec599b7aa652928b68d90f4877f8f4778def61'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 33, 'IT14.50%', 'a0a7bf126e362782e70bdf53c7e0d7a896a8c4c839e654cf4213740ae461af35'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 34, 'IT5.00%', '2f7df5a37e33026e997bf64d2c40a506f717c0fe2cfa17c023003606ebc9ed17'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 35, 'Exempted', '849edd2161c81ca6181e1105979b69e4f5c5dd3039b9fa2817234e945269128f'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 36, '5 % GST', 'b59e249dd454d8feabe62a4b05e840ec4dfc3eaa9a0df9d6579e6338031eb40a'),
    ('D55F8A0D-C230-44EA-BF56-02F143B948BD', 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D', 37, '12 % GST', '78293f4d49951ccfdd6d0f79715614ac8f175a88477bf3b361f82c16225e5afa');
DROP TABLE IF EXISTS nexora_sync.`V2_TEST`;
CREATE TABLE nexora_sync.`V2_TEST` (
    `id` int NOT NULL,
    `name` varchar(50) NULL,
    `mrp` decimal(10,2) NULL,
    PRIMARY KEY (`id`)
);
