"""The robot fleet: registration, telemetry, and start/stop/pause telecommands."""

from conftest import ROBOT_ACTIVE, ROBOT_FAULT, SITE

ZONE = "0f7c2a91-6d3b-4e28-9c47-58ba1e0d3f66"


def test_site_robots_are_listed_with_state_counts(api):
    body = api.get(f"/api/v1/sites/{SITE}/robots").json()
    assert body["count"] >= 4
    assert body["byState"] == {"ACTIVE": 2, "CHARGING": 1, "RETURNING": 1}
    dogge = next(r for r in body["robots"] if r["designation"] == "DOGGE-01")
    assert dogge["class"] == "HEAVY_EXCAVATOR"
    assert dogge["zoneId"] == ZONE
    assert dogge["batteryPct"] == 62.4


def test_robots_can_be_filtered(api):
    by_site = api.get("/api/v1/robots", params={"siteId": SITE}).json()
    assert all(r["siteId"] == SITE for r in by_site["robots"])
    active = api.get("/api/v1/robots", params={"siteId": SITE, "state": "ACTIVE"}).json()
    assert {r["designation"] for r in active["robots"]} == {"DOGGE-01", "EYE-02"}
    assert api.get("/api/v1/robots", params={"state": "NOT_A_STATE"}).json()["robots"] == []


def test_robot_document_carries_task_power_and_safety_state(api):
    robot = api.get(f"/api/v1/robots/{ROBOT_ACTIVE}").json()["robot"]
    assert robot["designation"] == "DOGGE-01"
    assert robot["state"] == "ACTIVE"
    assert robot["ownership"]["siteId"] == SITE
    assert robot["platform"]["energyCapacityKwh"] == 96.0
    assert robot["metrics"]["tasking"]["taskType"] == "CUT_BENCH"
    assert robot["metrics"]["tasking"]["tonsMoved"] == 1974.0
    assert robot["metrics"]["thermal"]["gearboxTempC"] == 48.9
    assert robot["metrics"]["power"]["batteryPct"] == 62.4
    assert robot["geofence"]["maxDistanceFromBaseM"] == 8000.0


def test_work_commands_move_the_robot_through_its_state_machine(api, make_robot):
    robot_id = make_robot(state="IDLE")

    assert api.post(f"/api/v1/robots/{robot_id}/command", json={"action": "START"}).json()["state"] == "ACTIVE"
    assert api.post(f"/api/v1/robots/{robot_id}/command", json={"action": "PAUSE"}).json()["state"] == "PAUSED"
    assert api.post(f"/api/v1/robots/{robot_id}/command", json={"action": "RESUME"}).json()["state"] == "ACTIVE"
    stopped = api.post(f"/api/v1/robots/{robot_id}/command", json={"action": "STOP", "issuedBy": "ops-lead"})
    assert stopped.json()["previousState"] == "ACTIVE" and stopped.json()["state"] == "STOPPED"

    assert api.get(f"/api/v1/robots/{robot_id}").json()["robot"]["state"] == "STOPPED"


def test_impossible_commands_are_refused_with_the_current_state(api, make_robot):
    robot_id = make_robot(state="IDLE")

    refused = api.post(f"/api/v1/robots/{robot_id}/command", json={"action": "PAUSE"})
    assert refused.status_code == 409
    assert "PAUSE not allowed from state IDLE" in refused.json()["detail"]

    api.post(f"/api/v1/robots/{robot_id}/command", json={"action": "START"})
    assert api.post(f"/api/v1/robots/{robot_id}/command", json={"action": "START"}).status_code == 409
    assert api.post(f"/api/v1/robots/{robot_id}/command", json={"action": "RESUME"}).status_code == 409

    # a faulted robot is grounded: telecommands cannot bring it back
    assert "START not allowed from state FAULT" in api.post(f"/api/v1/robots/{ROBOT_FAULT}/command", json={"action": "START"}).json()["detail"]
    assert api.post(f"/api/v1/robots/{ROBOT_FAULT}/command", json={"action": "STOP"}).status_code == 409


