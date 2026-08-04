import pytest
from app.core.settings import settings

@pytest.fixture(autouse=True)
def setup_demo_mode():
    settings.DEMO_MODE = True
    yield
    
