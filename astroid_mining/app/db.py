"""SQLite state for the asteroid mining fleet.

The rich documents (satellite / base station / robot) are stored as JSON blobs,
while everything the API transitions or queries (status, robot state, links,
backups, metrics history, reports, commands) lives in real columns.
"""

import json
import os
import sqlite3

from . import clock


def now_iso() -> str:
    return clock.iso()


def iso_in(seconds: int) -> str:
    """Same format as now_iso(), so SQLite can compare timestamps as text."""
    return clock.iso_in(seconds)

SCHEMA = """
CREATE TABLE IF NOT EXISTS satellites (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    operator TEXT,
    model TEXT,
    serial_number TEXT,
    status TEXT NOT NULL,
    doc TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- shortcut: a mining site and its surface base station share one row; split them when one site hosts several bases.
CREATE TABLE IF NOT EXISTS sites (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    designation TEXT,
    host_body TEXT,
    base_station_id TEXT,
    status TEXT NOT NULL,
    doc TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS robots (
    id TEXT PRIMARY KEY,
    designation TEXT NOT NULL,
    robot_class TEXT NOT NULL,
    status TEXT NOT NULL,
    state TEXT NOT NULL,
    site_id TEXT NOT NULL REFERENCES sites(id),
    base_station_id TEXT,
    zone_id TEXT,
    battery_pct REAL,
    health_pct REAL,
    doc TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id TEXT NOT NULL REFERENCES sites(id),
    satellite_id TEXT NOT NULL REFERENCES satellites(id),
    role TEXT NOT NULL,
    band TEXT,
    status TEXT NOT NULL,
    established_at TEXT,
    last_report_at TEXT,
    missed_reports INTEGER DEFAULT 0,
    share_pct REAL,
    UNIQUE (site_id, satellite_id)
);

-- satellite_id acts as a backup for primary_satellite_id
CREATE TABLE IF NOT EXISTS satellite_backups (
    satellite_id TEXT NOT NULL REFERENCES satellites(id),
    primary_satellite_id TEXT NOT NULL REFERENCES satellites(id),
    policy TEXT NOT NULL,
    failover_threshold_health REAL NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (satellite_id, primary_satellite_id)
);

CREATE TABLE IF NOT EXISTS relay_nets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    band TEXT,
    hello_interval_s INTEGER NOT NULL DEFAULT 10,
    dead_interval_s INTEGER NOT NULL DEFAULT 40,
    doc TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- one satellite's adjacency to a relay net; priority 0 means "always DROther"
CREATE TABLE IF NOT EXISTS adjacencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    net_id TEXT NOT NULL REFERENCES relay_nets(id),
    satellite_id TEXT NOT NULL REFERENCES satellites(id),
    priority INTEGER NOT NULL DEFAULT 1,
    state TEXT NOT NULL,
    last_hello_at TEXT,
    formed_at TEXT,
    UNIQUE (net_id, satellite_id)
);

CREATE TABLE IF NOT EXISTS elections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    net_id TEXT NOT NULL REFERENCES relay_nets(id),
    ds_id TEXT,
    bds_id TEXT,
    reason TEXT NOT NULL,
    ledger TEXT NOT NULL,
    elected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'viewer')),
    display_name TEXT,
    created_at TEXT NOT NULL
);

-- opaque bearer tokens, issued by the login endpoint, expired by expires_at
CREATE TABLE IF NOT EXISTS tokens (
    token TEXT PRIMARY KEY,
    username TEXT NOT NULL REFERENCES users(username),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS log_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    category TEXT NOT NULL,
    source TEXT,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS metrics_lookup ON metrics (entity_type, entity_id, id);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    schema_name TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    site_id TEXT NOT NULL,
    recipient_satellite_id TEXT NOT NULL,
    priority TEXT NOT NULL,
    seq INTEGER,
    generated_at TEXT,
    payload TEXT NOT NULL,
    accepted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commands (
    id TEXT PRIMARY KEY,
    robot_id TEXT NOT NULL REFERENCES robots(id),
    action TEXT NOT NULL,
    issued_by TEXT,
    previous_state TEXT NOT NULL,
    new_state TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);
"""


