
from config.database import get_connection

class UserRepository:

    def get_user_by_username(self, username):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT user_id,username,password_hash,first_name,is_platform_user,is_active
        FROM dbo.users
        WHERE username = ?
        """, username)
        row = cur.fetchone()
        conn.close()
        return row

    def update_last_login(self, user_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE dbo.users
        SET last_login = GETDATE()
        WHERE user_id = ?
        """, user_id)
        conn.commit()
        conn.close()
