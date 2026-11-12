"""Create (or reset) the restricted "SMS" Purchase Manager login for tenant SMS.

Owner request (2026-11-12): a single login, username "SMS", that can see only
three things: Procurement, Stock Availability (stock_availability), and
Supplier Stock Analysis. Multiple people may be signed in with this same
username at once (shared shop-floor login), unlike the default one-session-
per-user rule.

The tenant's existing PURCHASE_MANAGER role (0AE06EC0-59C9-4B6F-BB88-9559842564C7
on the live .32 platform DB) already grants almost this set, plus
PROCUREMENT_INTELLIGENCE (the cross-store network engine, not requested) -
and editing that shared role would also change every other PM login tenant-
wide. So this provisions a dedicated SMS_PM role instead, exactly mirroring
the create_product_mapping_user.py idiom:

  1. Ensure an SMS_PM role exists.
  2. Grant it role_module_access on exactly PROCUREMENT (view/create/edit/
     export, no delete), stock_availability (view only) and
     supplier_stock_analysis (view/create/edit/export, no delete) - matching
     the live PURCHASE_MANAGER grants for the same two latter modules. A role
     with ZERO role_module_access rows is treated as full access by the
     frontend (frontend/src/types/access.ts resolveAccess: caps.size===0 ->
     PERMISSIVE), so all three grants are mandatory, not optional.
  3. Create (or reset) the "SMS" user under tenant SMS and attach SMS_PM at
     every store in that tenant (SMF/SMG/SHP/SMA) - Procurement and Supplier
     Stock Analysis are store-scoped screens, so every store needs the grant
     for the store picker to work.

For username "SMS" to allow more than one concurrent session, add "SMS_PM" to
_MULTI_SESSION_ROLES in backend/controllers/auth_controller.py (done alongside
this script, not here - that's a code change, not a data change).

Usage:
    python scripts/create_sms_pm_user.py [username] [password]
"""

import os
import sys
import uuid

import bcrypt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import get_connection

# Tenant SMS (live .32 platform DB).
TENANT_ID = "2D5ED813-881C-4CCA-803D-9FC78A15B85A"

DEFAULT_USERNAME = "SMS"
DEFAULT_PASSWORD = "Admin@123"

ROLE_NAME = "SMS_PM"
ROLE_DESCRIPTION = "SMS tenant - Procurement, Stock Availability and Supplier Stock Analysis only"

# module_code -> (can_view, can_create, can_edit, can_delete, can_export)
MODULE_GRANTS = {
    "PROCUREMENT": (1, 1, 1, 0, 1),
    "stock_availability": (1, 0, 0, 0, 0),
    "supplier_stock_analysis": (1, 1, 1, 0, 1),
}

FIRST_NAME = "SMS"
LAST_NAME = "Purchase"


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


def _ensure_grants(cur, role_id):
    results = []
    for module_code, (can_view, can_create, can_edit, can_delete, can_export) in MODULE_GRANTS.items():
        cur.execute("SELECT module_id FROM dbo.modules WHERE module_code=?", module_code)
        row = cur.fetchone()
        if not row:
            sys.exit(f"Module {module_code} does not exist in dbo.modules.")
        module_id = str(row[0])

        cur.execute(
            "SELECT COUNT(*) FROM dbo.role_module_access WHERE role_id=? AND module_id=?",
            role_id, module_id,
        )
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO dbo.role_module_access "
                "(role_id, module_id, can_view, can_create, can_edit, can_delete, can_export, is_active) "
                "VALUES (?,?,?,?,?,?,?,1)",
                role_id, module_id, can_view, can_create, can_edit, can_delete, can_export,
            )
            results.append(f"granted {module_code}")
        else:
            cur.execute(
                "UPDATE dbo.role_module_access "
                "SET can_view=?, can_create=?, can_edit=?, can_delete=?, can_export=?, is_active=1 "
                "WHERE role_id=? AND module_id=?",
                can_view, can_create, can_edit, can_delete, can_export, role_id, module_id,
            )
            results.append(f"{module_code} grant refreshed")

    # Remove any other grant this role might have accumulated, so it stays
    # restricted to exactly the three modules above even if re-run after a
    # manual change.
    cur.execute(
        "SELECT m.module_code FROM dbo.role_module_access rma "
        "JOIN dbo.modules m ON m.module_id = rma.module_id "
        "WHERE rma.role_id=? AND rma.is_active=1",
        role_id,
    )
    extra = [r[0] for r in cur.fetchall() if r[0] not in MODULE_GRANTS]
    for module_code in extra:
        cur.execute(
            "UPDATE dbo.role_module_access SET is_active=0 "
            "WHERE role_id=? AND module_id=(SELECT module_id FROM dbo.modules WHERE module_code=?)",
            role_id, module_code,
        )
        results.append(f"deactivated stray grant {module_code}")

    return results


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
    grant_actions = _ensure_grants(cur, role_id)
    user_id, user_action, attached = _upsert_user(cur, username, password, role_id)

    conn.commit()
    conn.close()

    print(f"{role_action}: {ROLE_NAME} ({role_id})")
    for line in grant_actions:
        print(f"  {line}")
    print(f"{user_action} user: {username} ({user_id})")
    print(f"  role {ROLE_NAME} @ {', '.join(attached)}")
    print(f"  password: {password}")


if __name__ == "__main__":
    main(
        sys.argv[1] if len(sys.argv) > 1 else DEFAULT_USERNAME,
        sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PASSWORD,
    )
