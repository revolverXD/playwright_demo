"""Comms satellites: registration, metrics, connecting to sites, backups."""

from conftest import COLD_RELAY, GROUND_RELAY, RELAY, RELAY_BACKUP, ROBOT_ACTIVE, SITE

SEED_RELAYS = {"HEPHAESTUS-7", "RELAY-NODE-4", "DSN-CERES", "VESTA-COLD-1"}


def test_seeded_relays_are_listed(api):
    body = api.get("/api/v1/satellites").json()
    assert body["schemaVersion"] == "1.5.0"
    assert body["count"] >= 4
    assert {s["name"] for s in body["satellites"]} >= SEED_RELAYS
    relay = next(s for s in body["satellites"] if s["id"] == RELAY)
    assert relay["status"] == "OPERATIONAL"
    assert relay["healthScore"] == 0.94
    assert relay["connectedSites"] >= 2


def test_relays_can_be_filtered_by_status(api):
    body = api.get("/api/v1/satellites", params={"status": "STANDBY"}).json()
    assert COLD_RELAY in [s["id"] for s in body["satellites"]]
    assert all(s["status"] == "STANDBY" for s in body["satellites"])
    assert api.get("/api/v1/satellites", params={"status": "NOT_A_STATUS"}).status_code == 422


def test_relay_document_matches_the_fleet_schema(api):
    satellite = api.get(f"/api/v1/satellites/{RELAY}").json()["satellite"]
    assert satellite["id"] == RELAY
    assert satellite["name"] == "HEPHAESTUS-7"
    assert satellite["orbit"]["referenceFrame"] == "SUN_ECLIPTIC"
    assert satellite["orbit"]["semiMajorAxisKm"] == 412500000
    assert "robot-telemetry-gateway" in satellite["tags"]
    assert {s["siteId"] for s in satellite["miningSites"]} >= {SITE}
    primary = next(s for s in satellite["miningSites"] if s["siteId"] == SITE)
    assert primary["role"] == "PRIMARY"
    assert primary["sharePct"] == 62.0
    assert ROBOT_ACTIVE in primary["robotIds"]
    assert sorted(satellite["backups"]["satelliteIds"]) == sorted([RELAY_BACKUP, GROUND_RELAY, COLD_RELAY])
    assert satellite["backups"]["failoverThresholdHealth"] == 0.65


def test_relay_reports_its_own_telemetry(api):
    metrics = api.get(f"/api/v1/satellites/{RELAY}/metrics").json()["metrics"]
    assert metrics["power"]["arrayOutputKw"] == 118.4
    assert metrics["thermal"]["coreTempC"] == 22.4
    assert metrics["thermal"]["maxAllowedC"] == 85.0
    assert metrics["comms"]["downlinkMbps"] == 480.0
    assert metrics["anomalies"]["openCount"] == 2


def test_register_new_relay_rejects_duplicates_and_bad_input(api):
    created = api.post(
        "/api/v1/satellites",
        json={
            "name": "NEW-RELAY-A",
            "model": "HR-Mining Relay Mk IV",
            "serialNumber": "HRM4-1001",
            "status": "INTEGRATING",
            "orbit": {"referenceFrame": "SUN_ECLIPTIC", "semiMajorAxisKm": 4.0e8},
            "metrics": {"healthScore": 0.99, "thermal": {"coreTempC": 18.0}},
        },
    )
    assert created.status_code == 201
    satellite_id = created.json()["satelliteId"]

    listing = api.get("/api/v1/satellites").json()
    assert any(s["id"] == satellite_id and s["status"] == "INTEGRATING" for s in listing["satellites"])

    assert api.post("/api/v1/satellites", json={"id": satellite_id, "name": "CLONE"}).status_code == 409
    assert api.post("/api/v1/satellites", json={"model": "no name"}).status_code == 422
    assert api.post("/api/v1/satellites", json={"name": "BAD", "status": "SPINNING"}).status_code == 422


def test_relay_metrics_update_merges_and_keeps_history(api):
    satellite_id = api.post(
        "/api/v1/satellites",
        json={"name": "MERGE-RELAY", "metrics": {"healthScore": 0.9, "thermal": {"coreTempC": 20.0, "radiatorTempC": -10.0}}},
    ).json()["satelliteId"]

    accepted = api.post(
        f"/api/v1/satellites/{satellite_id}/metrics",
        json={"healthScore": 0.61, "thermal": {"coreTempC": 44.5}, "comms": {"downlinkMbps": 0.0}},
    )
    assert accepted.status_code == 201

    body = api.get(f"/api/v1/satellites/{satellite_id}/metrics", params={"history": 5}).json()
    assert body["metrics"]["healthScore"] == 0.61
    assert body["metrics"]["thermal"] == {"coreTempC": 44.5, "radiatorTempC": -10.0}
    assert body["metrics"]["comms"]["downlinkMbps"] == 0.0
    assert len(body["history"]) == 2
    assert body["history"][0]["healthScore"] == 0.61 and body["history"][1]["healthScore"] == 0.9

    assert api.post(f"/api/v1/satellites/{satellite_id}/metrics", json={}).status_code == 400


