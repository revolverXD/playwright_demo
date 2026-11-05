"""The service follows the host system clock: real timestamps, and OSPF dead timers really expire."""

import time
from ast import literal_eval
from datetime import datetime, timezone

from conftest import run_offline


def local_now() -> datetime:
    return datetime.now(timezone.utc)


def moment(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def test_the_service_reads_the_system_clock(api):
    body = api.get("/api/v1/clock").json()
    assert body["source"] == "system-utc" and body["tokenTtlS"] == 172800
    assert abs((moment(body["now"]) - local_now()).total_seconds()) < 5
    assert moment(body["serviceStartedAt"]) <= local_now() and body["uptimeS"] >= 0


def test_the_clock_never_runs_backwards(api):
    first, second = api.get("/api/v1/clock").json(), api.get("/api/v1/clock").json()
    assert moment(second["now"]) >= moment(first["now"])
    assert second["uptimeS"] >= first["uptimeS"]


def test_health_and_the_activity_log_use_the_same_clock(api, make_site):
    assert abs((moment(api.get("/health").json()["time"]) - local_now()).total_seconds()) < 5

    site = make_site()
    api.post(f"/api/v1/sites/{site['siteId']}/metrics", json={"healthScore": 0.8})
    newest = api.get("/api/v1/logs", params={"search": site["designation"], "limit": 1}).json()["lines"][-1]
    assert abs((moment(newest.split()[0]) - local_now()).total_seconds()) < 5


def test_the_seeded_neighbor_table_is_alive(api):
    net = api.get("/api/v1/relay-nets/net-belt-1").json()["relayNet"]
    assert net["deadIntervalS"] == 40
    for peer in net["adjacencies"]:
        assert peer["state"] == "FULL" and peer["helloAgeS"] < 60 and 0 < peer["holdTimeS"] <= 40


def test_an_older_databases_frozen_timers_are_put_back_on_the_real_clock(tmp_path):
    # databases written before this change kept the sample dates in the OSPF timer columns
    script = "\n".join(
        [
            "from app import db",
            "db.init_db()",
            "c = db.connect()",
            "c.execute(\"UPDATE adjacencies SET last_hello_at = '2035-06-11T14:03:41Z'\"); c.commit(); c.close()",
            "db.init_db()",
            "c = db.connect()",
            "print(sorted({r[0][:4] for r in c.execute('SELECT last_hello_at FROM adjacencies')}))",
        ]
    )
    years = literal_eval(run_offline(script, tmp_path / "old.db").strip().splitlines()[-1])
    assert years == [str(datetime.now(timezone.utc).year)]


def test_a_peer_that_stops_answering_hellos_dies_on_the_dead_interval(api, make_net, make_satellite):
    net_id = make_net(name="TEST-NET-DEAD-TIMER", helloIntervalS=1, deadIntervalS=2)
    satellite_id = make_satellite(name="TEST-RELAY-DEAD-TIMER")
    assert api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": satellite_id, "priority": 100}).status_code == 201

    def seen():
        return api.get(f"/api/v1/relay-nets/{net_id}/neighbors").json()

    assert seen()["ds"] and 0 < seen()["neighbors"][0]["holdTimeS"] <= 2

    time.sleep(1.2)
    refreshed = api.post(f"/api/v1/relay-nets/{net_id}/peers/{satellite_id}/hello").json()
    assert refreshed["state"] == "FULL", refreshed
    assert refreshed["reformedFrom"] is None, refreshed
    assert refreshed["holdTimeS"] > 1.5, refreshed  # the hello restarted the timer
    assert seen()["neighbors"][0]["holdTimeS"] > 1.5, seen()

    time.sleep(2.4)
    dead = seen()
    assert dead["neighbors"][0]["state"] == "DOWN" and dead["ds"] is None and dead["bds"] is None
    reasons = [e["reason"] for e in api.get(f"/api/v1/relay-nets/{net_id}/elections").json()["elections"]]
    assert "DEAD_INTERVAL" in reasons and "ADJACENCY_REFORMED" not in reasons
    dropped = api.get("/api/v1/logs", params={"category": "ospf", "search": "no hello", "limit": 1}).json()["lines"]
    assert any("no hello for" in line and "dead interval is 2s" in line for line in dropped)

    back = api.post(f"/api/v1/relay-nets/{net_id}/peers/{satellite_id}/hello").json()
    assert back["state"] == "FULL" and back["reformedFrom"] == "DOWN" and back["election"]["ds"]
    assert seen()["ds"] and seen()["neighbors"][0]["holdTimeS"] > 0.5
