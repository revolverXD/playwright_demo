"""Telemetry reports pushed from a mining site up to a relay."""

import uuid

from conftest import RELAY, SEED_REPORT, SITE, SITE_BASE


def report_body(site_id, base_station_id, satellite_id, **overrides):
    body = {
        "schema": "base.telemetry.report.v1",
        "senderId": base_station_id,
        "siteId": site_id,
        "recipientSatelliteId": satellite_id,
        "priority": "PRODUCTION",
        "seq": 104_883,
        "payload": {
            "healthScore": 0.88,
            "production": {"refinedTonsLastHour": 41.2, "oreIntakeTonsLastHour": 96.5, "fleetActiveCount": 2},
            "criticalAlerts": [{"code": "ANCHOR_03_HOLD_LOW", "severity": "MAJOR", "suggestedAction": "RE_ANCHOR_OR_RELOCATE"}],
            "robotDelta": [{"robotId": "8a2f6d31-5b04-4c97-9a8e-1d6c4f7b20e5", "state": "ACTIVE", "batteryPct": 62.4}],
        },
    }
    body.update(overrides)
    return body


def test_site_pushes_a_production_report_to_its_relay(api, make_site, make_satellite):
    site = make_site()
    relay = make_satellite()
    api.post(f"/api/v1/sites/{site['siteId']}/uplink", json={"satelliteId": relay, "role": "PRIMARY"})

    accepted = api.post("/api/v1/reports", json=report_body(site["siteId"], site["baseStationId"], relay))
    assert accepted.status_code == 201
    report_id = accepted.json()["reportId"]
    assert accepted.json()["link"]["missedReports"] == 0
    assert accepted.json()["link"]["lastReportAt"]

    fetched = api.get(f"/api/v1/reports/{report_id}").json()
    assert fetched["schema"] == "base.telemetry.report.v1"
    assert fetched["priority"] == "PRODUCTION"
    assert fetched["payload"]["production"]["refinedTonsLastHour"] == 41.2
    assert fetched["payload"]["criticalAlerts"][0]["code"] == "ANCHOR_03_HOLD_LOW"

    uplink = api.get(f"/api/v1/sites/{site['siteId']}/links").json()["uplink"]
    assert uplink["lastReportAt"] and uplink["missedReports"] == 0


def test_a_relayed_report_is_stamped_as_received(api):
    body = api.get(f"/api/v1/reports/{SEED_REPORT}").json()
    assert body["siteId"] == SITE
    assert body["recipientSatelliteId"] == RELAY
    assert body["seq"] == 104882
    assert body["generatedAt"] == "2035-06-11T14:03:41Z"
    assert body["acceptedAt"]


def test_reports_can_be_listed_and_filtered(api, make_site, make_satellite):
    site = make_site()
    relay_a, relay_b = make_satellite(), make_satellite()
    for relay, priority in ((relay_a, "SAFETY"), (relay_b, "RAW_TELEMETRY")):
        api.post(f"/api/v1/sites/{site['siteId']}/uplink", json={"satelliteId": relay, "role": "SECONDARY" if priority == "SAFETY" else "SURVEY"})
        api.post(
            "/api/v1/reports",
            json=report_body(site["siteId"], site["baseStationId"], relay, priority=priority, reportId=str(uuid.uuid4())),
        )

    by_site = api.get("/api/v1/reports", params={"siteId": site["siteId"]}).json()
    assert by_site["count"] == 2
    assert {r["priority"] for r in by_site["reports"]} == {"SAFETY", "RAW_TELEMETRY"}

    only_safety = api.get("/api/v1/reports", params={"siteId": site["siteId"], "priority": "SAFETY"}).json()
    assert [r["priority"] for r in only_safety["reports"]] == ["SAFETY"]
    assert only_safety["reports"][0]["recipientSatelliteId"] == relay_a

    by_relay = api.get("/api/v1/reports", params={"satelliteId": relay_b}).json()
    assert [r["reportId"] for r in by_relay["reports"]] and all(r["recipientSatelliteId"] == relay_b for r in by_relay["reports"])
    assert api.get("/api/v1/reports", params={"siteId": site["siteId"], "limit": 1}).json()["count"] == 1


def test_a_report_cannot_be_ingested_twice(api, make_site, make_satellite):
    site = make_site()
    relay = make_satellite()
    api.post(f"/api/v1/sites/{site['siteId']}/uplink", json={"satelliteId": relay, "role": "PRIMARY"})
    report_id = str(uuid.uuid4())

    first = api.post("/api/v1/reports", json=report_body(site["siteId"], site["baseStationId"], relay, reportId=report_id))
    assert first.status_code == 201
    duplicate = api.post("/api/v1/reports", json=report_body(site["siteId"], site["baseStationId"], relay, reportId=report_id))
    assert duplicate.status_code == 409
    assert "already ingested" in duplicate.json()["detail"]


def test_a_site_without_an_uplink_cannot_report(api, make_site, make_satellite):
    site = make_site()
    relay = make_satellite()

    refused = api.post("/api/v1/reports", json=report_body(site["siteId"], site["baseStationId"], relay))
    assert refused.status_code == 409
    assert "no established uplink" in refused.json()["detail"]

    api.post(f"/api/v1/sites/{site['siteId']}/uplink", json={"satelliteId": relay, "role": "PRIMARY"})
    assert api.post("/api/v1/reports", json=report_body(site["siteId"], site["baseStationId"], relay)).status_code == 201
    api.delete(f"/api/v1/sites/{site['siteId']}/uplink/{relay}")
    assert api.post("/api/v1/reports", json=report_body(site["siteId"], site["baseStationId"], relay)).status_code == 409


def test_a_downed_relay_blocks_reports(api, make_site, make_satellite):
    site = make_site()
    relay = make_satellite()
    api.post(f"/api/v1/sites/{site['siteId']}/uplink", json={"satelliteId": relay, "role": "PRIMARY"})
    api.patch(f"/api/v1/satellites/{relay}/status", params={"status": "OFFLINE"})

    assert api.post("/api/v1/reports", json=report_body(site["siteId"], site["baseStationId"], relay)).status_code == 409


def test_report_input_is_validated(api):
    assert api.post("/api/v1/reports", json=report_body("no-site", SITE_BASE, RELAY)).status_code == 404
    assert api.post("/api/v1/reports", json=report_body(SITE, SITE_BASE, "no-relay")).status_code == 404
    wrong_sender = api.post("/api/v1/reports", json=report_body(SITE, "not-the-base-station", RELAY))
    assert wrong_sender.status_code == 422
    assert "is not the base station" in wrong_sender.json()["detail"]
    assert api.post("/api/v1/reports", json={"siteId": SITE}).status_code == 422
    assert api.post("/api/v1/reports", json=report_body(SITE, SITE_BASE, RELAY, priority="TEA_BREAK")).status_code == 422
    assert api.get("/api/v1/reports/no-such-report").status_code == 404
