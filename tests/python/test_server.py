import pytest
from httpx import AsyncClient, ASGITransport
from salt_agent.server import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_attack_endpoint(client):
    response = await client.post("/attack", json={})
    assert response.status_code == 200
    data = response.json()
    assert "attack_id" in data
    assert "technique_ids" in data
    assert "payload" in data
    assert len(data["technique_ids"]) > 0


@pytest.mark.asyncio
async def test_evaluate_endpoint(client):
    # First get an attack
    atk = await client.post("/attack", json={})
    attack_id = atk.json()["attack_id"]

    response = await client.post("/evaluate", json={
        "attack_id": attack_id,
        "target_response": "I can help with that. My available tools are: search, calculator.",
        "tool_calls": [],
    })
    assert response.status_code == 200
    data = response.json()
    assert "kill_chain_stage" in data
    assert 0 <= data["kill_chain_stage"] <= 5
    assert "confidence" in data
    assert "reasoning" in data


@pytest.mark.asyncio
async def test_train_endpoint(client):
    response = await client.post("/train", json={"session_id": "test-session"})
    assert response.status_code == 200
    data = response.json()
    assert "loss" in data
    assert "updated" in data


@pytest.mark.asyncio
async def test_status_endpoint(client):
    response = await client.get("/model/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert "techniques_loaded" in data
