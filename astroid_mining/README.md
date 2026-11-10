# Astroid Mining Fleet Control

Small FastAPI + SQLite service for asteroid mining operations. Built as a target for
**pytest practice with `requests`**: every behaviour is reachable over real HTTP.

The fleet: comms satellites (relays), mining sites with their surface base station, and the
robot fleet that does the digging. The relays talk to each other the way OSPF routers do:
adjacencies over a shared relay net, with a Designated Satellite (DS) and a Backup Designated
Satellite (BDS) elected per net.

```
app/db.py      sqlite schema + connection + metrics + text log helpers
app/auth.py    users, password hashing, bearer tokens
app/clock.py   the one clock: host system time, UTC, and the OSPF hold-time maths
app/seed.py    the fleet in its known-good state (the sample documents from the spec, incl. users)
app/ospf.py    relay-net adjacencies and the DS/BDS election
app/main.py    FastAPI routes
web/           three.js 3D view of the live API, served at /viz (no build step)
tests/         pytest suite, live uvicorn server, requests client
```

## Setup

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
```

## Run

```bash
.venv/bin/python -m uvicorn app.main:app --reload      # Swagger UI at /docs, Redoc at /redoc, 3D view at /viz
```

State lives in `astroid_mining.db` (override with `ASTROID_DB_PATH=/path/to.db`). The schema is
created and the fleet seeded on first start. On start an older database gets the new tables, the two
accounts, and its OSPF timers moved onto the real clock; a database that predates relay nets does not
get the nets themselves — delete the file for a clean fleet. On boot each relay net runs its first
DS/BDS election, and every state change is written as a text log line — to the server console and to
the queryable `logs` table.

## Sign in

Only `POST /api/v1/auth/login` takes a username and password. Everything else takes the bearer token
it returns, which is valid for **2 days**. Two roles: `admin` may change fleet state, `viewer` may
only read it (`403` on any `POST/PATCH/PUT/DELETE`).

| user | password | role |
|---|---|---|
| `fleet-admin` | `regolith-7` | admin |
| `site-observer` | `stargazer-2` | viewer |

```bash
TOKEN=$(curl -s localhost:8000/api/v1/auth/login -H 'content-type: application/json' \
        -d '{"username": "fleet-admin", "password": "regolith-7"}' | jq -r .token)
curl -s localhost:8000/api/v1/fleet/summary -H "Authorization: Bearer $TOKEN" | jq .robotsByState
curl -s localhost:8000/api/v1/auth/me -H "Authorization: Bearer $TOKEN"      # who the token is
curl -s -X POST localhost:8000/api/v1/auth/logout -H "Authorization: Bearer $TOKEN"   # revoke it
```

Passwords are stored as PBKDF2-SHA256 (stdlib, 200k iterations); tokens are random strings with an
`expires_at` in SQLite, and expired rows are swept on each login. In Swagger UI use **Authorize** and
paste the token — the schema declares it as a bearer security scheme, and `/health` and the login are
the two endpoints that stay public (as does `/docs` itself).

## 3D view

`http://localhost:8000/viz/` — one page (`web/index.html` + `web/app.js`) with three.js r170 vendored
beside it, so there is no build step, no npm and nothing fetched from a CDN while you look at it. The
page holds no fleet data: the form signs in through `POST /api/v1/auth/login`, then it GETs
`/fleet/summary`, `/clock`, `/sites`, `/sites/{id}`, `/satellites` and `/relay-nets` every 5 s and
draws what it gets. Register a site and an asteroid appears; run an election and the gold ring moves.

| what is drawn | which field it comes from |
|---|---|
| asteroid size | `summary.productionRateTph` |
| asteroid colour | `healthScore` green → red; grey when the site is not `OPERATIONAL` |
| cubes circling an asteroid | `baseStation.fleet.roster[]`, coloured by robot `state` (legend in the panel) |
| octahedra on the inner ring | `/api/v1/satellites`, coloured by `status` |
| gold / silver ring around a relay | the current DS / BDS of that relay net |
| lines asteroid → relay | `satelliteLinks.links[]`: opacity by role (PRIMARY bold → COLD_STANDBY faint), colour by `status` (`DEGRADED` red) |
| relay ↔ relay mesh | one line per pair of peers on a net; any pair not `FULL` goes dark red |
| panel tables | DS/BDS per net, adjacency state and remaining `holdTimeS`, fleet counts, the server clock and token countdown |

