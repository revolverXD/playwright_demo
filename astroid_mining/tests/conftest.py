"""Live-server fixtures: the app runs under uvicorn, tests talk to it with `requests`."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from app import seed as fleet  # noqa: E402

# Seeded fleet ids, straight from the fleet documents.
RELAY = fleet.HEPHAESTUS_7["id"]
RELAY_BACKUP = fleet.RELAY_NODE_4["id"]
GROUND_RELAY = fleet.DSN_CERES["id"]
COLD_RELAY = fleet.COLD_STANDBY_VESTA["id"]
SITE = "a94f2c70-6b18-4d5a-92e3-0c7f4a6d8b21"
SITE_BASE = fleet.PSYCHE_DRILL_02["id"]
ROBOT_ACTIVE = "8a2f6d31-5b04-4c97-9a8e-1d6c4f7b20e5"
ROBOT_FAULT = "f60a29c7-3b84-4d1e-9c72-8a5b1d0e4f66"
SEEDED_ROBOTS = [r["id"] for r in fleet.ROBOTS]
SEED_REPORT = fleet.REPORTS[0]["id"]
NET_BELT = "net-belt-1"
NET_CERES = "net-ceres-1"
ADMIN = fleet.USERS[0]
VIEWER = fleet.USERS[1]


def login(base_url: str, user: dict) -> str:
    response = requests.post(f"{base_url}/api/v1/auth/login", json={"username": user["username"], "password": user["password"]}, timeout=15)
    assert response.status_code == 200, response.text
    return response.json()["token"]


def run_offline(code: str, db_file) -> str:
    """Run app code in a subprocess against its own throwaway database file."""
    done = subprocess.run(
        [sys.executable, "-c", code],
        cwd=APP_ROOT,
        env={**os.environ, "ASTROID_DB_PATH": str(db_file)},
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Api:
    """Thin `requests` wrapper so tests read as plain HTTP calls."""

    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url
        self.token = token

    def url(self, path: str) -> str:
        return self.base_url + path

    def request(self, method: str, path: str, **kwargs):
        kwargs.setdefault("timeout", 15)
        if self.token:
            kwargs.setdefault("headers", {}).setdefault("Authorization", f"Bearer {self.token}")
        return requests.request(method, self.url(path), **kwargs)

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def patch(self, path, **kw):
        return self.request("PATCH", path, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)


@pytest.fixture(scope="session")
def base_url(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("fleet") / "astroid.db"
    port = _free_port()
    env = {**os.environ, "ASTROID_DB_PATH": str(db_file)}
    log = open(tmp_path_factory.getbasetemp() / "uvicorn.log", "wb")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(APP_ROOT),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            if requests.get(f"{base}/health", timeout=2).status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.2)
    else:
        proc.terminate()
        log.flush()
        raise RuntimeError(f"uvicorn did not start; see {tmp_path_factory.getbasetemp() / 'uvicorn.log'}")
    yield base
    proc.terminate()
    proc.wait(timeout=10)
    log.close()


@pytest.fixture()
def api(base_url, admin_token):
    return Api(base_url, admin_token)


@pytest.fixture(scope="session")
def admin_token(base_url):
    return login(base_url, ADMIN)


@pytest.fixture(scope="session")
def viewer_token(base_url):
    return login(base_url, VIEWER)


@pytest.fixture()
def viewer(base_url, viewer_token):
    """Signed in as the read-only role."""
    return Api(base_url, viewer_token)


@pytest.fixture()
def anon(base_url):
    """No token at all."""
    return Api(base_url)


@pytest.fixture()
def make_site(api):
    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        body = {"name": f"TEST-BASE-{counter['n']:02d}", "designation": f"TEST-SPOT-{counter['n']:02d}"}
        body.update(overrides)
        response = api.post("/api/v1/sites", json=body)
        assert response.status_code == 201, response.text
        return {"designation": body["designation"], **response.json()}

    return _make


@pytest.fixture()
def make_satellite(api):
    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        body = {"name": f"TEST-RELAY-{counter['n']:02d}", "status": "OPERATIONAL"}
        body.update(overrides)
        response = api.post("/api/v1/satellites", json=body)
        assert response.status_code == 201, response.text
        return response.json()["satelliteId"]

    return _make


@pytest.fixture()
def make_net(api):
    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        body = {"name": f"TEST-NET-{counter['n']:02d}", "band": "Ka"}
        body.update(overrides)
        response = api.post("/api/v1/relay-nets", json=body)
        assert response.status_code == 201, response.text
        return response.json()["relayNet"]["id"]

    return _make


@pytest.fixture()
def make_robot(api, make_site):
    def _make(site_id=None, **overrides):
        site_id = site_id or make_site()["siteId"]
        body = {"designation": "TEST-ROBOT", "class": "HEAVY_EXCAVATOR", "siteId": site_id}
        body.update(overrides)
        response = api.post("/api/v1/robots", json=body)
        assert response.status_code == 201, response.text
        return response.json()["robotId"]

    return _make
