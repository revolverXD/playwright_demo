"""Users, roles and bearer tokens: login is the only place a password is accepted."""

from datetime import datetime, timedelta, timezone

from conftest import ADMIN, Api, SITE, VIEWER, login, run_offline

TWO_DAYS = timedelta(days=2)


def stamp(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def sign_in(api, user) -> dict:
    return api.post("/api/v1/auth/login", json={"username": user["username"], "password": user["password"]}).json()


def test_an_older_database_gains_the_accounts_on_next_start(tmp_path):
    # a database written before accounts existed has the users table but no rows in it
    script = "\n".join(
        [
            "from app import db",
            "db.init_db()",
            "c = db.connect(); c.execute('DELETE FROM users'); c.commit(); c.close()",
            "db.init_db()",
            "c = db.connect()",
            "print([r[0] for r in c.execute('SELECT username FROM users ORDER BY username')])",
        ]
    )
    assert run_offline(script, tmp_path / "old.db").strip().splitlines()[-1] == "['fleet-admin', 'site-observer']"


def test_login_returns_a_bearer_token_valid_for_two_days(api):
    body = sign_in(api, ADMIN)
    assert body["tokenType"] == "Bearer" and body["role"] == "admin" and len(body["token"]) >= 24
    assert stamp(body["expiresAt"]) - stamp(body["issuedAt"]) == TWO_DAYS
    assert stamp(body["expiresAt"]) - datetime.now(timezone.utc) > timedelta(days=1, hours=23)


def test_login_refuses_a_wrong_password_and_an_unknown_user(api):
    assert api.get("/api/v1/auth/login").status_code == 405  # credentials are a POST body
    bad = api.post("/api/v1/auth/login", json={"username": ADMIN["username"], "password": "wrong"})
    assert bad.status_code == 401 and "token" not in bad.json()
    assert api.post("/api/v1/auth/login", json={"username": "nobody", "password": "x"}).status_code == 401
    assert api.post("/api/v1/auth/login", json={"username": ADMIN["username"]}).status_code == 422


def test_liveness_needs_no_token_but_everything_else_does(anon):
    assert anon.get("/health").status_code == 200
    assert anon.get("/api/v1/sites").status_code == 401
    assert anon.post("/api/v1/sites", json={"name": "X", "designation": "X"}).status_code == 401
    assert anon.get("/api/v1/logs").status_code == 401


def test_a_made_up_or_malformed_token_is_refused(api, anon):
    assert anon.get("/api/v1/sites", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert anon.get("/api/v1/sites", headers={"Authorization": "not-a-bearer"}).status_code == 401
    assert anon.get("/api/v1/sites", auth=(ADMIN["username"], ADMIN["password"])).status_code == 401


def test_read_only_endpoints_answer_a_viewer(viewer):
    assert viewer.get("/api/v1/fleet/summary").status_code == 200
    assert viewer.get(f"/api/v1/sites/{SITE}").status_code == 200
    assert viewer.get("/api/v1/relay-nets/net-belt-1/neighbors").status_code == 200
    assert viewer.get("/api/v1/logs", params={"limit": 5}).status_code == 200


def test_a_viewer_may_not_change_anything(viewer, make_site, make_net, make_satellite):
    site_id = make_site()["siteId"]
    net_id = make_net()
    satellite_id = make_satellite()

    refused = [
        viewer.post(f"/api/v1/sites/{site_id}/metrics", json={"healthScore": 0.5}),
        viewer.post(f"/api/v1/sites/{site_id}/uplink", json={"satelliteId": satellite_id, "role": "SECONDARY"}),
        viewer.post(f"/api/v1/sites/{site_id}/links/failover"),
        viewer.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": satellite_id, "priority": 10}),
        viewer.post(f"/api/v1/relay-nets/{net_id}/election", json={"reason": "OPERATOR_CLEAR"}),
        viewer.patch(f"/api/v1/satellites/{satellite_id}/status", params={"status": "OFFLINE"}),
        viewer.delete(f"/api/v1/sites/{site_id}/uplink/{satellite_id}"),
    ]
    assert [r.status_code for r in refused] == [403] * len(refused)
    assert "read-only" in refused[0].json()["detail"]
    assert viewer.get(f"/api/v1/sites/{site_id}/metrics").status_code == 200


def test_an_admin_may_act(api, make_site, make_net, make_satellite):
    assert api.post(f"/api/v1/sites/{make_site()['siteId']}/metrics", json={"healthScore": 0.9}).status_code == 201
    assert api.post("/api/v1/relay-nets", json={"name": "TEST-AUTH-NET"}).status_code == 201


def test_whoami_reports_the_signed_in_role(api, viewer):
    admin_body = api.get("/api/v1/auth/me").json()
    assert admin_body["username"] == ADMIN["username"] and admin_body["role"] == "admin"

    body = viewer.get("/api/v1/auth/me").json()
    assert body["username"] == VIEWER["username"] and body["role"] == "viewer"
    assert body["displayName"] == VIEWER["displayName"]
    assert stamp(body["expiresAt"]) - stamp(body["issuedAt"]) == TWO_DAYS


def test_openapi_documents_the_bearer_scheme_and_the_groups(anon):
    assert anon.get("/docs").status_code == 200
    schema = anon.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["bearerToken"] == {"type": "http", "scheme": "bearer", "bearerFormat": "token"}
    assert schema["security"] == [{"bearerToken": []}]
    assert {t["name"] for t in schema["tags"]} >= {"auth", "relays", "relay nets", "activity log"}
    assert all(op.get("security") == [] for op in schema["paths"]["/health"].values())
    assert all(op.get("security") == [] for op in schema["paths"]["/api/v1/auth/login"].values())


def test_logout_kills_the_token_for_both_roles(base_url):
    for user in (ADMIN, VIEWER):
        client = Api(base_url, login(base_url, user))
        assert client.get("/api/v1/auth/me").status_code == 200
        assert client.post("/api/v1/auth/logout").status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.post("/api/v1/auth/logout").status_code == 401
