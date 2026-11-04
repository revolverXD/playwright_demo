import os 
import pytest
from playwright.sync_api import Page, BrowserContext

@pytest.fixture
def main_url():
    """Tries to get the app url using the APP_URL env variable else defaults to http://127.0.0.1:8091"""
    url = os.environ.get("APP_URL", "http://127.0.0.1:8091")
    return url

@pytest.fixture
def page(browser: BrowserContext) -> Page:
    """Create a new page for each test."""
    p = browser.new_page()
    p.set_default_timeout(5000)
    yield p
    p.close()

