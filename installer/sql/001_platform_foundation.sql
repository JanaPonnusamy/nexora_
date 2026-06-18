
IF DB_ID('NEXORA_PLATFORM') IS NULL
BEGIN
    CREATE DATABASE NEXORA_PLATFORM;
END
GO

USE NEXORA_PLATFORM;
GO

CREATE TABLE tenants(
    tenant_id UNIQUEIDENTIFIER PRIMARY KEY,
    tenant_code VARCHAR(50) NOT NULL UNIQUE,
    tenant_abbreviation VARCHAR(20) NOT NULL UNIQUE,
    tenant_name VARCHAR(200) NOT NULL,
    db_name VARCHAR(200) NOT NULL,
    platform_version VARCHAR(20) NULL,
    tenant_db_version VARCHAR(20) NULL,
    contact_name VARCHAR(100) NULL,
    contact_email VARCHAR(200) NULL,
    contact_phone VARCHAR(50) NULL,
    is_active BIT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    created_by UNIQUEIDENTIFIER NULL,
    updated_at DATETIME NULL,
    updated_by UNIQUEIDENTIFIER NULL
);

CREATE TABLE stores(
    store_id UNIQUEIDENTIFIER PRIMARY KEY,
    tenant_id UNIQUEIDENTIFIER NOT NULL,
    store_code VARCHAR(50) NOT NULL,
    store_name VARCHAR(200) NOT NULL,
    server_name VARCHAR(500) NULL,
    database_name VARCHAR(200) NULL,
    username VARCHAR(200) NULL,
    password_encrypted VARBINARY(MAX) NULL,
    connection_type VARCHAR(50) NULL,
    branch_codes VARCHAR(MAX) NULL,
    last_sync_time DATETIME NULL,
    last_sync_status VARCHAR(50) NULL,
    last_seen DATETIME NULL,
    connection_status VARCHAR(50) NULL,
    heartbeat_ip VARCHAR(100) NULL,
    is_active BIT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NULL
);

CREATE TABLE users(
    user_id UNIQUEIDENTIFIER PRIMARY KEY,
    tenant_id UNIQUEIDENTIFIER NULL,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(500) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NULL,
    email VARCHAR(200) NULL,
    mobile VARCHAR(50) NULL,
    is_platform_user BIT NOT NULL DEFAULT 0,
    is_active BIT NOT NULL DEFAULT 1,
    last_login DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NULL
);

CREATE TABLE roles(
    role_id UNIQUEIDENTIFIER PRIMARY KEY,
    role_name VARCHAR(50) NOT NULL,
    description VARCHAR(500) NULL,
    is_active BIT NOT NULL DEFAULT 1
);

CREATE TABLE user_store_roles(
    id BIGINT IDENTITY PRIMARY KEY,
    user_id UNIQUEIDENTIFIER NOT NULL,
    store_id UNIQUEIDENTIFIER NOT NULL,
    role_id UNIQUEIDENTIFIER NOT NULL,
    is_active BIT NOT NULL DEFAULT 1
);

CREATE TABLE modules(
    module_id UNIQUEIDENTIFIER PRIMARY KEY,
    module_code VARCHAR(50) NOT NULL,
    module_name VARCHAR(100) NOT NULL,
    description VARCHAR(500) NULL,
    is_active BIT NOT NULL DEFAULT 1
);

CREATE TABLE role_module_access(
    id BIGINT IDENTITY PRIMARY KEY,
    role_id UNIQUEIDENTIFIER NOT NULL,
    module_id UNIQUEIDENTIFIER NOT NULL,
    can_view BIT DEFAULT 0,
    can_create BIT DEFAULT 0,
    can_edit BIT DEFAULT 0,
    can_delete BIT DEFAULT 0,
    can_export BIT DEFAULT 0,
    is_active BIT DEFAULT 1
);

CREATE TABLE user_module_override(
    id BIGINT IDENTITY PRIMARY KEY,
    user_id UNIQUEIDENTIFIER NOT NULL,
    module_id UNIQUEIDENTIFIER NOT NULL,
    can_view BIT DEFAULT 0,
    can_create BIT DEFAULT 0,
    can_edit BIT DEFAULT 0,
    can_delete BIT DEFAULT 0,
    can_export BIT DEFAULT 0,
    is_active BIT DEFAULT 1
);

CREATE TABLE platform_settings(
    setting_id BIGINT IDENTITY PRIMARY KEY,
    setting_key VARCHAR(100) NOT NULL,
    setting_value VARCHAR(MAX) NULL,
    description VARCHAR(500) NULL,
    is_active BIT DEFAULT 1
);

CREATE TABLE global_audit_log(
    audit_id BIGINT IDENTITY PRIMARY KEY,
    tenant_id UNIQUEIDENTIFIER NULL,
    store_id UNIQUEIDENTIFIER NULL,
    user_id UNIQUEIDENTIFIER NULL,
    module_name VARCHAR(100),
    action_name VARCHAR(100),
    old_value NVARCHAR(MAX),
    new_value NVARCHAR(MAX),
    created_at DATETIME NOT NULL
);
GO
