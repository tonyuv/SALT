import json
from pathlib import Path


class AttackLibrary:
    def __init__(self, path: Path | None = None):
        if path is None:
            path = Path(__file__).parent.parent / "library" / "techniques.json"
        with open(path) as f:
            self.techniques: list[dict] = json.load(f)
        self._by_id = {t["id"]: t for t in self.techniques}

    def get(self, technique_id: str) -> dict | None:
        return self._by_id.get(technique_id)

    def get_by_category(self, category: str) -> list[dict]:
        return [t for t in self.techniques if t["category"] == category]

    def get_by_target_stage(self, stage: int) -> list[dict]:
        return [t for t in self.techniques if stage in t["target_stages"]]

    @property
    def technique_ids(self) -> list[str]:
        return list(self._by_id.keys())
