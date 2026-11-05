"""OSPF-style relay adjacencies: DS / BDS election, re-election and the neighbor table."""

from conftest import COLD_RELAY, GROUND_RELAY, NET_BELT, NET_CERES, RELAY, RELAY_BACKUP


def neighbors(api, net_id):
    return api.get(f"/api/v1/relay-nets/{net_id}/neighbors").json()


def roles_by_name(payload):
    return {n["name"]: n["role"] for n in payload["neighbors"]}


def roles_by_id(payload):
    return {n["id"]: n["role"] for n in payload["neighbors"]}


def test_fleet_api_lists_the_relay_nets_with_their_roles(api):
    body = api.get("/api/v1/relay-nets").json()
    assert {NET_BELT, NET_CERES} <= {n["id"] for n in body["relayNets"]}
    belt = next(n for n in body["relayNets"] if n["id"] == NET_BELT)
    assert belt["band"] == "Ka" and belt["helloIntervalS"] == 10 and belt["deadIntervalS"] == 40
    assert belt["ds"]["name"] == "HEPHAESTUS-7" and belt["bds"]["name"] == "RELAY-NODE-4"


def test_boot_election_picks_the_highest_priority_operational_relay(api):
    table = neighbors(api, NET_BELT)
    assert table["ds"] == "HEPHAESTUS-7" and table["bds"] == "RELAY-NODE-4"
    assert roles_by_name(table) == {
        "HEPHAESTUS-7": "DS",
        "RELAY-NODE-4": "BDS",
        "VESTA-COLD-1": "DROTHER",
        "DSN-CERES": "DROTHER",
    }
    assert table["neighbors"][0]["state"] == "FULL"


def test_priority_zero_relay_is_never_elected(api):
    table = neighbors(api, NET_CERES)
    assert table["ds"] == "HEPHAESTUS-7" and table["bds"] is None
    dsn = next(n for n in table["neighbors"] if n["id"] == GROUND_RELAY)
    assert dsn["priority"] == 0 and dsn["role"] == "DROTHER"


def test_a_relay_joins_by_walking_the_adjacency_up_to_full(api, make_net, make_satellite):
    net_id = make_net()
    assert neighbors(api, net_id)["neighbors"] == []

    satellite_id = make_satellite()
    response = api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": satellite_id, "priority": 5})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["state"] == "FULL" and body["election"]["dsId"] == satellite_id and body["election"]["bdsId"] is None

    handshake = api.get(f"/api/v1/logs?category=ospf&search={satellite_id[:8]}&limit=20").json()["lines"]
    assert any("state DOWN->INIT" in line for line in handshake)
    assert any("state INIT->2_WAY" in line for line in handshake)
    assert any("state 2_WAY->FULL" in line for line in handshake)


def test_election_is_non_preemptive_until_the_operator_clears_it(api, make_net, make_satellite):
    net_id = make_net()
    incumbent = make_satellite()
    newcomer = make_satellite()
    api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": incumbent, "priority": 100})
    join = api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": newcomer, "priority": 200}).json()["election"]
    assert join["dsId"] == incumbent and join["bdsId"] == newcomer
    assert "non-preemptive" in join["decision"]

    response = api.post(f"/api/v1/relay-nets/{net_id}/election", json={"reason": "OPERATOR_CLEAR"})
    assert response.status_code == 200
    election = response.json()["election"]
    assert election["dsId"] == newcomer and election["bdsId"] == incumbent and election["changed"] is True
    assert roles_by_id(neighbors(api, net_id)) == {newcomer: "DS", incumbent: "BDS"}


def test_highest_router_id_wins_a_priority_tie(api, make_net, make_satellite):
    net_id = make_net()
    first, second = make_satellite(), make_satellite()
    for satellite_id in (first, second):
        api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": satellite_id, "priority": 120})
    election = api.post(f"/api/v1/relay-nets/{net_id}/election", json={"reason": "POLICY_CHANGE"}).json()["election"]
    assert election["dsId"] == max(first, second) and election["bdsId"] == min(first, second)


def test_losing_the_ds_promotes_the_bds_and_the_next_backup(api, make_net, make_satellite):
    net_id = make_net()
    ds, bds, backup = (make_satellite() for _ in range(3))
    for satellite_id, priority in ((ds, 100), (bds, 90), (backup, 80)):
        api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": satellite_id, "priority": priority})

    response = api.patch(f"/api/v1/satellites/{ds}/status", params={"status": "OFFLINE"})
    assert response.status_code == 200
    table = neighbors(api, net_id)
    assert roles_by_id(table)[bds] == "DS" and roles_by_id(table)[backup] == "BDS" and roles_by_id(table)[ds] == "DROTHER"
    assert next(n for n in table["neighbors"] if n["id"] == ds)["state"] == "DOWN"

    removed = api.delete(f"/api/v1/relay-nets/{net_id}/peers/{backup}").json()["election"]
    assert removed["dsId"] == bds and removed["bdsId"] is None


