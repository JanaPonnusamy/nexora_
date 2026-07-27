"""Report builders for the Time Report module.

Ported from the standalone COSEC Flask app's reports.py. Every public function
returns a plain dict/list structure consumed identically by the JSON API and
the Excel exporter, so the two never drift apart.
"""
from calendar import monthrange
from datetime import date, datetime

from modules.time_report import config, repository as repo

PUNCH_COLS = repo.PUNCH_COLS


# ----------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------
def fmt_time(dt) -> str:
    return dt.strftime("%H:%M") if isinstance(dt, datetime) else ""


def fmt_hm(minutes) -> str:
    if minutes in (None, "", 0):
        return "" if minutes in (None, "") else "00:00"
    m = int(minutes)
    return f"{m // 60:02d}:{m % 60:02d}"


def fmt_date(d) -> str:
    """Format a date/ISO string as dd-mm-yyyy (config.DATE_FMT)."""
    if d is None:
        return ""
    if isinstance(d, str):
        d = datetime.fromisoformat(d)
    return d.strftime(config.DATE_FMT)


def _punch_list(row) -> list:
    """Formatted HH:MM for every populated punch (in order)."""
    out = []
    for c in PUNCH_COLS:
        v = row.get(c)
        if isinstance(v, datetime):
            out.append(v.strftime("%H:%M"))
    return out


def _build_day(row) -> dict:
    """Turn one Mx_DATDTrn-joined row into a classified day record."""
    punches = _punch_list(row)
    count = len(punches)
    work = row.get("WorkTime")
    late = int(row.get("LateIn") or 0)
    has_record = row.get("PDate") is not None
    status = config.classify_day(count, work, late, has_record)
    return {
        "user_id": row.get("UserID"),
        "name": row.get("UserName") or "",
        "department": row.get("Department") or "-",
        "dpt_id": row.get("DPTID"),
        "pdate": row.get("PDate"),
        "punches": punches,
        "punch_count": count,
        "first_in": punches[0] if punches else "",
        "last_out": fmt_time(row.get("OutPunch")) or (punches[-1] if count > 1 else ""),
        "work_minutes": int(work or 0),
        "work_hm": fmt_hm(work),
        "late_in": late,
        "early_out": int(row.get("EarlyOut") or 0),
        "is_late": late >= config.LATE_IN_FLAG_MINUTES,
        "status": status,
        "status_label": config.STATUS[status]["label"],
        "status_hex": config.STATUS[status]["hex"],
        "status_text": config.STATUS[status]["text"],
        "status_code": config.STATUS[status]["code"],
    }


def _empty_totals() -> dict:
    return {"full": 0, "short": 0, "low": 0, "miss_punch": 0,
            "absent": 0, "late": 0, "present": 0}


def _tally(t: dict, d: dict):
    s = d["status"]
    if s == "FULL":
        t["full"] += 1
    elif s == "SHORT":
        t["short"] += 1
    elif s == "LOW":
        t["low"] += 1
    elif s == "MISS_PUNCH":
        t["miss_punch"] += 1
    elif s == "ABSENT":
        t["absent"] += 1
    if d.get("is_late"):
        t["late"] += 1
    t["present"] = t["full"] + t["short"] + t["low"]


def _legend(keys=None) -> list:
    keys = keys or list(config.STATUS.keys())
    return [{"label": config.STATUS[k]["label"], "hex": config.STATUS[k]["hex"],
             "code": config.STATUS[k]["code"]} for k in keys]


# ----------------------------------------------------------------------------
# filter lookups (for the UI dropdowns)
# ----------------------------------------------------------------------------
def departments() -> list:
    return repo.get_departments()


def users(dept_id=None) -> list:
    return repo.get_users(dept_id)


def date_bounds() -> dict:
    return repo.date_bounds()


def catalog() -> list:
    """Catalog of the reports this module exposes, for a nav/selector UI."""
    return [
        {"key": "daily", "label": "Daily", "group": "Attendance",
         "description": "Department-wise attendance for one date. Absentees included."},
        {"key": "monthly", "label": "Monthly", "group": "Attendance",
         "description": "Day-by-day muster grid for a month with present/absent/miss/late totals."},
        {"key": "misspunch", "label": "Miss Punch", "group": "Attendance",
         "description": "Every day with an odd punch count (finger not placed properly)."},
        {"key": "user", "label": "User", "group": "Attendance",
         "description": "Per-user or all-users, summary (totals) or detail (day by day)."},
        {"key": "inactive", "label": "Inactive Users", "group": "Attendance",
         "description": "Users active in the system but with no punch for ~1 month."},
    ]


# ----------------------------------------------------------------------------
# 1. Department-wise DAILY report
# ----------------------------------------------------------------------------
def daily_report(report_date: str, dept_id=None) -> dict:
    rows = [_build_day(r) for r in repo.daily_rows(report_date, dept_id)]

    departments_ = []
    grand = _empty_totals()
    for r in rows:
        dept_name = r["department"]
        if not departments_ or departments_[-1]["name"] != dept_name:
            departments_.append({"name": dept_name, "dpt_id": r["dpt_id"],
                                  "rows": [], "totals": _empty_totals()})
        departments_[-1]["rows"].append(r)
        _tally(departments_[-1]["totals"], r)
        _tally(grand, r)

    period = f"Department-Wise Daily Details From {fmt_date(report_date)} To {fmt_date(report_date)}"
    return {
        "title": "Department-wise Daily Attendance",
        "date": report_date,
        "date_fmt": fmt_date(report_date),
        "period": period,
        "departments": departments_,
        "totals": grand,
        "legend": _legend(),
    }


