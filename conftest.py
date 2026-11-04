import os 
import pytest
from playwright.sync_api import Page, BrowserContext
from pages.form_field_page import formField

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

