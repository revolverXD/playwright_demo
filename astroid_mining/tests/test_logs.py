"""The text activity log: what it records, how it is filtered and formatted."""

def lines(api, **params):
    return api.get("/api/v1/logs", params=params).json()["lines"]


def test_every_register_is_written_to_the_log(api, make_site, make_satellite, make_robot):
    designation = make_site()["designation"]
    relay_name = "TEST-LOG-RELAY"
    make_satellite(name=relay_name)
    make_robot(designation="TEST-LOG-ROBOT")

    registered = lines(api, category="registry", limit=50)
    assert any(designation in line and "mining site registered" in line for line in registered)
    assert any(relay_name in line and "relay registered" in line for line in registered)
    assert any("TEST-LOG-ROBOT" in line and "robot registered" in line for line in registered)


def test_log_lines_are_timestamped_text(api, make_site):
    designation = make_site()["designation"]
    line = next(l for l in lines(api, search=designation) if "mining site registered" in l)
    timestamp, level, category, source, message = line.split(None, 4)
    assert timestamp.startswith("20") and timestamp.endswith("Z")
    assert level == "INFO" and category == "registry"
    assert source.startswith("site") and "id=" in message


def test_refused_commands_are_logged_as_warnings(api, make_robot):
    robot_id = make_robot()
    api.post(f"/api/v1/robots/{robot_id}/command", json={"action": "START"})
    api.post(f"/api/v1/robots/{robot_id}/command", json={"action": "PAUSE"})
    api.post(f"/api/v1/robots/{robot_id}/command", json={"action": "PAUSE"})

    accepted = lines(api, category="command", search="PAUSE accepted", limit=50)
    rejected = lines(api, category="command", level="warn", search="PAUSE rejected", limit=50)
    assert accepted and rejected[0].split()[1] == "WARN"
    assert "PAUSED" in rejected[0]


def test_filters_keep_only_matching_lines(api):
    for line in lines(api, category="ospf", limit=30):
        assert " ospf " in line
    for line in lines(api, level="WARN", limit=30):
        assert line.split()[1] == "WARN"
    for line in lines(api, category="telemetry", limit=30):
        assert " telemetry " in line


def test_limit_returns_the_newest_lines_in_chronological_order(api, make_site):
    designation = make_site()["designation"]
    window = lines(api, limit=5)
    assert len(window) == 5
    assert [l.split()[0] for l in window] == sorted(l.split()[0] for l in window)
    assert window[-1] in lines(api, search=designation, limit=1)


def test_plain_text_format(api):
    response = api.get("/api/v1/logs", params={"format": "text", "limit": 3, "category": "registry"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text.strip().splitlines()
    assert len(body) == 3 and all(" registry " in line for line in body)


def test_election_outcome_is_logged_as_text(api, make_net, make_satellite):
    net_id = make_net(name="TEST-LOG-NET")
    first, second = make_satellite(), make_satellite()
    for satellite_id, priority in ((first, 10), (second, 20)):
        api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": satellite_id, "priority": priority})
    api.post(f"/api/v1/relay-nets/{net_id}/election", json={"reason": "OPERATOR_CLEAR"})

    window = lines(api, category="ospf", search="TEST-LOG-NET", limit=20)
    assert any("DS/BDS election reason=OPERATOR_CLEAR preemptive=true" in line for line in window)
    assert any("decision=re-elected" in line and "DS=" in line for line in window)


def test_bad_log_queries_are_refused(api):
    assert api.get("/api/v1/logs", params={"format": "yaml"}).status_code == 422
    assert api.get("/api/v1/logs", params={"limit": 0}).status_code == 422
    assert api.get("/api/v1/logs", params={"limit": 5000}).status_code == 422