# ----------------------------------------------------------------------------
# 2. Department-wise MONTHLY report (muster grid + totals)
# ----------------------------------------------------------------------------
def monthly_report(year: int, month: int, dept_id=None) -> dict:
    days_in_month = monthrange(year, month)[1]
    start = f"{year:04d}-{month:02d}-01"
    end = f"{year:04d}-{month:02d}-{days_in_month:02d}"

    users_ = repo.get_users(dept_id, active_only=True)
    rows = repo.monthly_rows(start, end, dept_id)

    by_user = {}
    for r in rows:
        d = _build_day({**r, "UserName": "", "Department": "", "DPTID": None})
        day = r["PDate"].day
        by_user.setdefault(r["UserID"], {})[day] = d

    dept_name = {x["DPTID"]: x["Name"] for x in repo.get_departments()}

    user_rows = []
    grand = _empty_totals()
    for u in users_:
        days = by_user.get(u["UserID"], {})
        cells = []
        tot = _empty_totals()
        total_minutes = 0
        for day in range(1, days_in_month + 1):
            d = days.get(day)
            if d:
                cells.append({"code": d["status_code"], "status": d["status"],
                              "hex": d["status_hex"], "work_hm": d["work_hm"]})
                _tally(tot, d)
                _tally(grand, d)
                total_minutes += d["work_minutes"]
            else:
                cells.append({"code": "", "status": None, "hex": "FFFFFF", "work_hm": ""})
        user_rows.append({
            "user_id": u["UserID"],
            "name": u["Name"],
            "dpt_id": u["DPTID"],
            "department": dept_name.get(u["DPTID"], "-"),
            "cells": cells,
            "present": tot["full"] + tot["short"] + tot["low"],
            "absent": tot["absent"],
            "miss_punch": tot["miss_punch"],
            "late": tot["late"],
            "total_hm": fmt_hm(total_minutes) or "00:00",
        })

    user_rows.sort(key=lambda x: (x["department"], x["name"]))

    return {
        "title": "Department-wise Monthly Muster",
        "year": year,
        "month": month,
        "month_name": date(year, month, 1).strftime("%B %Y"),
        "days_in_month": days_in_month,
        "days": list(range(1, days_in_month + 1)),
        "rows": user_rows,
        "totals": grand,
        "legend": _legend(),
    }


# ----------------------------------------------------------------------------
# 3. MISS PUNCH report
# ----------------------------------------------------------------------------
def misspunch_report(start: str, end: str, dept_id=None, user_id=None) -> dict:
    rows = []
    for r in repo.misspunch_rows(start, end, dept_id, user_id):
        d = _build_day(r)
        if d["status"] == "MISS_PUNCH":
            d["pdate_str"] = r["PDate"].date().isoformat()
            rows.append(d)

    return {
        "title": "Miss Punch Report",
        "start": start,
        "end": end,
        "rows": rows,
        "count": len(rows),
        "legend": _legend(["MISS_PUNCH"]),
    }


# ----------------------------------------------------------------------------
# 4. USER report (summary / detail, single user or all)
# ----------------------------------------------------------------------------
def user_report(start: str, end: str, user_id=None, dept_id=None,
                mode: str = "detail", search: str = None) -> dict:
    raw = repo.user_rows(start, end, user_id, dept_id, search)
    search = (search or "").strip()

    if mode == "summary":
        agg = {}
        for r in raw:
            d = _build_day(r)
            key = d["user_id"]
            s = agg.setdefault(key, {
                "user_id": d["user_id"], "name": d["name"],
                "department": d["department"], "totals": _empty_totals(),
                "minutes": 0, "days": 0,
            })
            _tally(s["totals"], d)
            s["minutes"] += d["work_minutes"]
            s["days"] += 1
        summary = []
        for s in agg.values():
            t = s["totals"]
            summary.append({
                "user_id": s["user_id"], "name": s["name"],
                "department": s["department"],
                "present": t["full"] + t["short"] + t["low"],
                "full": t["full"], "short": t["short"], "low": t["low"],
                "miss_punch": t["miss_punch"], "absent": t["absent"],
                "late": t["late"], "total_hm": fmt_hm(s["minutes"]) or "00:00",
            })
        summary.sort(key=lambda x: (x["department"], x["name"]))
        return {"title": "User Summary Report", "start": start, "end": end,
                "mode": "summary", "rows": summary, "legend": _legend(),
                "search": search}

    rows = []
    for r in raw:
        d = _build_day(r)
        d["pdate_str"] = r["PDate"].date().isoformat()
        rows.append(d)
    return {"title": "User Detail Report", "start": start, "end": end,
            "mode": "detail", "rows": rows, "legend": _legend(),
            "search": search}


# ----------------------------------------------------------------------------
# 5. INACTIVE users (active in DB, no punch for N days)
# ----------------------------------------------------------------------------
def inactive_users(inactive_days: int = None, dept_id=None) -> dict:
    inactive_days = inactive_days or config.INACTIVE_DAYS
    today = date.today()
    rows = []
    for r in repo.inactive_rows(inactive_days, dept_id):
        last = r["LastSeen"]
        last_str = last.date().isoformat() if last else "Never"
        days_since = (today - last.date()).days if last else None
        rows.append({
            "user_id": r["UserID"],
            "name": r["UserName"] or "",
            "department": r["Department"] or "-",
            "join_dt": r["JoinDT"].date().isoformat() if r["JoinDT"] else "",
            "last_seen": last_str,
            "days_since": days_since if days_since is not None else "-",
        })

    return {
        "title": "Inactive Users (active in system, no punch)",
        "inactive_days": inactive_days,
        "rows": rows,
        "count": len(rows),
    }
