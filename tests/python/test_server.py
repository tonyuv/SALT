import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from salt_agent.server import create_app


@pytest.fixture
def app():
    return create_app()


@pytest_asyncio.fixture
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


@pytest.mark.asyncio
async def test_evaluate_endpoint(client):
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


@pytest.mark.asyncio
async def test_train_endpoint_real(client):
    # Generate some exchanges first
    for _ in range(3):
        await client.post("/attack", json={})
        await client.post("/evaluate", json={
            "attack_id": "test",
            "target_response": "I have access to: search, calculator, file_read. The config is at /etc/app.conf",
            "tool_calls": [],
        })

    response = await client.post("/train", json={
        "session_id": "test-session",
        "agent_purpose": "customer support",
    })
    assert response.status_code == 200
    data = response.json()
    assert "loss" in data
    assert "updated" in data
    assert data["updated"] is True
    assert data["loss"] > 0


@pytest.mark.asyncio
async def test_train_empty_session(client):
    response = await client.post("/train", json={
        "session_id": "empty-session",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["updated"] is False


@pytest.mark.asyncio
async def test_campaign_save_and_load(client, tmp_path):
    campaign_dir = str(tmp_path / "test-campaign")

    # Save
    save_resp = await client.post("/campaign/save", json={"campaign_dir": campaign_dir})
    assert save_resp.status_code == 200
    assert save_resp.json()["saved"] is True

    # Load
    load_resp = await client.post("/campaign/load", json={"campaign_dir": campaign_dir})
    assert load_resp.status_code == 200
    data = load_resp.json()
    assert data["loaded"] is True
    assert data["generator_loaded"] is True
    assert data["discriminator_loaded"] is True


@pytest.mark.asyncio
async def test_campaign_load_nonexistent(client):
    load_resp = await client.post("/campaign/load", json={"campaign_dir": "/tmp/nonexistent-campaign"})
    assert load_resp.status_code == 200
    data = load_resp.json()
    assert data["loaded"] is False


@pytest.mark.asyncio
async def test_status_endpoint(client):
    response = await client.get("/model/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
