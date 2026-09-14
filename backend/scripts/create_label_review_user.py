"""Create (or reset) a REVIEW-ONLY Label Exporter login for Nathan Medicals C (NMC).

The user gets the LABEL_REVIEW role bound to the NMC store only. In the Label
Exporter this means they can review products (Y/N include/exclude, unit
correction, remarks) but CANNOT assign/clear locations or print — those stay
super-admin only server-side (dependencies.store_scope.require_super_admin).
The desktop client further restricts this role's navigation to just the Label
Exporter + Settings tabs (see isLabelReviewOnly in supplier-stock-client App.jsx).

It is an ordinary tenant user (is_platform_user 0, tenant_id set), NOT a super
admin. Idempotent: re-running resets the password and re-attaches the role.

Usage:
    python scripts/create_label_review_user.py
"""

import os
import sys
import uuid

import bcrypt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import get_connection

# Nathan Medicals tenant (all NM* stores share it).
TENANT_ID = "A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D"

ROLE_NAME = "LABEL_REVIEW"
ROLE_DESCRIPTION = "Label Exporter review-only: mark Y/N, correct unit, add remarks. No location assignment/print."

USER = {
    "username": "nmcreview",
    "password": "NmcReview@2026",
    "first_name": "NMC",
    "last_name": "Label Review",
    "store_codes": ["NMC"],   # single store
}


def _ensure_role(cur):
    cur.execute("SELECT role_id FROM dbo.roles WHERE role_name=?", ROLE_NAME)
    row = cur.fetchone()
    if row:
        return str(row[0])
    role_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO dbo.roles (role_id, role_name, description, is_active) VALUES (?,?,?,1)",
        role_id, ROLE_NAME, ROLE_DESCRIPTION,
    )
    print(f"created role {ROLE_NAME} ({role_id})")
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

    role_id = _ensure_role(cur)
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

    conn.commit()
    conn.close()

    print(f"{action} {USER['username']} ({user_id})")
    print(f"  role {ROLE_NAME} @ {', '.join(attached)}")
    print(f"  username: {USER['username']}")
    print(f"  password: {USER['password']}")


if __name__ == "__main__":
    main()
