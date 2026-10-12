# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/run_semantic.py
# Description : Fixed synthetic corpus with local CPU embeddings and disposable Qdrant.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Experiment only: no durable passage-index writer or production activation.

Requires qwen3-embedding:0.6b already pulled in local Ollama and a disposable
Qdrant server on 127.0.0.1:16333. No download, corpus rewrite or threshold tuning.
Run from repository root with --out FILE. All input is the fixed synthetic corpus.
"""
import argparse
import hashlib
import http.client
import json
import math
from pathlib import Path
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from qdrant_client import QdrantClient, models
from core.indexing.port import IndexHit
from core.retrieval.archive_chunks import CHUNK_POLICY, PASSAGE_POLICY, chunk_messages
from core.retrieval.contextual import ContextualRecall
from tests.claude_memory_eval.run_baseline import CORPUS, build, evaluate, summarize

MODEL = 'qwen3-embedding:0.6b'
EXPECTED_DIGEST = 'ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d'
INSTRUCTION = 'Given a question, retrieve relevant passages from a personal memory archive that answer the question'
OPTIONS = {'num_gpu': 0, 'num_thread': 2, 'num_ctx': 2048}
DIMENSIONS = 1024
EMBEDDING_ID = f'qwen3-0.6b:{EXPECTED_DIGEST}:memory-query-v1:ctx2048:{CHUNK_POLICY}'


def ollama(path, body=None):
    # Fixed loopback endpoint, no environment proxy or redirect following.
    connection = http.client.HTTPConnection('127.0.0.1', 11434, timeout=60)
    try:
        raw = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        connection.request('GET' if body is None else 'POST', path, raw,
                           {'Content-Type': 'application/json'})
        response = connection.getresponse()
        data = response.read(4_000_001)
        if response.status != 200 or len(data) > 4_000_000:
            raise RuntimeError(f'Ollama HTTP status or response size invalid: {response.status}')
        return json.loads(data)
    finally:
        connection.close()


def verify_model():
    found = [m for m in ollama('/api/tags')['models'] if m['name'] == MODEL]
    if len(found) != 1 or found[0]['digest'] != EXPECTED_DIGEST:
        raise ValueError('missing or changed embedding model; explicit review required')


def embed(texts):
    if (not texts or len(texts) > 8 or any(not isinstance(t, str) or not t or len(t) > 16000
                                          for t in texts)):
        raise ValueError('invalid embedding batch')
    verify_model()
    result = ollama('/api/embed', {'model': MODEL, 'input': texts, 'truncate': False,
                                'keep_alive': '2m', 'options': OPTIONS})
    verify_model()
    vectors = result.get('embeddings')
    if result.get('model') != MODEL or not isinstance(vectors, list) or len(vectors) != len(texts):
        raise ValueError('embedding response mismatch')
    for vector in vectors:
        if (not isinstance(vector, list) or len(vector) != DIMENSIONS
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)
                or not 0 < math.hypot(*vector) < float('inf')):
            raise ValueError('invalid embedding vector')
    return vectors


class ExperimentCandidates:
    def __init__(self, client, collection):
        self.client, self.collection = client, collection

    def query(self, text, *, limit):
        vector = embed([f'Instruct: {INSTRUCTION}\nQuery:{text}'])[0]
        points = self.client.query_points(self.collection, query=vector, limit=limit,
                                         with_payload=True, with_vectors=False).points
        return [IndexHit(point.payload['information_id'], point.score, {
            'revision': point.payload['revision'], 'passage': point.payload['reference'],
            'policy': 'qdrant-message-passages-experiment/1', 'embedding_id': EMBEDDING_ID,
            'index_freshness': 'ISOLATED_FIXED_CORPUS'}) for point in points]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    raw = CORPUS.read_bytes()
    corpus = json.loads(raw)
    verify_model()
    version = ollama('/api/version')['version']
    client = QdrantClient(url='http://127.0.0.1:16333', timeout=5)
    collection = 'eidolon_eval_g182_' + uuid.uuid4().hex
    created = False
    try:
        with tempfile.TemporaryDirectory(prefix='eidolon-semantic-eval-') as tmp:
            backend = build(Path(tmp), corpus['documents'])
            chunks = []
            for doc in corpus['documents']:
                memory = backend.get(doc['id'])
                for chunk in chunk_messages(memory.content):
                    chunks.append((memory.information_id, memory.revision, chunk))
            client.create_collection(collection, vectors_config=models.VectorParams(
                size=DIMENSIONS, distance=models.Distance.COSINE))
            created = True
            started = time.perf_counter()
            for offset in range(0, len(chunks), 8):
                batch = chunks[offset:offset + 8]
                vectors = embed([entry[2].text for entry in batch])
                client.upsert(collection, points=[models.PointStruct(
                    id=offset + i, vector=vector, payload={'information_id': identity,
                        'revision': revision, 'reference': chunk.reference})
                    for i, ((identity, revision, chunk), vector) in enumerate(zip(batch, vectors))], wait=True)
            index_seconds = time.perf_counter() - started
            if client.count(collection, exact=True).count != len(chunks):
                raise ValueError('passage count mismatch')
            resident = [m for m in ollama('/api/ps')['models'] if m['name'] == MODEL]
            if len(resident) != 1 or resident[0].get('size_vram') != 0:
                raise ValueError('CPU-only embedding execution not verified')
            reader = ContextualRecall(backend, index=ExperimentCandidates(client, collection))
            evidence = []
            def recall(question):
                bundle = reader.recall(question)
                evidence.append({'query': question, 'items': [
                    {'id': item.information_id, 'score': item.score, 'content': item.content,
                     'reference': item.excerpt_reference, 'needs_review': item.needs_review}
                    for item in bundle.items]})
                print(json.dumps({'completed': len(evidence), 'total': len(corpus['questions'])}), flush=True)
                return bundle.items
            rows = evaluate(corpus, recall)
            result = {'schema': 'claude-memory-eval-result/1',
                'engine': 'Qwen3 embedding CPU + Qdrant passages + canonical ContextualRecall',
                'corpus_sha256': hashlib.sha256(raw).hexdigest(),
                'retrieval_only': True, 'synthetic': True, 'experimental': True,
                'model': MODEL, 'model_digest': EXPECTED_DIGEST, 'ollama_version': version,
                'embedding_id': EMBEDDING_ID, 'dimensions': DIMENSIONS,
                'options': OPTIONS, 'query_instruction': INSTRUCTION, 'truncate': False,
                'chunk_chars': 1200, 'chunk_overlap': 160, 'chunk_count': len(chunks),
                'chunk_policy': CHUNK_POLICY, 'passage_policy': PASSAGE_POLICY,
                'index_seconds': round(index_seconds, 3), 'size_vram': resident[0]['size_vram'],
                'size_resident': resident[0].get('size'), 'abstention_threshold': None,
                'summary': summarize(rows), 'rows': rows, 'evidence': evidence}
            if CORPUS.read_bytes() != raw:
                raise ValueError('evaluation corpus changed during run')
            Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
            print(json.dumps(result['summary'], ensure_ascii=False, indent=1), flush=True)
    finally:
        if created:
            client.delete_collection(collection)
        client.close()


if __name__ == '__main__':
    main()
