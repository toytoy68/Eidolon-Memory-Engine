import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.retrieval.ranking import lexical_ranking


def test_lexical_ranking_explains_content_and_metadata_matches():
    content = lexical_ranking("cuivre pompe", "pompe cuivre pour le serveur",
                              "info-a", {})
    metadata = lexical_ranking("cuivre pompe", "texte indépendant", "info-b",
                               {"context": {"topic": ["pompe cuivre"]}})
    assert content.score > metadata.score > 0
    assert content.coverage == metadata.coverage == 1
    assert content.content_coverage == 1
    assert metadata.content_coverage == 0
    assert content.phrase_in_content is False
    assert content.explanation()["policy"] == "lexical_v1"


def test_opt_in_ranking_is_stable_across_pages_and_ignores_truth_labels(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("meta", content="texte indépendant",
                         metadata={"topic": "pompe cuivre", "epistemic_status": "CONFIRMED"}))
    backend.store(Memory("content-a", content="pompe cuivre",
                         metadata={"epistemic_status": "REFUTED"}))
    backend.store(Memory("content-b", content="pompe cuivre",
                         metadata={"epistemic_status": "UNVERIFIED"}))
    first = backend.search("pompe cuivre", {"ranking": "lexical_v1", "limit": 2})
    second = backend.search("pompe cuivre", {"ranking": "lexical_v1", "limit": 2,
                                            "offset": 2})
    assert [hit.memory.information_id for hit in first + second] == [
        "content-a", "content-b", "meta",
    ]
    assert first[0].score == first[1].score
    assert first[0].metadata["ranking"]["content_coverage"] == 1
    assert backend.search("pompe cuivre", {"ranking": "lexical_v1"}) == first + second


def test_ranking_rejects_unknown_policy_and_nontext_metadata(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("info", content="cuivre", metadata={"tag": None}))
    assert backend.search("cuivre", {"ranking": "lexical_v1"})
    with pytest.raises(ValueError, match="ranking"):
        backend.search("cuivre", {"ranking": []})


def test_phrase_requires_repeated_query_terms_in_order():
    single = lexical_ranking("test test", "test", "one", {})
    repeated = lexical_ranking("test test", "test test", "two", {})
    assert single.coverage == repeated.coverage == 1
    assert single.phrase_in_content is False
    assert repeated.phrase_in_content is True
    assert repeated.score > single.score


def test_opt_in_ranking_can_find_provenance_and_relation_values(tmp_path):
    backend = FilesystemBackend(tmp_path / "persistent", tmp_path / "history")
    backend.store(Memory("info", content="unrelated",
                         provenance={"source": "atelier"},
                         relations=[{"type": "CONCERNS", "target_id": "robot"}]))
    matches = backend.search("atelier robot", {"ranking": "lexical_v1"})
    assert [hit.memory.information_id for hit in matches] == ["info"]
    assert matches[0].metadata["ranking"]["content_coverage"] == 0


def test_opt_in_ranking_indexes_numeric_values_without_boolean_noise():
    numeric = lexical_ranking("80", "other", "info", {"temperature": 80})
    boolean = lexical_ranking("true", "other", "info", {"flag": True})
    assert numeric.coverage == 1
    assert boolean.coverage == 0
