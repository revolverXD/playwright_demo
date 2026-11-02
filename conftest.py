import os 
import pytest

@pytest.fixture
def main_url():
    url = os.environ.get("APP_URL", "http://127.0.0.1:8091")
    return url