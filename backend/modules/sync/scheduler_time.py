"""Grid-aligned schedule time math shared by the sync scheduler and the
Schedule Plan API.

Kept dependency-free (no DB imports, no FastAPI) so every caller -- the
background scheduler tick, the Schedule Plan list endpoint, the status board
-- computes the exact same boundary from (interval_minutes, wall clock) alone.
next_run_at is therefore never persisted: a stored value is a second source of
truth that can drift from what the scheduler actually does, which is exactly
the kind of disconnect that made the old Schedule Plan screen lie about its
own state.

Timezone: server local time throughout (Python datetime.now() and SQL
Server GETDATE()), matching every other timestamp already written by this
sync subsystem (sync_execution.started_at, sync_schedule.last_run_at, etc).
Never mixed with UTC or browser-local time -- the displayed Schedule Plan
time and the actual scheduler firing time must agree, and the only way to
guarantee that is to use one clock everywhere.
"""
import datetime as _dt

# Arbitrary fixed epoch aligned to midnight -- NOT a "start date" for any
# schedule, just the zero point the grid is measured from so every interval
# lands on :00/:30-style boundaries regardless of when a schedule row was
# created.
_ANCHOR = _dt.datetime(2000, 1, 1)


def _step_seconds(interval_minutes):
    if not interval_minutes or interval_minutes <= 0:
        return None
    return interval_minutes * 60


def current_grid_slot(interval_minutes, now=None):
    """Most recent grid boundary <= now -- the slot that is currently due.

    Used by the scheduler to decide *what* to dispatch: "have I already
    handled (store, schedule, this slot)?" If the process was offline across
    several boundaries, this still returns only the single latest one --
    that's what collapses an outage into one catch-up run instead of a
    backlog of missed runs.
    """
    step = _step_seconds(interval_minutes)
    if step is None:
        return None
    now = now or _dt.datetime.now()
    elapsed = (now - _ANCHOR).total_seconds()
    n = int(elapsed // step)
    return _ANCHOR + _dt.timedelta(seconds=n * step)


def next_grid_boundary(interval_minutes, now=None):
    """Smallest grid boundary strictly after now -- the "Next Run" display
    value. Always one step ahead of current_grid_slot()."""
    step = _step_seconds(interval_minutes)
    if step is None:
        return None
    now = now or _dt.datetime.now()
    elapsed = (now - _ANCHOR).total_seconds()
    n = int(elapsed // step) + 1
    return _ANCHOR + _dt.timedelta(seconds=n * step)
