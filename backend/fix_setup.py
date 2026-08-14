import os, uuid, bcrypt
from config.database import get_connection

pw   = (os.getenv("UNINEX_SETUP_PASSWORD") or "").strip()
user = (os.getenv("UNINEX_SETUP_USERNAME") or "setupdeploy").strip()
assert pw, "No UNINEX_SETUP_PASSWORD in effect"
print("using password:", repr(pw), "user:", user)

c = get_connection(); cur = c.cursor()
h = bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

cur.execute("SELECT user_id FROM dbo.users WHERE username=?", user)
row = cur.fetchone()
if row:
    uid = str(row[0])
    cur.execute("UPDATE dbo.users SET password_hash=?, is_active=1 WHERE user_id=?", h, uid)
    print("updated existing user")
else:
    uid = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO dbo.users (user_id,username,password_hash,first_name,last_name,is_platform_user,is_active,created_at) "
        "VALUES (?,?,?,?,?,1,1,GETDATE())", uid, user, h, "Setup", "Deploy")
    print("inserted new user")

cur.execute("SELECT TOP 1 store_id FROM dbo.stores ORDER BY store_code")
store = cur.fetchone()
cur.execute("SELECT role_id FROM dbo.roles WHERE role_name='PLATFORM_OWNER'")
role = cur.fetchone()
if store and role:
    sid, rid = str(store[0]), str(role[0])
    cur.execute("SELECT COUNT(*) FROM dbo.user_store_roles WHERE user_id=? AND store_id=? AND role_id=?", uid, sid, rid)
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO dbo.user_store_roles (user_id,store_id,role_id,is_active) VALUES (?,?,?,1)", uid, sid, rid)
        print("role assigned")
    else:
        print("role already present")
else:
    print("WARN: no store or PLATFORM_OWNER role found")

c.commit()
cur.execute("SELECT username, is_active, LEN(password_hash) FROM dbo.users WHERE username=?", user)
print("VERIFY row:", cur.fetchone())
