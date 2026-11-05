"""OSPF-shaped relay adjacencies between satellites.

Satellites attach to a relay net (a shared comms band, the equivalent of an OSPF
broadcast network). Adjacencies walk DOWN -> INIT -> 2_WAY -> FULL; each net runs a
Designated Satellite (DS) / Backup Designated Satellite (BDS) election:

  * a peer with priority 0 is always DROther and can never be elected,
  * a peer is only a candidate while its adjacency is FULL and it is OPERATIONAL,
  * highest priority wins, ties broken by highest router id (the satellite id),
  * the election is non-preemptive: an incumbent DS keeps the role until it is lost,
    until the operator triggers a re-election, or until the adjacency is cleared.
"""

import json
import sqlite3

from . import clock
from . import db as dbmod

ELIGIBLE_STATUS = {"OPERATIONAL"}


def net_row(conn, net_id: str):
    return conn.execute("SELECT * FROM relay_nets WHERE id = ?", (net_id,)).fetchone()


def neighbors(conn, net_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT a.satellite_id, a.priority, a.state, a.last_hello_at, a.formed_at, s.name, s.status"
        " FROM adjacencies a JOIN satellites s ON s.id = a.satellite_id WHERE a.net_id = ?"
        " ORDER BY a.priority DESC, a.satellite_id DESC",
        (net_id,),
    ).fetchall()
    return [
        {
            "satelliteId": r["satellite_id"],
            "name": r["name"],
            "routerId": r["satellite_id"],
            "priority": r["priority"],
            "state": r["state"],
            "status": r["status"],
            "lastHelloAt": r["last_hello_at"],
            "formedAt": r["formed_at"],
        }
        for r in rows
    ]


def current_roles(conn, net_id: str) -> tuple[str | None, str | None]:
    row = conn.execute("SELECT ds_id, bds_id FROM elections WHERE net_id = ? ORDER BY id DESC LIMIT 1", (net_id,)).fetchone()
    return (row["ds_id"], row["bds_id"]) if row else (None, None)


def roles_of(conn, satellite_id: str) -> dict[str, str]:
    """Which relay nets this satellite currently holds DS / BDS on."""
    roles = {}
    for row in conn.execute("SELECT net_id, ds_id, bds_id FROM elections ORDER BY id"):
        if row["ds_id"] == satellite_id:
            roles[row["net_id"]] = "DS"
        elif row["bds_id"] == satellite_id:
            roles[row["net_id"]] = "BDS"
    return roles


def evaluate(conn, net_id: str) -> tuple[list[dict], list[dict]]:
    eligible, ineligible = [], []
    for peer in neighbors(conn, net_id):
        if peer["state"] != "FULL":
            ineligible.append({**peer, "excluded": f"adjacency is {peer['state']}"})
        elif peer["priority"] == 0:
            ineligible.append({**peer, "excluded": "priority 0, always DROther"})
        elif peer["status"] not in ELIGIBLE_STATUS:
            ineligible.append({**peer, "excluded": f"status is {peer['status']}"})
        else:
            eligible.append(peer)
    eligible.sort(key=lambda p: p["satelliteId"], reverse=True)
    eligible.sort(key=lambda p: p["priority"], reverse=True)
    return eligible, ineligible


def describe(peer: dict | None) -> str:
    if not peer:
        return "none"
    return f"{peer['name']}({peer['routerId'][:8]} prio={peer['priority']})"


