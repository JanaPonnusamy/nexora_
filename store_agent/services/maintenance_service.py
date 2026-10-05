"""Scheduled SQLite cache maintenance so store_agent.db never bloats.

The sync orchestrators prune sync_row_cache incrementally per cycle, but the
DB file only shrinks on VACUUM and the history tables (sync_execution_log /
sync_execution / sync_ack) grow unbounded otherwise. This runs the same trim
the one-shot cleanup script does, but on a timer inside the agent, for every
store's rows in the shared DB at once.

Never touches sync_pending_chunks: those are the offline-HO recovery outbox and
a PENDING chunk not yet acked is real un-uploaded data, never garbage.
"""
import sqlite3
import threading
import time


def run_cache_maintenance(db_path, log_retention_days=30):
    """Prune ROLLING_WINDOW row-hash backlog + old history rows, then VACUUM.
    Returns a stats dict. Safe to call repeatedly."""
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        table_rows_removed = {}
        cur.execute(
            "SELECT table_name, sync_mode, window_days FROM sync_table_config "
            "WHERE is_active = 1"
        )
        for table_name, sync_mode, window_days in cur.fetchall():
            if (sync_mode or "").upper() != "ROLLING_WINDOW" or not window_days:
                continue
            cutoff = time.strftime(
                "%Y-%m-%dT%H:%M:%S",
                time.gmtime(time.time() - (int(window_days) + 30) * 86400),
            )
            cur.execute(
                "DELETE FROM sync_row_cache WHERE table_name = ? AND last_sync_time < ?",
                (table_name, cutoff),
            )
            table_rows_removed[table_name] = cur.rowcount

        log_cutoff = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - log_retention_days * 86400)
        )
        cur.execute("DELETE FROM sync_execution_log WHERE created_on < ?", (log_cutoff,))
        exec_log_removed = cur.rowcount
        cur.execute(
            "DELETE FROM sync_execution WHERE completed_at IS NOT NULL AND completed_at < ?",
            (log_cutoff,),
        )
        exec_removed = cur.rowcount
        cur.execute("DELETE FROM sync_ack WHERE acked_at < ?", (log_cutoff,))
        ack_removed = cur.rowcount

        conn.commit()
        cur.execute("VACUUM")
        return {
            "row_cache_removed_by_table": table_rows_removed,
            "sync_execution_log_removed": exec_log_removed,
            "sync_execution_removed": exec_removed,
            "sync_ack_removed": ack_removed,
        }
    finally:
        conn.close()


def start_cache_maintenance_thread(db_path, interval_seconds=6 * 3600,
                                   startup_delay_seconds=300, log=print):
    """Daemon thread that runs run_cache_maintenance() shortly after startup and
    every interval_seconds thereafter. Never raises out of the loop."""
    def _loop():
        time.sleep(startup_delay_seconds)
        while True:
            try:
                stats = run_cache_maintenance(db_path)
                total = (sum(stats["row_cache_removed_by_table"].values())
                         + stats["sync_execution_log_removed"]
                         + stats["sync_execution_removed"]
                         + stats["sync_ack_removed"])
                if total:
                    log(f"[MAINT] cache trim removed {total} rows + VACUUM")
            except Exception:
                try:
                    log("[MAINT] cache maintenance failed")
                except Exception:
                    pass
            time.sleep(interval_seconds)

    threading.Thread(target=_loop, daemon=True).start()
