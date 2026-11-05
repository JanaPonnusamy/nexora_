"""Create (or reset) a TESTSMS tenant login on the .32 (Success) HO.

  * activates tenant TESTSMS and the given store(s)
  * default: user testsmsadmin / Testsms@123, TENANT_ADMIN role bound to TESTSMA

Same shape as scripts/create_nmv_users.py, but it connects to the .32 HO's own
NEXORA_PLATFORM explicitly (backend/.env points at .73). Idempotent: re-running
resets the password and re-attaches the role.

Usage (from backend/):
    .venv\\Scripts\\python.exe scripts\\create_testsms_admin.py
    .venv\\Scripts\\python.exe scripts\\create_testsms_admin.py --username TESTSMA ^
        --password Testsma@123 --first-name TESTSMA --last-name "Purchase Manager" ^
        --role PURCHASE_MANAGER --stores TESTSMA
"""
import argparse
import uuid

import bcrypt
import pyodbc

CONN = ("DRIVER={ODBC Driver 17 for SQL Server};SERVER=192.168.10.32;"
        "DATABASE=NEXORA_PLATFORM;UID=sa;PWD=Admin123;TrustServerCertificate=yes;")


def _args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", default="testsmsadmin")
    ap.add_argument("--password", default="Testsms@123")
    ap.add_argument("--first-name", default="TESTSMS")
    ap.add_argument("--last-name", default="Admin")
    ap.add_argument("--role", default="TENANT_ADMIN")
    ap.add_argument("--stores", default="TESTSMA", help="comma-separated store codes")
    ap.add_argument("--tenant", default="SMS", help="tenant code (TESTSMS was renamed SMS on 2026-11-04)")
    ap.add_argument("--no-activate", action="store_true",
                    help="leave the tenant/store is_active flags as they are (e.g. a store not ready to sync)")
    return ap.parse_args()


def main():
    a = _args()
    USER = {"username": a.username, "password": a.password, "first_name": a.first_name,
            "last_name": a.last_name, "role_name": a.role}
    store_codes = [c.strip() for c in a.stores.split(",") if c.strip()]
    conn = pyodbc.connect(CONN, timeout=15)
    cur = conn.cursor()
    cur.execute("SELECT tenant_id FROM dbo.tenants WHERE tenant_code=?", a.tenant)
    tenant_id = str(cur.fetchone()[0])
    store_ids = []
    for code in store_codes:
        cur.execute("SELECT store_id FROM dbo.stores WHERE tenant_id=? AND store_code=?", tenant_id, code)
        store_ids.append(str(cur.fetchone()[0]))
    cur.execute("SELECT role_id FROM dbo.roles WHERE role_name=?", USER["role_name"])
    role_id = str(cur.fetchone()[0])

    if not a.no_activate:
        cur.execute("UPDATE dbo.tenants SET is_active=1, updated_at=GETDATE() WHERE tenant_id=?", tenant_id)
        for store_id in store_ids:
            cur.execute("UPDATE dbo.stores SET is_active=1, updated_at=GETDATE() WHERE store_id=?", store_id)

    password_hash = bcrypt.hashpw(USER["password"].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    cur.execute("SELECT user_id FROM dbo.users WHERE username=?", USER["username"])
    existing = cur.fetchone()
    if existing:
        user_id = str(existing[0])
        cur.execute(
            "UPDATE dbo.users SET password_hash=?, tenant_id=?, is_active=1, is_platform_user=0, "
            "failed_login_attempts=0, locked_until=NULL, force_password_change=0, "
            "password_changed_at=GETDATE(), updated_at=GETDATE() WHERE user_id=?",
            password_hash, tenant_id, user_id,
        )
        action = "reset"
    else:
        user_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO dbo.users (user_id,username,password_hash,first_name,last_name,tenant_id,"
            "is_platform_user,is_active,created_at,failed_login_attempts,force_password_change,"
            "password_changed_at) VALUES (?,?,?,?,?,?,0,1,GETDATE(),0,0,GETDATE())",
            user_id, USER["username"], password_hash, USER["first_name"], USER["last_name"], tenant_id,
        )
        action = "created"

    for store_id in store_ids:
        cur.execute("SELECT COUNT(*) FROM dbo.user_store_roles WHERE user_id=? AND store_id=? AND role_id=?",
                    user_id, store_id, role_id)
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO dbo.user_store_roles (user_id,store_id,role_id,is_active) VALUES (?,?,?,1)",
                        user_id, store_id, role_id)
        else:
            cur.execute("UPDATE dbo.user_store_roles SET is_active=1 WHERE user_id=? AND store_id=? AND role_id=?",
                        user_id, store_id, role_id)
    conn.commit()
    conn.close()
    print(f"{action} {USER['username']} ({user_id})")
    print(f"  {USER['role_name']} @ {', '.join(store_codes)} (tenant {a.tenant}); "
          + ("is_active flags left as they were" if a.no_activate else "tenant + store(s) activated"))
    print(f"  password: {USER['password']}")


if __name__ == "__main__":
    main()
