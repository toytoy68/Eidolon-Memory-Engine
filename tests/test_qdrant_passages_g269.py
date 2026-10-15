# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_qdrant_passages_g269.py
# Description : Persisted passage citations, failures and document-worker separation
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from contextlib import closing
import pytest
from qdrant_client import QdrantClient
from core.indexing.qdrant_passages import QdrantPassageIndex
from core.indexing.qdrant_index import QdrantIndex
from core.retrieval.contextual import ContextualRecall
from core.backend.models import Memory
from tests.test_archive_chunks import store_archive
from tests.test_contextual_recall import backend
from tests.test_qdrant_index import embed

@pytest.fixture
def index():
    with closing(QdrantClient(":memory:")) as client:
        yield QdrantPassageIndex(client,"eidolon_passages",embed=embed,dimensions=32,embedding_id="synthetic",create=True)

def test_archive_quote_survives_reopen_without_index_body(tmp_path,index):
    data=backend(tmp_path)
    archive=store_archive(data,["Ne pas acheter la V100 maintenant.","Garder la carte actuelle."])
    index.rebuild(data.persistent_root)
    reopened=QdrantPassageIndex(index.client,index.alias,embed=embed,dimensions=32,embedding_id="synthetic")
    result=ContextualRecall(data,index=reopened).recall("V100")
    item=result.items[0]
    assert (item.information_id,item.revision)==("archive",archive.revision)
    assert item.content.startswith("Ne pas")
    assert {"message_index","start","end"}<=item.excerpt_reference.keys()
    assert result.index_status.state=="INDEX_SNAPSHOT_MATCH"
    points,_=index.client.scroll(index.alias,limit=100,with_payload=True)
    assert "Ne pas" not in repr([p.payload for p in points])
    with pytest.raises(ValueError):
        QdrantIndex(index.client,index.alias,embed=embed,dimensions=32,embedding_id="synthetic")


def test_source_change_keeps_old_alias_and_recall_rejects_old_digest(tmp_path,index):
    data=backend(tmp_path);store_archive(data,["V100 hardware."])
    index.rebuild(data.persistent_root);generation=index.active_generation()
    real=index.embed
    def changing(text):
        p=data.persistent_root/"archive.md";p.write_bytes(p.read_bytes()+b"\n")
        return real(text)
    index.embed=changing
    with pytest.raises(ValueError,match="changed"): index.rebuild(data.persistent_root)
    index.embed=real
    assert index.active_generation()==generation
    assert not ContextualRecall(data,index=index).recall("V100").items


def test_mixed_document_and_archive(tmp_path,index):
    data=backend(tmp_path);store_archive(data,["V100 hardware."])
    data.store(Memory("normal",content="soup recipe"))
    index.rebuild(data.persistent_root)
    assert index.status().points==2
    assert {h.information_id for h in index.query("hardware soup",limit=10)}=={"normal","archive"}

@pytest.mark.parametrize("method,args",[("upsert",(Memory("a",content="x"),)),("delete",("a",)),
                                      ("evidence_for",("a",)),("inventory_page",())])
def test_incremental_api_refused(index,method,args):
    with pytest.raises(ValueError,match="full rebuild"):getattr(index,method)(*args)


def test_embedding_failure_does_not_publish_partial_archive(tmp_path,index):
    data=backend(tmp_path);store_archive(data,["V100 "*1000])
    original=index.active_generation();count=[]
    def failed(text):
        count.append(1)
        if len(count)==2:raise OSError("offline")
        return embed(text)
    index.embed=failed
    with pytest.raises(OSError):index.rebuild(data.persistent_root)
    assert index.active_generation()==original
