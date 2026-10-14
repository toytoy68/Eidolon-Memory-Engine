import pytest
from core.indexing.reconcile_plan import Action, Canonical
from core.indexing.worker_gate import check_upsert

SHA = "a" * 64


def gate(**overrides):
    params = dict(action=Action("INDEX_UPSERT", "doc", 1, 2, "published"),
                  canonical=Canonical(2, SHA), profile_id="owner", model_id="embedding-v1",
                  permitted=True, expected_revision=2, expected_sha256=SHA)
    params.update(overrides)
    return check_upsert(**params)


def test_matching_canonical_and_permissions_is_verified_candidate():
    result = gate()
    assert result.verified
    assert result.information_id == "doc"


@pytest.mark.parametrize("override", [
    {"permitted": False},
    {"canonical": Canonical(3, SHA)},
    {"canonical": Canonical(2, "b" * 64)},
    {"expected_revision": 3},
    {"expected_sha256": "b" * 64},
])
def test_mismatched_evidence_is_not_verified(override):
    assert not gate(**override).verified


@pytest.mark.parametrize("override", [
    {"action": Action("ENQUEUE_DELETE", "doc", None, 2, "absent")},
    {"permitted": 1},
    {"model_id": ""},
    {"profile_id": ""},
    {"expected_sha256": "invalid"},
    {"canonical": Canonical(2, "invalid")},
])
def test_malformed_or_delete_evidence_is_rejected(override):
    with pytest.raises(ValueError):
        gate(**override)
