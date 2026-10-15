# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_index_runtime_g269.py
# Description : Runtime pinning, canonical bridge and refusal integration
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from contextlib import closing
from dataclasses import asdict, replace
import json
import pytest
from core.indexing.runtime import IndexRuntime, OllamaEmbedding, load_runtime
from core.indexing.qdrant_index import QdrantIndex
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from services.memory_bridge import build_recall
from qdrant_client import QdrantClient


def config():
    return IndexRuntime("eidolon_g269", "test:latest", "a"*64, 2, "Retrieve",11434,6333,3,4096,2048)


def test_query_and_document_preprocessing_are_separate():
    calls=[]
    with closing(QdrantClient(":memory:")) as client:
        index=QdrantIndex(client,"eidolon_g269",dimensions=2,embedding_id="fixture",create=True,
                          embed=lambda text: calls.append(("document",text)) or [1.,0.],
                          query_embed=lambda text: calls.append(("query",text)) or [1.,0.])
        index.upsert(Memory("a",content="document"))
        assert index.query("question")[0].information_id == "a"
    assert calls == [("document","document"),("query","question")]


def test_bridge_really_uses_supplied_index(tmp_path):
    backend=FilesystemBackend(tmp_path/"memory/persistent",tmp_path/"memory/history")
    backend.store(Memory("a", content="different wording"))
    with closing(QdrantClient(":memory:")) as client:
        index=QdrantIndex(client,"eidolon_g269",dimensions=2,embedding_id="fixture",create=True,
                          embed=lambda _: [1.,0.])
        index.rebuild(backend.persistent_root)
        recall=build_recall(tmp_path,index=index)
        assert recall.index is index
        bundle=recall.recall("question", max_items=1, max_chars=500, max_item_chars=500)
        assert bundle.items[0].information_id == "a"
        assert bundle.index_status.state == "INDEX_SNAPSHOT_MATCH"


def test_config_strict_offline_and_identity(tmp_path):
    path=tmp_path/"runtime.json"
    path.write_text(json.dumps({"schema":"eidolon-index-runtime/1",**asdict(config())}))
    assert load_runtime(path)==config()
    assert replace(config(),ollama_port=12345).embedding_id == config().embedding_id
    for key,value in [("query_instruction","Other"),("num_ctx",4096),("model_digest","b"*64)]:
        assert replace(config(),**{key:value}).embedding_id != config().embedding_id
    path.write_text('{"schema":"eidolon-index-runtime/1","schema":"bad"}')
    with pytest.raises(ValueError): load_runtime(path)


@pytest.mark.parametrize("key,value", [("dimensions",True),("timeout_seconds",0),("qdrant_port",80),
    ("model_digest","latest"),("alias","other"),("max_input_chars",0),("query_instruction","a\nb")])
def test_bad_config(key,value):
    with pytest.raises(ValueError): replace(config(),**{key:value})


def fake_embedding(monkeypatch, *, vector=None, changed=False):
    embedding=OllamaEmbedding(config());calls=[]
    def request(method,path,payload=None):
        calls.append((method,path,payload))
        if path=="/api/tags":
            return {"models":[{"name":"test:latest", "digest":("b" if changed and len(calls)>1 else "a")*64}]}
        return {"model":"test:latest","embeddings":[[1.,0.] if vector is None else vector]}
    monkeypatch.setattr(embedding,"_request",request)
    return embedding,calls


def test_embedding_model_pin_cpu_and_no_truncation(monkeypatch):
    embedding,calls=fake_embedding(monkeypatch)
    assert embedding.query("question")==[1.,0.]
    assert [c[1] for c in calls]==["/api/tags","/api/embed","/api/tags"]
    payload=calls[1][2]
    assert payload["input"]==["Instruct: Retrieve\nQuery:question"]
    assert payload["truncate"] is False and payload["options"]["num_gpu"]==0


@pytest.mark.parametrize("vector", [[True,0],[0,0],[float("nan"),1],[1]])
def test_bad_embeddings_refuse(monkeypatch,vector):
    embedding,_=fake_embedding(monkeypatch,vector=vector)
    with pytest.raises(ValueError): embedding("doc")


def test_model_changed_during_request_refuses(monkeypatch):
    embedding,_=fake_embedding(monkeypatch,changed=True)
    with pytest.raises(ValueError,match="changed"): embedding("doc")


def test_input_budget_before_network(monkeypatch):
    embedding,calls=fake_embedding(monkeypatch)
    with pytest.raises(ValueError): embedding("x"*4097)
    assert calls==[]


def test_storage_check_rejects_index_before_any_effect(tmp_path):
    import subprocess,sys
    result=subprocess.run([sys.executable,"-m","services.memory_bridge","--root",str(tmp_path/"absent"),
        "--check-storage","--index-config",str(tmp_path/"missing.json")],capture_output=True)
    assert result.returncode==64 and not (tmp_path/"absent").exists()


def test_open_index_requires_existing_alias_and_disables_proxies(monkeypatch):
    import qdrant_client
    from core.indexing.runtime import open_index
    real=qdrant_client.QdrantClient
    options=[]
    def client(**kwargs):
        options.append(kwargs)
        return real(":memory:")
    monkeypatch.setattr(qdrant_client,"QdrantClient",client)
    with pytest.raises(ValueError,match="explicit create"):
        open_index(config())
    index=open_index(config(),create=True)
    try: assert index.status().documents==0
    finally:index.client.close()
    assert all(o["trust_env"] is False and o["url"]=="http://127.0.0.1:6333" for o in options)


def test_http_transport_bounded_no_redirect_and_closed(monkeypatch):
    import core.indexing.runtime as runtime
    calls=[]
    class Response:
        status=302
        def read(self,limit):
            calls.append(("read",limit));return b'{"models": []}'
    class Connection:
        def __init__(self,*args,**kwargs): calls.append(("open",args,kwargs))
        def request(self,*args):calls.append(("request",args))
        def getresponse(self):return Response()
        def close(self):calls.append(("close",))
    monkeypatch.setattr(runtime.http.client,"HTTPConnection",Connection)
    embedding=OllamaEmbedding(config())
    with pytest.raises(ValueError):embedding.verify_model()
    assert calls[-1]==("close",) and not any(c[0]=="read" for c in calls)
    Response.status=200
    with pytest.raises(ValueError,match="absent"):embedding.verify_model()
    assert ("read",4*1024*1024+1) in calls and calls[-1]==("close",)
    assert calls[0][1]==("127.0.0.1",11434)
