# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_rebuild_staging_cleanup.py
# Description : Refus de suppression des générations publiées ou ambiguës
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import pytest
from qdrant_client import models
from tests.test_qdrant_index import client, index
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory

def source(tmp_path):
    root = tmp_path / "persistent"
    FilesystemBackend(root, tmp_path / "history").store(Memory("new", content="fibre"))
    return root

def names(client):
    return {c.name for c in client.get_collections().collections}

def test_unpublished_embedding_failure_removes_only_new_staging(index, client, tmp_path):
    before = names(client)
    def fail(_): raise RuntimeError("embedding offline")
    index.embed = fail
    with pytest.raises(RuntimeError, match="embedding offline"):
        index.rebuild(source(tmp_path))
    assert names(client) == before

def test_alias_publication_timeout_retains_possible_target(index, client, tmp_path, monkeypatch):
    before = names(client)
    def timeout(*args, **kwargs): raise TimeoutError("unknown publication")
    monkeypatch.setattr(client, "update_collection_aliases", timeout)
    with pytest.raises(TimeoutError):
        index.rebuild(source(tmp_path))
    assert len(names(client) - before) == 1
    monkeypatch.undo()

def test_other_alias_protects_staging(index, client, tmp_path, monkeypatch):
    original = index._generation
    alias = index.alias + "_reader"
    def published_elsewhere():
        generation = original()
        client.update_collection_aliases([models.CreateAliasOperation(
            create_alias=models.CreateAlias(collection_name=generation, alias_name=alias))])
        return generation
    monkeypatch.setattr(index, "_generation", published_elsewhere)
    def fail(_): raise RuntimeError("embedding offline")
    index.embed = fail
    before = names(client)
    with pytest.raises(RuntimeError):
        index.rebuild(source(tmp_path))
    assert len(names(client) - before) == 1
    client.update_collection_aliases([models.DeleteAliasOperation(
        delete_alias=models.DeleteAlias(alias_name=alias))])

def test_cleanup_failure_keeps_original_error(index, client, tmp_path, monkeypatch):
    def fail(_): raise ValueError("source invalid")
    def unavailable(*args, **kwargs): raise TimeoutError("delete unavailable")
    index.embed = fail
    monkeypatch.setattr(client, "delete_collection", unavailable)
    with pytest.raises(ValueError, match="source invalid") as caught:
        index.rebuild(source(tmp_path))
    assert "staging cleanup unconfirmed" in str(caught.value.__notes__)
    monkeypatch.undo()