def test_commands_are_audited_per_robot(api, make_robot):
    robot_id = make_robot(state="IDLE")
    api.post(f"/api/v1/robots/{robot_id}/command", json={"action": "START", "issuedBy": "base-orchestrator", "note": "shift start"})
    api.post(f"/api/v1/robots/{robot_id}/command", json={"action": "STOP", "issuedBy": "safety-officer", "note": "seismic trip"})

    log = api.get(f"/api/v1/robots/{robot_id}/commands").json()
    assert log["count"] == 2
    newest, oldest = log["commands"]
    assert (oldest["action"], oldest["previousState"], oldest["state"]) == ("START", "IDLE", "ACTIVE")
    assert oldest["issuedBy"] == "base-orchestrator" and oldest["note"] == "shift start"
    assert (newest["action"], newest["previousState"], newest["state"]) == ("STOP", "ACTIVE", "STOPPED")
    assert newest["issuedBy"] == "safety-officer"


def test_a_whole_site_can_be_ordered_to_stop(api, make_site, make_robot):
    site_id = make_site()["siteId"]
    for name in ("HAULER-A", "HAULER-B"):
        make_robot(site_id=site_id, designation=name, state="ACTIVE")

    result = api.post(f"/api/v1/sites/{site_id}/robots/command", json={"action": "STOP", "issuedBy": "fleet-orchestrator"}).json()
    assert len(result["accepted"]) == 2
    assert result["rejected"] == []
    assert api.get(f"/api/v1/sites/{site_id}/robots").json()["byState"] == {"STOPPED": 2}

    pause = api.post(f"/api/v1/sites/{site_id}/robots/command", json={"action": "PAUSE"}).json()
    assert pause["accepted"] == []
    assert {r["reason"] for r in pause["rejected"]} == {"PAUSE not allowed from state STOPPED"}


def test_robot_telemetry_updates_battery_and_health(api, make_site, make_robot):
    site_id = make_site()["siteId"]
    robot_id = make_robot(site_id=site_id, batteryPct=88.0, healthPct=90.0)

    pushed = api.post(
        f"/api/v1/robots/{robot_id}/metrics",
        json={"healthScore": 0.42, "power": {"batteryPct": 9.5}, "thermal": {"coreTempC": 51.0}},
    )
    assert pushed.status_code == 201

    listed = api.get("/api/v1/robots", params={"siteId": site_id}).json()["robots"][0]
    assert listed["batteryPct"] == 9.5
    assert listed["healthPct"] == 42.0

    robot = api.get(f"/api/v1/robots/{robot_id}").json()["robot"]
    assert robot["metrics"]["power"]["batteryPct"] == 9.5
    assert robot["metrics"]["thermal"]["coreTempC"] == 51.0
    history = api.get(f"/api/v1/robots/{robot_id}/metrics", params={"history": 5}).json()["history"]
    assert len(history) == 2 and history[1]["power"]["batteryPct"] == 88.0


def test_registering_robots_is_validated(api, make_site):
    site_id = make_site()["siteId"]
    created = api.post(
        "/api/v1/robots",
        json={"designation": "NEW-DOGG", "class": "MAINTENANCE", "siteId": site_id, "zoneId": "zone-9", "batteryPct": 40},
    )
    assert created.status_code == 201
    robot_id = created.json()["robotId"]
    assert api.get(f"/api/v1/robots/{robot_id}").json()["robot"]["state"] == "IDLE"

    assert api.post("/api/v1/robots", json={"id": robot_id, "designation": "DUP", "class": "HAULER", "siteId": site_id}).status_code == 409
    assert api.post("/api/v1/robots", json={"designation": "no class", "siteId": site_id}).status_code == 422
    assert api.post("/api/v1/robots", json={"designation": "bad site", "class": "HAULER", "siteId": "no-site"}).status_code == 404
    assert api.post("/api/v1/robots", json={"designation": "bad state", "class": "HAULER", "siteId": site_id, "state": "ASLEEP"}).status_code == 422
    assert api.post(f"/api/v1/robots/no-robot/command", json={"action": "START"}).status_code == 404
    assert api.post(f"/api/v1/robots/{robot_id}/command", json={"action": "SPIN"}).status_code == 422
