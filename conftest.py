import os 
import pytest
from playwright.sync_api import Page, BrowserContext
import requests

ONLINE_URL = "https://practice-automation.com"


@pytest.fixture
def page(context: BrowserContext) -> Page:
    """Create a new page for each test."""
    p = context.new_page()
    p.set_default_timeout(5000)
    yield p
    p.close()

@pytest.fixture
def api_url():
    """the astroid miner app api url"""
    return "http://127.0.0.1:8000"

@pytest.fixture
def ast_admin_token(api_url):
    token = requests.post(f"{api_url}/api/v1/auth/login", json={"username": "fleet-admin", "password": "regolith-7"}).json()['token']
    return token

@pytest.fixture
def ast_admin_session( ast_admin_token):
    admin_session = requests.Session()
    admin_session.headers["Authorization"] = f"Bearer {ast_admin_token}"
    yield admin_session
    admin_session.close()