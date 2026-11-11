import pytest

@pytest.mark.api
def test_site_operational(api_url, ast_admin_session):
    sites = ast_admin_session.get(f"{api_url}/api/v1/sites")
    sites.raise_for_status()
    sites_data = sites.json()['sites']
    for site in sites_data:
        id = site['id']
        site_data = ast_admin_session.get(f"{api_url}/api/v1/sites/{id}")
        site_data.raise_for_status()
        assert site_data.json()['site_data'] == "OPERATIONAL"


def test_site_addition(api_url, ast_admin_session):
    # Trigger build
    data = {
        "name": "PsychoLink1",
        "designation": "Test-Station",
        "hostBody": "(4124) Orvar-SW",
        "baseStationId": "e70b39a5-2c48-4d1f-9b6a-84fc0e2d7b13",
        "status": "PLANNED",
        "autonomyTier": "L4_SUPERVISED",
        "metrics": {},
        "id": "1"
    }
    site_creation = ast_admin_session.post(f"{api_url}/api/v1/sites", json=data)
    site_creation.raise_for_status()
    site = ast_admin_session.get(f"{api_url}/api/v1/sites/1")
    site.raise_for_status()
    site_json = site.json()
    assert site_json["baseStationId"] == 'e70b39a5-2c48-4d1f-9b6a-84fc0e2d7b13'
    assert site_json["status"] == 'PLANNED'
    assert site_json['id'] == "1"