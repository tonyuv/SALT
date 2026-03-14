import torch
import torch.nn as nn


class Generator(nn.Module):
    def __init__(
        self,
        num_techniques: int,
        embedding_dim: int = 384,
        hidden_dim: int = 256,
        history_len: int = 10,
    ):
        super().__init__()
        self.num_techniques = num_techniques

        self.technique_embedding = nn.Embedding(num_techniques + 1, 32, padding_idx=0)
        # +1 for padding index 0

        self.history_encoder = nn.LSTM(
            input_size=32,
            hidden_size=hidden_dim // 2,
            batch_first=True,
        )

        # stage one-hot (6) + response embedding (384) + history encoding (hidden_dim//2)
        input_dim = 6 + embedding_dim + hidden_dim // 2

        self.policy = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, num_techniques),
            nn.Softmax(dim=-1),
        )

    def forward(
        self,
        current_stage_onehot: torch.Tensor,
        response_embedding: torch.Tensor,
        technique_history: torch.Tensor,
    ) -> torch.Tensor:
        hist_emb = self.technique_embedding(technique_history)
        _, (hist_hidden, _) = self.history_encoder(hist_emb)
        hist_context = hist_hidden.squeeze(0)

        combined = torch.cat(
            [current_stage_onehot, response_embedding, hist_context], dim=-1
        )

        return self.policy(combined)

    def select_technique(
        self,
        current_stage_onehot: torch.Tensor,
        response_embedding: torch.Tensor,
        technique_history: torch.Tensor,
    ) -> int:
        with torch.no_grad():
            probs = self(current_stage_onehot, response_embedding, technique_history)
            idx = torch.multinomial(probs, 1).item()
        return idx
