import pytest
from salt_agent.library import AttackLibrary


def test_load_techniques():
    lib = AttackLibrary()
    assert len(lib.techniques) > 0


def test_get_technique_by_id():
    lib = AttackLibrary()
    technique = lib.get("PI-001")
    assert technique is not None
    assert technique["category"] == "prompt_injection"


def test_get_nonexistent_technique():
    lib = AttackLibrary()
    technique = lib.get("FAKE-999")
    assert technique is None


def test_get_by_category():
    lib = AttackLibrary()
    recon = lib.get_by_category("recon_tasking")
    assert len(recon) >= 3
    assert all(t["category"] == "recon_tasking" for t in recon)


def test_get_by_target_stage():
    lib = AttackLibrary()
    stage_1 = lib.get_by_target_stage(1)
    assert len(stage_1) > 0
    assert all(1 in t["target_stages"] for t in stage_1)


def test_all_technique_ids_unique():
    lib = AttackLibrary()
    ids = [t["id"] for t in lib.techniques]
    assert len(ids) == len(set(ids))
