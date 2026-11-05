"""Fleet-wide state endpoints."""

from conftest import SEEDED_ROBOTS


def test_health_reports_live_fleet_counts(api):
    body = api.get("/health").json()
    assert body["status"] == "ok"
    assert body["schemaVersion"] == "1.5.0"
    assert body["satellites"] >= 4
    assert body["sites"] >= 3


def test_fleet_summary_matches_the_registry(api):
    summary = api.get("/api/v1/fleet/summary").json()
    assert summary["totalRobots"] >= len(SEEDED_ROBOTS)
    assert summary["byClass"]["HEAVY_EXCAVATOR"] >= 2
    assert sum(summary["byState"].values()) == summary["totalRobots"]
    assert summary["establishedLinks"] >= 4
    assert 0.0 < summary["averageHealthPct"] <= 100.0


def test_unknown_route_is_a_404(api):
    assert api.get("/api/v1/nope").status_code == 404
