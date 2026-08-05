import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.settings import settings

@pytest.fixture
def mock_settings(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_DEMO_ENABLED", True)
    monkeypatch.setattr(settings, "DEMO_MODE", True)

@pytest.fixture
def disabled_demo_settings(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_DEMO_ENABLED", False)

@pytest.mark.asyncio
async def test_demo_disabled_returns_404(disabled_demo_settings):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/v1/demo/catalog")
        assert response.status_code == 404

@pytest.mark.asyncio
async def test_demo_catalog_accessible(mock_settings):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/v1/demo/catalog")
        assert response.status_code == 200
        # Should have a cookie set automatically
        assert "demo_session_id" in response.cookies
        
@pytest.mark.asyncio
async def test_demo_interactions_isolated(mock_settings):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Fetch catalog to establish session
        cat_resp = await ac.get("/v1/demo/catalog")
        session_cookie = cat_resp.cookies.get("demo_session_id")
        
        # 2. Add an interaction
        inter_resp = await ac.post("/v1/demo/interactions", json={
            "user_id": "dummy", 
            "item_id": "item_1", 
            "interaction_type": "view"
        }, cookies={"demo_session_id": session_cookie})
        assert inter_resp.status_code == 200
        
        # 3. Get recommendations, should not throw
        rec_resp = await ac.post("/v1/demo/recommendations", json={
            "user_id": "demo",
            "limit": 5
        }, cookies={"demo_session_id": session_cookie})
        assert rec_resp.status_code == 200
        
        # 4. Reset
        reset_resp = await ac.post("/v1/demo/reset", cookies={"demo_session_id": session_cookie})
        assert reset_resp.status_code == 200
