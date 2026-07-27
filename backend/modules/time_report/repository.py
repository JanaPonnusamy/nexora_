"""Data access for the Time Report module -- read-only queries against the
COSEC database (Mx_DATDTrn / Mx_UserMst / Mx_DepartmentMst).

Ported faithfully from the standalone Flask app's db.py + the query bodies in
reports.py. Every function opens its own short-lived connection and closes it
(no shared/singleton connection -- this backend serves concurrent requests).
"""
from datetime import date, timedelta

from modules.time_report import config
from modules.time_report.database import get_connection

PUNCH_COLS = [f"Punch{i}" for i in range(1, config.MAX_PUNCHES + 1)]
_PUNCH_SELECT = ", ".join(f"a.{c}" for c in PUNCH_COLS)


def query(sql: str, params: tuple = ()) -> list:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def scalar(sql: str, params: tuple = ()):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def active_cutoff() -> str:
    """Earliest date a punch can fall on for a user to count as ACTIVE.

    = the earlier of (first day of the current month, today - N days), so both
    "punched this month" and "punched in the last 30 days" are covered.
    """
    today = date.today()
    month_start = today.replace(day=1)
    window_start = today - timedelta(days=config.ACTIVE_WINDOW_DAYS)
    return min(month_start, window_start).isoformat()


def get_departments() -> list:
    return query("SELECT DPTID, Name FROM Mx_DepartmentMst ORDER BY Name")


def get_users(dept_id=None, active_only: bool = False) -> list:
    sql = "SELECT u.UserID, u.Name, u.DPTID FROM Mx_UserMst u WHERE u.dltdflg = 0 "
    params = []
    if dept_id:
        sql += "AND u.DPTID = ? "
        params.append(dept_id)
    if active_only:
        sql += ("AND u.UserID IN (SELECT UserID FROM Mx_DATDTrn "
                 "WHERE Punch1 IS NOT NULL AND PDate >= ?) ")
        params.append(active_cutoff())
    sql += "ORDER BY u.Name"
    return query(sql, tuple(params))


def get_active_user_ids(dept_id=None) -> set:
    sql = ("SELECT DISTINCT a.UserID FROM Mx_DATDTrn a "
           "JOIN Mx_UserMst u ON u.UserID = a.UserID "
           "WHERE u.dltdflg = 0 AND a.Punch1 IS NOT NULL AND a.PDate >= ?")
    params = [active_cutoff()]
    if dept_id:
        sql += " AND u.DPTID = ?"
        params.append(dept_id)
    return {r["UserID"] for r in query(sql, tuple(params))}


def find_users(term: str, dept_id=None) -> list:
    """Resolve a single search box: match UserID exactly OR Name (contains)."""
    term = (term or "").strip()
    if not term:
        return []
    sql = ("SELECT u.UserID, u.Name, u.DPTID FROM Mx_UserMst u "
           "WHERE u.dltdflg = 0 AND (u.UserID = ? OR u.Name LIKE ?)")
    params = [term, f"%{term}%"]
    if dept_id:
        sql += " AND u.DPTID = ?"
        params.append(dept_id)
    sql += " ORDER BY u.Name"
    return query(sql, tuple(params))


def date_bounds() -> dict:
    rows = query("SELECT MIN(PDate) AS mn, MAX(PDate) AS mx FROM Mx_DATDTrn")
    row = rows[0] if rows else {}
    mn, mx = row.get("mn"), row.get("mx")
    return {
        "min": mn.date().isoformat() if mn else "2017-01-01",
        "max": mx.date().isoformat() if mx else date.today().isoformat(),
    }


def daily_rows(report_date: str, dept_id=None) -> list:
    """All (non-deleted) users for one date, LEFT JOINed so absentees appear."""
    sql = f"""
        SELECT u.UserID, u.Name AS UserName, d.Name AS Department, u.DPTID,
               a.PDate, {_PUNCH_SELECT}, a.OutPunch, a.WorkTime, a.LateIn, a.EarlyOut
        FROM Mx_UserMst u
        LEFT JOIN Mx_DepartmentMst d ON d.DPTID = u.DPTID
        LEFT JOIN Mx_DATDTrn a ON a.UserID = u.UserID AND a.PDate = ?
        WHERE u.dltdflg = 0
          AND u.UserID IN (SELECT UserID FROM Mx_DATDTrn
                           WHERE Punch1 IS NOT NULL AND PDate >= ?)
    """
    params = [report_date, active_cutoff()]
    if dept_id:
        sql += " AND u.DPTID = ?"
        params.append(dept_id)
    sql += " ORDER BY d.Name, u.Name"
    return query(sql, tuple(params))


