"""Named OrderNMC mirror SOURCES (the HO-side databases a target copies).

    ORDERNMC_MIRROR_SOURCES=success=192.168.10.32;nmc=192.168.10.73/OrderNMC

Each entry is ``name=server[/database]`` (database defaults to OrderNMC). The
login is ORDERNMC_MIRROR_<NAME>_USERNAME / _PASSWORD when set, else the Legacy
Order console's OrderNMC login (LEGACY_DB_* -> DB_*). The source ``default`` is
always available and is exactly the Legacy Order console's central OrderNMC.

A source only needs to be reachable from the HO backend that the remote PC
talks to, not from the remote PC itself -- the remote side only ever sees HTTP.
"""
from __future__ import annotations

import os
import re

import pyodbc

from modules.legacy_order import database as legacy_db

DEFAULT_SOURCE = "default"
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,50}$")


def configured_sources() -> dict[str, dict]:
    """{name: {"server", "database"}} parsed from ORDERNMC_MIRROR_SOURCES."""
    out = {}
    raw = os.getenv("ORDERNMC_MIRROR_SOURCES", "")
    for part in re.split(r"[;,]", raw):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, target = (s.strip() for s in part.split("=", 1))
        if not _NAME_RE.match(name) or not target:
            continue
        server, _, database = target.partition("/")
        out[name.lower()] = {"server": server.strip(), "database": database.strip() or "OrderNMC"}
    return out


def source_names() -> list[str]:
    return [DEFAULT_SOURCE] + sorted(n for n in configured_sources() if n != DEFAULT_SOURCE)


def describe(name: str) -> dict:
    """Server/database of a source (no credentials) for admin listings."""
    key = (name or "").lower()
    if key == DEFAULT_SOURCE:
        return {"name": DEFAULT_SOURCE,
                "server": os.getenv("LEGACY_DB_SERVER") or os.getenv("DB_SERVER"),
                "database": os.getenv("LEGACY_DB_DATABASE", "OrderNMC")}
    src = configured_sources().get(key)
    if not src:
        raise KeyError(name)
    return {"name": key, **src}


def connection_string(name: str) -> str:
    key = (name or "").lower()
    if key == DEFAULT_SOURCE:
        return legacy_db.central_connection_string()
    src = configured_sources().get(key)
    if not src:
        raise KeyError(f"Unknown OrderNMC mirror source '{name}'")
    env = key.upper().replace("-", "_")
    username = (os.getenv(f"ORDERNMC_MIRROR_{env}_USERNAME")
                or os.getenv("LEGACY_DB_USERNAME") or os.getenv("DB_USERNAME"))
    password = (os.getenv(f"ORDERNMC_MIRROR_{env}_PASSWORD")
                or os.getenv("LEGACY_DB_PASSWORD") or os.getenv("DB_PASSWORD"))
    return legacy_db.branch_connection_string(src["server"], src["database"], username, password)


def connect(name: str, timeout: int = 10, query_timeout: int = 180):
    conn = pyodbc.connect(connection_string(name), timeout=timeout)
    conn.timeout = query_timeout
    return conn
