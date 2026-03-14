import pytest
import torch
from salt_agent.discriminator import Discriminator


@pytest.fixture
def discriminator():
    return Discriminator(num_techniques=16, embedding_dim=384)


def test_forward_returns_correct_shape(discriminator):
    response_emb = torch.randn(1, 384)
    technique_id = torch.tensor([0])
    kill_chain_stage = torch.tensor([1])

    stage_probs, confidence = discriminator(response_emb, technique_id, kill_chain_stage)
    assert stage_probs.shape == (1, 6)
    assert confidence.shape == (1, 1)


def test_stage_probs_sum_to_one(discriminator):
    response_emb = torch.randn(1, 384)
    technique_id = torch.tensor([3])
    kill_chain_stage = torch.tensor([0])

    stage_probs, _ = discriminator(response_emb, technique_id, kill_chain_stage)
    assert abs(stage_probs.sum().item() - 1.0) < 1e-5


def test_confidence_between_zero_and_one(discriminator):
    response_emb = torch.randn(1, 384)
    technique_id = torch.tensor([5])
    kill_chain_stage = torch.tensor([2])

    _, confidence = discriminator(response_emb, technique_id, kill_chain_stage)
    assert 0.0 <= confidence.item() <= 1.0


def test_batch_forward(discriminator):
    batch_size = 4
    response_emb = torch.randn(batch_size, 384)
    technique_ids = torch.tensor([0, 1, 2, 3])
    stages = torch.tensor([0, 1, 2, 3])

    stage_probs, confidence = discriminator(response_emb, technique_ids, stages)
    assert stage_probs.shape == (batch_size, 6)
    assert confidence.shape == (batch_size, 1)
