"""FastAPI service for the asteroid mining fleet: relays, mining sites, robot fleet.

Run:  uvicorn app.main:app --reload
"""

import json
import sqlite3
import uuid
from typing import Any, Literal

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from . import auth
from . import clock
from . import db as dbmod
from . import ospf

SCHEMA_VERSION = "1.5.0"
LinkRole = Literal["PRIMARY", "SECONDARY", "COLD_STANDBY", "SURVEY"]
EntityStatus = Literal["PLANNED", "INTEGRATING", "STANDBY", "OPERATIONAL", "DEGRADED", "OFFLINE", "DECOMMISSIONED"]
RobotState = Literal["IDLE", "ACTIVE", "PAUSED", "STOPPED", "CHARGING", "RETURNING", "MAINTENANCE", "FAULT", "LOST"]

# action -> (states the command is accepted from, resulting state)
LABEL_COLUMN = {"satellite": "name", "site": "designation", "robot": "designation"}

TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "START": (frozenset({"IDLE", "CHARGING", "RETURNING", "PAUSED", "STOPPED", "MAINTENANCE"}), "ACTIVE"),
    "PAUSE": (frozenset({"ACTIVE"}), "PAUSED"),
    "STOP": (frozenset({"ACTIVE", "PAUSED", "CHARGING", "RETURNING", "IDLE", "MAINTENANCE"}), "STOPPED"),
    "RESUME": (frozenset({"PAUSED", "STOPPED", "CHARGING"}), "ACTIVE"),
}
ROLE_PRIORITY = ["PRIMARY", "SECONDARY", "SURVEY", "COLD_STANDBY"]


def now_iso() -> str:
    return clock.iso()


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class SatelliteIn(CamelModel):
    id: str | None = None
    name: str
    operator: str = "Helios Resources Ltd."
    sat_model: str = Field("HR-Mining Relay Mk III", alias="model")
    serial_number: str = Field("HRM3-0000", alias="serialNumber")
    status: EntityStatus = "PLANNED"
    launch_date: str | None = Field(None, alias="launchDate")
    design_life_years: int | None = Field(None, alias="designLifeYears")
    tags: list[str] = []
    orbit: dict[str, Any] = {}
    metrics: dict[str, Any] = {}


class ConnectionIn(CamelModel):
    site_ids: list[str] | Literal["all"] = Field("all", alias="siteIds")
    role: LinkRole = "SECONDARY"
    band: Literal["Ka", "X", "S"] = "X"
    share_pct: float | None = Field(None, alias="sharePct")


class BackupIn(CamelModel):
    backup_of: str = Field(alias="backupOf")
    policy: Literal["HOT_STANDBY_ROUND_ROBIN", "COLD_STANDBY", "SITE_HANDOVER_TO_SIBLING_BASE"] = "HOT_STANDBY_ROUND_ROBIN"
    failover_threshold_health: float = Field(0.65, alias="failoverThresholdHealth", ge=0.0, le=1.0)


class UplinkIn(CamelModel):
    satellite_id: str = Field(alias="satelliteId")
    role: LinkRole = "PRIMARY"
    band: Literal["Ka", "X", "S"] = "Ka"
    share_pct: float | None = Field(None, alias="sharePct")


class SiteIn(CamelModel):
    id: str | None = None
    name: str
    designation: str
    host_body: str = Field("(4124) Orvar-SW", alias="hostBody")
    base_station_id: str | None = Field(None, alias="baseStationId")
    status: EntityStatus = "PLANNED"
    autonomy_tier: str = Field("L4_SUPERVISED", alias="autonomyTier")
    metrics: dict[str, Any] = {}


class RobotIn(CamelModel):
    id: str | None = None
    designation: str
    robot_class: str = Field(alias="class")
    model: str = "HR-Traverse Digger Mk4"
    serial_number: str = Field("HTD4-0000", alias="serialNumber")
    site_id: str = Field(alias="siteId")
    zone_id: str | None = Field(None, alias="zoneId")
    state: RobotState = "IDLE"
    battery_pct: float = Field(100.0, alias="batteryPct", ge=0.0, le=100.0)
    health_pct: float = Field(100.0, alias="healthPct", ge=0.0, le=100.0)


class CommandIn(CamelModel):
    action: Literal["START", "STOP", "PAUSE", "RESUME"]
    issued_by: str = Field("fleet-orchestrator", alias="issuedBy")
    note: str = ""


class PeerIn(CamelModel):
    satellite_id: str = Field(alias="satelliteId")
    priority: int = Field(1, ge=0, le=255)


class RelayNetIn(CamelModel):
    id: str | None = None
    name: str
    band: Literal["Ka", "X", "S"] = "X"
    hello_interval_s: int = Field(10, alias="helloIntervalS", ge=1, le=600)
    dead_interval_s: int = Field(40, alias="deadIntervalS", ge=1, le=3600)
    network_type: Literal["BROADCAST_RELAY", "POINT_TO_MULTIPOINT"] = Field("BROADCAST_RELAY", alias="networkType")


class ElectionIn(CamelModel):
    reason: Literal["OPERATOR_CLEAR", "POLICY_CHANGE", "SHOW_ONLY"] = "OPERATOR_CLEAR"
    preemptive: bool = True


class LoginIn(CamelModel):
    username: str
    password: str


class ReportIn(CamelModel):
    report_id: str | None = Field(None, alias="reportId")
    schema_name: str = Field("base.telemetry.report.v1", alias="schema")
    sender_id: str = Field(alias="senderId")
    site_id: str = Field(alias="siteId")
    recipient_satellite_id: str = Field(alias="recipientSatelliteId")
    priority: Literal["SAFETY", "FLEET_STATE", "PRODUCTION", "RAW_TELEMETRY"] = "PRODUCTION"
    seq: int | None = None
    generated_at: str | None = Field(None, alias="generatedAt")
    payload: dict[str, Any] = {}


DESCRIPTION = """
Everything the fleet knows about itself, over HTTP: comms relays, mining sites with their surface
base station, the robot fleet, and the OSPF-style adjacency mesh the relays run between themselves.
State lives in SQLite; a cold start seeds a fleet in a known-good state.

**Rules the service enforces**

* one `PRIMARY` relay per site; a second one is refused, `failover` promotes the next usable backup.
* robot commands are state-machine transitions (`START/PAUSE/STOP/RESUME`); a command from a state it
  is not accepted from is `409`.
* a telemetry report needs an established uplink and a `senderId` equal to the site's base station.
* metrics pushes are partial: they deep-merge into the last snapshot, and every snapshot is kept as history.
* relay nets elect a **Designated Satellite (DS)** and a **Backup Designated Satellite (BDS)**: only
  `FULL` adjacencies of `OPERATIONAL` relays are candidates, priority 0 is always DROther, highest
  priority wins, ties go to the highest router id. The election is non-preemptive - a better newcomer
  takes over only on `POST /relay-nets/{net}/election` or when the incumbent is lost.
* the service has no clock of its own: every timestamp is the host system clock in UTC, and a relay
  adjacency that stops hearing hellos is declared DOWN once the net's `deadIntervalS` has passed
  (`GET /api/v1/clock` reports that time, `POST /relay-nets/{net}/peers/{sat}/hello` keeps a peer up).
* every state change writes a text log line, queryable at `GET /api/v1/logs`.
"""

TAGS = [
    {"name": "auth", "description": "the only place a password is accepted: sign in, get a bearer token, check it, revoke it."},
    {"name": "fleet", "description": "liveness and the fleet-wide picture."},
    {"name": "relays", "description": "comms satellites: registration, telemetry, links to mining sites, status changes."},
    {"name": "relay nets", "description": "OSPF-style adjacencies between relays: neighbor table, DS/BDS election and re-election."},
    {"name": "mining sites", "description": "mining spots and their surface base station: metrics, uplinks, failover, robot roster."},
    {"name": "robots", "description": "the digging fleet: state commands, telemetry, telecommand audit log."},
    {"name": "telemetry reports", "description": "base station to relay report ingest."},
    {"name": "activity log", "description": "the text log of everything the service did, JSON or plain text."},
]

