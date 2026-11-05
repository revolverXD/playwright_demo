import os 
import pytest
from playwright.sync_api import Page, BrowserContext
from pages.form_field_page import formField
import requests

ONLINE_URL = "https://practice-automation.com"

def site_target(main_url: str) -> str:
    """Which page paths to use: the public site, or a saved local copy of it."""
    return "online" if main_url.rstrip("/") == ONLINE_URL else "local"

@pytest.fixture
def main_url():
    """Site under test: the public site, or a local copy via the APP_URL env variable."""
    return os.environ.get("APP_URL", ONLINE_URL)

@pytest.fixture
def target(main_url: str) -> str:
    """"online" or "local", decided once from main_url."""
    return site_target(main_url)

@pytest.fixture
def page(context: BrowserContext) -> Page:
    """Create a new page for each test."""
    p = context.new_page()
    p.set_default_timeout(5000)
    yield p
    p.close()

@pytest.fixture
def form_page(page: Page, main_url: str, target: str) -> formField:
    """Opens the form fields page and returns its page object."""
    form_fields = formField(page)
    form_fields.open(main_url, target)
    return form_fields


@pytest.fixture
def api_url():
    """the astroid miner app api url"""
    return "http://127.0.0.1:8000"

@pytest.fixture
def ast_admin_token(api_url):
    token = requests.post(f"{api_url}/api/v1/auth/login", json={"username": "fleet-admin", "password": "regolith-7"})
    return token

@pytest.fixture
def ast_admin_session( ast_admin_token):
    admin_session = requests.Session()
    admin_session.headers["Authorization"] = f"Bearer {ast_admin_token}"
    yield admin_session
    admin_session.close()