def db_path() -> str:
    return os.environ.get("ASTROID_DB_PATH", "astroid_mining.db")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    from . import auth, ospf
    from .seed import USERS, seed

    conn = connect()
    try:
        conn.executescript(SCHEMA)
        empty = conn.execute("SELECT COUNT(*) FROM satellites").fetchone()[0] == 0
        if empty:
            seed(conn)
            log(conn, "INFO", "system", "fleet-control", f"cold start: {db_path()} seeded, {count(conn, 'relay_nets')} relay nets up")
            for row in conn.execute("SELECT id, name FROM relay_nets"):
                ospf.run_election(conn, row["id"], "BOOT", preemptive=True)
        if not count(conn, "users"):
            # a database written before accounts existed still has to gain the two logins
            for user in USERS:
                conn.execute(
                    "INSERT INTO users (username, password_hash, role, display_name, created_at) VALUES (?,?,?,?,?)",
                    (user["username"], auth.hash_password(user["password"]), user["role"], user["displayName"], now_iso()),
                )
            log(conn, "INFO", "auth", "fleet-control", f"{count(conn, 'users')} accounts added to {db_path()}")
        # an older database froze the OSPF timers in the sample dates; those clocks run on real time now
        conn.execute("UPDATE adjacencies SET last_hello_at = ?, formed_at = ? WHERE last_hello_at > ?", (now_iso(), iso_in(-6 * 3600), now_iso()))
        conn.commit()
    finally:
        conn.close()


def count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def log(conn: sqlite3.Connection, level: str, category: str, source: str, message: str, ts: str | None = None) -> str:
    """Text log line: stored so it can be queried, printed so it shows in the server console."""
    ts = ts or now_iso()
    line = f"{ts} {level:<5} {category:<9} {source:<28} {message}"
    conn.execute("INSERT INTO log_events (ts, level, category, source, message) VALUES (?,?,?,?,?)", (ts, level, category, source, message))
    print(line, flush=True)
    return line


def get_db():
    """FastAPI dependency: one connection per request."""
    conn = connect()
    try:
        yield conn
    finally:
        # commit even when the request failed, so refusals stay in the log and audit trail
        conn.commit()
        conn.close()


def doc(row: sqlite3.Row) -> dict:
    return json.loads(row["doc"])


def latest_metrics(conn: sqlite3.Connection, entity_type: str, entity_id: str) -> dict | None:
    row = conn.execute(
        "SELECT payload FROM metrics WHERE entity_type = ? AND entity_id = ? ORDER BY id DESC LIMIT 1",
        (entity_type, entity_id),
    ).fetchone()
    return json.loads(row["payload"]) if row else None


def metrics_history(conn: sqlite3.Connection, entity_type: str, entity_id: str, limit: int) -> list[dict]:
    rows = conn.execute(
        "SELECT collected_at, payload FROM metrics WHERE entity_type = ? AND entity_id = ?"
        " ORDER BY id DESC LIMIT ?",
        (entity_type, entity_id, limit),
    ).fetchall()
    return [{"collectedAt": r["collected_at"], **json.loads(r["payload"])} for r in rows]


def deep_merge(base: dict, update: dict) -> dict:
    out = dict(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def put_metrics(conn: sqlite3.Connection, entity_type: str, entity_id: str, payload: dict, collected_at: str) -> dict:
    merged = deep_merge(latest_metrics(conn, entity_type, entity_id) or {}, payload)
    conn.execute(
        "INSERT INTO metrics (entity_type, entity_id, collected_at, payload) VALUES (?,?,?,?)",
        (entity_type, entity_id, collected_at, json.dumps(merged)),
    )
    if entity_type == "robot":
        power = payload.get("power") or {}
        if isinstance(power.get("batteryPct"), (int, float)):
            conn.execute("UPDATE robots SET battery_pct = ? WHERE id = ?", (power["batteryPct"], entity_id))
        if isinstance(payload.get("healthScore"), (int, float)):
            conn.execute(
                "UPDATE robots SET health_pct = ? WHERE id = ?", (round(payload["healthScore"] * 100, 1), entity_id)
            )
    return merged