def get_conn():
    yield from dbmod.get_db()


# ---------------------------------------------------------------- access control

# no token needed: liveness probe and the login itself
PUBLIC_PATHS = {"/health", "/api/v1/auth/login"}
# any signed-in role may do these, they are not fleet actions
ROLE_FREE_PATHS = PUBLIC_PATHS | {"/api/v1/auth/logout"}
WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


def authenticate(request: Request, conn: sqlite3.Connection) -> sqlite3.Row:
    token = auth.bearer(request.headers.get("authorization"))
    row = conn.execute(
        "SELECT t.token, t.username, t.created_at, t.expires_at, u.role, u.display_name"
        " FROM tokens t JOIN users u ON u.username = t.username WHERE t.token = ? AND t.expires_at > ?",
        (token or "", dbmod.now_iso()),
    ).fetchone()
    if not row:
        raise HTTPException(401, "no valid bearer token: POST /api/v1/auth/login with a username and password")
    return row


def require_access(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> sqlite3.Row | None:
    """App-wide guard: every endpoint needs a token, and only admins may change fleet state."""
    if request.url.path in PUBLIC_PATHS:
        return None
    token = authenticate(request, conn)
    if request.method in WRITE_METHODS and request.url.path not in ROLE_FREE_PATHS and token["role"] != "admin":
        raise HTTPException(403, f"role 'viewer' is read-only: {request.method} {request.url.path} needs an admin token")
    return token


app = FastAPI(
    title="Astroid Mining Fleet Control",
    version=SCHEMA_VERSION,
    description=DESCRIPTION,
    openapi_tags=TAGS,
    dependencies=[Depends(require_access)],
)


def openapi_with_bearer() -> dict:
    """Show the bearer token in Swagger UI so `Authorize` + Try it out work for every endpoint."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title, version=app.version, description=DESCRIPTION, routes=app.routes, tags=app.openapi_tags
    )
    schema.setdefault("components", {})["securitySchemes"] = {"bearerToken": {"type": "http", "scheme": "bearer", "bearerFormat": "token"}}
    schema["security"] = [{"bearerToken": []}]
    for path, operations in schema["paths"].items():
        if path in PUBLIC_PATHS:
            for operation in operations.values():
                operation["security"] = []
    app.openapi_schema = schema
    return schema


app.openapi = openapi_with_bearer
dbmod.init_db()


# ---------------------------------------------------------------- auth

@app.post("/api/v1/auth/login", tags=["auth"])
def login(body: LoginIn, conn: sqlite3.Connection = Depends(get_conn)):
    """Username and password are accepted here and nowhere else; the answer is a bearer token."""
    conn.execute("DELETE FROM tokens WHERE expires_at <= ?", (dbmod.now_iso(),))
    user = conn.execute("SELECT * FROM users WHERE username = ?", (body.username,)).fetchone()
    if not user or not auth.verify_password(body.password, user["password_hash"]):
        dbmod.log(conn, "WARN", "auth", f"user {body.username}", "login refused: unknown user or wrong password")
        raise HTTPException(401, "unknown user or wrong password")
    token, issued_at, expires_at = auth.new_token(), dbmod.now_iso(), dbmod.iso_in(auth.TOKEN_TTL_SECONDS)
    conn.execute(
        "INSERT INTO tokens (token, username, created_at, expires_at) VALUES (?,?,?,?)",
        (token, user["username"], issued_at, expires_at),
    )
    dbmod.log(
        conn, "INFO", "auth", f"user {user['username']}",
        f"login ok role={user['role']} token valid until {expires_at} ({auth.TOKEN_TTL_DAYS} days)",
    )
    return {
        "token": token,
        "tokenType": "Bearer",
        "username": user["username"],
        "role": user["role"],
        "displayName": user["display_name"],
        "issuedAt": issued_at,
        "expiresAt": expires_at,
    }


@app.get("/api/v1/auth/me", tags=["auth"])
def whoami(token: sqlite3.Row = Depends(require_access)):
    return {
        "username": token["username"],
        "role": token["role"],
        "displayName": token["display_name"],
        "issuedAt": token["created_at"],
        "expiresAt": token["expires_at"],
    }


@app.post("/api/v1/auth/logout", tags=["auth"])
def logout(token: sqlite3.Row = Depends(require_access), conn: sqlite3.Connection = Depends(get_conn)):
    conn.execute("DELETE FROM tokens WHERE token = ?", (token["token"],))
    dbmod.log(conn, "INFO", "auth", f"user {token['username']}", "token revoked")
    return {"revoked": True}


# ---------------------------------------------------------------- text log

def log(conn: sqlite3.Connection, level: str, category: str, source: str, message: str) -> None:
    dbmod.log(conn, level, category, source, message)


# ---------------------------------------------------------------- helpers

def get_satellite(conn: sqlite3.Connection, satellite_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM satellites WHERE id = ?", (satellite_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"satellite {satellite_id} not registered")
    return row


def get_site(conn: sqlite3.Connection, site_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"mining site {site_id} not registered")
    return row


def get_robot(conn: sqlite3.Connection, robot_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM robots WHERE id = ?", (robot_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"robot {robot_id} not registered")
    return row


def links_of_site(conn: sqlite3.Connection, site_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM links WHERE site_id = ? ORDER BY id", (site_id,)).fetchall()
    return [link_json(r) for r in rows]


def link_json(row: sqlite3.Row) -> dict:
    return {
        "satelliteId": row["satellite_id"],
        "role": row["role"],
        "band": row["band"],
        "status": row["status"],
        "establishedAt": row["established_at"],
        "lastReportAt": row["last_report_at"],
        "missedReports": row["missed_reports"],
        "sharePct": row["share_pct"],
    }


def backups_for(conn: sqlite3.Connection, satellite_id: str) -> dict:
    as_backup = [r["primary_satellite_id"] for r in conn.execute(
        "SELECT primary_satellite_id FROM satellite_backups WHERE satellite_id = ?", (satellite_id,))]
    serving = conn.execute(
        "SELECT satellite_id, policy, failover_threshold_health FROM satellite_backups WHERE primary_satellite_id = ?",
        (satellite_id,),
    ).fetchall()
    return {
        "servesAsBackupOf": as_backup,
        "policy": serving[0]["policy"] if serving else None,
        "failoverThresholdHealth": serving[0]["failover_threshold_health"] if serving else None,
        "satelliteIds": [r["satellite_id"] for r in serving],
    }


def site_robots(conn: sqlite3.Connection, site_id: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM robots WHERE site_id = ? ORDER BY designation", (site_id,)).fetchall()


def robot_summary(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "designation": row["designation"],
        "class": row["robot_class"],
        "status": row["status"],
        "state": row["state"],
        "siteId": row["site_id"],
        "baseStationId": row["base_station_id"],
        "zoneId": row["zone_id"],
        "batteryPct": row["battery_pct"],
        "healthPct": row["health_pct"],
    }


def metrics_response(conn: sqlite3.Connection, entity_type: str, entity_id: str, history: int) -> dict:
    latest = dbmod.latest_metrics(conn, entity_type, entity_id)
    out: dict[str, Any] = {"schemaVersion": SCHEMA_VERSION, "entityType": entity_type, "entityId": entity_id, "metrics": latest or {}}
    if history > 0:
        out["history"] = dbmod.metrics_history(conn, entity_type, entity_id, history)
    return out


def site_summary(metrics: dict) -> dict:
    thermal = metrics.get("thermal") or {}
    excavation = metrics.get("excavation") or {}
    inventory = metrics.get("inventory") or {}
    return {
        "temperatureC": thermal.get("coreTempC"),
        "exteriorTempC": thermal.get("exteriorTempC"),
        "productionRateTph": excavation.get("sintererOutputTph") or excavation.get("crusherThroughputTph"),
        "rawOreStockTons": inventory.get("rawOreOnSiteTons"),
        "refinedStockTons": inventory.get("refinedMetalTons"),
    }


# ---------------------------------------------------------------- meta

@app.get("/health", tags=["fleet"])
def health(conn: sqlite3.Connection = Depends(get_conn)):
    satellites = conn.execute("SELECT COUNT(*) FROM satellites").fetchone()[0]
    sites = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
    return {"status": "ok", "time": now_iso(), "schemaVersion": SCHEMA_VERSION, "satellites": satellites, "sites": sites}


@app.get("/api/v1/clock", tags=["fleet"])
def clock_state():
    """The one clock the service uses: the host's system clock, in UTC. Nothing here is simulated."""
    started = clock.iso(clock.STARTED_AT)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "now": clock.iso(),
        "source": "system-utc",
        "serviceStartedAt": started,
        "uptimeS": clock.uptime_s(),
        "tokenTtlS": auth.TOKEN_TTL_SECONDS,
        "note": "adjacency and token expiry are measured against this clock, no timers are run",
    }


