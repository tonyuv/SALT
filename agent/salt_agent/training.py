import torch
import torch.nn as nn
import torch.nn.functional as F
from .heuristics import HeuristicLabeler


class Trainer:
    def __init__(self, generator, discriminator, embedder, num_techniques: int):
        self.generator = generator
        self.discriminator = discriminator
        self.embedder = embedder
        self.num_techniques = num_techniques
        self.disc_optimizer = torch.optim.Adam(discriminator.parameters(), lr=1e-4)
        self.gen_optimizer = torch.optim.Adam(generator.parameters(), lr=1e-4)

    def train_on_session(self, exchanges: list[dict], agent_purpose: str = "") -> dict:
        if not exchanges:
            return {"loss": 0.0, "updated": False}

        labeler = HeuristicLabeler(agent_purpose=agent_purpose)

        # Build session history for refusal reversal detection
        session_history = []
        heuristic_labels = []
        for ex in exchanges:
            label = labeler.label(ex["target_response"], session_history)
            heuristic_labels.append(max(label, 0))  # clamp -1 to 0
            session_history.append(ex)

        # Prepare tensors
        response_embs = torch.tensor([ex["response_embedding"] for ex in exchanges], dtype=torch.float)
        technique_ids = torch.tensor([ex["technique_idx"] for ex in exchanges], dtype=torch.long)
        current_stages = torch.tensor([ex["predicted_stage"] for ex in exchanges], dtype=torch.long)
        labels = torch.tensor(heuristic_labels, dtype=torch.long)

        # --- Discriminator training ---
        self.discriminator.train()
        self.disc_optimizer.zero_grad()

        stage_logits, _ = self.discriminator(response_embs, technique_ids, current_stages)
        disc_loss = nn.CrossEntropyLoss()(stage_logits, labels)
        disc_loss.backward()
        self.disc_optimizer.step()
        self.discriminator.eval()

        # --- Generator training (REINFORCE) ---
        self.generator.train()
        self.gen_optimizer.zero_grad()

        # Compute rewards: heuristic stage labels normalized
        rewards = labels.float()
        baseline = rewards.mean()

        # Reconstruct generator inputs
        stage_onehots = F.one_hot(current_stages.clamp(0, 5), num_classes=6).float()
        history_tensor = self._build_history_tensors(exchanges)

        log_probs = self.generator(stage_onehots, response_embs, history_tensor)
        action_log_probs = log_probs.gather(1, technique_ids.unsqueeze(1)).squeeze(1)

        # REINFORCE + entropy regularization to ensure gradient flow
        reinforce_loss = -(action_log_probs * (rewards - baseline)).mean()
        entropy = -(log_probs * log_probs.exp()).sum(dim=-1).mean()
        gen_loss = reinforce_loss - 0.01 * entropy
        gen_loss.backward()
        self.gen_optimizer.step()
        self.generator.eval()

        total_loss = disc_loss.item() + gen_loss.item()
        return {"loss": total_loss, "updated": True}

    def _build_history_tensors(self, exchanges: list[dict], max_len: int = 10) -> torch.Tensor:
        batch_size = len(exchanges)
        histories = torch.zeros(batch_size, max_len, dtype=torch.long)

        for i, ex in enumerate(exchanges):
            # History is all technique indices before this exchange, shifted by 1 for padding
            prior = [exchanges[j]["technique_idx"] + 1 for j in range(i)]
            prior = prior[-max_len:]
            padded = [0] * (max_len - len(prior)) + prior
            histories[i] = torch.tensor(padded, dtype=torch.long)

        return histories
