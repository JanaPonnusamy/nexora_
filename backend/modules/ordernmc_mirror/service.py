"""Pull / ack protocol for the OrderNMC mirror.

The agent loops ``pull`` -> apply -> ``ack`` until ``pull`` says idle. HO owns
all state: which table is next, the keyset cursor inside it, and the ledger of
row hashes each target has applied. A pull that finds no changed rows keeps
advancing through the table server-side (within a time budget) so the remote
PC only round-trips for real data.

Statuses returned by pull:
  batch     -- rows to apply, then ack(batch_id)
  progress  -- scanned for a while, nothing to send yet; pull again now
  idle      -- every table is up to date; pull again after the interval
  disabled  -- no enabled target for this device
"""
from __future__ import annotations

import datetime
import os
import time

from modules.ordernmc_mirror import catalog, repository as repo, sources
from modules.ordernmc_mirror.sql_builder import heap_groups_sql, keyset_params, pk_page_sql, sql_type


class MirrorError(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _int_env(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


PAGE_ROWS = _int_env("ORDERNMC_MIRROR_PAGE_ROWS", 10000)
HEAP_GROUPS = _int_env("ORDERNMC_MIRROR_HEAP_GROUPS", 5000)
PULL_BUDGET_SECONDS = _int_env("ORDERNMC_MIRROR_PULL_BUDGET_SECONDS", 20)
# Even a table the usage stats call unchanged is fully re-verified this often.
FULL_PASS_HOURS = _int_env("ORDERNMC_MIRROR_FULL_PASS_HOURS", 24)
# Without trustworthy write stats every table is re-verified this often instead
# (a pass only SENDS changed rows, but it hashes every in-scope row).
UNTRACKED_RESCAN_MINUTES = _int_env("ORDERNMC_MIRROR_UNTRACKED_RESCAN_MINUTES", 30)


def _whitelist(target):
    raw = (target.get("tables") or "").strip()
    return [p.strip() for p in raw.split(",") if p.strip()] or None


def _stores(target):
    """Store names a store-scoped target is limited to, or [] for everything."""
    raw = (target.get("stores") or "").strip()
    return sorted({p.strip() for p in raw.split(",") if p.strip()})


def _list_tables(conn, target):
    return catalog.list_tables(conn, _whitelist(target), store_scoped=bool(_stores(target)))


def _store_params(table, stores):
    return list(stores) if table.get("store_column") and stores else []


def _needs_pass(state, object_id, now, server_start, last_updates):
    started = state.get("last_pass_started_at") if state else None
    if started is None:
        return True
    done = state.get("last_pass_completed_at")
    if done is None or now - done > datetime.timedelta(hours=FULL_PASS_HOURS):
        return True
    if last_updates is None:
        return now - done > datetime.timedelta(minutes=UNTRACKED_RESCAN_MINUTES)
    lu = last_updates.get(object_id)
    if lu is None:
        # No write since SQL Server started; unchanged only if our last pass
        # began after that start (otherwise the stats were reset under us).
        return server_start is None or server_start > started
    return lu >= started


def _column_meta(table):
    return [{"name": c["name"], "type": c["type"], "sql_type": sql_type(c),
             "nullable": c["nullable"], "identity": c["identity"]}
            for c in table["columns"]]


def _encode_cursor(table, row_by_name):
    return [catalog.encode_value(row_by_name[k]) for k in table["key_columns"]]


def _decode_cursor(table, cursor):
    types = {c["name"]: c["type"] for c in table["columns"]}
    return [catalog.decode_value(types[k], v) for k, v in zip(table["key_columns"], cursor)]


def _fetch_pk_page(conn, target_id, table_id, table, cursor, stores=()):
    """-> (changed_rows, items, next_cursor, is_last). Rows are lists in column
    order; items are (ph, rh) for the ledger."""
    cols = table["columns"]
    by_name = {c["name"]: c for c in cols}
    key_cols = [by_name[k] for k in table["key_columns"]]
    store_params = _store_params(table, stores)
    sql = pk_page_sql(table["name"], cols, key_cols, cursor is not None,
                      table.get("store_column"), len(store_params))
    params = [PAGE_ROWS] + store_params
    if cursor is not None:
        params += keyset_params(_decode_cursor(table, cursor))
    params += [int(target_id), int(table_id), PAGE_ROWS]
    cur = conn.cursor()
    cur.execute(sql, params)
    names = [d[0] for d in cur.description]
    n = len(cols)
    i_ph, i_rh, i_rn, i_lrh = (names.index(x) for x in ("__ph", "__rh", "__rn", "__lrh"))
    rows, items, next_cursor, is_last = [], [], None, True
    for r in cur.fetchall():
        changed = r[i_lrh] is None or bytes(r[i_lrh]) != bytes(r[i_rh])
        if changed:
            rows.append([catalog.encode_value(v) for v in r[:n]])
            items.append((bytes(r[i_ph]), bytes(r[i_rh])))
        if r[i_rn] == PAGE_ROWS:
            is_last = False
            next_cursor = _encode_cursor(table, dict(zip(names[:n], r[:n])))
    return rows, items, next_cursor, is_last


def _fetch_heap_groups(conn, target_id, table_id, table, stores=()):
    cols = table["columns"]
    by_name = {c["name"]: c for c in cols}
    key_cols = [by_name[k] for k in table["key_columns"]]
    store_params = _store_params(table, stores)
    cur = conn.cursor()
    cur.execute(heap_groups_sql(table["name"], cols, key_cols,
                                table.get("store_column"), len(store_params)),
                store_params + [HEAP_GROUPS, int(target_id), int(table_id)])
    names = [d[0] for d in cur.description]
    n = len(cols)
    i_ph, i_grh = names.index("__ph"), names.index("__grh")
    rows, groups = [], {}
    for r in cur.fetchall():
        rows.append([catalog.encode_value(v) for v in r[:n]])
        groups[bytes(r[i_ph])] = bytes(r[i_grh])
    return rows, list(groups.items()), None, len(groups) < HEAP_GROUPS


def _target_for_device(device_id):
    target = repo.get_target_by_device(device_id)
    if not target or not target["is_enabled"]:
        return None
    return target


def agent_config(device_id):
    target = _target_for_device(device_id)
    if not target:
        return {"enabled": False}
    return {
        "enabled": True,
        "target_id": target["target_id"],
        "source_name": target["source_name"],
        "interval_seconds": target["interval_seconds"],
        "target": {
            "server_name": target["server_name"],
            "database_name": target["database_name"],
            "username": target["username"],
            "password_encrypted": target["password_encrypted"].hex() if target["password_encrypted"] else None,
        },
    }


def pull(device_id):
    target = _target_for_device(device_id)
    if not target:
        return {"status": "disabled"}
    target_id = target["target_id"]
    repo.touch_target(target_id, pulled=True)
    conn = sources.connect(target["source_name"])
    try:
        repo.ensure_source_schema(conn, target["source_name"])
        repo.purge_stale_batches(conn, target_id)
        tables = _list_tables(conn, target)
        stores = _stores(target)
        ids = repo.table_ids(conn, [t["name"] for t in tables])
        states = repo.load_states(conn, target_id)
        now, server_start = repo.server_clock(conn)
        last_updates = catalog.last_user_updates(conn)
        deadline = time.monotonic() + PULL_BUDGET_SECONDS

        for table in tables:
            table_id = ids[table["name"]]
            state = states.get(table_id) or {}
            if state.get("error_until") and state["error_until"] > now:
                continue
            if state.get("pass_started_at"):
                pass_started, cursor = state["pass_started_at"], state.get("cursor")
            elif _needs_pass(state, table["object_id"], now, server_start, last_updates):
                pass_started, cursor = now, None
            else:
                continue

            while True:
                if table["mode"] == "upsert":
                    rows, items, next_cursor, is_last = _fetch_pk_page(conn, target_id, table_id, table,
                                                                       cursor, stores)
                else:
                    rows, items, next_cursor, is_last = _fetch_heap_groups(conn, target_id, table_id, table,
                                                                           stores)
                if rows:
                    batch_id = repo.save_batch(conn, target_id, table_id, next_cursor,
                                               pass_started, is_last, items)
                    return {
                        "status": "batch", "batch_id": batch_id, "table": table["name"],
                        "mode": table["mode"], "key_columns": table["key_columns"],
                        "pk_columns": table["pk_columns"], "columns": _column_meta(table),
                        "rows": rows, "is_last": is_last, "source_rows": table["rows"],
                    }
                if is_last:
                    repo.complete_pass(conn, target_id, table_id, pass_started)
                    break
                cursor = next_cursor
                repo.save_progress(conn, target_id, table_id, cursor, pass_started)
                if time.monotonic() > deadline:
                    return {"status": "progress", "table": table["name"]}
            if time.monotonic() > deadline:
                return {"status": "progress", "table": table["name"]}
        return {"status": "idle", "interval_seconds": target["interval_seconds"]}
    finally:
        conn.close()


def ack(device_id, batch_id, ok, error=None):
    target = _target_for_device(device_id)
    if not target:
        raise MirrorError(404, "No enabled OrderNMC mirror target for this device")
    conn = sources.connect(target["source_name"])
    try:
        batch = repo.get_batch(conn, batch_id)
        if not batch or batch["target_id"] != target["target_id"]:
            # Reset, purged as stale, or already acked: the agent just pulls again.
            raise MirrorError(409, "Unknown or expired batch")
        if ok:
            repo.commit_batch(conn, batch)
            repo.touch_target(target["target_id"], acked=True, clear_error=True)
        else:
            repo.fail_batch(conn, batch, error or "apply failed")
            repo.touch_target(target["target_id"], error=error or "apply failed")
        return {"ok": True}
    finally:
        conn.close()


# ---- admin ----------------------------------------------------------------

def target_status(target_id):
    target = repo.get_target(target_id)
    if not target:
        raise MirrorError(404, "Target not found")
    conn = sources.connect(target["source_name"])
    try:
        repo.ensure_source_schema(conn, target["source_name"])
        tables = _list_tables(conn, target)
        ids = repo.table_ids(conn, [t["name"] for t in tables])
        states = repo.load_states(conn, target_id)
        counts = repo.ledger_counts(conn, target_id)
        out = []
        for t in tables:
            tid = ids[t["name"]]
            st = states.get(tid) or {}
            out.append({
                "table": t["name"], "mode": t["mode"], "source_rows": t["rows"],
                "acknowledged_keys": counts.get(tid, 0),
                "pass_in_progress": bool(st.get("pass_started_at")),
                "last_pass_completed_at": st.get("last_pass_completed_at"),
                "rows_sent": st.get("rows_sent", 0),
                "last_error": st.get("last_error"), "error_until": st.get("error_until"),
            })
        return {"target": public_target(target), "tables": out}
    finally:
        conn.close()


def reset(target_id, tables=None):
    target = repo.get_target(target_id)
    if not target:
        raise MirrorError(404, "Target not found")
    conn = sources.connect(target["source_name"])
    try:
        repo.ensure_source_schema(conn, target["source_name"])
        scope = None
        if tables:
            scope = list(repo.table_ids(conn, tables).values())
        repo.reset_target(conn, target_id, scope)
        return {"ok": True}
    finally:
        conn.close()


def public_target(target):
    t = dict(target)
    t["has_password"] = bool(t.pop("password_encrypted", None))
    return t