@app.get("/api/v1/fleet/summary", tags=["fleet"])
def fleet_summary(conn: sqlite3.Connection = Depends(get_conn)):
    by_class = {r["robot_class"]: r["n"] for r in conn.execute("SELECT robot_class, COUNT(*) AS n FROM robots GROUP BY robot_class")}
    by_state = {r["state"]: r["n"] for r in conn.execute("SELECT state, COUNT(*) AS n FROM robots GROUP BY state")}
    totals = conn.execute("SELECT COUNT(*) AS n, AVG(health_pct) AS h FROM robots").fetchone()
    links = conn.execute("SELECT COUNT(*) AS n FROM links WHERE status = 'ESTABLISHED'").fetchone()["n"]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": now_iso(),
        "totalRobots": totals["n"],
        "byClass": by_class,
        "byState": by_state,
        "averageHealthPct": round(totals["h"], 1) if totals["n"] else 0.0,
        "satellites": conn.execute("SELECT COUNT(*) FROM satellites").fetchone()[0],
        "establishedLinks": links,
        "openAnomalies": sum(
            (dbmod.latest_metrics(conn, kind, row["id"]) or {}).get("anomalies", {}).get("openCount", 0)
            for kind, table in [("site", "sites"), ("satellite", "satellites")]
            for row in conn.execute(f"SELECT id FROM {table}")
        ),
    }


# ---------------------------------------------------------------- satellites

@app.post("/api/v1/satellites", tags=["relays"], status_code=201)
def register_satellite(body: SatelliteIn, conn: sqlite3.Connection = Depends(get_conn)):
    satellite_id = body.id or str(uuid.uuid4())
    if conn.execute("SELECT 1 FROM satellites WHERE id = ?", (satellite_id,)).fetchone():
        raise HTTPException(409, f"satellite {satellite_id} already registered")
    doc = {
        "id": satellite_id,
        "name": body.name,
        "operator": body.operator,
        "model": body.sat_model,
        "serialNumber": body.serial_number,
        "status": body.status,
        "launchDate": body.launch_date,
        "designLifeYears": body.design_life_years,
        "tags": body.tags,
        "orbit": body.orbit,
    }
    stamp = now_iso()
    conn.execute(
        "INSERT INTO satellites (id, name, operator, model, serial_number, status, doc, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (satellite_id, body.name, body.operator, body.sat_model, body.serial_number, body.status, json.dumps(doc), stamp, stamp),
    )
    if body.metrics:
        store_metrics(conn, "satellite", satellite_id, body.metrics)
    log(conn, "INFO", "registry", f"sat {body.name}", f"relay registered id={satellite_id} status={body.status} serial={body.serial_number}")
    return {"schemaVersion": SCHEMA_VERSION, "satelliteId": satellite_id, "status": body.status, "registeredAt": stamp}


@app.get("/api/v1/satellites", tags=["relays"])
def list_satellites(status: EntityStatus | None = None, conn: sqlite3.Connection = Depends(get_conn)):
    rows = conn.execute("SELECT * FROM satellites ORDER BY name").fetchall()
    out = []
    for row in rows:
        if status and row["status"] != status:
            continue
        latest = dbmod.latest_metrics(conn, "satellite", row["id"]) or {}
        out.append(
            {
                "id": row["id"],
                "name": row["name"],
                "operator": row["operator"],
                "status": row["status"],
                "healthScore": latest.get("healthScore"),
                "connectedSites": conn.execute("SELECT COUNT(*) FROM links WHERE satellite_id = ?", (row["id"],)).fetchone()[0],
            }
        )
    return {"schemaVersion": SCHEMA_VERSION, "count": len(out), "satellites": out}


