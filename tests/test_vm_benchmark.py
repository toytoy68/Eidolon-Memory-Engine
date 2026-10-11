"""Meaningful boundary, snapshot and historical-retrieval regression checks."""
from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.collaboration.experimental_router import classify, rerank
from services.collaboration.vm_benchmark import snapshot, sandbox_argv, status
from services.collaboration.vm_gateway import dispatch, inventory
from services.collaboration.independent_benchmark import metric, original_router, CASES


@pytest.mark.parametrize('query,expected', [
 ('Quelle est la configuration actuelle en 2026 ?', 'factual'),
 ('Comment installer le premier agent ?', 'documentary'),
 ('Quel GPU utilisions-nous avant ?', 'historical'),
 ('Quelle sera la configuration en 2027 ?', 'general'),
 ('Quel était le projet GPU initial ?', 'historical'),
 ('Quels composants sont encore à installer ?', 'general'),
])
def test_intent_regressions(query, expected):
    assert classify(query, date(2026, 10, 11)) == expected


def test_inventory_skips_links_and_hidden_files(tmp_path):
    (tmp_path / 'router.py').write_text('pass')
    (tmp_path / '.private.json').write_text('secret')
    (tmp_path / 'leak.py').symlink_to('/etc/passwd')
    result = inventory(tmp_path)
    assert result == {'files': [{'path': 'router.py', 'bytes': 4}], 'truncated': False}
    assert dispatch({'action': 'inventory', 'root': 'tools'}, {'tools': tmp_path}) == result


@pytest.mark.parametrize('payload', [
 {'action': 'benchmark_start', 'command': 'id'},
 {'action': 'benchmark_start'},
 {'action': 'benchmark_status', 'job_id': '../credentials'},
 {'action': 'inventory', 'root': 'outside'},
])
def test_execution_is_disabled_without_operator_configuration(tmp_path, payload):
    with pytest.raises(ValueError):
        dispatch(payload, {'tools': tmp_path})


def test_snapshot_is_disposable_and_rejects_links(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    (source / 'a.md').write_text('original')
    (source / '.lock').write_text('ignored')
    dest = tmp_path / 'dest'
    provenance = snapshot(source, dest)
    assert provenance['files'] == 1
    (dest / 'a.md').write_text('experiment')
    assert (source / 'a.md').read_text() == 'original'
    (source / 'link.md').symlink_to(source / 'a.md')
    with pytest.raises((ValueError, OSError)):
        snapshot(source, tmp_path / 'reject')


def test_bwrap_has_no_network_or_writable_original_corpus():
    argv = sandbox_argv({'lab': '/home/toytoy/lab', 'repo': '/opt/repo'}, Path('/tmp/stage'))
    assert '--unshare-all' in argv
    assert '--share-net' not in argv
    assert argv[argv.index('--bind') + 1:argv.index('--bind') + 3] == ['/tmp/stage', '/tmp/work']
    assert '--clearenv' in argv
    assert 'HF_HUB_OFFLINE' in argv
    assert argv[-2:] == ['/tmp/runtime/.venv/bin/python', '/tmp/benchmark-code/independent_benchmark.py']


def test_job_id_cannot_read_arbitrary_file(tmp_path):
    for identity in ['../secret', '/etc/passwd', 'a'*33, '']:
        with pytest.raises(ValueError):
            status({'jobs': str(tmp_path)}, identity)
    identity = 'a'*32
    (tmp_path / identity).mkdir()
    (tmp_path / identity / 'status.json').symlink_to('/etc/passwd')
    with pytest.raises(OSError):
        status({'jobs': str(tmp_path)}, identity)


def test_original_baseline_preserved_and_metrics_not_precision():
    original = original_router()
    assert original['classify']('Quelle sera la configuration en 2027 ?') == 'historical'
    assert len(CASES) == 40
    assert sum(c['judged'] for c in CASES) == 35
    metrics = metric(['noise', 'right', 'noise2'], ['right'])
    assert metrics['reference_recall_at_5'] == 1
    assert metrics['reciprocal_rank_at_5'] == .5


def test_reranking_reports_real_score_without_modifying_memory():
    memory = SimpleNamespace(metadata={'type': 'FACTUAL_REFERENCE', 'reference': {'domain': 'hardware'}})
    ranked = rerank('Quel GPU actuel ?', [('gpu', .5)], {'gpu': memory}, date(2026, 10, 11))
    assert ranked[0]['original_score'] == .5
    assert ranked[0]['score'] > .5
    assert memory.metadata == {'type': 'FACTUAL_REFERENCE', 'reference': {'domain': 'hardware'}}


def test_superseded_evidence_available_in_historical_recall_only(tmp_path):
    from core.backend.filesystem import FilesystemBackend
    from core.backend.models import Memory
    from core.retrieval.contextual import ContextualRecall
    backend = FilesystemBackend(tmp_path / 'memory/persistent', tmp_path / 'memory/history')
    memory = Memory('old-gpu', content='ancienne carte graphique gpu',
                    metadata={'epistemic_status': 'SUPERSEDED', 'context': {}},
                    provenance={'source': 'synthetic'}, temporal={}, verification={})
    backend.store(memory)
    recall = ContextualRecall(backend)
    assert not recall.recall('gpu').items
    result = recall.recall('gpu', mode='historical')
    assert result.items[0].information_id == 'old-gpu'
    assert result.items[0].needs_review
