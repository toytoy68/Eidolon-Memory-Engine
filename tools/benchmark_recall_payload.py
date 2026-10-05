# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tools/benchmark_recall_payload.py
# Description : Measure complete recall rendering on fresh disposable synthetic corpora.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Measure complete recall rendering on fresh disposable synthetic corpora."""
from dataclasses import asdict
from hashlib import sha256
import argparse
import json
from pathlib import Path
import statistics
import tempfile
from time import perf_counter

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.operations.readiness import check_readiness
from core.retrieval.contextual import ContextualRecall
from core.retrieval.payload import render
from tools.vm_acceptance import hashes
from core.persistence import has_symlink_component

SCOPE = {'goal': 'payload-benchmark'}
PREFIX = 'Sources synthétiques, réserves à respecter :\n'
SUFFIX = '\nNe pas convertir une hypothèse en fait.'


def run(*, metadata_sizes=(200, 2000, 10000), replicas=3, queries=3, budgets=(2000, 8000, 20000), temp_parent=None):
    if (type(replicas) is not int or replicas < 1 or type(queries) is not int or queries < 1
            or any(type(value) is not int or value < 1 for value in [*metadata_sizes, *budgets])):
        raise ValueError('positive sizes, budgets and repetitions required')
    if temp_parent is not None:
        temp_parent = Path(temp_parent).absolute()
        if not temp_parent.is_dir() or has_symlink_component(temp_parent):
            raise ValueError('temporary parent must be an existing real directory')
    points = []
    corpora = []
    for size in metadata_sizes:
        for replica in range(replicas):
            with tempfile.TemporaryDirectory(prefix='em-payload-bench-', dir=temp_parent) as folder:
                root = Path(folder)
                backend = FilesystemBackend(root / 'memory/persistent', root / 'memory/history')
                for index in range(8):
                    backend.store(Memory(f'item-{index:02}', content='payload measurement',
                        metadata={'epistemic_status': 'UNVERIFIED', 'availability': 'INTERMEDIATE',
                                  'context': {'scope': SCOPE}},
                        provenance={'source': 'synthetic-benchmark', 'author_role': 'ADMIN'},
                        verification={'evidence': 'E' * (size if index == 0 else 16)}))
                assert check_readiness(root)['ready']
                reader = ContextualRecall(backend)
                reader.recall('payload measurement', query_scope=SCOPE)  # Warmup, outside measured points.
                before = hashes(root)
                for repetition in range(queries):
                    start = perf_counter()
                    bundle = reader.recall('payload measurement', query_scope=SCOPE)
                    recall_seconds = perf_counter() - start
                    full = PREFIX + json.dumps(asdict(bundle), ensure_ascii=False, sort_keys=True,
                                              separators=(',', ':'), allow_nan=False) + SUFFIX
                    assert len(bundle.items) == 5 and bundle.items[0].information_id == 'item-00'
                    originals = {item.information_id: json.loads(json.dumps(asdict(item))) for item in bundle.items}
                    for budget in budgets:
                        start = perf_counter()
                        payload = render(bundle, max_payload_chars=budget, prefix=PREFIX, suffix=SUFFIX)
                        render_seconds = perf_counter() - start
                        assert payload.text.startswith(PREFIX) and payload.text.endswith(SUFFIX)
                        value = json.loads(payload.text[len(PREFIX):-len(SUFFIX)])
                        identities = tuple(item['information_id'] for item in value['items'])
                        assert identities == payload.included_ids
                        assert len(payload.text) == payload.payload_chars <= budget
                        assert all(item == originals[item['information_id']] for item in value['items'])
                        assert all(item['needs_review'] and item['epistemic_status'] == 'UNVERIFIED'
                                   and item['applicability'] == 'MATCH' for item in value['items'])
                        assert value['used_chars'] == sum(len(item['content']) for item in value['items'])
                        assert value['excluded_counts'].get('PAYLOAD_BUDGET', 0) == len(payload.omitted_ids)
                        assert set(payload.included_ids) | set(payload.omitted_ids) == set(originals)
                        points.append(dict(metadata_chars=size, corpus_replica=replica, query_repetition=repetition,
                            budget_chars=budget, recall_seconds=recall_seconds, render_seconds=render_seconds,
                            unbounded_payload_chars=len(full), payload_chars=payload.payload_chars,
                            payload_utf8_bytes=len(payload.text.encode('utf-8')), excerpt_chars=bundle.used_chars,
                            included_ids=payload.included_ids, omitted_ids=payload.omitted_ids,
                            payload_sha256=sha256(payload.text.encode('utf-8')).hexdigest()))
                assert hashes(root) == before, 'read/render modified the corpus'
                assert all(backend.get(f'item-{index:02}').revision == 1 for index in range(8))
                assert check_readiness(root)['ready']
                corpora.append(dict(metadata_chars=size, replica=replica, canonical_objects=8,
                                    files=len(before), sha256_unchanged=True, readiness=True))
    summaries = []
    for size in metadata_sizes:
        for budget in budgets:
            group = [point for point in points if point['metadata_chars'] == size and point['budget_chars'] == budget]
            summaries.append(dict(metadata_chars=size, budget_chars=budget, measurements=len(group),
                recall_median_seconds=statistics.median(point['recall_seconds'] for point in group),
                render_median_seconds=statistics.median(point['render_seconds'] for point in group),
                render_min_seconds=min(point['render_seconds'] for point in group),
                render_max_seconds=max(point['render_seconds'] for point in group),
                unbounded_payload_chars=sorted(set(point['unbounded_payload_chars'] for point in group)),
                payload_chars=sorted(set(point['payload_chars'] for point in group)),
                included_counts=sorted(set(len(point['included_ids']) for point in group))))
    return dict(status='OK', synthetic=True, temporary_parent=str(temp_parent) if temp_parent is not None else tempfile.gettempdir(),
                corpus_replicas=replicas, queries_per_warm_corpus=queries,
                points=points, summaries=summaries, corpora=corpora,
                tool_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                limitations=['character budgets only, no real tokenizer', 'render time excludes recall and network',
                             'storage filesystem must be identified separately; no isolated physical disk latency', 'synthetic metadata, no real user corpus',
                             'adapter only considers the already selected five items'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--temp-parent', type=Path, help='Existing real parent for disposable corpora')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('output must be a new file')
    report = run(temp_parent=args.temp_parent)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': report['status'], 'corpora': len(report['corpora']), 'render_points': len(report['points'])}))
    for summary in report['summaries']:
        print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