def monthly_rows(start: str, end: str, dept_id=None) -> list:
    sql = f"""
        SELECT a.UserID, a.PDate, {_PUNCH_SELECT}, a.OutPunch,
               a.WorkTime, a.LateIn, a.EarlyOut
        FROM Mx_DATDTrn a
        JOIN Mx_UserMst u ON u.UserID = a.UserID
        WHERE a.PDate BETWEEN ? AND ? AND u.dltdflg = 0
    """
    params = [start, end]
    if dept_id:
        sql += " AND u.DPTID = ?"
        params.append(dept_id)
    return query(sql, tuple(params))


def misspunch_rows(start: str, end: str, dept_id=None, user_id=None) -> list:
    sql = f"""
        SELECT u.UserID, u.Name AS UserName, d.Name AS Department, u.DPTID,
               a.PDate, {_PUNCH_SELECT}, a.OutPunch, a.WorkTime, a.LateIn, a.EarlyOut
        FROM Mx_DATDTrn a
        JOIN Mx_UserMst u ON u.UserID = a.UserID
        LEFT JOIN Mx_DepartmentMst d ON d.DPTID = u.DPTID
        WHERE a.PDate BETWEEN ? AND ? AND u.dltdflg = 0
    """
    params = [start, end]
    if dept_id:
        sql += " AND u.DPTID = ?"
        params.append(dept_id)
    if user_id:
        sql += " AND u.UserID = ?"
        params.append(user_id)
    sql += " ORDER BY a.PDate, d.Name, u.Name"
    return query(sql, tuple(params))


def user_rows(start: str, end: str, user_id=None, dept_id=None, search: str = None) -> list:
    sql = f"""
        SELECT u.UserID, u.Name AS UserName, d.Name AS Department, u.DPTID,
               a.PDate, {_PUNCH_SELECT}, a.OutPunch, a.WorkTime, a.LateIn, a.EarlyOut
        FROM Mx_DATDTrn a
        JOIN Mx_UserMst u ON u.UserID = a.UserID
        LEFT JOIN Mx_DepartmentMst d ON d.DPTID = u.DPTID
        WHERE a.PDate BETWEEN ? AND ? AND u.dltdflg = 0
    """
    params = [start, end]
    if dept_id:
        sql += " AND u.DPTID = ?"
        params.append(dept_id)

    search = (search or "").strip()
    if search:
        sql += " AND (u.UserID = ? OR u.Name LIKE ?)"
        params += [search, f"%{search}%"]
    elif user_id:
        sql += " AND u.UserID = ?"
        params.append(user_id)
    else:
        sql += (" AND u.UserID IN (SELECT UserID FROM Mx_DATDTrn "
                 "WHERE Punch1 IS NOT NULL AND PDate >= ?)")
        params.append(active_cutoff())
    sql += " ORDER BY u.Name, a.PDate"
    return query(sql, tuple(params))


def inactive_rows(inactive_days: int, dept_id=None) -> list:
    sql = """
        SELECT u.UserID, u.Name AS UserName, d.Name AS Department, u.DPTID,
               u.JoinDT, u.LeaveDT,
               MAX(a.PDate) AS LastSeen
        FROM Mx_UserMst u
        LEFT JOIN Mx_DepartmentMst d ON d.DPTID = u.DPTID
        LEFT JOIN Mx_DATDTrn a
               ON a.UserID = u.UserID AND a.Punch1 IS NOT NULL
        WHERE u.dltdflg = 0
          AND (u.LeaveDT IS NULL OR u.LeaveDT > GETDATE())
    """
    params = []
    if dept_id:
        sql += " AND u.DPTID = ?"
        params.append(dept_id)
    sql += """
        GROUP BY u.UserID, u.Name, d.Name, u.DPTID, u.JoinDT, u.LeaveDT
        HAVING MAX(a.PDate) IS NULL
            OR MAX(a.PDate) < DATEADD(DAY, -?, CAST(GETDATE() AS date))
        ORDER BY d.Name, u.Name
    """
    params.append(inactive_days)
    return query(sql, tuple(params))
