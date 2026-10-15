# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_qdrant_server_recall_g243.py
# Description : Freshness and verified candidates through owned real HTTP Qdrant.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from uuid import uuid4

import pytest

from core.retrieval.contextual import ContextualRecall
from tests.qdrant_server_fixture import qdrant_server
from tests.test_contextual_recall import backend, store

pytest.importorskip('qdrant_client')
from core.indexing.qdrant_index import QdrantIndex, _point_id


def make_index(client, alias, *, create=False):
    return QdrantIndex(client, alias, embed=lambda _: [1., 0.],
        dimensions=2, embedding_id='recall-server-synthetic-v1', create=create)


def test_empty_then_stale_then_rebuild_match_survives_server_restart(tmp_path, qdrant_server):
    data = backend(tmp_path)
    alias = 'eidolon_recall_' + uuid4().hex
    with qdrant_server.client() as client:
        index = make_index(client, alias, create=True)
        index.rebuild(data.persistent_root)
        store(data, 'new')
        result = ContextualRecall(data, index=index).recall('power')
        assert not result.items and result.index_status.state == 'INDEX_STALE'
        index.rebuild(data.persistent_root)
        result = ContextualRecall(data, index=index).recall('power')
        assert result.index_status.state == 'INDEX_SNAPSHOT_MATCH'
        proof = result.items[0].ranking['index']['canonical_sha256']
    qdrant_server.stop()
    qdrant_server.start()
    with qdrant_server.client() as client:
        index = make_index(client, alias)
        result = ContextualRecall(data, index=index).recall('power')
        assert result.index_status.state == 'INDEX_SNAPSHOT_MATCH'
        assert result.items[0].ranking['index']['canonical_sha256'] == proof


def test_same_revision_change_excluded_until_rebuild_on_server(tmp_path, qdrant_server):
    data = backend(tmp_path)
    store(data, 'one')
    with qdrant_server.client() as client:
        index = make_index(client, 'eidolon_recall_' + uuid4().hex, create=True)
        index.rebuild(data.persistent_root)
        path = data.persistent_root / 'one.md'
        path.write_bytes(path.read_bytes().replace(b'power measurement', b'other measurement'))
        result = ContextualRecall(data, index=index).recall('power')
        assert not result.items and result.excluded_counts == {'INDEX_DIGEST_MISMATCH': 1}
        assert result.index_status.state == 'INDEX_STALE'
        index.rebuild(data.persistent_root)
        result = ContextualRecall(data, index=index).recall('power')
        assert result.items[0].content == 'other measurement'
        assert result.index_status.state == 'INDEX_SNAPSHOT_MATCH'


def test_corrupted_candidate_proof_is_refused_over_http(tmp_path, qdrant_server):
    data = backend(tmp_path)
    store(data, 'one')
    with qdrant_server.client() as client:
        index = make_index(client, 'eidolon_recall_' + uuid4().hex, create=True)
        index.rebuild(data.persistent_root)
        client.set_payload(index.alias, {'generation': 'foreign-generation'},
            points=[_point_id('one')], wait=True)
        with pytest.raises(ValueError, match='proof'):
            ContextualRecall(data, index=index).recall('power')
