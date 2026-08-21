"""Create (or reset) two Nathan Medicals logins:

  1. NMC salesman  - SALESMAN role bound to the NMC store only. A salesman-only
     login is deliberately barred from the NMW Sales Report (see
     modules/nmw_sales_report/service.py); this account is for regular sales.

  2. NMC purchase manager (all-store) - PURCHASE_MANAGER role bound to EVERY
     store in the tenant. Ordinary purchase managers are attached to a single
     store and therefore see only that store's approved NMW dispatch bills;
     attaching this one user to all stores lets it see every store's approved
     bills (list_bills scopes non-super-admin users to their assigned stores via
     dbo.user_store_roles). It is NOT a super admin: no approval rights, no
     cross-tenant / all-module access.

Both are ordinary tenant users (is_platform_user 0, tenant_id set), unlike the
superadmin. Idempotent: re-running resets the password and re-attaches roles.
failed_login_attempts / force_password_change / password_changed_at are set
explicitly because they are NOT NULL with no default in the platform dump.

Usage:
    python scripts/create_nmc_users.py
"""

import os
import sys
import uuid

import bcrypt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import get_connection

# Nathan Medicals tenant (all NM* stores share it).
TENANT_ID = "A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D"

SALESMAN = {
    "username": "nmcsalesman",
    "password": "Nmc@Sales2026",
    "first_name": "NMC",
    "last_name": "Salesman",
    "role_name": "SALESMAN",
    "store_codes": ["NMC"],          # single store
}

PURCHASE_MANAGER = {
    "username": "nmcpm",
    "password": "NmcPM@2026",
    "first_name": "NMC",
    "last_name": "Purchase Manager",
    "role_name": "PURCHASE_MANAGER",
    "store_codes": None,             # None => every store in the tenant (all-store view)
}


def _role_id(cur, role_name):
    cur.execute("SELECT role_id FROM dbo.roles WHERE role_name=?", role_name)
    row = cur.fetchone()
    if not row:
        sys.exit(f"Role {role_name} does not exist. Seed roles first.")
    return str(row[0])


def _store_ids(cur, store_codes):
    if store_codes is None:
        cur.execute("SELECT store_id, store_code FROM dbo.stores WHERE tenant_id=? ORDER BY store_code", TENANT_ID)
    else:
        placeholders = ",".join("?" for _ in store_codes)
        cur.execute(
            f"SELECT store_id, store_code FROM dbo.stores WHERE tenant_id=? AND store_code IN ({placeholders})",
            TENANT_ID, *store_codes,
        )
    rows = cur.fetchall()
    if not rows:
        sys.exit(f"No stores found for {store_codes} in tenant {TENANT_ID}.")
    return [(str(r[0]), r[1]) for r in rows]


def _upsert_user(cur, spec):
    role_id = _role_id(cur, spec["role_name"])
    stores = _store_ids(cur, spec["store_codes"])
    password_hash = bcrypt.hashpw(spec["password"].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    cur.execute("SELECT user_id FROM dbo.users WHERE username=?", spec["username"])
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
            user_id, spec["username"], password_hash, spec["first_name"], spec["last_name"], TENANT_ID,
        )
        action = "created"

    attached = []
    for store_id, store_code in stores:
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

    print(f"{action} {spec['username']} ({user_id})")
    print(f"  role {spec['role_name']} @ {', '.join(attached)}")
    print(f"  password: {spec['password']}")


def main():
    conn = get_connection()
    cur = conn.cursor()
    _upsert_user(cur, SALESMAN)
    _upsert_user(cur, PURCHASE_MANAGER)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
