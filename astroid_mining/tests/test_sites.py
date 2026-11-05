"""Mining sites: registering, telemetry reporting, uplinks and relay failover."""

from conftest import COLD_RELAY, RELAY, RELAY_BACKUP, SITE, SITE_BASE

SURVEY_SITE = "0d6b7a48-2f91-4c3d-84ae-91e5f7b0c2d6"


def test_mining_sites_are_listed_with_live_summary(api):
    body = api.get("/api/v1/sites").json()
    assert body["count"] >= 3
    by_id = {s["id"]: s for s in body["sites"]}

    site = by_id[SITE]
    assert site["name"] == "PSYCHE-DRILL-02"
    assert site["designation"] == "PSYCHE-SW-04"
    assert site["hostBody"] == "(4124) Orvar-SW"
    assert site["summary"] == {
        "temperatureC": 19.8,
        "exteriorTempC": -68.2,
        "productionRateTph": 41.2,
        "rawOreStockTons": 18410.0,
        "refinedStockTons": 6204.5,
    }
    assert set(site["relays"]) >= {RELAY, RELAY_BACKUP, COLD_RELAY}
    assert by_id[SURVEY_SITE]["summary"]["productionRateTph"] is None


def test_site_document_carries_host_body_zones_and_fleet(api):
    base = api.get(f"/api/v1/sites/{SITE}").json()["baseStation"]
    assert base["id"] == SITE_BASE
    assert base["siteRef"]["hostBody"]["estimatedNiFeGradePct"] == 41.7
    assert base["siteRef"]["hostBody"]["surfaceGravityMs2"] == 0.000148
    assert len(base["zones"]) == 3
    assert base["surfaceLocation"]["latitudeDeg"] == -38.412
    assert [a["state"] for a in base["surfaceLocation"]["anchorPoints"]].count("DEGRADED") == 1
    seeded = [l for l in base["satelliteLinks"]["links"] if l["satelliteId"] in {RELAY, RELAY_BACKUP, COLD_RELAY}]
    assert [l["role"] for l in seeded] == ["PRIMARY", "SECONDARY", "COLD_STANDBY"]
    assert len(base["fleet"]["roster"]) == 4
    assert {r["state"] for r in base["fleet"]["roster"]} == {"ACTIVE", "CHARGING", "RETURNING"}


def test_mining_site_reports_temperature_production_and_stock(api, make_site):
    site = make_site(
        metrics={
            "healthScore": 0.8,
            "thermal": {"coreTempC": 15.0, "exteriorTempC": -70.0},
            "excavation": {"sintererOutputTph": 10.0},
            "inventory": {"rawOreOnSiteTons": 100.0, "refinedMetalTons": 5.0},
        }
    )["siteId"]

    pushed = api.post(
        f"/api/v1/sites/{site}/metrics",
        json={
            "thermal": {"coreTempC": 24.5},
            "excavation": {"sintererOutputTph": 47.5},
            "inventory": {"rawOreOnSiteTons": 980.0, "refinedMetalTons": 210.0},
        },
    )
    assert pushed.status_code == 201

    metrics = api.get(f"/api/v1/sites/{site}/metrics").json()
    assert metrics["summary"] == {
        "temperatureC": 24.5,
        "exteriorTempC": -70.0,
        "productionRateTph": 47.5,
        "rawOreStockTons": 980.0,
        "refinedStockTons": 210.0,
    }
    assert metrics["metrics"]["healthScore"] == 0.8


def test_metric_history_of_a_site_is_queryable(api):
    api.post(f"/api/v1/sites/{SITE}/metrics", json={"inventory": {"rawOreOnSiteTons": 19000.0}})
    history = api.get(f"/api/v1/sites/{SITE}/metrics", params={"history": 3}).json()["history"]
    assert len(history) >= 2
    assert history[0]["inventory"]["rawOreOnSiteTons"] == 19000.0
    assert all("thermal" in snapshot for snapshot in history)
    assert api.get(f"/api/v1/sites/{SITE}/metrics", params={"history": 999}).status_code == 422


