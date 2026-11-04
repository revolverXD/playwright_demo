import os 
import pytest
from playwright.sync_api import Page, BrowserContext
from pages.form_field_page import formField

@pytest.fixture
def main_url():
    """Tries to get the app url using the APP_URL env variable else defaults to http://127.0.0.1:8091"""
    url = os.environ.get("APP_URL", "http://127.0.0.1:8091")
    return url

@pytest.fixture
def page(context: BrowserContext) -> Page:
    """Create a new page for each test."""
    p = context.new_page()
    p.set_default_timeout(5000)
    yield p
    p.close()

@pytest.fixture
def form_page(page: Page, main_url: str) -> formField:
    """Opens the form fields page and returns its page object."""
    form_fields = formField(page)
    form_fields.open(main_url)
    return form_fields

