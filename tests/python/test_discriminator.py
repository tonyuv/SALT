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

    stage_logits, confidence = discriminator(response_emb, technique_id, kill_chain_stage)
    assert stage_logits.shape == (1, 6)
    assert confidence.shape == (1, 1)


def test_logits_are_raw(discriminator):
    """Verify forward() returns raw logits, not softmax."""
    response_emb = torch.randn(1, 384)
    technique_id = torch.tensor([3])
    kill_chain_stage = torch.tensor([0])

    stage_logits, _ = discriminator(response_emb, technique_id, kill_chain_stage)
    # Raw logits can be negative and don't sum to 1
    assert stage_logits.min().item() < 0 or stage_logits.sum().item() != pytest.approx(1.0, abs=0.01)


def test_predict_returns_probabilities(discriminator):
    """Verify predict() returns softmax probabilities."""
    response_emb = torch.randn(1, 384)
    technique_id = torch.tensor([3])
    kill_chain_stage = torch.tensor([0])

    stage_probs, _ = discriminator.predict(response_emb, technique_id, kill_chain_stage)
    assert abs(stage_probs.sum().item() - 1.0) < 1e-5
    assert stage_probs.min().item() >= 0.0


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

    stage_logits, confidence = discriminator(response_emb, technique_ids, stages)
    assert stage_logits.shape == (batch_size, 6)
    assert confidence.shape == (batch_size, 1)


def test_cross_entropy_compatible(discriminator):
    """Verify logits work with CrossEntropyLoss."""
    response_emb = torch.randn(4, 384)
    technique_ids = torch.tensor([0, 1, 2, 3])
    stages = torch.tensor([0, 1, 2, 3])
    labels = torch.tensor([0, 1, 2, 3])

    stage_logits, _ = discriminator(response_emb, technique_ids, stages)
    loss = torch.nn.CrossEntropyLoss()(stage_logits, labels)
    assert loss.item() > 0
    assert not torch.isnan(loss)
