/*====================================================
002_platform_seed.sql
NEXORA Platform Foundation V1
====================================================
*/

SET NOCOUNT ON;

----------------------------------------------------
-- ROLES
----------------------------------------------------

IF NOT EXISTS (SELECT 1 FROM roles WHERE role_name = 'SuperAdmin')
BEGIN
    INSERT INTO roles
    (
        role_id,
        role_name,
        description,
        is_active
    )
    VALUES
    (
        NEWID(),
        'SuperAdmin',
        'Platform Super Administrator',
        1
    );
END;

IF NOT EXISTS (SELECT 1 FROM roles WHERE role_name = 'Admin')
BEGIN
    INSERT INTO roles
    (
        role_id,
        role_name,
        description,
        is_active
    )
    VALUES
    (
        NEWID(),
        'Admin',
        'Tenant Administrator',
        1
    );
END;

IF NOT EXISTS (SELECT 1 FROM roles WHERE role_name = 'Manager')
BEGIN
    INSERT INTO roles
    (
        role_id,
        role_name,
        description,
        is_active
    )
    VALUES
    (
        NEWID(),
        'Manager',
        'Store Manager',
        1
    );
END;

IF NOT EXISTS (SELECT 1 FROM roles WHERE role_name = 'User')
BEGIN
    INSERT INTO roles
    (
        role_id,
        role_name,
        description,
        is_active
    )
    VALUES
    (
        NEWID(),
        'User',
        'Standard User',
        1
    );
END;

----------------------------------------------------
-- MODULES
----------------------------------------------------

IF NOT EXISTS (SELECT 1 FROM modules WHERE module_code = 'SYNC')
BEGIN
    INSERT INTO modules
    (
        module_id,
        module_code,
        module_name,
        description,
        is_active
    )
    VALUES
    (
        NEWID(),
        'SYNC',
        'Sync',
        'Store Synchronization',
        1
    );
END;

IF NOT EXISTS (SELECT 1 FROM modules WHERE module_code = 'STOCK')
BEGIN
    INSERT INTO modules
    (
        module_id,
        module_code,
        module_name,
        description,
        is_active
    )
    VALUES
    (
        NEWID(),
        'STOCK',
        'Stock',
        'Stock Management',
        1
    );
END;

IF NOT EXISTS (SELECT 1 FROM modules WHERE module_code = 'PROCUREMENT')
BEGIN
    INSERT INTO modules
    (
        module_id,
        module_code,
        module_name,
        description,
        is_active
    )
    VALUES
    (
        NEWID(),
        'PROCUREMENT',
        'Procurement',
        'Procurement Management',
        1
    );
END;

IF NOT EXISTS (SELECT 1 FROM modules WHERE module_code = 'DEMAND')
BEGIN
    INSERT INTO modules
    (
        module_id,
        module_code,
        module_name,
        description,
        is_active
    )
    VALUES
    (
        NEWID(),
        'DEMAND',
        'Demand',
        'Demand Planning',
        1
    );
END;

IF NOT EXISTS (SELECT 1 FROM modules WHERE module_code = 'TRANSFER')
BEGIN
    INSERT INTO modules
    (
        module_id,
        module_code,
        module_name,
        description,
        is_active
    )
    VALUES
    (
        NEWID(),
        'TRANSFER',
        'Transfer',
        'Stock Transfer',
        1
    );
END;

IF NOT EXISTS (SELECT 1 FROM modules WHERE module_code = 'SUPPLIER')
BEGIN
    INSERT INTO modules
    (
        module_id,
        module_code,
        module_name,
        description,
        is_active
    )
    VALUES
    (
        NEWID(),
        'SUPPLIER',
        'Supplier',
        'Supplier Management',
        1
    );
END;

IF NOT EXISTS (SELECT 1 FROM modules WHERE module_code = 'REPORTS')
BEGIN
    INSERT INTO modules
    (
        module_id,
        module_code,
        module_name,
        description,
        is_active
    )
    VALUES
    (
        NEWID(),
        'REPORTS',
        'Reports',
        'Reporting Module',
        1
    );
END;

IF NOT EXISTS (SELECT 1 FROM modules WHERE module_code = 'SETTINGS')
BEGIN
    INSERT INTO modules
    (
        module_id,
        module_code,
        module_name,
        description,
        is_active
    )
    VALUES
    (
        NEWID(),
        'SETTINGS',
        'Settings',
        'Platform Settings',
        1
    );
END;

----------------------------------------------------
-- PLATFORM SETTINGS
----------------------------------------------------

IF NOT EXISTS (
    SELECT 1
    FROM platform_settings
    WHERE setting_key = 'THEME'
)
BEGIN
    INSERT INTO platform_settings
    (
        setting_key,
        setting_value,
        description,
        is_active
    )
    VALUES
    (
        'THEME',
        'DARK',
        'Default Application Theme',
        1
    );
END;

IF NOT EXISTS (
    SELECT 1
    FROM platform_settings
    WHERE setting_key = 'PASSWORD_EXPIRY_DAYS'
)
BEGIN
    INSERT INTO platform_settings
    (
        setting_key,
        setting_value,
        description,
        is_active
    )
    VALUES
    (
        'PASSWORD_EXPIRY_DAYS',
        '90',
        'Password Expiry Policy',
        1
    );
END;

IF NOT EXISTS (
    SELECT 1
    FROM platform_settings
    WHERE setting_key = 'SESSION_TIMEOUT'
)
BEGIN
    INSERT INTO platform_settings
    (
        setting_key,
        setting_value,
        description,
        is_active
    )
    VALUES
    (
        'SESSION_TIMEOUT',
        '30',
        'Session Timeout In Minutes',
        1
    );
END;

----------------------------------------------------
-- SUPER ADMIN
----------------------------------------------------

IF NOT EXISTS
(
    SELECT 1
    FROM users
    WHERE username = 'superadmin'
)
BEGIN
    INSERT INTO users
    (
        user_id,
        tenant_id,
        username,
        password_hash,
        first_name,
        last_name,
        email,
        mobile,
        is_platform_user,
        is_active,
        created_at
    )
    VALUES
    (
        NEWID(),
        NULL,
        'superadmin',
        'CHANGE_ME',
        'Super',
        'Admin',
        NULL,
        NULL,
        1,
        1,
        GETDATE()
    );
END;

PRINT 'NEXORA PLATFORM SEED COMPLETED';
GO