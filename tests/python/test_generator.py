import pytest
import torch
from salt_agent.generator import Generator


@pytest.fixture
def generator():
    return Generator(num_techniques=16, embedding_dim=384)


def test_forward_returns_log_probabilities(generator):
    current_stage = torch.tensor([[1, 0, 0, 0, 0, 0]], dtype=torch.float)
    response_emb = torch.randn(1, 384)
    history = torch.zeros(1, 10, dtype=torch.long)

    log_probs = generator(current_stage, response_emb, history)
    assert log_probs.shape == (1, 16)
    # Log probs should be <= 0
    assert log_probs.max().item() <= 0.0 + 1e-5
    # exp(log_probs) should sum to 1
    probs = torch.exp(log_probs)
    assert abs(probs.sum().item() - 1.0) < 1e-5


def test_select_technique_returns_valid_id(generator):
    current_stage = torch.tensor([[0, 1, 0, 0, 0, 0]], dtype=torch.float)
    response_emb = torch.randn(1, 384)
    history = torch.zeros(1, 10, dtype=torch.long)

    technique_idx = generator.select_technique(current_stage, response_emb, history)
    assert 0 <= technique_idx < 16


def test_batch_forward(generator):
    batch_size = 4
    current_stage = torch.zeros(batch_size, 6)
    current_stage[:, 0] = 1.0
    response_emb = torch.randn(batch_size, 384)
    history = torch.zeros(batch_size, 10, dtype=torch.long)

    log_probs = generator(current_stage, response_emb, history)
    assert log_probs.shape == (batch_size, 16)


def test_reinforce_compatible(generator):
    """Verify log-probs work for REINFORCE policy gradient."""
    current_stage = torch.tensor([[1, 0, 0, 0, 0, 0]], dtype=torch.float)
    response_emb = torch.randn(1, 384)
    history = torch.zeros(1, 10, dtype=torch.long)

    log_probs = generator(current_stage, response_emb, history)
    action = torch.tensor([3])
    reward = torch.tensor([2.0])

    # REINFORCE: -log_prob(action) * reward
    loss = -(log_probs[0, action] * reward).mean()
    assert not torch.isnan(loss)
    loss.backward()
    # Verify gradients exist
    assert any(p.grad is not None for p in generator.parameters())
