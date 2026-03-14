import torch
import torch.nn as nn


class Discriminator(nn.Module):
    def __init__(self, num_techniques: int, embedding_dim: int = 384, hidden_dim: int = 256):
        super().__init__()
        self.technique_embedding = nn.Embedding(num_techniques, 32)
        self.stage_embedding = nn.Embedding(6, 16)

        input_dim = embedding_dim + 32 + 16

        self.classifier = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(0.2),
        )

        self.stage_head = nn.Sequential(
            nn.Linear(hidden_dim // 2, 6),
            nn.Softmax(dim=-1),
        )

        self.confidence_head = nn.Sequential(
            nn.Linear(hidden_dim // 2, 1),
            nn.Sigmoid(),
        )

    def forward(
        self,
        response_embedding: torch.Tensor,
        technique_id: torch.Tensor,
        current_stage: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        tech_emb = self.technique_embedding(technique_id)
        stage_emb = self.stage_embedding(current_stage)

        combined = torch.cat([response_embedding, tech_emb, stage_emb], dim=-1)
        hidden = self.classifier(combined)

        stage_probs = self.stage_head(hidden)
        confidence = self.confidence_head(hidden)

        return stage_probs, confidence
