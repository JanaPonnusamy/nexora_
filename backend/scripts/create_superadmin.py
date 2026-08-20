"""Create (or reset) the platform superadmin login.

UserRoleRepository.seed_all_role_users() covers this for a fresh install, but it
seeds seven role users at once and its INSERT omits failed_login_attempts /
force_password_change - both NOT NULL with no default constraint in the
nexora_platform dump, so it fails there. This creates just the superadmin and
sets those columns explicitly.

The account is a platform user (tenant_id NULL, is_platform_user 1) so it is not
scoped to any tenant; see dependencies/store_scope.py. SUPER_ADMIN also bypasses
role_module_access entirely (repositories/user_repository.py), so no module
permission rows are needed. A user_store_roles row is still required because
that table is the only place a role is attached - the store on it is irrelevant
for this role, matching what seed_all_role_users() does.

Idempotent: re-running resets the password and re-attaches the role.

Usage:
    python scripts/create_superadmin.py [username] [password]
"""

import os
import sys
import uuid

import bcrypt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import get_connection

DEFAULT_USERNAME = "superadmin"
DEFAULT_PASSWORD = "Nexora@123"
ROLE_NAME = "SUPER_ADMIN"


def create_superadmin(username, password):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT role_id FROM dbo.roles WHERE role_name=?", ROLE_NAME)
    role = cur.fetchone()
    if not role:
        conn.close()
        sys.exit(f"Role {ROLE_NAME} does not exist. Seed roles first.")
    role_id = str(role[0])

    cur.execute("SELECT TOP 1 store_id, store_code FROM dbo.stores ORDER BY store_code")
    store = cur.fetchone()
    if not store:
        conn.close()
        sys.exit("No stores exist. A user_store_roles row needs one.")
    store_id, store_code = str(store[0]), store[1]

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    cur.execute("SELECT user_id FROM dbo.users WHERE username=?", username)
    existing = cur.fetchone()

    if existing:
        user_id = str(existing[0])
        cur.execute(
            "UPDATE dbo.users SET password_hash=?, is_active=1, is_platform_user=1, "
            "failed_login_attempts=0, locked_until=NULL, force_password_change=0, "
            "password_changed_at=GETDATE(), updated_at=GETDATE() WHERE user_id=?",
            password_hash, user_id,
        )
        action = "reset existing user"
    else:
        user_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO dbo.users (user_id,username,password_hash,first_name,last_name,"
            "is_platform_user,is_active,created_at,failed_login_attempts,force_password_change,"
            "password_changed_at) VALUES (?,?,?,?,?,1,1,GETDATE(),0,0,GETDATE())",
            user_id, username, password_hash, "Super", "Admin",
        )
        action = "created user"

    cur.execute(
        "SELECT COUNT(*) FROM dbo.user_store_roles WHERE user_id=? AND store_id=? AND role_id=?",
        user_id, store_id, role_id,
    )
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO dbo.user_store_roles (user_id,store_id,role_id,is_active) VALUES (?,?,?,1)",
            user_id, store_id, role_id,
        )
        role_action = f"attached {ROLE_NAME} at store {store_code}"
    else:
        cur.execute(
            "UPDATE dbo.user_store_roles SET is_active=1 WHERE user_id=? AND store_id=? AND role_id=?",
            user_id, store_id, role_id,
        )
        role_action = f"{ROLE_NAME} already attached at store {store_code}"

    conn.commit()
    conn.close()

    print(f"{action}: {username} ({user_id})")
    print(role_action)
    print(f"password: {password}")


if __name__ == "__main__":
    create_superadmin(
        sys.argv[1] if len(sys.argv) > 1 else DEFAULT_USERNAME,
        sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PASSWORD,
    )
