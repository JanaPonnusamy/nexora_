"""Create (or reset) a single Product Mapping login.

The Product Mapping module (capability PRODUCT_MAPPING) is currently reachable
only by SUPER_ADMIN - it is the only role with a role_module_access row for that
module (confirmed against the live platform DB). This script provisions a
dedicated, non-admin login that can use Product Mapping and nothing else:

  1. Ensures a PRODUCT_MAPPER role exists.
  2. Ensures that role has role_module_access on the PRODUCT_MAPPING module with
     can_view / can_create / can_edit / can_export (the review workflow writes,
     so view alone is not enough), can_delete = 0. Capabilities are role-based,
     not store-based (see repositories/user_repository.py:get_user_modules), so
     one grant covers the login everywhere.
  3. Creates (or resets) the user, an ordinary Nathan Medicals tenant user
     (is_platform_user 0, tenant_id set - NOT a super admin), and attaches the
     PRODUCT_MAPPER role at every store in the tenant. Product Mapping is
     cross-store within a tenant and the module data is scoped by tenant_id
     (dependencies/store_scope.py:assert_tenant_access), so an all-store
     attachment simply lets the store pickers work for any source/target pair.

failed_login_attempts / force_password_change / password_changed_at are set
explicitly because they are NOT NULL with no default in the platform dump
(matching scripts/create_nmc_users.py). Idempotent: re-running resets the
password and re-attaches the role/grant.

Usage:
    python scripts/create_product_mapping_user.py [username] [password]
"""

import os
import sys
import uuid

import bcrypt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import get_connection

# Nathan Medicals tenant (all NM* stores share it) - the only real tenant that
# uses Product Mapping.
TENANT_ID = "A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D"

DEFAULT_USERNAME = "productmapping"
DEFAULT_PASSWORD = "Product@Map2026"

ROLE_NAME = "PRODUCT_MAPPER"
ROLE_DESCRIPTION = "Product Mapping module access only"
MODULE_CODE = "PRODUCT_MAPPING"

FIRST_NAME = "Product"
LAST_NAME = "Mapping"


def _ensure_role(cur):
    cur.execute("SELECT role_id FROM dbo.roles WHERE role_name=?", ROLE_NAME)
    row = cur.fetchone()
    if row:
        role_id = str(row[0])
        cur.execute("UPDATE dbo.roles SET is_active=1 WHERE role_id=?", role_id)
        return role_id, "existing role"
    role_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO dbo.roles (role_id, role_name, description, is_active) VALUES (?,?,?,1)",
        role_id, ROLE_NAME, ROLE_DESCRIPTION,
    )
    return role_id, "created role"


def _ensure_grant(cur, role_id):
    cur.execute("SELECT module_id FROM dbo.modules WHERE module_code=?", MODULE_CODE)
    row = cur.fetchone()
    if not row:
        sys.exit(f"Module {MODULE_CODE} does not exist in dbo.modules.")
    module_id = str(row[0])

    cur.execute(
        "SELECT COUNT(*) FROM dbo.role_module_access WHERE role_id=? AND module_id=?",
        role_id, module_id,
    )
    if cur.fetchone()[0] == 0:
        # id is IDENTITY - omit it.
        cur.execute(
            "INSERT INTO dbo.role_module_access "
            "(role_id, module_id, can_view, can_create, can_edit, can_delete, can_export, is_active) "
            "VALUES (?,?,1,1,1,0,1,1)",
            role_id, module_id,
        )
        return "granted PRODUCT_MAPPING"
    cur.execute(
        "UPDATE dbo.role_module_access "
        "SET can_view=1, can_create=1, can_edit=1, can_delete=0, can_export=1, is_active=1 "
        "WHERE role_id=? AND module_id=?",
        role_id, module_id,
    )
    return "PRODUCT_MAPPING grant refreshed"


def _stores(cur):
    cur.execute(
        "SELECT store_id, store_code FROM dbo.stores WHERE tenant_id=? ORDER BY store_code",
        TENANT_ID,
    )
    rows = cur.fetchall()
    if not rows:
        sys.exit(f"No stores found for tenant {TENANT_ID}.")
    return [(str(r[0]), r[1]) for r in rows]


def _upsert_user(cur, username, password, role_id):
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    cur.execute("SELECT user_id FROM dbo.users WHERE username=?", username)
    existing = cur.fetchone()
    if existing:
        user_id = str(existing[0])
        cur.execute(
            "UPDATE dbo.users SET password_hash=?, tenant_id=?, is_active=1, is_platform_user=0, "
            "failed_login_attempts=0, locked_until=NULL, force_password_change=0, "
            "password_changed_at=GETDATE(), updated_at=GETDATE() WHERE user_id=?",
            password_hash, TENANT_ID, user_id,
        )
        action = "reset"
    else:
        user_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO dbo.users (user_id,username,password_hash,first_name,last_name,tenant_id,"
            "is_platform_user,is_active,created_at,failed_login_attempts,force_password_change,"
            "password_changed_at) VALUES (?,?,?,?,?,?,0,1,GETDATE(),0,0,GETDATE())",
            user_id, username, password_hash, FIRST_NAME, LAST_NAME, TENANT_ID,
        )
        action = "created"

    attached = []
    for store_id, store_code in _stores(cur):
        cur.execute(
            "SELECT COUNT(*) FROM dbo.user_store_roles WHERE user_id=? AND store_id=? AND role_id=?",
            user_id, store_id, role_id,
        )
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO dbo.user_store_roles (user_id,store_id,role_id,is_active) VALUES (?,?,?,1)",
                user_id, store_id, role_id,
            )
        else:
            cur.execute(
                "UPDATE dbo.user_store_roles SET is_active=1 WHERE user_id=? AND store_id=? AND role_id=?",
                user_id, store_id, role_id,
            )
        attached.append(store_code)

    return user_id, action, attached


def main(username, password):
    conn = get_connection()
    cur = conn.cursor()

    role_id, role_action = _ensure_role(cur)
    grant_action = _ensure_grant(cur, role_id)
    user_id, user_action, attached = _upsert_user(cur, username, password, role_id)

    conn.commit()
    conn.close()

    print(f"{role_action}: {ROLE_NAME} ({role_id})")
    print(f"  {grant_action}")
    print(f"{user_action} user: {username} ({user_id})")
    print(f"  role {ROLE_NAME} @ {', '.join(attached)}")
    print(f"  password: {password}")


if __name__ == "__main__":
    main(
        sys.argv[1] if len(sys.argv) > 1 else DEFAULT_USERNAME,
        sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PASSWORD,
    )
