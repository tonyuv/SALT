from pydantic import BaseModel


class AttackRequest(BaseModel):
    pass


class AttackResponse(BaseModel):
    attack_id: str
    technique_ids: list[str]
    payload: str


class EvaluateRequest(BaseModel):
    attack_id: str
    target_response: str
    tool_calls: list[dict] = []


class EvaluateResponse(BaseModel):
    kill_chain_stage: int
    confidence: float
    reasoning: str


class ModelStatus(BaseModel):
    status: str
    techniques_loaded: int
    total_attacks_generated: int
    total_evaluations: int
