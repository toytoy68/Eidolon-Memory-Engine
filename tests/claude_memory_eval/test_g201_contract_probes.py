# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_g201_contract_probes.py
# Description : Cas de test proposés par Claude pour les décisions G201 : passages, retard d'index, calibration
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Executable acceptance cases for GPT's G201 decisions (Claude, own file). Strict xfail = not built yet;
each turns red the day the behaviour exists, so the probe is then promoted to an ordinary test.
The only names assumed are the ones G201 chose (INDEX_STALE / INDEX_PENDING); placement is left free."""
from collections import Counter
import hashlib
import json
from pathlib import Path

import pytest

from core.retrieval.contextual import ContextualRecall
from tests.test_archive_chunks import store_archive
from tests.test_contextual_recall import backend, store, STAMP
from tests.test_qdrant_index import client, index  # noqa: F401  (fixtures)

EVAL = Path(__file__).resolve().parents[2] / 'docs' / 'claude-memory-eval'
DEV_SHA256 = '244b8fd5cb0775451a4c1b6dc33edbb0ea1f144fe269823291f5632f71563780'


def test_calibration_set_is_frozen_and_disjoint_from_the_held_out_corpus():
    raw = (EVAL / 'dev-calibration-v1.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == DEV_SHA256
    dev = json.loads(raw)['questions']
    held_out = json.loads((EVAL / 'corpus-v1.json').read_text())
    documents = {d['id'] for d in held_out['documents']}
    assert Counter(q['category'] for q in dev) == {'direct': 8, 'paraphrase': 8, 'off_topic': 8}
    assert not {q['question'] for q in dev} & {q['question'] for q in held_out['questions']}
    assert all(set(q['expected']) <= documents for q in dev)
    assert all(q['expected'] == [] for q in dev if q['category'] == 'off_topic')


@pytest.mark.xfail(strict=True, reason='G201 Q2 not built yet: changes after the last indexing must be '
                   'signalled (INDEX_STALE or INDEX_PENDING), never silently absent from semantic recall')
def test_unindexed_changes_are_signalled_in_the_result(tmp_path, index):
    data = backend(tmp_path)
    store(data, 'first')
    index.rebuild(data.persistent_root)
    store(data, 'second', content='power second measurement')
    result = ContextualRecall(data, index=index).recall('second measurement', query_scope={'goal': 'efficiency'}, at=STAMP)
    assert 'INDEX_STALE' in repr(result) or 'INDEX_PENDING' in repr(result)


@pytest.mark.xfail(strict=True, reason='G201 Q1 (passages in production) not built yet: an archive passage '
                   'found through the production index must carry document, revision/digest and position, '
                   'and be re-read from the Markdown before citation')
def test_production_index_returns_verified_archive_passages(tmp_path, index):
    data = backend(tmp_path)
    archive = store_archive(data, ['Ne pas acheter la V100 maintenant.', 'Garder la carte actuelle.'])
    index.rebuild(data.persistent_root)
    item = ContextualRecall(data, index=index).recall('V100').items[0]
    reference = item.excerpt_reference
    assert (item.information_id, item.revision) == ('archive', archive.revision)
    assert {'message_index', 'start', 'end'} <= set(reference)
    assert item.content.startswith('Ne pas')                     # negation kept (A5-02, P3)


@pytest.mark.xfail(strict=True, reason='G201 Q3 not built yet: a failed rebuild must not leave an unreferenced '
                   'generation, and any cleanup must spare the aliased generation and readers in flight')
def test_retention_never_removes_the_live_generation_and_leaves_no_orphan(tmp_path, index, client):
    data = backend(tmp_path)
    store(data, 'item')
    index.rebuild(data.persistent_root)
    live = {a.alias_name: a.collection_name for a in client.get_aliases().aliases}[index.alias]
    before = {c.name for c in client.get_collections().collections}
    path = data.persistent_root / 'item.md'
    real = index.embed

    def changing(text):
        path.write_bytes(path.read_bytes() + b'\n')
        return real(text)
    index.embed = changing
    with pytest.raises(ValueError):
        index.rebuild(data.persistent_root)
    index.embed = real
    names = {c.name for c in client.get_collections().collections}
    assert live in names and names <= before                   # live kept; nothing left by the failure
