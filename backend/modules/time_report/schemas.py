"""Response schemas for the Time Report module.

Only the light-weight metadata endpoint is strictly typed. The report bodies
themselves are richly nested (department-grouped daily rows, a monthly muster
grid of coloured cells, etc.) and vary per report, so they are returned as
plain dicts and serialised by FastAPI directly -- the frontend renders each
shape with a dedicated view, exactly as the legacy app did.
"""
from typing import List, Optional

from pydantic import BaseModel


class DepartmentOption(BaseModel):
    # DPTID is numeric in COSEC (returned as Decimal) -> coerced to int.
    DPTID: int
    Name: Optional[str] = None


class UserOption(BaseModel):
    # UserID is a varchar in COSEC and is NOT always numeric (e.g. '493SA'),
    # so it must be carried as a string end-to-end.
    UserID: str
    Name: Optional[str] = None
    DPTID: Optional[int] = None


class DateBounds(BaseModel):
    min: str
    max: str


class ReportInfo(BaseModel):
    key: str
    label: str
    group: str
    description: str


class TimeReportMeta(BaseModel):
    reports: List[ReportInfo]
    departments: List[DepartmentOption]
    users: List[UserOption]
    bounds: DateBounds
    today: str
    this_year: int
    this_month: int