def test_new_site_can_be_registered(api):
    created = api.post(
        "/api/v1/sites",
        json={"name": "VESTA-PIT-07", "designation": "VESTA-W-07", "hostBody": "(4) Vesta-W", "status": "INTEGRATING"},
    )
    assert created.status_code == 201
    site_id = created.json()["siteId"]
    assert api.get(f"/api/v1/sites/{site_id}").json()["baseStation"]["siteRef"]["designation"] == "VESTA-W-07"

    assert api.post("/api/v1/sites", json={"id": site_id, "name": "X", "designation": "DUP"}).status_code == 409
    assert api.post("/api/v1/sites", json={"name": "no designation"}).status_code == 422


def test_uplink_can_be_established_and_dropped(api, make_site, make_satellite):
    site_id = make_site()["siteId"]
    relay = make_satellite()

    established = api.post(f"/api/v1/sites/{site_id}/uplink", json={"satelliteId": relay, "role": "PRIMARY", "band": "Ka"})
    assert established.status_code == 201
    assert established.json()["status"] == "ESTABLISHED"

    links = api.get(f"/api/v1/sites/{site_id}/links").json()
    assert links["count"] == 1
    assert links["uplink"]["satelliteId"] == relay
    assert links["uplink"]["band"] == "Ka"

    assert api.post(f"/api/v1/sites/{site_id}/uplink", json={"satelliteId": relay}).status_code == 409
    assert api.post(f"/api/v1/sites/{site_id}/uplink", json={"satelliteId": "no-relay"}).status_code == 404
    assert api.post(f"/api/v1/sites/no-site/uplink", json={"satelliteId": relay}).status_code == 404

    assert api.delete(f"/api/v1/sites/{site_id}/uplink/{relay}").status_code == 200
    after = api.get(f"/api/v1/sites/{site_id}/links").json()
    assert after["count"] == 0 and after["uplink"] is None
    assert api.delete(f"/api/v1/sites/{site_id}/uplink/{relay}").status_code == 404


def test_a_site_keeps_only_one_primary_relay(api, make_site, make_satellite):
    site_id = make_site()["siteId"]
    first, second = make_satellite(), make_satellite()
    api.post(f"/api/v1/sites/{site_id}/uplink", json={"satelliteId": first, "role": "PRIMARY"})

    refused = api.post(f"/api/v1/sites/{site_id}/uplink", json={"satelliteId": second, "role": "PRIMARY"})
    assert refused.status_code == 409
    assert second not in [l["satelliteId"] for l in api.get(f"/api/v1/sites/{site_id}/links").json()["links"]]

    assert api.post(f"/api/v1/sites/{site_id}/uplink", json={"satelliteId": second, "role": "SECONDARY"}).status_code == 201


def test_failover_moves_the_primary_role_to_a_backup(api, make_site, make_satellite):
    site_id = make_site()["siteId"]
    primary, backup = make_satellite(), make_satellite()
    api.post(f"/api/v1/sites/{site_id}/uplink", json={"satelliteId": primary, "role": "PRIMARY"})
    api.post(f"/api/v1/sites/{site_id}/uplink", json={"satelliteId": backup, "role": "COLD_STANDBY"})

    result = api.post(f"/api/v1/sites/{site_id}/links/failover").json()
    assert result["failedOverFrom"] == primary
    assert result["failedOverTo"] == backup
    assert {l["role"] for l in result["links"]} == {"SECONDARY", "PRIMARY"}
    assert next(l for l in result["links"] if l["satelliteId"] == backup)["status"] == "ESTABLISHED"

    # the demoted relay is still usable, so a second failover hands the primary role back
    back = api.post(f"/api/v1/sites/{site_id}/links/failover").json()
    assert back["failedOverTo"] == primary


def test_failover_needs_a_backup(api, make_site, make_satellite):
    site_id = make_site()["siteId"]
    api.post(f"/api/v1/sites/{site_id}/uplink", json={"satelliteId": make_satellite(), "role": "PRIMARY"})
    assert api.post(f"/api/v1/sites/{site_id}/links/failover").status_code == 409
    assert api.post(f"/api/v1/sites/no-site/links/failover").status_code == 404


def test_unknown_site_is_404_everywhere(api):
    for path in [
        "/api/v1/sites/no-site",
        "/api/v1/sites/no-site/metrics",
        "/api/v1/sites/no-site/links",
        "/api/v1/sites/no-site/robots",
    ]:
        assert api.get(path).status_code == 404
