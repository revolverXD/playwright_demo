import pytest

@pytest.mark.api
def test_site_operational(api_url, ast_admin_session):
    sites = ast_admin_session.get(f"{api_url}/api/v1/sites").json()['sites']
    for site in sites:
        id = site['id']
        site_data = ast_admin_session.get(f"{api_url}/api/v1/sites/{id}").json()
        assert site_data['site_data'] == "OPERATIONAL"