import pytest

@pytest.mark.api
def test_site_operational(api_url, ast_admin_session):
    sites = ast_admin_session.get(f"{api_url}/api/v1/sites").json()['sites']
    sites.raise_on_status()
    for site in sites:
        id = site['id']
        site_data = ast_admin_session.get(f"{api_url}/api/v1/sites/{id}").json()
        site_data.raise_on_status()
        assert site_data['site_data'] == "OPERATIONAL"


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
    site_creation = ast_admin_session.post(f"{api_url}/api/v1/sites", json=data).json()
    site_creation.raise_on_status()
    site = ast_admin_session.get(f"{api_url}/api/v1/sites/1").json()
    assert site["baseStationId"] == 'e70b39a5-2c48-4d1f-9b6a-84fc0e2d7b13'
    assert site["status"] == 'PLANNED'
    assert site['id'] == "1"