"""Create (or reset) a STOCK + LABEL login for Nathan Medicals A (NMA).

Roles STOCK_VIEWER + LABEL_REVIEW, both bound to the NMA store only. The
desktop Stock Client trims this login's navigation to Stock (Vertical) + NMW
Sales Report + Label Exporter -- see isStockAndLabelViewer in
supplier-stock-client App.jsx. In the Label Exporter it can review (Y/N, unit
correction, remarks) and export the label queue PDF / Excel; location
assign/clear stay super-admin only (dependencies.store_scope.require_super_admin).
An ordinary tenant user, NOT a super admin. Idempotent: re-running resets the
password and re-attaches both roles.

Usage:
    python scripts/create_nma_stock_label_user.py
"""

import os
import sys
import uuid

import bcrypt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import get_connection

# Nathan Medicals tenant (all NM* stores share it).
TENANT_ID = "A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D"

# Both roles already exist (seeded by create_stock_viewer_user.py and
# create_label_review_user.py); created here too if missing.
ROLES = {
    "STOCK_VIEWER": "Stock Client: Stock (Vertical) + NMW bills only.",
    "LABEL_REVIEW": "Label Exporter review-only: mark Y/N, correct unit, add remarks. No location assignment/print.",
}

USER = {
    "username": "NMA1",
    "password": "Stock@123",
    "first_name": "NMA",
    "last_name": "Stock & Label",
    "store_codes": ["NMA"],   # single store
}


def _ensure_role(cur, role_name, description):
    cur.execute("SELECT role_id FROM dbo.roles WHERE role_name=?", role_name)
    row = cur.fetchone()
    if row:
        return str(row[0])
    role_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO dbo.roles (role_id, role_name, description, is_active) VALUES (?,?,?,1)",
        role_id, role_name, description,
    )
    print(f"created role {role_name} ({role_id})")
    return role_id


def _store_ids(cur, store_codes):
    placeholders = ",".join("?" for _ in store_codes)
    cur.execute(
        f"SELECT store_id, store_code FROM dbo.stores WHERE tenant_id=? AND store_code IN ({placeholders})",
        TENANT_ID, *store_codes,
    )
    rows = cur.fetchall()
    if not rows:
        sys.exit(f"No stores found for {store_codes} in tenant {TENANT_ID}.")
    return [(str(r[0]), r[1]) for r in rows]


def main():
    conn = get_connection()
    cur = conn.cursor()

    role_ids = {name: _ensure_role(cur, name, desc) for name, desc in ROLES.items()}
    stores = _store_ids(cur, USER["store_codes"])
    password_hash = bcrypt.hashpw(USER["password"].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    cur.execute("SELECT user_id FROM dbo.users WHERE username=?", USER["username"])
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
            user_id, USER["username"], password_hash, USER["first_name"], USER["last_name"], TENANT_ID,
        )
        action = "created"

    attached = []
    for role_name, role_id in role_ids.items():
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
            attached.append(f"{role_name} @ {store_code}")

    conn.commit()
    conn.close()

    print(f"{action} {USER['username']} ({user_id})")
    for line in attached:
        print(f"  role {line}")
    print(f"  username: {USER['username']}")
    print(f"  password: {USER['password']}")


if __name__ == "__main__":
    main()
