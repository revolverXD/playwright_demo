"""The three.js view at /viz: public static files, plus the data contract it draws the fleet from.

web/app.js is not executed here (no browser in this environment): these tests pin the two things
that can silently break it - the files it loads, and the field names and ids it reads.
"""

from concurrent.futures import ThreadPoolExecutor

from conftest import ADMIN

def test_the_view_and_its_vendor_files_need_no_token(anon):
    for path in ("/viz/", "/viz/app.js", "/viz/three.module.min.js", "/viz/OrbitControls.js"):
        assert anon.get(path).status_code == 200, path
    page = anon.get("/viz/").text
    assert 'src="/viz/app.js"' in page
    assert '"three": "/viz/three.module.min.js"' in page  # import map resolves the bare specifier
    assert 'three/addons/controls/OrbitControls.js' in page
    app_js = anon.get("/viz/app.js").text
    for call in ("/api/v1/fleet/summary", "/api/v1/clock", "/api/v1/sites", "/api/v1/satellites", "/api/v1/relay-nets"):
        assert call in app_js, f"the view reads {call}"


def test_the_view_signs_in_through_the_login_endpoint(anon):
    session = anon.post("/api/v1/auth/login", json={"username": ADMIN["username"], "password": ADMIN["password"]}).json()
    assert all(key in session for key in ("token", "username", "role", "expiresAt")), session  # app.js keeps exactly these
    assert anon.get("/api/v1/sites").status_code == 401  # before signing in, the page has nothing to draw


def test_fetching_the_view_data_at_once_answers_200(api, make_net, make_satellite):
    """web/app.js asks for everything at once; a connection pinned to one thread answers 500."""
    paths = ["/api/v1/fleet/summary", "/api/v1/clock", "/api/v1/sites", "/api/v1/satellites", "/api/v1/relay-nets"]
    for _ in range(3):
        with ThreadPoolExecutor(max_workers=len(paths)) as pool:
            codes = [response.status_code for response in pool.map(api.get, paths)]
        assert codes == [200] * len(paths), codes

    # a writer at the same time, so concurrent commits wait on the lock instead of failing
    net_id = make_net(name="TEST-NET-CONCURRENT")
    relay_id = make_satellite(name="TEST-RELAY-CONCURRENT")
    assert api.post(f"/api/v1/relay-nets/{net_id}/peers", json={"satelliteId": relay_id, "priority": 10}).status_code == 201
    with ThreadPoolExecutor(max_workers=len(paths) + 1) as pool:
        jobs = [pool.submit(api.get, path) for path in paths]
        jobs.append(pool.submit(api.post, f"/api/v1/relay-nets/{net_id}/peers/{relay_id}/hello"))
        codes = [job.result().status_code for job in jobs]
    assert codes == [200] * (len(paths) + 1), codes


def snapshot(api):
    """The same requests web/app.js makes, in the same shape."""
    sites = api.get("/api/v1/sites").json()["sites"]
    return {
        "summary": api.get("/api/v1/fleet/summary").json(),
        "clock": api.get("/api/v1/clock").json(),
        "sites": sites,
        "relays": api.get("/api/v1/satellites").json()["satellites"],
        "nets": api.get("/api/v1/relay-nets").json()["relayNets"],
        "bases": {site["id"]: api.get(f"/api/v1/sites/{site['id']}").json()["baseStation"] for site in sites},
    }


def need(obj, keys, what):
    missing = [key for key in keys if key not in obj]
    assert not missing, f"{what} is missing {missing}: {sorted(obj)}"


def test_every_field_the_view_reads_is_in_the_api(api):
    data = snapshot(api)
    need(data["summary"], ["satellites", "establishedLinks", "totalRobots", "openAnomalies", "averageHealthPct", "byState"], "fleet summary")
    need(data["clock"], ["now", "uptimeS"], "clock")

    for site in data["sites"]:
        need(site, ["id", "name", "designation", "hostBody", "baseStationId", "status", "healthScore", "summary"], f"site {site.get('id')}")
        need(site["summary"], ["productionRateTph", "rawOreStockTons", "refinedStockTons"], f"site summary {site['name']}")
        base = data["bases"][site["id"]]
        links = base["satelliteLinks"]["links"]
        need(base, ["summary", "satelliteLinks", "fleet"], f"base station {site['name']}")
        for link in links:
            need(link, ["satelliteId", "role", "band", "status", "sharePct", "missedReports"], f"uplink of {site['name']}")
        for robot in base["fleet"]["roster"]:
            need(robot, ["designation", "class", "state", "status", "batteryPct", "healthPct"], f"robot {robot.get('designation')}")

    for relay in data["relays"]:
        need(relay, ["id", "name", "operator", "status", "healthScore", "connectedSites"], f"relay {relay.get('id')}")

    for net in data["nets"]:
        need(net, ["id", "name", "band", "helloIntervalS", "deadIntervalS", "ds", "bds", "adjacencies"], f"relay net {net.get('id')}")
        for peer in net["adjacencies"]:
            need(peer, ["satelliteId", "name", "state", "role", "holdTimeS"], f"adjacency on {net['name']}")


def test_the_view_can_resolve_every_id_it_draws(api):
    # a link or peer pointing at a relay the relay list does not contain would silently lose its line
    data = snapshot(api)
    relay_ids = {relay["id"] for relay in data["relays"]}
    for site in data["sites"]:
        for link in data["bases"][site["id"]]["satelliteLinks"]["links"]:
            assert link["satelliteId"] in relay_ids, f"{site['name']} uplinks to an unknown relay {link['satelliteId']}"
    for net in data["nets"]:
        for peer in net["adjacencies"]:
            assert peer["satelliteId"] in relay_ids, f"{net['name']} has an unknown peer {peer['satelliteId']}"