Drag to orbit, wheel to zoom, hover any body or line for its live fields. Nothing is animated from
invented numbers — the rings turn at the `SPIN` rate and their bodies sit at the `*_RING` radius, both
constants at the top of `web/app.js`, and position is a pure function of the page clock, so a 5 s poll
never snaps anything back to its start angle. The layout is schematic: orbit bands and sizes are not to
scale, since the real positions are in units of 10⁸ km. A browser without WebGL says so and still fills
in the panel.

## What the API does

| | |
|---|---|
| `POST /api/v1/auth/login` | username + password → bearer token, `expiresAt` 2 days out (no token needed) |
| `GET /api/v1/auth/me` | the signed-in user and when its token expires |
| `POST /api/v1/auth/logout` | revoke this token (either role) |
| `GET /health` | liveness + fleet counts (public) |
| `GET /api/v1/fleet/summary` | robots by class/state, link health, open anomalies |
| `GET /api/v1/clock` | the host system time the service runs on, plus uptime |
| `POST /api/v1/satellites` | register a relay (optionally with its first telemetry) |
| `GET /api/v1/satellites` `?status=` | list relays |
| `GET /api/v1/satellites/{id}` | full relay document: orbit, live metrics, backups, served mining sites |
| `GET/POST /api/v1/satellites/{id}/metrics` `?history=N` | read / push telemetry (push is merged, history kept) |
| `POST /api/v1/satellites/{id}/connections` | connect the relay to `"all"` sites or `{"siteIds": [...]}` |
| `GET /api/v1/satellites/{id}/links` | links this relay serves |
| `POST /api/v1/satellites/{id}/backups` | designate it as backup of another relay |
| `PATCH /api/v1/satellites/{id}/status` | set status; OFFLINE degrades its links and drops its adjacencies |
| `DELETE /api/v1/satellites/{id}/connections/{siteId}` | drop a link |
| `GET /api/v1/relay-nets` | relay nets with adjacencies, DS and BDS |
| `POST /api/v1/relay-nets` | create a relay net (band, hello/dead timers) |
| `GET /api/v1/relay-nets/{net}` | one net: adjacencies, current DS/BDS, last election ledger |
| `GET /api/v1/relay-nets/{net}/neighbors` | neighbor table, like `show ip ospf neighbor` |
| `POST /api/v1/relay-nets/{net}/peers` | attach a relay with a router `priority` (0 = always DROther) |
| `POST /api/v1/relay-nets/{net}/peers/{satId}/clear` | bounce one adjacency and re-check the roles |
| `POST /api/v1/relay-nets/{net}/peers/{satId}/hello` | keepalive: restart the dead timer, re-form a dead adjacency |
| `DELETE /api/v1/relay-nets/{net}/peers/{satId}` | remove a peer |
| `POST /api/v1/relay-nets/{net}/election` | trigger the DS/BDS re-election (`preemptive`, `reason`) |
| `GET /api/v1/relay-nets/{net}/elections` | election history |
| `GET /api/v1/logs` `?level=&category=&search=&limit=&format=text` | the text activity log |
| `POST /api/v1/sites` | register a mining spot |
| `GET /api/v1/sites` / `GET /api/v1/sites/{id}` | sites, or one full base-station document |
| `GET/POST /api/v1/sites/{id}/metrics` | temperature, production rate, stock — flat `summary` included |
| `POST /api/v1/sites/{id}/uplink` | establish uplink with a relay (`role`: PRIMARY/SECONDARY/…) |
| `GET /api/v1/sites/{id}/links` | link list + the current `uplink` |
| `POST /api/v1/sites/{id}/links/failover` | hand the PRIMARY role to the next backup |
| `DELETE /api/v1/sites/{id}/uplink/{satelliteId}` | drop uplink |
| `GET /api/v1/sites/{id}/robots` | fleet at a site with `byState` counts |
| `POST /api/v1/sites/{id}/robots/command` | `START/STOP/PAUSE/RESUME` for every robot at the site |
| `POST /api/v1/robots` | register a robot |
| `GET /api/v1/robots` `?siteId=&state=` | list robots |
| `GET /api/v1/robots/{id}` | full robot document |
| `GET/POST /api/v1/robots/{id}/metrics` | robot telemetry, battery/health mirrored to the registry |
| `POST /api/v1/robots/{id}/command` | `{"action": "START" \| "STOP" \| "PAUSE" \| "RESUME"}` |
| `GET /api/v1/robots/{id}/commands` | telecommand audit log |
| `POST /api/v1/reports` | a base pushes a telemetry report to a relay (needs an established uplink) |
| `GET /api/v1/reports` `?siteId=&satelliteId=&priority=&limit=` | ingested reports |
| `GET /api/v1/reports/{id}` | one report |