def run_election(conn, net_id: str, reason: str, preemptive: bool = False) -> dict:
    net = net_row(conn, net_id)
    previous_ds, previous_bds = current_roles(conn, net_id)
    eligible, ineligible = evaluate(conn, net_id)
    by_id = {p["satelliteId"]: p for p in eligible}

    if preemptive or previous_ds not in by_id:
        ds = eligible[0] if eligible else None
        bds = eligible[1] if len(eligible) > 1 else None
        decision = "re-elected" if ds else "no eligible candidate"
    else:
        ds = by_id[previous_ds]
        rest = [p for p in eligible if p["satelliteId"] != ds["satelliteId"]]
        bds = by_id.get(previous_bds) or (rest[0] if rest else None)
        decision = "incumbent kept, election is non-preemptive"

    stamp = dbmod.now_iso()
    changed = (ds["satelliteId"] if ds else None) != previous_ds or (bds["satelliteId"] if bds else None) != previous_bds
    excluded = "; ".join(f"{p['name']} {p['excluded']}" for p in ineligible)

    dbmod.log(
        conn, "INFO", "ospf", f"net {net['name']}",
        f"DS/BDS election reason={reason} preemptive={str(preemptive).lower()}"
        f" peers={len(eligible) + len(ineligible)} candidates={len(eligible)} excluded=[{excluded}]",
    )
    dbmod.log(
        conn, "INFO" if ds else "WARN", "ospf", f"net {net['name']}",
        f"DS={describe(ds)} BDS={describe(bds)} decision={decision}"
        + (f" previous DS={previous_ds or 'none'} BDS={previous_bds or 'none'}" if changed else " (no change)"),
    )
    ledger = {
        "netId": net_id,
        "reason": reason,
        "preemptive": preemptive,
        "decision": decision,
        "changed": changed,
        "ds": ds,
        "bds": bds,
        "candidates": eligible,
        "excluded": ineligible,
        "electedAt": stamp,
    }
    conn.execute(
        "INSERT INTO elections (net_id, ds_id, bds_id, reason, ledger, elected_at) VALUES (?,?,?,?,?,?)",
        (net_id, ds["satelliteId"] if ds else None, bds["satelliteId"] if bds else None, reason, json.dumps(ledger), stamp),
    )
    return ledger


def form_adjacency(conn, net_id: str, satellite: dict, priority: int) -> None:
    """Log the OSPF handshake that brings an adjacency up to FULL."""
    net = net_row(conn, net_id)
    source = f"net {net['name']}"
    who = f"{satellite['name']}({satellite['id'][:8]})"
    dbmod.log(conn, "INFO", "ospf", source, f"peer {who} configured priority={priority} hello={net['hello_interval_s']}s dead={net['dead_interval_s']}s")
    dbmod.log(conn, "INFO", "ospf", source, f"{who} state DOWN->INIT (1-way HELLO received)")
    dbmod.log(conn, "INFO", "ospf", source, f"{who} state INIT->2_WAY (2-way communication confirmed)")
    dbmod.log(conn, "INFO", "ospf", source, f"{who} DBD exchange: master, 12 LSAs described, 0 retransmits")
    dbmod.log(conn, "INFO", "ospf", source, f"{who} LSU/LSAck: 3 router-LSA 5 network-LSA exchanged, state 2_WAY->FULL")


def drop_adjacency(conn, net_id: str, satellite: dict, reason: str) -> None:
    net = net_row(conn, net_id)
    dbmod.log(conn, "WARN", "ospf", f"net {net['name']}", f"{satellite['name']}({satellite['id'][:8]}) adjacency DOWN ({reason})")


def hold_time(dead_interval_s: int, last_hello_at: str) -> float | None:
    """Seconds a neighbor has left before its adjacency is declared dead, like an OSPF hold time."""
    age = clock.age_of(last_hello_at)
    return None if age is None else round(int(dead_interval_s) - age, 1)


def expire_stale(conn, net) -> list[dict]:
    """Apply the net's dead timer against the system clock instead of running timers of our own.

    Called before anything reads or changes a net, so a peer that stopped answering hellos is down by
    the time anyone looks. Returns the peers that were dropped; a drop re-runs the DS/BDS election.
    """
    dead = int(net["dead_interval_s"])
    dropped = []
    for row in conn.execute("SELECT * FROM adjacencies WHERE net_id = ? AND state <> 'DOWN'", (net["id"],)).fetchall():
        left = hold_time(dead, row["last_hello_at"])
        if left is None or left > 0:
            continue
        satellite = conn.execute("SELECT id, name FROM satellites WHERE id = ?", (row["satellite_id"],)).fetchone()
        if not satellite:
            continue
        conn.execute("UPDATE adjacencies SET state = 'DOWN' WHERE id = ?", (row["id"],))
        drop_adjacency(conn, net["id"], dict(satellite), f"no hello for {int(dead - left)}s, dead interval is {dead}s")
        dropped.append({"satelliteId": row["satellite_id"], "priority": row["priority"], "helloAgeS": round(dead - left, 1)})
    if dropped:
        run_election(conn, net["id"], "DEAD_INTERVAL")
    return dropped
