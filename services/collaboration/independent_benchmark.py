# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : services/collaboration/independent_benchmark.py
# Description : Same-corpus offline retrieval evaluation with explicit limits.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Runs only inside the operator sandbox. Gold labels measure reference retrieval,
not truth of declarations. Unjudged questions are excluded from accuracy metrics."""
import ast
from datetime import date
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import statistics
import time
import unicodedata

if __package__:
    from .experimental_router import classify, rerank
else:
    from experimental_router import classify, rerank

PREFIX = 'eidolon-factual-v2-'
GROUPS = [
 ('01-vm-services', [
 'Quelle machine héberge la mémoire Eidolon ?',
 'Sur quelle adresse IP trouve-t-on Memory Engine ?',
 'Quelles sont les fonctions déclarées des VM100, VM101 et VM110 ?',
 'Quelle correspondance entre VMID et IP reste à confirmer ?',
 'Quels services sont répartis entre les machines virtuelles ?']),
 ('02-vm-communications', [
 'Comment Core accède-t-il à la mémoire distante ?',
 'Le dialogue peut-il continuer pendant une panne du service mémoire ?',
 'Que se passe-t-il lorsque la connexion mémoire revient ?',
 'Quel mécanisme authentifie les échanges entre Core et Memory Engine ?',
 'Quels liens relient Ollama, Core et le Memory Bridge ?']),
 ('03-gpu-active', [
 'Quelle accélératrice a servi aux benchmarks locaux ?',
 'Combien de mémoire possède la V100 des essais ?',
 'L ECC était-il activé sur la carte utilisée ?',
 'Les anciens benchmarks identifient-ils le GPU de chaque requête ?',
 'Quelle carte graphique était utilisée lors des essais d inférence ?']),
 ('04-gpu-available', [
 'Quelle carte de douze gigaoctets est disponible ?',
 'La GTX 1060 participait-elle aux premiers essais Core ?',
 'Quels GPU sont disponibles sans affectation confirmée à une VM ?',
 'Une carte disponible est-elle nécessairement installée ?',
 'Quel est le statut déclaré de la RTX 2060 ?']),
 ('05-gpu-planned', [
 'Quelle évolution vers deux accélérateurs est projetée ?',
 'Quel volume de VRAM physique est visé avec deux V100 de 32 Go ?',
 'NVLink fusionne-t-il automatiquement la mémoire pour tous les moteurs ?',
 'Quelles validations restent nécessaires pour le double SXM2 ?',
 'Quel adaptateur est prévu pour les futures cartes ?']),
 ('06-hardware-decisions', [
 'Quel processeur et quelle RAM sont déclarés pour le serveur ?',
 'Quelle carte mère est prévue pour remplacement ?',
 'Quelles décisions matérielles sont actuelles et lesquelles restent des projets ?',
 'Quel débit réseau est déclaré pour le serveur Proxmox ?',
 'Les deux V100 32 Go sont-elles une installation confirmée ?']),
 ('07-gpu-history', [
 'Quelles familles RTX avaient été envisagées avant la V100 ?',
 'Quel était le projet GPU initial ?',
 'Comment les choix de cartes graphiques ont-ils évolué ?',
 'Les anciennes hypothèses matérielles décrivent-elles le serveur actuel ?',
 'Quels choix historiques ont précédé les essais Tesla ?']),
]
UNJUDGED = [
 'Comment importer de nouveaux souvenirs ?',
 'Quelle commande diagnostique le Memory Bridge ?',
 'Quel est le rôle de SOUL dans Eidolon Core ?',
 'Quel est le numéro de série exact de la V100 ?',
 'Combien de pannes de ventilateur ont été mesurées en 2027 ?',
]
CASES = [{'question': q, 'expected': [PREFIX + identity], 'judged': True}
         for identity, questions in GROUPS for q in questions]
CASES += [{'question': q, 'expected': [], 'judged': False} for q in UNJUDGED]


def original_router():
    path = Path(__file__).parent / 'baselines/router_v3_original.py'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != '3d8ccad793dec2ffbebbef4f5a272afcf45365f861bd7616afb5cb3899049ad3':
        raise ValueError('Original router baseline changed')
    wanted = {'TOPICS', 'ADMIN', 'HISTORY', 'PROCEDURE', 'CURRENT',
              'normalize', 'contains', 'classify', 'detect_topics', 'domain_of', 'score_item'}
    nodes = [n for n in ast.parse(raw).body
             if isinstance(n, ast.FunctionDef) and n.name in wanted
             or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in wanted for t in n.targets)]
    namespace = {'re': re, 'unicodedata': unicodedata}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'audited-router-v3', 'exec'), namespace)
    return namespace


def eligible(memory, historical=False):
    from core.routing.policy import applicability
    if historical:
        return True
    if memory.metadata.get('epistemic_status') in {'REFUTED', 'SUPERSEDED'}:
        return False
    try:
        return applicability(memory, {}, at='2026-10-11T00:00:00Z',
              unresolved_conflict=memory.metadata.get('epistemic_status') == 'CONFLICTED') not in {'EXPIRED', 'OUT_OF_SCOPE'}
    except (ValueError, TypeError, AttributeError):
        return True  # Unknown applicability stays review-required, never confirmed.


def metric(ranking, expected):
    top = ranking[:5]
    ranks = [i for i, identity in enumerate(ranking, 1) if identity in expected]
    return {'reference_recall_at_5': len(set(top) & set(expected)) / len(expected),
            'reciprocal_rank_at_5': 1 / min(ranks) if ranks and min(ranks) <= 5 else 0,
            'candidate_reference_recall': len(set(ranking) & set(expected)) / len(expected)}


def main():
    from core.backend.filesystem import FilesystemBackend
    from core.retrieval.contextual import ContextualRecall
    import torch
    from sentence_transformers import SentenceTransformer, CrossEncoder
    torch.set_num_threads(2)
    root = Path('/tmp/work/corpus')
    backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
    memories = {m.information_id: m for m in backend.list(limit=10000)}
    if not memories or len(memories) > 1000:
        raise ValueError('Expected 1–1000 readable corpus records')
    missing = sorted({x for c in CASES for x in c['expected']} - memories.keys())
    if missing:
        raise ValueError('Gold references missing: ' + ', '.join(missing))
    recall = ContextualRecall(backend)
    pending = {i for i in memories if (backend.pending_delete_root / (i + '.json')).exists()
               and backend._load_delete_request(backend.pending_delete_root / (i + '.json'), i)['status'] == 'PENDING_DELETE'}
    original = original_router()
    ids = sorted(memories)
    texts = [' > '.join(memories[i].metadata.get('reference', {}).get('heading_path', []))
             + '\n' + memories[i].content for i in ids]
    load_start = time.perf_counter()
    model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
              device='cpu', cache_folder='/tmp/runtime/models', local_files_only=True)
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=8, show_progress_bar=False)
    vector_setup_ms = (time.perf_counter() - load_start) * 1000
    # CrossEncoder is optional: absent offline cache is reported, never downloaded.
    load_start = time.perf_counter()
    try:
        encoder = CrossEncoder('cross-encoder/mmarco-mMiniLMv2-L12-H384-v1',
                  device='cpu', cache_folder='/tmp/runtime/models', max_length=512, local_files_only=True)
        encoder_error = None
    except Exception as exc:
        encoder = None
        encoder_error = str(exc)[:1000]
    encoder_load_ms = (time.perf_counter() - load_start) * 1000
    results = []
    for case in CASES:
        query = case['question']
        mode = classify(query, date(2026, 10, 11))
        started = time.perf_counter()
        lexical_bundle = recall.recall(query, mode='historical' if mode == 'historical' else 'operational',
                                       at='2026-10-11T00:00:00Z', max_items=1000, max_chars=2000000, max_item_chars=2000)
        lexical_pairs = [(i.information_id, float(i.score or 0)) for i in lexical_bundle.items]
        lexical = [i for i, _ in lexical_pairs]
        lexical_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        factual = [i for i in lexical if memories[i].metadata.get('type') == 'FACTUAL_REFERENCE']
        factual_ms = lexical_ms + (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        routed = rerank(query, lexical_pairs, memories, date(2026, 10, 11))
        routed_ids = [i['id'] for i in routed]
        router_ms = lexical_ms + (time.perf_counter() - started) * 1000
        # Original uses operational recall even on historical queries.
        started = time.perf_counter()
        legacy = recall.recall(query, max_items=171, max_chars=150000, max_item_chars=800)
        legacy_pairs = [(i.information_id, float(i.score or 0)) for i in legacy.items]
        old_mode = original['classify'](query)
        old_topics = original['detect_topics'](query)
        legacy_rank = sorted(legacy_pairs, key=lambda x: (
            -original['score_item'](memories[x[0]], x[1], old_mode, old_topics), x[0]))
        legacy_ids = [i for i, _ in legacy_rank]
        legacy_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        vector = model.encode(query, normalize_embeddings=True)
        scores = embeddings @ vector
        semantic = sorted(zip(ids, scores), key=lambda x: (-float(x[1]), x[0]))
        vector_ids = [i for i, _ in semantic if eligible(memories[i], mode == 'historical')
                      and (mode == 'historical' or i not in pending)]
        vector_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        fusion = {}
        for ranking in (lexical[:20], vector_ids[:20]):
            for position, identity in enumerate(ranking, 1):
                fusion[identity] = fusion.get(identity, 0) + 1 / (60 + position)
        hybrid = sorted(fusion, key=lambda i: (-fusion[i], i))
        hybrid_ms = lexical_ms + vector_ms + (time.perf_counter() - started) * 1000
        rankings = {'lexical': lexical, 'factual': factual, 'router_v3': legacy_ids,
                    'router_v4': routed_ids, 'vector': vector_ids, 'hybrid_rrf': hybrid}
        times = dict(zip(rankings, [lexical_ms, factual_ms, legacy_ms, router_ms, vector_ms, hybrid_ms]))
        if encoder and hybrid:
            started = time.perf_counter()
            pair_scores = encoder.predict([(query, memories[i].content) for i in hybrid],
                                          batch_size=8, show_progress_bar=False)
            rankings['cross_encoder'] = [i for i, _ in sorted(zip(hybrid, pair_scores), key=lambda x: (-float(x[1]), x[0]))]
            times['cross_encoder'] = hybrid_ms + (time.perf_counter() - started) * 1000
        methods = {}
        for name, ranking in rankings.items():
            methods[name] = {'top5': ranking[:5], 'candidate_count': len(ranking),
                             'elapsed_ms': round(times[name], 3)}
            if case['judged']:
                methods[name]['metrics'] = metric(ranking, case['expected'])
        results.append({**case, 'mode_v3': old_mode, 'mode_v4': mode, 'methods': methods})
    summary = {}
    for name in results[0]['methods']:
        measured = [r['methods'][name] for r in results if name in r['methods']]
        judged = [x['metrics'] for x in measured if 'metrics' in x]
        latencies = sorted(x['elapsed_ms'] for x in measured)
        summary[name] = {'judged_questions': len(judged),
          'reference_recall_at_5': statistics.mean(x['reference_recall_at_5'] for x in judged),
          'mrr_at_5': statistics.mean(x['reciprocal_rank_at_5'] for x in judged),
          'mean_ms': statistics.mean(latencies), 'p95_ms': latencies[int(.95 * (len(latencies) - 1))]}
    selected = {i for r in results for method in r['methods'].values() for i in method['top5']}
    provenance = {i: {'content_sha256': hashlib.sha256(memories[i].content.encode()).hexdigest(),
        'provenance': memories[i].provenance, 'temporal': memories[i].temporal,
        'verification': memories[i].verification,
        'epistemic_status': memories[i].metadata.get('epistemic_status'),
        'review_required': memories[i].metadata.get('epistemic_status') != 'CONFIRMED'} for i in sorted(selected)}
    versions = {}
    for name in ('sentence-transformers', 'torch', 'transformers'):
        versions[name] = importlib.metadata.version(name)
    payload = {'schema': 'eidolon-independent-benchmark/1', 'questions': len(CASES),
       'judged': 35, 'unjudged': 5, 'corpus_records': len(memories), 'summary': summary,
       'setup': {'vector_encoding_and_load_ms': vector_setup_ms, 'cross_encoder_load_ms': encoder_load_ms,
                 'cross_encoder_error': encoder_error, 'versions': versions},
       'results': results, 'selected_provenance': provenance,
       'limitations': ['Gold labels are provisional card relevance, not validated real-world truth.',
          '35 judged queries concern seven factual cards; five wider queries remain unjudged.',
          'Vector retrieval uses exact in-memory cosine over the same snapshot, not Qdrant timings.',
          'No automatic content-answer or temporal truth score. Unknown evidence requires review.',
          'Corrected operational methods use 2026-10-11T00:00:00Z; original router preserves its implicit-time behavior.',
          'Latency includes query retrieval but excludes model load and corpus embedding setup.']}
    Path('/tmp/work/result.json').write_text(json.dumps(payload, ensure_ascii=True))


if __name__ == '__main__':
    main()