Rules the service enforces (the interesting part for tests):

- every endpoint but `/health` and the login needs `Authorization: Bearer <token>`; a `POST`, `PATCH`,
  `PUT` or `DELETE` additionally needs an **admin** token → `403` for a viewer, `401` for no/expired
  token;

- one PRIMARY relay per site; a second one is refused, and a cold standby can be promoted by failover;
- robot states follow a machine: `START` from `IDLE/CHARGING/RETURNING/PAUSED/STOPPED/MAINTENANCE`,
  `PAUSE` only from `ACTIVE`, `STOP` from any working state; `FAULT`/`LOST` robots are grounded → `409`;
- a report without an established uplink is refused with `409`, the same report twice is `409`;
- metrics pushes deep-merge into the last snapshot, so a partial push keeps the rest of the document.

OSPF behaviour on a relay net: an adjacency is only a candidate while it is `FULL` and the relay is
`OPERATIONAL`; priority `0` means DROther forever; highest priority wins and ties go to the highest
router id (the satellite id). The election is **non-preemptive** — a newcomer with a higher priority
takes over only when the operator calls `POST .../election`, or when the incumbent is lost (status
`OFFLINE`/`DECOMMISSIONED`, peer removed, adjacency cleared, dead timer expired). Every election,
adjacency up/down, registration, command, report and failover writes a log line.

Time: the service keeps no clock of its own, it uses the **host system clock** in UTC (millisecond
stamps, `Z` suffix), which `GET /api/v1/clock` reports. That clock expires tokens and ages out
adjacencies: a neighbor not seen for `deadIntervalS` is `DOWN` the next time anyone reads the net, and
the net re-elects. No timers are run — the dead interval is applied when a net is read or changed, so
an untouched net costs nothing. `POST .../peers/{satId}/hello` restarts a neighbor's hold timer and
brings a dead one back up through `INIT → 2_WAY → FULL`; the neighbor table reports the remaining
`holdTimeS`, like `show ip ospf neighbor` does.

## Test

```bash
.venv/bin/python -m pytest                # 87 tests
.venv/bin/python -m pytest -k failover -x  # one behaviour
```

| file | what it pins down |
|---|---|
| `test_fleet.py` | the fleet picture and the two relays that are not live |
| `test_auth.py` | login, 2-day token, `401` for no/expired token, `403` when a viewer acts, logout, the OpenAPI bearer scheme |
| `test_satellites.py` | registration (incl. a cold standby, which must stay out of failover), backups, telemetry, status side-effects, the OSPF block in the relay document |
| `test_ospf.py` | DS/BDS election: priority order, `0` → DROther, tie-break, non-preemption, takeover after `OPERATOR_CLEAR`, DS lost → BDS promoted, adjacency walking `DOWN → INIT → 2_WAY → FULL`, election ledger |
| `test_logs.py` | every action writes a timestamped line: registration, refused commands, telemetry, link/failover changes, elections; filter by level/category/search, text and JSON output |
| `test_clock.py` | the service reads the system clock, not a simulated one; health/log stamps match it; a peer that stops answering hellos is DOWN after `deadIntervalS`, the net re-elects, a `hello` brings it back |
| `test_sites.py` | uplinks, PRIMARY conflict, failover order, production/stock metrics, bulk robot commands |
| `test_robots.py` | the `START/PAUSE/RESUME/STOP` state machine, telemetry, audit trail |
| `test_reports.py` | reports need an uplink, `senderId` must be the base, duplicates refused |
| `test_viz.py` | `/viz` and its vendored three.js are served without a token; every field and id the 3D view reads is present in the API (its exact fetch sequence); the five endpoints it calls at once all answer 200 |

`tests/conftest.py` starts uvicorn on a free port against a throwaway SQLite file, waits for
`/health`, signs in as the seeded admin and hands the tests an `api` fixture that is a thin
`requests` wrapper with the token attached. `viewer` is the same wrapper with the read-only account,
`anon` sends no token at all. Tests use the seeded fleet ids from `app/seed.py` and create their own
sites/relays/robots when they mutate state.

