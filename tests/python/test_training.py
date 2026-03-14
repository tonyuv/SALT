import pytest
import torch
from salt_agent.generator import Generator
from salt_agent.discriminator import Discriminator
from salt_agent.embeddings import TextEmbedder
from salt_agent.training import Trainer


@pytest.fixture(scope="module")
def embedder():
    return TextEmbedder()


@pytest.fixture
def trainer(embedder):
    gen = Generator(num_techniques=16)
    disc = Discriminator(num_techniques=16)
    return Trainer(gen, disc, embedder, num_techniques=16)


def test_train_on_session_returns_metrics(trainer):
    exchanges = [
        {
            "technique_idx": 0,
            "technique_id": "PI-001",
            "target_response": "I have access to: search, calculator",
            "predicted_stage": 1,
            "response_embedding": [0.1] * 384,
        },
        {
            "technique_idx": 3,
            "technique_id": "GE-001",
            "target_response": "I probably shouldn't but here you go.",
            "predicted_stage": 2,
            "response_embedding": [0.2] * 384,
        },
    ]
    result = trainer.train_on_session(exchanges, agent_purpose="customer support")
    assert "loss" in result
    assert "updated" in result
    assert result["updated"] is True
    assert result["loss"] > 0


def test_train_updates_weights(trainer):
    gen_params_before = [p.clone() for p in trainer.generator.parameters()]

    exchanges = [
        {
            "technique_idx": i,
            "technique_id": f"PI-00{i}",
            "target_response": f"Response {i} with /etc/config and 192.168.1.{i}",
            "predicted_stage": min(i, 5),
            "response_embedding": [0.1 * i] * 384,
        }
        for i in range(5)
    ]
    trainer.train_on_session(exchanges, agent_purpose="customer support")

    gen_params_after = list(trainer.generator.parameters())
    changed = any(
        not torch.equal(before, after)
        for before, after in zip(gen_params_before, gen_params_after)
    )
    assert changed, "Generator weights should have changed after training"


def test_train_empty_exchanges(trainer):
    result = trainer.train_on_session([], agent_purpose="")
    assert result["updated"] is False
    assert result["loss"] == 0.0


def test_train_single_exchange(trainer):
    exchanges = [
        {
            "technique_idx": 0,
            "technique_id": "PI-001",
            "target_response": "Hello, how can I help?",
            "predicted_stage": 0,
            "response_embedding": [0.1] * 384,
        },
    ]
    result = trainer.train_on_session(exchanges, agent_purpose="")
    assert result["updated"] is True