@app.get("/api/v1/satellites/{satellite_id}", tags=["relays"])
def get_satellite_doc(satellite_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    row = get_satellite(conn, satellite_id)
    doc = dbmod.doc(row)
    doc["status"] = row["status"]
    doc["metrics"] = dbmod.latest_metrics(conn, "satellite", satellite_id) or {}
    doc["backups"] = backups_for(conn, satellite_id)
    sites = []
    for link in conn.execute("SELECT * FROM links WHERE satellite_id = ? ORDER BY id", (satellite_id,)):
        robots = conn.execute("SELECT id FROM robots WHERE site_id = ?", (link["site_id"],)).fetchall()
        sites.append(
            {
                "siteId": link["site_id"],
                "role": link["role"],
                "sharePct": link["share_pct"],
                "baseStationIds": [conn.execute("SELECT base_station_id FROM sites WHERE id = ?", (link["site_id"],)).fetchone()["base_station_id"]],
                "robotIds": [r["id"] for r in robots],
            }
        )
    doc["miningSites"] = sites
    doc["ospf"] = {"routerId": satellite_id, "nets": []}
    nets = conn.execute(
        "SELECT * FROM relay_nets WHERE id IN (SELECT net_id FROM adjacencies WHERE satellite_id = ?)", (satellite_id,)
    ).fetchall()
    for net in nets:
        view = net_view(conn, net["id"])
        self_peer = next((p for p in view["adjacencies"] if p["satelliteId"] == satellite_id), None)
        doc["ospf"]["nets"].append(
            {
                "netId": net["id"],
                "netName": net["name"],
                "band": net["band"],
                "role": self_peer["role"] if self_peer else "DROTHER",
                "adjacency": self_peer,
                "ds": view["ds"]["name"] if view["ds"] else None,
                "bds": view["bds"]["name"] if view["bds"] else None,
                "neighbors": [p for p in view["adjacencies"] if p["satelliteId"] != satellite_id],
            }
        )
    return {"schemaVersion": SCHEMA_VERSION, "satellite": doc}


@app.post("/api/v1/satellites/{satellite_id}/connections", tags=["relays"], status_code=201)
def connect_satellite(satellite_id: str, body: ConnectionIn, conn: sqlite3.Connection = Depends(get_conn)):
    row = get_satellite(conn, satellite_id)
    if body.site_ids == "all":
        targets = [r["id"] for r in conn.execute("SELECT id FROM sites ORDER BY id")]
    else:
        targets = body.site_ids
    created, skipped = [], []
    for site_id in targets:
        get_site(conn, site_id)
        existing = conn.execute("SELECT * FROM links WHERE site_id = ? AND satellite_id = ?", (site_id, satellite_id)).fetchone()
        if existing:
            skipped.append({"siteId": site_id, "reason": f"link already exists as {existing['role']}"})
            continue
        holder = conn.execute(
            "SELECT satellite_id FROM links WHERE site_id = ? AND role = 'PRIMARY' AND status = 'ESTABLISHED'", (site_id,)
        ).fetchone()
        if body.role == "PRIMARY" and holder:
            skipped.append({"siteId": site_id, "reason": f"primary relay already held by {holder['satellite_id']}"})
            continue
        conn.execute(
            "INSERT INTO links (site_id, satellite_id, role, band, status, established_at, share_pct) VALUES (?,?,?,?,?,?,?)",
            (site_id, satellite_id, body.role, body.band, "ESTABLISHED", now_iso(), body.share_pct),
        )
        created.append({"siteId": site_id, "role": body.role, "band": body.band, "status": "ESTABLISHED"})
    if created:
        log(conn, "INFO", "link", f"sat {row['name']}", f"connected to {len(created)} mining site(s) role={body.role} band={body.band}")
    return {"schemaVersion": SCHEMA_VERSION, "satelliteId": satellite_id, "connected": created, "skipped": skipped}


@app.post("/api/v1/satellites/{satellite_id}/backups", tags=["relays"], status_code=201)
def designate_backup(satellite_id: str, body: BackupIn, conn: sqlite3.Connection = Depends(get_conn)):
    row = get_satellite(conn, satellite_id)
    if body.backup_of == satellite_id:
        raise HTTPException(400, "a satellite cannot be its own backup")
    get_satellite(conn, body.backup_of)
    exists = conn.execute(
        "SELECT 1 FROM satellite_backups WHERE satellite_id = ? AND primary_satellite_id = ?", (satellite_id, body.backup_of)
    ).fetchone()
    if exists:
        raise HTTPException(409, f"{satellite_id} is already a backup of {body.backup_of}")
    conn.execute(
        "INSERT INTO satellite_backups (satellite_id, primary_satellite_id, policy, failover_threshold_health, created_at)"
        " VALUES (?,?,?,?,?)",
        (satellite_id, body.backup_of, body.policy, body.failover_threshold_health, now_iso()),
    )
    log(conn, "INFO", "registry", f"sat {row['name']}", f"designated backup of {body.backup_of} policy={body.policy} threshold={body.failover_threshold_health}")
    return {"schemaVersion": SCHEMA_VERSION, "satelliteId": satellite_id, "backupOf": body.backup_of, "policy": body.policy}


@app.get("/api/v1/satellites/{satellite_id}/links", tags=["relays"])
def satellite_links(satellite_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    get_satellite(conn, satellite_id)
    rows = conn.execute("SELECT * FROM links WHERE satellite_id = ? ORDER BY id", (satellite_id,)).fetchall()
    out = [{"siteId": r["site_id"], **link_json(r)} for r in rows]
    return {"schemaVersion": SCHEMA_VERSION, "satelliteId": satellite_id, "count": len(out), "links": out}


@app.get("/api/v1/satellites/{satellite_id}/metrics", tags=["relays"])
def satellite_metrics(
    satellite_id: str, history: int = Query(0, ge=0, le=100), conn: sqlite3.Connection = Depends(get_conn)
):
    get_satellite(conn, satellite_id)
    return metrics_response(conn, "satellite", satellite_id, history)


@app.post("/api/v1/satellites/{satellite_id}/metrics", tags=["relays"], status_code=201)
def report_satellite_metrics(
    satellite_id: str, payload: dict[str, Any] = Body(...), conn: sqlite3.Connection = Depends(get_conn)
):
    get_satellite(conn, satellite_id)
    return report_metrics(conn, "satellite", satellite_id, payload)


# ---------------------------------------------------------------- relay nets (OSPF-style adjacencies)

def get_net(conn: sqlite3.Connection, net_id: str) -> sqlite3.Row:
    row = ospf.net_row(conn, net_id)
    if not row:
        raise HTTPException(404, f"relay net {net_id} not registered")
    ospf.expire_stale(conn, row)  # every operation on a net starts by applying its dead timer
    return row


def get_adjacency(conn: sqlite3.Connection, net_id: str, satellite_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM adjacencies WHERE net_id = ? AND satellite_id = ?", (net_id, satellite_id)).fetchone()
    if not row:
        raise HTTPException(404, f"satellite {satellite_id} has no adjacency on net {net_id}")
    return row


def election_summary(ledger: dict) -> dict:
    return {
        "netId": ledger["netId"],
        "reason": ledger["reason"],
        "decision": ledger["decision"],
        "changed": ledger["changed"],
        "ds": ledger["ds"]["name"] if ledger["ds"] else None,
        "dsId": ledger["ds"]["satelliteId"] if ledger["ds"] else None,
        "bds": ledger["bds"]["name"] if ledger["bds"] else None,
        "bdsId": ledger["bds"]["satelliteId"] if ledger["bds"] else None,
        "excluded": [{"satelliteId": p["satelliteId"], "excluded": p["excluded"]} for p in ledger["excluded"]],
        "electedAt": ledger["electedAt"],
    }


def net_view(conn: sqlite3.Connection, net_id: str) -> dict:
    row = ospf.net_row(conn, net_id)
    ospf.expire_stale(conn, row)  # a read reports the net as the dead timer already sees it
    net = dbmod.doc(row)
    ds_id, bds_id = ospf.current_roles(conn, net_id)
    peers = ospf.neighbors(conn, net_id)
    for peer in peers:
        peer["role"] = "DS" if peer["satelliteId"] == ds_id else "BDS" if peer["satelliteId"] == bds_id else "DROTHER"
        age = clock.age_of(peer["lastHelloAt"])
        peer["helloAgeS"] = None if age is None else round(age, 1)
        peer["holdTimeS"] = ospf.hold_time(net["deadIntervalS"], peer["lastHelloAt"])
    last = conn.execute("SELECT ledger FROM elections WHERE net_id = ? ORDER BY id DESC LIMIT 1", (net_id,)).fetchone()
    net["adjacencies"] = peers
    net["ds"] = next((p for p in peers if p["role"] == "DS"), None)
    net["bds"] = next((p for p in peers if p["role"] == "BDS"), None)
    net["lastElection"] = json.loads(last["ledger"]) if last else None
    return net


@app.get("/api/v1/relay-nets", tags=["relay nets"])
def list_relay_nets(conn: sqlite3.Connection = Depends(get_conn)):
    nets = [net_view(conn, row["id"]) for row in conn.execute("SELECT id FROM relay_nets ORDER BY id")]
    return {"schemaVersion": SCHEMA_VERSION, "count": len(nets), "relayNets": nets}


@app.post("/api/v1/relay-nets", tags=["relay nets"], status_code=201)
def register_relay_net(body: RelayNetIn, conn: sqlite3.Connection = Depends(get_conn)):
    net_id = body.id or f"net-{str(uuid.uuid4())[:8]}"
    if ospf.net_row(conn, net_id):
        raise HTTPException(409, f"relay net {net_id} already registered")
    doc = {
        "id": net_id,
        "name": body.name,
        "band": body.band,
        "helloIntervalS": body.hello_interval_s,
        "deadIntervalS": body.dead_interval_s,
        "networkType": body.network_type,
    }
    conn.execute(
        "INSERT INTO relay_nets (id, name, band, hello_interval_s, dead_interval_s, doc, created_at) VALUES (?,?,?,?,?,?,?)",
        (net_id, body.name, body.band, body.hello_interval_s, body.dead_interval_s, json.dumps(doc), now_iso()),
    )
    log(conn, "INFO", "ospf", f"net {body.name}", f"relay net created band={body.band} type={body.network_type} hello={body.hello_interval_s}s dead={body.dead_interval_s}s")
    return {"schemaVersion": SCHEMA_VERSION, "relayNet": doc}


@app.get("/api/v1/relay-nets/{net_id}", tags=["relay nets"])
def get_relay_net(net_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    get_net(conn, net_id)
    return {"schemaVersion": SCHEMA_VERSION, "relayNet": net_view(conn, net_id)}


@app.post("/api/v1/relay-nets/{net_id}/peers", tags=["relay nets"], status_code=201)
def add_peer(net_id: str, body: PeerIn, conn: sqlite3.Connection = Depends(get_conn)):
    net = get_net(conn, net_id)
    satellite = get_satellite(conn, body.satellite_id)
    if conn.execute("SELECT 1 FROM adjacencies WHERE net_id = ? AND satellite_id = ?", (net_id, body.satellite_id)).fetchone():
        raise HTTPException(409, f"satellite {body.satellite_id} is already a peer of net {net_id}")
    stamp = now_iso()
    conn.execute(
        "INSERT INTO adjacencies (net_id, satellite_id, priority, state, last_hello_at, formed_at) VALUES (?,?,?,?,?,?)",
        (net_id, body.satellite_id, body.priority, "FULL", stamp, stamp),
    )
    ospf.form_adjacency(conn, net_id, dict(satellite), body.priority)
    ledger = ospf.run_election(conn, net_id, "PEER_JOINED")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "netId": net_id,
        "satelliteId": body.satellite_id,
        "priority": body.priority,
        "state": "FULL",
        "election": election_summary(ledger),
    }


@app.delete("/api/v1/relay-nets/{net_id}/peers/{satellite_id}", tags=["relay nets"])
def remove_peer(net_id: str, satellite_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    get_net(conn, net_id)
    row = get_adjacency(conn, net_id, satellite_id)
    satellite = get_satellite(conn, satellite_id)
    ospf.drop_adjacency(conn, net_id, dict(satellite), "peer removed from configuration")
    conn.execute("DELETE FROM adjacencies WHERE id = ?", (row["id"],))
    ledger = ospf.run_election(conn, net_id, "PEER_REMOVED")
    return {"schemaVersion": SCHEMA_VERSION, "netId": net_id, "satelliteId": satellite_id, "state": "REMOVED", "election": election_summary(ledger)}


@app.post("/api/v1/relay-nets/{net_id}/peers/{satellite_id}/clear", tags=["relay nets"])
def clear_peer(net_id: str, satellite_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """Bounce one adjacency, like clearing an OSPF interface: the adjacency re-forms and the roles are re-checked."""
    get_net(conn, net_id)
    row = get_adjacency(conn, net_id, satellite_id)
    satellite = get_satellite(conn, satellite_id)
    ospf.drop_adjacency(conn, net_id, dict(satellite), "adjacency cleared by operator")
    conn.execute("UPDATE adjacencies SET state = 'DOWN' WHERE id = ?", (row["id"],))
    ledger_down = ospf.run_election(conn, net_id, "ADJACENCY_CLEARED")
    conn.execute("UPDATE adjacencies SET state = 'FULL', last_hello_at = ?, formed_at = ? WHERE id = ?", (now_iso(), now_iso(), row["id"]))
    ospf.form_adjacency(conn, net_id, dict(satellite), row["priority"])
    ledger_up = ospf.run_election(conn, net_id, "ADJACENCY_REFORMED")
    return {"schemaVersion": SCHEMA_VERSION, "netId": net_id, "satelliteId": satellite_id, "state": "FULL", "election": election_summary(ledger_up), "whileDown": election_summary(ledger_down)}


@app.post("/api/v1/relay-nets/{net_id}/peers/{satellite_id}/hello", tags=["relay nets"])
def peer_hello(net_id: str, satellite_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """A keepalive from the relay. Nothing else restarts the dead timer, and a dead adjacency walks back up."""
    net = get_net(conn, net_id)
    row = get_adjacency(conn, net_id, satellite_id)
    satellite = get_satellite(conn, satellite_id)
    was_down = row["state"] != "FULL"
    conn.execute("UPDATE adjacencies SET last_hello_at = ? WHERE id = ?", (now_iso(), row["id"]))
    ledger = None
    if was_down:
        conn.execute("UPDATE adjacencies SET state = 'FULL', formed_at = ? WHERE id = ?", (now_iso(), row["id"]))
        ospf.form_adjacency(conn, net_id, dict(satellite), row["priority"])
        ledger = ospf.run_election(conn, net_id, "ADJACENCY_REFORMED")
    else:
        dbmod.log(
            conn, "INFO", "ospf", f"net {net['name']}",
            f"{satellite['name']}({satellite['id'][:8]}) hello received, hold timer restarted ({net['dead_interval_s']}s)",
        )
    refreshed = get_adjacency(conn, net_id, satellite_id)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "netId": net_id,
        "satelliteId": satellite_id,
        "state": refreshed["state"],
        "lastHelloAt": refreshed["last_hello_at"],
        "holdTimeS": ospf.hold_time(net["dead_interval_s"], refreshed["last_hello_at"]),
        "reformedFrom": row["state"] if was_down else None,
        "election": election_summary(ledger) if ledger else None,
    }


@app.post("/api/v1/relay-nets/{net_id}/election", tags=["relay nets"])
def trigger_election(net_id: str, body: ElectionIn = ElectionIn(), conn: sqlite3.Connection = Depends(get_conn)):
    """DS/BDS re-election, the equivalent of `clear ip ospf process` on the net."""
    get_net(conn, net_id)
    ledger = ospf.run_election(conn, net_id, body.reason, preemptive=body.preemptive)
    return {"schemaVersion": SCHEMA_VERSION, "election": election_summary(ledger), "candidates": ledger["candidates"], "relayNet": net_view(conn, net_id)}


@app.get("/api/v1/relay-nets/{net_id}/elections", tags=["relay nets"])
def election_history(net_id: str, limit: int = Query(20, ge=1, le=200), conn: sqlite3.Connection = Depends(get_conn)):
    get_net(conn, net_id)
    rows = conn.execute("SELECT ledger FROM elections WHERE net_id = ? ORDER BY id DESC LIMIT ?", (net_id, limit)).fetchall()
    history = [election_summary(json.loads(r["ledger"])) for r in rows]
    return {"schemaVersion": SCHEMA_VERSION, "netId": net_id, "count": len(history), "elections": history}


@app.get("/api/v1/relay-nets/{net_id}/neighbors", tags=["relay nets"])
def neighbors(net_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """The neighbor table, like `show ip ospf neighbor`."""
    net = get_net(conn, net_id)
    view = net_view(conn, net_id)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "netId": net_id,
        "netName": net["name"],
        "ds": view["ds"]["name"] if view["ds"] else None,
        "bds": view["bds"]["name"] if view["bds"] else None,
        "neighbors": [
            {"id": p["satelliteId"], "priority": p["priority"], "state": p["state"], "role": p["role"], "name": p["name"], "holdTimeS": p["holdTimeS"]}
            for p in view["adjacencies"]
        ],
    }


# ---------------------------------------------------------------- mining sites

@app.post("/api/v1/sites", tags=["mining sites"], status_code=201)
def register_site(body: SiteIn, conn: sqlite3.Connection = Depends(get_conn)):
    site_id = body.id or str(uuid.uuid4())
    if conn.execute("SELECT 1 FROM sites WHERE id = ?", (site_id,)).fetchone():
        raise HTTPException(409, f"mining site {site_id} already registered")
    base_station_id = body.base_station_id or str(uuid.uuid4())
    doc = {
        "id": base_station_id,
        "name": body.name,
        "class": "SURFACE_MINING_BASE",
        "status": body.status,
        "autonomyTier": body.autonomy_tier,
        "siteRef": {"siteId": site_id, "designation": body.designation, "hostBody": {"provisionalName": body.host_body}},
    }
    stamp = now_iso()
    conn.execute(
        "INSERT INTO sites (id, name, designation, host_body, base_station_id, status, doc, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (site_id, body.name, body.designation, body.host_body, base_station_id, body.status, json.dumps(doc), stamp, stamp),
    )
    if body.metrics:
        store_metrics(conn, "site", site_id, body.metrics)
    log(conn, "INFO", "registry", f"site {body.designation}", f"mining site registered id={site_id} baseStation={base_station_id} hostBody={body.host_body}")
    return {"schemaVersion": SCHEMA_VERSION, "siteId": site_id, "baseStationId": base_station_id, "status": body.status}


@app.get("/api/v1/sites", tags=["mining sites"])
def list_sites(conn: sqlite3.Connection = Depends(get_conn)):
    out = []
    for row in conn.execute("SELECT * FROM sites ORDER BY designation"):
        metrics = dbmod.latest_metrics(conn, "site", row["id"]) or {}
        out.append(
            {
                "id": row["id"],
                "name": row["name"],
                "designation": row["designation"],
                "hostBody": row["host_body"],
                "baseStationId": row["base_station_id"],
                "status": row["status"],
                "healthScore": metrics.get("healthScore"),
                "summary": site_summary(metrics),
                "relays": [l["satelliteId"] for l in links_of_site(conn, row["id"])],
            }
        )
    return {"schemaVersion": SCHEMA_VERSION, "count": len(out), "sites": out}


@app.get("/api/v1/sites/{site_id}", tags=["mining sites"])
def get_site_doc(site_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    row = get_site(conn, site_id)
    doc = dbmod.doc(row)
    doc["status"] = row["status"]
    doc["metrics"] = dbmod.latest_metrics(conn, "site", site_id) or {}
    doc["summary"] = site_summary(doc["metrics"])
    doc.setdefault("satelliteLinks", {})["links"] = links_of_site(conn, site_id)
    doc["fleet"] = {"roster": [robot_summary(r) for r in site_robots(conn, site_id)]}
    return {"schemaVersion": SCHEMA_VERSION, "baseStation": doc}


@app.get("/api/v1/sites/{site_id}/metrics", tags=["mining sites"])
def site_metrics(site_id: str, history: int = Query(0, ge=0, le=100), conn: sqlite3.Connection = Depends(get_conn)):
    get_site(conn, site_id)
    out = metrics_response(conn, "site", site_id, history)
    out["summary"] = site_summary(out["metrics"])
    return out


@app.post("/api/v1/sites/{site_id}/metrics", tags=["mining sites"], status_code=201)
def report_site_metrics(site_id: str, payload: dict[str, Any] = Body(...), conn: sqlite3.Connection = Depends(get_conn)):
    get_site(conn, site_id)
    return report_metrics(conn, "site", site_id, payload)


def store_metrics(conn: sqlite3.Connection, entity_type: str, entity_id: str, payload: dict) -> str:
    collected_at = payload.pop("collectedAt", None) or now_iso()
    dbmod.put_metrics(conn, entity_type, entity_id, payload, collected_at)
    return collected_at


def report_metrics(conn: sqlite3.Connection, entity_type: str, entity_id: str, payload: dict) -> dict:
    if not payload:
        raise HTTPException(400, "metrics payload must not be empty")
    collected_at = store_metrics(conn, entity_type, entity_id, payload)
    merged = dbmod.latest_metrics(conn, entity_type, entity_id)
    name = conn.execute(f"SELECT {LABEL_COLUMN[entity_type]} FROM {entity_type}s WHERE id = ?", (entity_id,)).fetchone()[0]
    log(conn, "INFO", "telemetry", f"{entity_type} {name}", f"metrics snapshot accepted collectedAt={collected_at} keys=[{','.join(sorted(payload))}]")
    return {"schemaVersion": SCHEMA_VERSION, "entityType": entity_type, "entityId": entity_id, "collectedAt": collected_at, "metrics": merged}


@app.get("/api/v1/sites/{site_id}/links", tags=["mining sites"])
def site_links(site_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    get_site(conn, site_id)
    links = links_of_site(conn, site_id)
    primary = next((l for l in links if l["role"] == "PRIMARY"), None)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "siteId": site_id,
        "count": len(links),
        "uplink": primary or None,
        "links": links,
    }


@app.post("/api/v1/sites/{site_id}/uplink", tags=["mining sites"], status_code=201)
def establish_uplink(site_id: str, body: UplinkIn, conn: sqlite3.Connection = Depends(get_conn)):
    site = get_site(conn, site_id)
    relay = get_satellite(conn, body.satellite_id)
    existing = conn.execute("SELECT * FROM links WHERE site_id = ? AND satellite_id = ?", (site_id, body.satellite_id)).fetchone()
    if existing and existing["status"] == "ESTABLISHED":
        raise HTTPException(409, f"uplink to {body.satellite_id} already established")
    holder = conn.execute(
        "SELECT satellite_id FROM links WHERE site_id = ? AND role = 'PRIMARY' AND status = 'ESTABLISHED'", (site_id,)
    ).fetchone()
    if body.role == "PRIMARY" and holder and holder["satellite_id"] != body.satellite_id:
        raise HTTPException(409, f"primary relay already held by {holder['satellite_id']}")
    stamp = now_iso()
    if existing:
        conn.execute(
            "UPDATE links SET role = ?, band = ?, status = 'ESTABLISHED', established_at = ?, missed_reports = 0"
            " WHERE site_id = ? AND satellite_id = ?",
            (body.role, body.band, stamp, site_id, body.satellite_id),
        )
    else:
        conn.execute(
            "INSERT INTO links (site_id, satellite_id, role, band, status, established_at, missed_reports, share_pct)"
            " VALUES (?,?,?,?,?,?,0,?)",
            (site_id, body.satellite_id, body.role, body.band, "ESTABLISHED", stamp, body.share_pct),
        )
    role_note = ""
    roles = ospf.roles_of(conn, body.satellite_id)
    if roles:
        role_note = " relayIs=" + ",".join(f"{net}:{role}" for net, role in roles.items())
    log(conn, "INFO", "link", f"site {site['designation']}", f"uplink {body.role} -> {relay['name']} band={body.band} established{role_note}")
    return {"schemaVersion": SCHEMA_VERSION, "siteId": site_id, "satelliteId": body.satellite_id, "role": body.role, "status": "ESTABLISHED", "establishedAt": stamp}


@app.delete("/api/v1/sites/{site_id}/uplink/{satellite_id}", tags=["mining sites"])
def drop_uplink(site_id: str, satellite_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    site = get_site(conn, site_id)
    link = conn.execute("SELECT * FROM links WHERE site_id = ? AND satellite_id = ?", (site_id, satellite_id)).fetchone()
    if not link:
        raise HTTPException(404, f"no link between site {site_id} and satellite {satellite_id}")
    conn.execute("DELETE FROM links WHERE site_id = ? AND satellite_id = ?", (site_id, satellite_id))
    log(conn, "WARN", "link", f"site {site['designation']}", f"uplink to {satellite_id} torn down (role was {link['role']})")
    return {"schemaVersion": SCHEMA_VERSION, "siteId": site_id, "satelliteId": satellite_id, "status": "REMOVED"}


@app.post("/api/v1/sites/{site_id}/links/failover", tags=["mining sites"])
def failover(site_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    site = get_site(conn, site_id)
    links = [l for l in conn.execute("SELECT * FROM links WHERE site_id = ?", (site_id,)).fetchall()]
    current = next((l for l in links if l["role"] == "PRIMARY"), None)
    if not current:
        raise HTTPException(409, "site has no primary relay to fail over from")
    candidates = sorted(
        (l for l in links if l["id"] != current["id"] and l["status"] in ("ESTABLISHED", "STANDBY")),
        key=lambda l: ROLE_PRIORITY.index(l["role"]),
    )
    if not candidates:
        raise HTTPException(409, "no usable backup relay for this site")
    next_link, stamp = candidates[0], now_iso()
    conn.execute("UPDATE links SET role = 'SECONDARY' WHERE id = ?", (current["id"],))
    conn.execute("UPDATE links SET role = 'PRIMARY', status = 'ESTABLISHED', established_at = ? WHERE id = ?", (stamp, next_link["id"]))
    log(
        conn, "WARN", "link", f"site {site['designation']}",
        f"failover {current['satellite_id']} -> {next_link['satellite_id']} newRole={next_link['role']} previousRole demoted to SECONDARY",
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "siteId": site_id,
        "failedOverFrom": current["satellite_id"],
        "failedOverTo": next_link["satellite_id"],
        "failedOverAt": stamp,
        "links": links_of_site(conn, site_id),
    }


# ---------------------------------------------------------------- robots

@app.post("/api/v1/robots", tags=["robots"], status_code=201)
def register_robot(body: RobotIn, conn: sqlite3.Connection = Depends(get_conn)):
    robot_id = body.id or str(uuid.uuid4())
    if conn.execute("SELECT 1 FROM robots WHERE id = ?", (robot_id,)).fetchone():
        raise HTTPException(409, f"robot {robot_id} already registered")
    site = get_site(conn, body.site_id)
    doc = {
        "id": robot_id,
        "designation": body.designation,
        "class": body.robot_class,
        "model": body.model,
        "serialNumber": body.serial_number,
        "status": "OPERATIONAL",
        "state": body.state,
        "mode": "AUTONOMOUS",
        "ownership": {
            "baseStationId": site["base_station_id"],
            "tenure": "OWNED",
            "siteId": body.site_id,
            "zoneId": body.zone_id,
        },
    }
    stamp = now_iso()
    conn.execute(
        "INSERT INTO robots (id, designation, robot_class, status, state, site_id, base_station_id, zone_id, battery_pct,"
        " health_pct, doc, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (robot_id, body.designation, body.robot_class, "OPERATIONAL", body.state, body.site_id, site["base_station_id"],
         body.zone_id, body.battery_pct, body.health_pct, json.dumps(doc), stamp, stamp),
    )
    dbmod.put_metrics(
        conn, "robot", robot_id,
        {"healthScore": body.health_pct / 100, "power": {"batteryPct": body.battery_pct}, "tasking": {"currentTaskId": None, "taskType": None, "progressPct": 0.0, "tonsMoved": 0.0}},
        stamp,
    )
    log(conn, "INFO", "registry", f"robot {body.designation}", f"robot registered class={body.robot_class} site={body.site_id} zone={body.zone_id or '-'} state={body.state}")
    return {"schemaVersion": SCHEMA_VERSION, "robotId": robot_id, "state": body.state, "registeredAt": stamp}


@app.get("/api/v1/robots", tags=["robots"])
def list_robots(site_id: str | None = Query(None, alias="siteId"), state: str | None = None, conn: sqlite3.Connection = Depends(get_conn)):
    query, params = "SELECT * FROM robots", []
    if site_id:
        query += " WHERE site_id = ?"
        params.append(site_id)
    query += " ORDER BY designation"
    rows = [r for r in conn.execute(query, params) if not state or r["state"] == state]
    return {"schemaVersion": SCHEMA_VERSION, "count": len(rows), "robots": [robot_summary(r) for r in rows]}


@app.get("/api/v1/robots/{robot_id}", tags=["robots"])
def get_robot_doc(robot_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    row = get_robot(conn, robot_id)
    doc = dbmod.doc(row)
    doc["status"] = row["status"]
    doc["state"] = row["state"]
    doc["metrics"] = dbmod.latest_metrics(conn, "robot", robot_id) or {}
    doc["metrics"]["power"] = {**(doc["metrics"].get("power") or {}), "batteryPct": row["battery_pct"]}
    return {"schemaVersion": SCHEMA_VERSION, "robot": doc}


@app.get("/api/v1/robots/{robot_id}/metrics", tags=["robots"])
def robot_metrics(robot_id: str, history: int = Query(0, ge=0, le=100), conn: sqlite3.Connection = Depends(get_conn)):
    get_robot(conn, robot_id)
    return metrics_response(conn, "robot", robot_id, history)


@app.post("/api/v1/robots/{robot_id}/metrics", tags=["robots"], status_code=201)
def report_robot_metrics(robot_id: str, payload: dict[str, Any] = Body(...), conn: sqlite3.Connection = Depends(get_conn)):
    get_robot(conn, robot_id)
    return report_metrics(conn, "robot", robot_id, payload)


def apply_command(conn: sqlite3.Connection, row: sqlite3.Row, action: str, issued_by: str, note: str) -> dict:
    allowed, new_state = TRANSITIONS[action]
    previous = row["state"]
    if previous not in allowed:
        log(conn, "WARN", "command", f"robot {row['designation']}", f"{action} rejected from state {previous}")
        return {"robotId": row["id"], "accepted": False, "state": previous, "reason": f"{action} not allowed from state {previous}"}
    stamp = now_iso()
    conn.execute(
        "UPDATE robots SET state = ?, updated_at = ?, doc = ? WHERE id = ?",
        (new_state, stamp, json.dumps({**dbmod.doc(row), "state": new_state}), row["id"]),
    )
    conn.execute(
        "INSERT INTO commands (id, robot_id, action, issued_by, previous_state, new_state, note, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), row["id"], action, issued_by, previous, new_state, note, stamp),
    )
    dbmod.put_metrics(conn, "robot", row["id"], {"tasking": {"lastCommand": {"action": action, "at": stamp, "issuedBy": issued_by}}}, stamp)
    log(conn, "INFO", "command", f"robot {row['designation']}", f"{action} accepted by {issued_by}: {previous} -> {new_state}" + (f" note={note}" if note else ""))
    return {"robotId": row["id"], "designation": row["designation"], "accepted": True, "previousState": previous, "state": new_state, "issuedAt": stamp}


@app.post("/api/v1/robots/{robot_id}/command", tags=["robots"])
def command_robot(robot_id: str, body: CommandIn, conn: sqlite3.Connection = Depends(get_conn)):
    result = apply_command(conn, get_robot(conn, robot_id), body.action, body.issued_by, body.note)
    if not result["accepted"]:
        raise HTTPException(409, result["reason"])
    return {"schemaVersion": SCHEMA_VERSION, **result}


@app.get("/api/v1/robots/{robot_id}/commands", tags=["robots"])
def robot_commands(robot_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    get_robot(conn, robot_id)
    rows = conn.execute("SELECT * FROM commands WHERE robot_id = ? ORDER BY rowid DESC", (robot_id,)).fetchall()
    out = [{"commandId": r["id"], "action": r["action"], "issuedBy": r["issued_by"], "previousState": r["previous_state"],
            "state": r["new_state"], "note": r["note"], "issuedAt": r["created_at"]} for r in rows]
    return {"schemaVersion": SCHEMA_VERSION, "robotId": robot_id, "count": len(out), "commands": out}


@app.post("/api/v1/sites/{site_id}/robots/command", tags=["mining sites"])
def command_site_robots(site_id: str, body: CommandIn, conn: sqlite3.Connection = Depends(get_conn)):
    get_site(conn, site_id)
    results = [apply_command(conn, r, body.action, body.issued_by, body.note) for r in site_robots(conn, site_id)]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "siteId": site_id,
        "action": body.action,
        "accepted": [r for r in results if r["accepted"]],
        "rejected": [{"robotId": r["robotId"], "reason": r["reason"]} for r in results if not r["accepted"]],
    }


# ---------------------------------------------------------------- telemetry reports

@app.post("/api/v1/reports", tags=["telemetry reports"], status_code=201)
def ingest_report(body: ReportIn, conn: sqlite3.Connection = Depends(get_conn)):
    site = get_site(conn, body.site_id)
    get_satellite(conn, body.recipient_satellite_id)
    report_id = body.report_id or str(uuid.uuid4())
    if conn.execute("SELECT 1 FROM reports WHERE id = ?", (report_id,)).fetchone():
        raise HTTPException(409, f"report {report_id} already ingested")
    link = conn.execute(
        "SELECT * FROM links WHERE site_id = ? AND satellite_id = ?", (body.site_id, body.recipient_satellite_id)
    ).fetchone()
    if not link or link["status"] != "ESTABLISHED":
        raise HTTPException(409, f"no established uplink from site {body.site_id} to satellite {body.recipient_satellite_id}")
    if body.sender_id != site["base_station_id"]:
        raise HTTPException(422, f"senderId {body.sender_id} is not the base station of site {body.site_id}")
    stamp = now_iso()
    conn.execute(
        "INSERT INTO reports (id, schema_name, sender_id, site_id, recipient_satellite_id, priority, seq, generated_at,"
        " payload, accepted_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (report_id, body.schema_name, body.sender_id, body.site_id, body.recipient_satellite_id, body.priority, body.seq,
         body.generated_at or stamp, json.dumps(body.payload), stamp),
    )
    conn.execute("UPDATE links SET last_report_at = ?, missed_reports = 0 WHERE id = ?", (stamp, link["id"]))
    log(
        conn, "INFO", "telemetry", f"site {site['designation']}",
        f"report {report_id} seq={body.seq} priority={body.priority} accepted via {body.recipient_satellite_id} in {stamp}",
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "reportId": report_id,
        "acceptedAt": stamp,
        "recipientSatelliteId": body.recipient_satellite_id,
        "link": link_json(conn.execute("SELECT * FROM links WHERE id = ?", (link["id"],)).fetchone()),
    }


@app.get("/api/v1/reports", tags=["telemetry reports"])
def list_reports(
    site_id: str | None = Query(None, alias="siteId"),
    satellite_id: str | None = Query(None, alias="satelliteId"),
    priority: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    conn: sqlite3.Connection = Depends(get_conn),
):
    query, params = "SELECT * FROM reports", []
    if site_id:
        query += " AND site_id = ?" if params else " WHERE site_id = ?"
        params.append(site_id)
    if satellite_id:
        query += " AND recipient_satellite_id = ?" if params else " WHERE recipient_satellite_id = ?"
        params.append(satellite_id)
    if priority:
        query += " AND priority = ?" if params else " WHERE priority = ?"
        params.append(priority)
    query += " ORDER BY rowid DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    out = [{"reportId": r["id"], "schema": r["schema_name"], "senderId": r["sender_id"], "siteId": r["site_id"],
            "recipientSatelliteId": r["recipient_satellite_id"], "priority": r["priority"], "seq": r["seq"],
            "generatedAt": r["generated_at"], "acceptedAt": r["accepted_at"], "payload": json.loads(r["payload"])} for r in rows]
    return {"schemaVersion": SCHEMA_VERSION, "count": len(out), "reports": out}


@app.get("/api/v1/reports/{report_id}", tags=["telemetry reports"])
def get_report(report_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"report {report_id} not found")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "reportId": row["id"],
        "schema": row["schema_name"],
        "senderId": row["sender_id"],
        "siteId": row["site_id"],
        "recipientSatelliteId": row["recipient_satellite_id"],
        "priority": row["priority"],
        "seq": row["seq"],
        "generatedAt": row["generated_at"],
        "acceptedAt": row["accepted_at"],
        "payload": json.loads(row["payload"]),
    }


@app.get("/api/v1/sites/{site_id}/robots", tags=["mining sites"])
def site_robot_list(site_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    get_site(conn, site_id)
    rows = site_robots(conn, site_id)
    by_state: dict[str, int] = {}
    for r in rows:
        by_state[r["state"]] = by_state.get(r["state"], 0) + 1
    return {
        "schemaVersion": SCHEMA_VERSION,
        "siteId": site_id,
        "count": len(rows),
        "byState": by_state,
        "robots": [robot_summary(r) for r in rows],
    }


@app.delete("/api/v1/satellites/{satellite_id}/connections/{site_id}", tags=["relays"])
def disconnect_satellite(satellite_id: str, site_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    get_satellite(conn, satellite_id)
    link = conn.execute("SELECT * FROM links WHERE site_id = ? AND satellite_id = ?", (site_id, satellite_id)).fetchone()
    if not link:
        raise HTTPException(404, f"no link between site {site_id} and satellite {satellite_id}")
    conn.execute("DELETE FROM links WHERE id = ?", (link["id"],))
    return {"schemaVersion": SCHEMA_VERSION, "satelliteId": satellite_id, "siteId": site_id, "status": "REMOVED"}


@app.patch("/api/v1/satellites/{satellite_id}/status", tags=["relays"])
def set_satellite_status(satellite_id: str, status: EntityStatus = Query(...), conn: sqlite3.Connection = Depends(get_conn)):
    row = get_satellite(conn, satellite_id)
    stamp = now_iso()
    conn.execute(
        "UPDATE satellites SET status = ?, updated_at = ?, doc = ? WHERE id = ?",
        (status, stamp, json.dumps({**dbmod.doc(row), "status": status}), satellite_id),
    )
    log(conn, "INFO" if status not in ("OFFLINE", "DECOMMISSIONED") else "WARN", "link", f"sat {row['name']}", f"status -> {status}")
    if status in ("OFFLINE", "DECOMMISSIONED"):
        rows = conn.execute("SELECT id FROM links WHERE satellite_id = ? AND status = 'ESTABLISHED'", (satellite_id,)).fetchall()
        for link in rows:
            conn.execute("UPDATE links SET status = 'DEGRADED', missed_reports = missed_reports + 1 WHERE id = ?", (link["id"],))
        if rows:
            log(conn, "WARN", "link", f"sat {row['name']}", f"{len(rows)} site uplink(s) degraded because the relay is {status}")
        degraded = [
            link_json(conn.execute("SELECT * FROM links WHERE id = ?", (link["id"],)).fetchone()) for link in rows
        ]
    else:
        degraded = []

    held = ospf.roles_of(conn, satellite_id)
    adjacencies = conn.execute(
        "SELECT a.id, a.net_id, r.name FROM adjacencies a JOIN relay_nets r ON r.id = a.net_id"
        " WHERE a.satellite_id = ? AND a.state != 'DOWN'",
        (satellite_id,),
    ).fetchall()
    for adjacency in adjacencies:
        conn.execute("UPDATE adjacencies SET state = 'DOWN' WHERE id = ?", (adjacency["id"],))
        ospf.drop_adjacency(conn, adjacency["net_id"], {"id": satellite_id, "name": row["name"]}, f"relay status is {status}")
        ospf.run_election(conn, adjacency["net_id"], "RELAY_LOST")
    if adjacencies and held:
        log(conn, "WARN", "ospf", f"sat {row['name']}", f"lost {', '.join(f'{role}@{net}' for net, role in held.items())}")
    elif adjacencies:
        log(conn, "INFO", "ospf", f"sat {row['name']}", f"adjacency down on {', '.join(a['net_id'] for a in adjacencies)}")
    if status not in ("OFFLINE", "DECOMMISSIONED"):
        down = conn.execute(
            "SELECT net_id FROM adjacencies WHERE satellite_id = ? AND state = 'DOWN'", (satellite_id,)
        ).fetchall()
        if down:
            log(conn, "INFO", "ospf", f"sat {row['name']}", f"back to {status}; adjacency on {', '.join(d['net_id'] for d in down)} stays DOWN until cleared")
    return {"schemaVersion": SCHEMA_VERSION, "satelliteId": satellite_id, "status": status, "degradedLinks": degraded}


# ---------------------------------------------------------------- activity log

@app.get("/api/v1/logs", tags=["activity log"])
def get_logs(
    limit: int = Query(50, ge=1, le=2000),
    level: str | None = None,
    category: str | None = None,
    search: str | None = None,
    fmt: Literal["json", "text"] = Query("json", alias="format"),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Text activity log, oldest line first. `format=text` returns plain text."""
    query, params = "SELECT * FROM log_events", []
    if level:
        query += " AND level = ?" if params else " WHERE level = ?"
        params.append(level.upper())
    if category:
        query += " AND category = ?" if params else " WHERE category = ?"
        params.append(category)
    if search:
        clause = "(message LIKE ? OR source LIKE ?)"
        query += f" AND {clause}" if params else f" WHERE {clause}"
        params.extend([f"%{search}%", f"%{search}%"])
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = list(reversed(conn.execute(query, params).fetchall()))
    lines = [f"{r['ts']} {r['level']:<5} {r['category']:<9} {(r['source'] or ''):<28} {r['message']}" for r in rows]
    if fmt == "text":
        return PlainTextResponse("\n".join(lines) + ("\n" if lines else ""))
    return {"schemaVersion": SCHEMA_VERSION, "count": len(lines), "lines": lines}