## Example session

```bash
curl -s localhost:8000/api/v1/sites -H "Authorization: Bearer $TOKEN" | jq '.sites[0].summary'
curl -s -X POST localhost:8000/api/v1/sites/a94f2c70-6b18-4d5a-92e3-0c7f4a6d8b21/metrics \
     -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     -d '{"inventory": {"rawOreOnSiteTons": 20500}, "excavation": {"sintererOutputTph": 52}}'
curl -s -X POST localhost:8000/api/v1/robots/8a2f6d31-5b04-4c97-9a8e-1d6c4f7b20e5/command \
     -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     -d '{"action": "PAUSE", "issuedBy": "safety-officer"}'
curl -s -X POST localhost:8000/api/v1/satellites \
     -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     -d '{"name": "NEW-RELAY-1", "status": "INTEGRATING"}' | jq .

# who runs the belt relay net, then hand the net to a better relay
curl -s localhost:8000/api/v1/relay-nets/net-belt-1/neighbors -H "Authorization: Bearer $TOKEN" \
     | jq '.ds, .neighbors[] | {name, priority, state, role}'
curl -s -X POST localhost:8000/api/v1/relay-nets/net-belt-1/peers -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"satelliteId": "<new relay id>", "priority": 250}' | jq .election
curl -s -X POST localhost:8000/api/v1/relay-nets/net-belt-1/election -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"reason": "OPERATOR_CLEAR"}' | jq .election

# the clock, the neighbor hold times, and a keepalive that keeps a peer up
curl -s localhost:8000/api/v1/clock -H "Authorization: Bearer $TOKEN" | jq
curl -s localhost:8000/api/v1/relay-nets/net-belt-1/neighbors -H "Authorization: Bearer $TOKEN" \
     | jq '.neighbors[] | {name, state, holdTimeS}'
curl -s -X POST localhost:8000/api/v1/relay-nets/net-belt-1/peers/9f1c4c2e-8b7a-4d6f-9a3e-2c5d7e8f1a44/hello \
     -H "Authorization: Bearer $TOKEN" | jq '{state, holdTimeS}'

# the text log
curl -s "localhost:8000/api/v1/logs?format=text&limit=20&category=ospf" -H "Authorization: Bearer $TOKEN"
```

## Swagger / OpenAPI ---------------------

Built into FastAPI, nothing to install: `/docs` (Swagger UI), `/redoc`, `/openapi.json` — all three
stay readable without a token.

- `openapi_tags`: eight groups — auth, fleet, relays, relay nets, mining sites, robots, telemetry
  reports, activity log — each with a description, so `/docs` reads as an operations manual rather
  than 48 flat operations.
- The app `description` (shown at the top of `/docs`) states the rules the API enforces: token + role
  rules, one PRIMARY per site, the robot state machine, uplink-before-report, merged metrics, and the
  DS/BDS election rules including non-preemption.
- Swagger UI has a global **Authorize**: the schema declares a `bearerToken` security scheme on every
  operation except `/health` and the login, so pasting a token once makes *Try it out* work.
- Request bodies are Pydantic models (`LoginIn`, `SatelliteIn`, `RobotIn`, `PeerIn`, `ReportIn`, …),
  so their fields and `minLength`/`minimum` constraints appear in the docs; `GET /logs` declares its
  query constraints and its `format` enum.
- The generated schema is what a client generator or contract test would consume; `tests/test_auth.py`
  asserts the tag groups, the bearer scheme and the two public endpoints, so the docs cannot drift
  away from the API.

## What is not implemented ----------------

Deliberately left out, so the demo stays a test target rather than a product:

- the 3D view is a read-only demo client: it polls every 5 s, draws no metrics graphs and no log, and
  has no camera presets or history scrub
- no automatic failure simulator (relays go offline only when told to), and nothing sends hellos for
  you: leave a demo running for `deadIntervalS` (40 s on the seeded nets) and its relays go DOWN
  until a `hello` arrives
- dead timers are applied when a net is read or changed, not by a background timer — a net nobody
  touches keeps its last known state until someone looks
- no user management over HTTP: the two accounts are seeded, passwords cannot be changed or rotated
- no expiry handling beyond `expires_at` (no refresh flow, no rate limit, no auth on `/health`)
- no delete endpoints for sites or relays, no cascading delete of links/metrics/history
- a site and its base station are one table (`sites`), split it if they ever need to diverge