def test_register_relay_and_connect_it_to_every_site(api, make_satellite):
    satellite_id = make_satellite()
    sites = api.get("/api/v1/sites").json()["sites"]

    result = api.post(f"/api/v1/satellites/{satellite_id}/connections", json={"siteIds": "all", "role": "SECONDARY", "band": "X"}).json()
    assert {c["siteId"] for c in result["connected"]} == {s["id"] for s in sites}
    assert result["skipped"] == []

    links = api.get(f"/api/v1/satellites/{satellite_id}/links").json()
    assert links["count"] == len(sites)
    assert all(link["status"] == "ESTABLISHED" and link["role"] == "SECONDARY" for link in links["links"])

    again = api.post(f"/api/v1/satellites/{satellite_id}/connections", json={"siteIds": "all"}).json()
    assert again["connected"] == []
    assert {s["siteId"] for s in again["skipped"]} == {s["id"] for s in sites}
    assert "already exists" in again["skipped"][0]["reason"]


def test_register_relay_and_connect_it_to_only_some_sites(api, make_satellite):
    satellite_id = make_satellite()
    sites = [s["id"] for s in api.get("/api/v1/sites").json()["sites"]][:2]

    result = api.post(f"/api/v1/satellites/{satellite_id}/connections", json={"siteIds": sites, "role": "SECONDARY"}).json()
    assert {c["siteId"] for c in result["connected"]} == set(sites)

    only = api.get(f"/api/v1/satellites/{satellite_id}/links").json()
    assert {link["siteId"] for link in only["links"]} == set(sites)


def test_connecting_a_second_primary_relay_is_refused(api, make_satellite, make_site):
    site_id = make_site()["siteId"]
    first = make_satellite()
    second = make_satellite()
    api.post(f"/api/v1/satellites/{first}/connections", json={"siteIds": [site_id], "role": "PRIMARY"})

    result = api.post(f"/api/v1/satellites/{second}/connections", json={"siteIds": [site_id], "role": "PRIMARY"}).json()
    assert result["connected"] == []
    assert result["skipped"][0]["reason"] == f"primary relay already held by {first}"


def test_new_relay_can_be_designated_as_backup(api, make_satellite):
    satellite_id = make_satellite()
    designated = api.post(
        f"/api/v1/satellites/{satellite_id}/backups",
        json={"backupOf": RELAY, "policy": "HOT_STANDBY_ROUND_ROBIN", "failoverThresholdHealth": 0.5},
    )
    assert designated.status_code == 201

    satellite = api.get(f"/api/v1/satellites/{RELAY}").json()["satellite"]
    assert satellite_id in satellite["backups"]["satelliteIds"]
    assert api.get(f"/api/v1/satellites/{satellite_id}").json()["satellite"]["backups"]["servesAsBackupOf"] == [RELAY]

    assert api.post(f"/api/v1/satellites/{satellite_id}/backups", json={"backupOf": RELAY}).status_code == 409
    assert api.post(f"/api/v1/satellites/{satellite_id}/backups", json={"backupOf": satellite_id}).status_code == 400
    assert api.post(f"/api/v1/satellites/{satellite_id}/backups", json={"backupOf": "no-such-relay"}).status_code == 404
    assert api.post(f"/api/v1/satellites/{RELAY}/backups", json={"backupOf": RELAY}).status_code == 400


def test_going_offline_degrades_the_links_it_serves(api, make_satellite, make_site):
    satellite_id = make_satellite()
    site_id = make_site()["siteId"]
    api.post(f"/api/v1/sites/{site_id}/uplink", json={"satelliteId": satellite_id, "role": "PRIMARY"})

    result = api.patch(f"/api/v1/satellites/{satellite_id}/status", params={"status": "OFFLINE"}).json()
    assert result["status"] == "OFFLINE"
    assert result["degradedLinks"][0]["status"] == "DEGRADED"
    assert api.get(f"/api/v1/sites/{site_id}/links").json()["links"][0]["status"] == "DEGRADED"

    assert api.patch(f"/api/v1/satellites/{satellite_id}/status", params={"status": "MELTED"}).status_code == 422


def test_disconnecting_a_site_removes_the_link(api, make_satellite, make_site):
    satellite_id = make_satellite()
    site_id = make_site()["siteId"]
    api.post(f"/api/v1/satellites/{satellite_id}/connections", json={"siteIds": [site_id]})

    assert api.delete(f"/api/v1/satellites/{satellite_id}/connections/{site_id}").status_code == 200
    assert api.get(f"/api/v1/sites/{site_id}/links").json()["count"] == 0
    assert api.delete(f"/api/v1/satellites/{satellite_id}/connections/{site_id}").status_code == 404


def test_unknown_relay_is_404_everywhere(api):
    for path in ["/api/v1/satellites/nope", "/api/v1/satellites/nope/metrics", "/api/v1/satellites/nope/links"]:
        assert api.get(path).status_code == 404
    assert api.post("/api/v1/satellites/nope/connections", json={"siteIds": "all"}).status_code == 404
    assert api.post("/api/v1/satellites/nope/metrics", json={"healthScore": 1.0}).status_code == 404
