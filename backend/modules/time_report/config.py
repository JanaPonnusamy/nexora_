"""Business rules and colour rules for the Time Report module.

Ported unchanged from the standalone COSEC Flask app's config.py -- everything
tunable about the reports lives here so the rest of the module never
hard-codes a threshold or a colour.
"""

# ======================= BUSINESS RULES =======================
# A normal full working day, in minutes.
# >= 8h30m worked is treated as a good/full day -> shown WHITE (no colour).
FULL_DAY_MINUTES = 510        # 8h 30m
# 8h00m..8h29m -> "near full" (soft yellow)
NEAR_FULL_MINUTES = 480       # 8h 00m

# Date format used on report headers (period line). dd-mm-yyyy.
DATE_FMT = "%d-%m-%Y"

# A user is considered ACTIVE only if they punched at least once within this
# window (current month OR the last N days, whichever reaches further back).
# Everyone else is treated as inactive and hidden from the attendance reports.
ACTIVE_WINDOW_DAYS = 30

# Legacy/explicit inactivity threshold for the dedicated Inactive report.
INACTIVE_DAYS = 30            # no punch in current month / last 30 days

# How many punch columns exist on Mx_DATDTrn (Punch1..Punch12).
MAX_PUNCHES = 12

# Late-in (minutes) above which a day is flagged as a late arrival.
LATE_IN_FLAG_MINUTES = 1


# ======================= COLOUR / STATUS RULES =======================
# Smooth / light palette with BLACK text everywhere (easy on the eyes).
BLACK = "000000"
STATUS = {
    "FULL": {"hex": "FFFFFF", "text": BLACK, "label": "Full Day (>= 8:30)", "code": "P"},
    "SHORT": {"hex": "FFF3B0", "text": BLACK, "label": "Near Full (8:00-8:29)", "code": "S"},
    "LOW": {"hex": "BBDEFB", "text": BLACK, "label": "Short (< 8:00)", "code": "L"},
    "MISS_PUNCH": {"hex": "F4A7A7", "text": BLACK, "label": "Miss Punch (finger not placed)", "code": "M"},
    "ABSENT": {"hex": "FFFFFF", "text": BLACK, "label": "Absent / No punch", "code": "A"},
    "LATE": {"hex": "FFD9A0", "text": BLACK, "label": "Late Arrival", "code": "T"},
}

COLOR_HEADER = "92D050"        # department header (smooth green)
COLOR_SUBHEAD = "D9D9D9"       # column header (light grey)
COLOR_TOTAL = "E2EFDA"         # totals row (very light green)

WHITE = "FFFFFF"


def classify_day(punch_count: int, work_minutes, late_in, has_record: bool) -> str:
    """Return a STATUS key for one attendance day.

    Rules (in priority order):
      1. No record / no punches at all     -> ABSENT  (blank work hours)
      2. Odd number of punches             -> MISS_PUNCH (finger not placed properly)
      3. Worktime >= 8:30                   -> FULL
      4. Worktime 8:00-8:29                 -> SHORT (near full)
      5. anything else (present, < 8:00)    -> LOW
    Late arrival is reported as a *separate* flag, not as the row colour, so a
    late-but-full day is still visibly a full day.
    """
    wm = int(work_minutes or 0)

    if not has_record or (punch_count == 0 and wm == 0):
        return "ABSENT"
    if punch_count % 2 != 0:
        return "MISS_PUNCH"
    if wm >= FULL_DAY_MINUTES:
        return "FULL"
    if wm >= NEAR_FULL_MINUTES:
        return "SHORT"
    return "LOW"
