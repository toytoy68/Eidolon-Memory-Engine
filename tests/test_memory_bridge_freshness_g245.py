# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_memory_bridge_freshness_g245.py
# Description : Canonical freshness and proofs cross the actual HTTP bridge.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import hashlib
import json

from core.retrieval.contextual import ContextualRecall
from tests.test_contextual_recall import backend, store
from tests.test_qdrant_index import client, index  # noqa: F401
from tests.test_memory_bridge_limits_g245 import request, server


def test_empty_stale_then_proven_recall_survives_http_serialization(tmp_path, index):
    data = backend(tmp_path)
    index.rebuild(data.persistent_root)
    store(data, 'new')
    with server(ContextualRecall(data, index=index), timeout=2) as (httpd, _):
        code, body = request(httpd)
        result = json.loads(body)
        assert code == 200 and result['schema'] == 'eidolon-memory-recall/1'
        assert result['result']['items'] == []
        assert result['result']['index_status']['state'] == 'INDEX_STALE'
        index.rebuild(data.persistent_root)
        path = data.persistent_root / 'new.md'
        before = path.read_bytes()
        code, body = request(httpd)
        result = json.loads(body)['result']
        assert code == 200 and result['index_status']['state'] == 'INDEX_SNAPSHOT_MATCH'
        assert result['items'][0]['ranking']['index']['canonical_sha256'] == hashlib.sha256(before).hexdigest()
        assert path.read_bytes() == before
        path.write_bytes(before.replace(b'power measurement', b'other measurement'))
        code, body = request(httpd)
        result = json.loads(body)['result']
        assert code == 200 and result['index_status']['state'] == 'INDEX_STALE'
        assert result['items'] == [] and result['excluded_counts'] == {'INDEX_DIGEST_MISMATCH': 1}


def test_index_failure_is_sanitized_over_http_without_lexical_fallback(tmp_path, index):
    data = backend(tmp_path)
    store(data, 'new')
    index.rebuild(data.persistent_root)
    def unavailable(_):
        raise ConnectionError('private path /secret or credential never returned')
    index.embed = unavailable
    with server(ContextualRecall(data, index=index)) as (httpd, _):
        code, body = request(httpd)
        assert code == 503 and json.loads(body) == {'error': 'RECALL_UNAVAILABLE'}
        assert b'secret' not in body and b'power' not in body