def test_a_standby_relay_is_not_a_candidate(api, make_net, make_satellite):
    net_id = make_net()
    working, standby = make_satellite(), make_satellite(status="STANDBY")
    api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": standby, "priority": 255})
    api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": working, "priority": 1})
    election = api.post(f"/api/v1/relay-nets/{net_id}/election", json={"reason": "POLICY_CHANGE"}).json()["election"]
    assert election["dsId"] == working
    assert [p["satelliteId"] for p in election["excluded"]] == [standby]
    assert "STANDBY" in election["excluded"][0]["excluded"]


def test_a_net_without_any_candidate_has_no_ds(api, make_net, make_satellite):
    net_id = make_net()
    api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": make_satellite(), "priority": 0})
    election = api.post(f"/api/v1/relay-nets/{net_id}/election", json={"reason": "SHOW_ONLY"}).json()["election"]
    assert election["ds"] is None and election["bds"] is None and election["decision"] == "no eligible candidate"
    assert neighbors(api, net_id)["ds"] is None


def test_show_only_election_does_not_change_the_roles(api, make_net, make_satellite):
    net_id = make_net()
    first, second = make_satellite(), make_satellite()
    for satellite_id, priority in ((first, 10), (second, 20)):
        api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": satellite_id, "priority": priority})
    shown = api.post(f"/api/v1/relay-nets/{net_id}/election", json={"reason": "SHOW_ONLY", "preemptive": False}).json()["election"]
    assert shown["dsId"] == first and shown["changed"] is False
    assert roles_by_id(neighbors(api, net_id)) == {first: "DS", second: "BDS"}


def test_clearing_a_peer_re_forms_the_adjacency_and_keeps_the_roles(api, make_net, make_satellite):
    net_id = make_net()
    ds = make_satellite()
    api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": ds, "priority": 100})
    response = api.post(f"/api/v1/relay-nets/{net_id}/peers/{ds}/clear")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "FULL"
    assert body["whileDown"]["dsId"] is None and body["whileDown"]["reason"] == "ADJACENCY_CLEARED"
    assert body["election"]["dsId"] == ds and body["election"]["reason"] == "ADJACENCY_REFORMED"
    assert next(n for n in neighbors(api, net_id)["neighbors"] if n["id"] == ds)["state"] == "FULL"


def test_satellite_document_exposes_its_ospf_roles_and_neighbors(api):
    body = api.get(f"/api/v1/satellites/{RELAY}").json()["satellite"]
    nets = {n["netId"]: n for n in body["ospf"]["nets"]}
    assert body["ospf"]["routerId"] == RELAY
    assert nets[NET_BELT]["role"] == "DS" and nets[NET_BELT]["ds"] == "HEPHAESTUS-7"
    assert nets[NET_CERES]["role"] == "DS"
    assert {n["satelliteId"] for n in nets[NET_BELT]["neighbors"]} == {RELAY_BACKUP, GROUND_RELAY, COLD_RELAY}


def test_elections_are_audited_per_net(api):
    body = api.get(f"/api/v1/relay-nets/{NET_CERES}/elections", params={"limit": 5}).json()
    boot = [e for e in body["elections"] if e["reason"] == "BOOT"]
    assert body["count"] >= 1 and boot[-1]["dsId"] == RELAY and boot[-1]["changed"] is True


def test_bad_peer_requests_are_refused(api, make_net, make_satellite):
    net_id = make_net()
    satellite_id = make_satellite()
    assert api.get("/api/v1/relay-nets/net-nope/neighbors").status_code == 404
    assert api.post("/api/v1/relay-nets/net-nope/election", json={}).status_code == 404
    assert api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": "nope", "priority": 1}).status_code == 404
    assert api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": satellite_id, "priority": 256}).status_code == 422
    assert api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": satellite_id, "priority": -1}).status_code == 422
    assert api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": satellite_id, "priority": 1}).status_code == 201
    assert api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": satellite_id, "priority": 1}).status_code == 409
    assert api.delete(f"/api/v1/relay-nets/{net_id}/peers/{RELAY}").status_code == 404
    assert api.post(f"/api/v1/relay-nets/{net_id}/peers/{RELAY}/clear").status_code == 404


def test_registering_a_relay_net_twice_is_a_conflict(api, make_net):
    net_id = make_net(name="TEST-DUP")
    response = api.post("/api/v1/relay-nets", json={"id": net_id, "name": "TEST-DUP-AGAIN"})
    assert response.status_code == 409
