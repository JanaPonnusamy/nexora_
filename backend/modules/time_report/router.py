"""Time Report API — read-only attendance reports over the Matrix COSEC
database, ported from the standalone COSEC Flask app.

Mirrors the legacy app's routes 1:1 (daily / monthly / misspunch / user /
inactive), returning JSON for the SPA and, when ``export=xlsx`` is passed, a
styled .xlsx download built by the same report dicts. No writes.
"""
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from modules.time_report import config, excel_export as xls, images, service
from modules.time_report.database import TimeReportDatabaseUnavailable
from modules.time_report.schemas import TimeReportMeta

router = APIRouter(prefix="/api/time-report", tags=["Time Report"])

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(buf, filename):
    return Response(
        content=buf.getvalue(),
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _guard(fn):
    """Translate a COSEC connectivity failure into a clean 503."""
    try:
        return fn()
    except TimeReportDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:  # module not configured (missing env)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/meta", response_model=TimeReportMeta)
def meta():
    """Filter context for the UI: report catalog, departments, users, bounds."""
    def build():
        return {
            "reports": service.catalog(),
            "departments": service.departments(),
            "users": service.users(),
            "bounds": service.date_bounds(),
            "today": date.today().isoformat(),
            "this_year": date.today().year,
            "this_month": date.today().month,
        }
    return _guard(build)


# --------------------------------------------------------------------------
# 1. Daily
# --------------------------------------------------------------------------
@router.get("/daily")
def daily(
    date_: str = Query(None, alias="date"),
    dept_id: str = Query(None),
    export: str = Query(None),
):
    rdate = date_ or date.today().isoformat()
    data = _guard(lambda: service.daily_report(rdate, dept_id))
    if export == "xlsx":
        return _xlsx(xls.daily_xlsx(data), f"daily_{rdate}.xlsx")
    return data


@router.get("/daily/image")
def daily_image(
    date_: str = Query(None, alias="date"),
    dept_id: str = Query(None),
):
    """PNG of a single store/department for one date."""
    rdate = date_ or date.today().isoformat()
    data = _guard(lambda: service.daily_report(rdate, dept_id))
    if not data["departments"]:
        raise HTTPException(status_code=404, detail="No data for that store/date.")
    dept = data["departments"][0]
    buf = images.department_image(dept, data)
    filename = f"{images._safe(dept['name'])}_{data['date_fmt']}.png"
    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/daily/images")
def daily_images(
    date_: str = Query(None, alias="date"),
    dept_id: str = Query(None),
):
    """One click -> zip with one PNG per store/department."""
    rdate = date_ or date.today().isoformat()
    data = _guard(lambda: service.daily_report(rdate, dept_id))
    buf = images.all_departments_zip(data)
    filename = f"store_images_{data['date_fmt']}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------
# 2. Monthly
# --------------------------------------------------------------------------
@router.get("/monthly")
def monthly(
    year: int = Query(None),
    month: int = Query(None),
    dept_id: str = Query(None),
    export: str = Query(None),
):
    today = date.today()
    year = year or today.year
    month = month or today.month
    data = _guard(lambda: service.monthly_report(year, month, dept_id))
    if export == "xlsx":
        return _xlsx(xls.monthly_xlsx(data), f"monthly_{year}_{month:02d}.xlsx")
    return data


# --------------------------------------------------------------------------
# 3. Miss punch
# --------------------------------------------------------------------------
@router.get("/misspunch")
def misspunch(
    start: str = Query(None),
    end: str = Query(None),
    dept_id: str = Query(None),
    user_id: str = Query(None),
    export: str = Query(None),
):
    start = start or date.today().replace(day=1).isoformat()
    end = end or date.today().isoformat()
    data = _guard(lambda: service.misspunch_report(start, end, dept_id, user_id))
    if export == "xlsx":
        rows = [([d["pdate_str"], d["user_id"], d["name"], d["department"],
                  " | ".join(d["punches"]), d["punch_count"], d["work_hm"]],
                 config.STATUS["MISS_PUNCH"]["hex"]) for d in data["rows"]]
        buf = xls.table_xlsx(
            f"Miss Punch Report  {start} to {end}",
            ["Date", "UserID", "Name", "Department", "Punches", "#Punch", "Work"],
            rows, legend=data["legend"])
        return _xlsx(buf, f"misspunch_{start}_{end}.xlsx")
    return data


# --------------------------------------------------------------------------
# 4. User report (summary / detail)
# --------------------------------------------------------------------------
@router.get("/user")
def user(
    start: str = Query(None),
    end: str = Query(None),
    user_id: str = Query(None),
    dept_id: str = Query(None),
    mode: str = Query("detail"),
    search: str = Query(None),
    export: str = Query(None),
):
    start = start or date.today().replace(day=1).isoformat()
    end = end or date.today().isoformat()
    data = _guard(lambda: service.user_report(start, end, user_id, dept_id, mode, search))

    if export == "xlsx":
        if mode == "summary":
            rows = [([d["user_id"], d["name"], d["department"], d["present"],
                      d["full"], d["short"], d["low"], d["miss_punch"],
                      d["absent"], d["late"], d["total_hm"]], None)
                    for d in data["rows"]]
            buf = xls.table_xlsx(
                f"User Summary  {start} to {end}",
                ["UserID", "Name", "Department", "Present", "Full", "Short",
                 "Low", "Miss", "Absent", "Late", "Total Hrs"], rows,
                legend=data["legend"])
        else:
            rows = [([d["pdate_str"], d["user_id"], d["name"],
                      " | ".join(d["punches"]), d["work_hm"], d["late_in"] or ""],
                     d["status_hex"]) for d in data["rows"]]
            buf = xls.table_xlsx(
                f"User Detail  {start} to {end}",
                ["Date", "UserID", "Name", "Punches", "Work", "Late"],
                rows, legend=data["legend"])
        return _xlsx(buf, f"user_{mode}_{start}_{end}.xlsx")
    return data


# --------------------------------------------------------------------------
# 5. Inactive users
# --------------------------------------------------------------------------
@router.get("/inactive")
def inactive(
    days: int = Query(None),
    dept_id: str = Query(None),
    export: str = Query(None),
):
    days = days or config.INACTIVE_DAYS
    data = _guard(lambda: service.inactive_users(days, dept_id))
    if export == "xlsx":
        rows = [([d["user_id"], d["name"], d["department"], d["join_dt"],
                  d["last_seen"], d["days_since"]], None) for d in data["rows"]]
        buf = xls.table_xlsx(
            f"Inactive Users (no punch for {days}+ days)",
            ["UserID", "Name", "Department", "Join Date", "Last Punch", "Days Since"],
            rows)
        return _xlsx(buf, f"inactive_users_{days}d.xlsx")
    return data
