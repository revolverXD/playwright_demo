from datetime import datetime, timezone

def test_health(api_url, ast_admin_session):
    """Checks the response from the /health endpoint"""
    health_json = ast_admin_session.get(f"{api_url}/health").json()
    dt = datetime.fromisoformat(health_json['time'])
    assert health_json['status'] == "ok"
    assert dt.tzinfo == timezone.utc
    assert health_json['satellites'] is not None
    assert health_json['sites'] is not None
