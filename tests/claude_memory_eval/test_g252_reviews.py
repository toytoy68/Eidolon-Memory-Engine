# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_g252_reviews.py
# Description : Contre-revue Claude G252 (tâches 1, 2, 3, 6, 8) sur Memory 4d288dc
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Independent probes; GPT's files are not modified. Manifest probes kill two mutants of
core/indexing/manifest.py that survive GPT's 47 freshness/proof tests (local mutation, file restored)."""
from datetime import timedelta

import pytest

from core.backend.models import Memory
from core.indexing import manifest as manifests
from core.indexing.index_lag import evaluate_lag
from core.indexing.worker_canonical import CanonicalReader
from core.retrieval.contextual import ContextualRecall
from tests.test_contextual_recall import backend, store
from tests.test_qdrant_index import client, index  # noqa: F401 (fixtures)


def _recall(data, index, **kw):
    return ContextualRecall(data, index=index, **kw).recall('power')


# --- 1. Global freshness (G242) ------------------------------------------------------------------------------

def test_worker_style_incremental_write_never_claims_a_full_snapshot(tmp_path, index):
    data = backend(tmp_path)
    memory = store(data, 'one')
    index.rebuild(data.persistent_root)
    assert _recall(data, index).index_status.state == 'INDEX_SNAPSHOT_MATCH'
    data.update('one', Memory('one', content='power corrected', revision=2,
                              metadata=memory.metadata, provenance=memory.provenance,
                              verification=memory.verification), previous_revision=1)
    current, digest = CanonicalReader(data.persistent_root)('one')
    index.upsert_verified(current, canonical_sha256=digest)       # the journal worker's path
    status = _recall(data, index).index_status
    assert (status.state, status.reason) == ('INDEX_UNVERIFIED', 'NO_FULL_SOURCE_DIGEST')


def test_an_empty_result_from_a_stale_index_is_never_an_absence_claim(tmp_path, index):
    data = backend(tmp_path)
    index.rebuild(data.persistent_root)                           # empty, matching snapshot
    assert _recall(data, index).index_status.state == 'INDEX_SNAPSHOT_MATCH'
    store(data, 'late', content='power measurement added later')
    result = _recall(data, index)
    assert result.index_status.state == 'INDEX_STALE'             # empty items, explicitly stale
    assert all(i.information_id != 'late' or 'index_candidate' not in i.selection_reasons for i in result.items)


def test_a_change_then_revert_is_a_match_again(tmp_path, index):
    data = backend(tmp_path)
    store(data, 'one')
    index.rebuild(data.persistent_root)
    path = data.persistent_root / 'one.md'
    original = path.read_bytes()
    path.write_bytes(original.replace(b'power measurement', b'other measurement'))
    assert _recall(data, index).index_status.state == 'INDEX_STALE'
    path.write_bytes(original)
    assert _recall(data, index).index_status.state == 'INDEX_SNAPSHOT_MATCH'


# --- 2. Candidate proofs (G243): a bad row neither cited nor masking the global diagnostic -------------------

def test_a_drifted_candidate_is_excluded_and_the_global_state_still_says_stale(tmp_path, index):
    data = backend(tmp_path)
    store(data, 'one')
    store(data, 'two', content='power measurement two')
    index.rebuild(data.persistent_root)
    path = data.persistent_root / 'one.md'
    path.write_bytes(path.read_bytes().replace(b'power measurement', b'power altered'))   # same revision
    result = _recall(data, index)
    assert all(i.content != 'power altered' for i in result.items)
    assert result.index_status.state == 'INDEX_STALE'


# --- 3. Manifest budgets and races -----------------------------------------------------------------------------

def test_a_name_added_during_the_bounded_scan_refuses_the_snapshot(tmp_path, monkeypatch):
    data = backend(tmp_path)
    store(data, 'a')
    store(data, 'b')
    original = CanonicalReader.read_sized
    added = []

    def add_once(self, identity):
        if not added:
            added.append(1)
            store(data, 'c-new')
        return original(self, identity)
    monkeypatch.setattr(CanonicalReader, 'read_sized', add_once)
    with pytest.raises(ValueError, match='inventory changed'):
        manifests.build_bounded_manifest(data.persistent_root)


def test_the_entry_budget_counts_every_directory_entry(tmp_path):
    data = backend(tmp_path)
    store(data, 'a')
    (data.persistent_root / 'notes.txt').write_text('x')                # non-Markdown entries count too
    count = sum(1 for _ in data.persistent_root.iterdir())
    with pytest.raises(ValueError):
        manifests.build_bounded_manifest(data.persistent_root,
                                         budget=manifests.ManifestBudget(max_entries=count - 1))
    assert manifests.build_bounded_manifest(data.persistent_root,
                                            budget=manifests.ManifestBudget(max_entries=count)).entries


# --- 6. Lag diagnostics (G250/G251): mixed dates and health ------------------------------------------------------

class Intent:
    def __init__(self, created):
        self.created = created


HEALTHY = dict(index_available=True, index_compatible=True, canonical_complete=True)


def test_mixed_known_unknown_dates_keep_lagging_as_a_lower_bound():
    report = evaluate_lag([Intent(0.0), Intent(None), Intent(990.0)], now=1000.0, threshold_seconds=60, **HEALTHY)
    assert (report.state, report.lagging, report.oldest_age_seconds) == ('INDEX_LAGGING', 1, None)
    assert 'AGE_UNKNOWN' in report.reasons


def test_incompatible_health_wins_and_out_of_range_values_fail_with_a_stable_error():
    report = evaluate_lag([Intent(0.0)], now=1000.0, threshold_seconds=60,
                          **{**HEALTHY, 'index_compatible': False})
    assert report.state == 'INDEX_INCOMPATIBLE' and 'ALSO_LAGGING' in report.reasons
    for bad in (dict(now=10 ** 400), dict(threshold_seconds=10 ** 400), dict(now=-1.0)):
        args = dict(now=1000.0, threshold_seconds=60, **HEALTHY)
        args.update(bad)
        with pytest.raises(ValueError):
            evaluate_lag([Intent(1.0)], **args)
    with pytest.raises(ValueError):
        evaluate_lag([Intent(10 ** 400)], now=1000.0, threshold_seconds=60, **HEALTHY)


# --- 8. Restricted worker port (G253) ----------------------------------------------------------------------------

def test_the_controller_and_all_children_only_hold_the_restricted_view(tmp_path):
    from tests.claude_memory_eval.test_maintenance_probes_g234 import World
    from core.indexing.worker_port import WorkerIndexView
    world = World(tmp_path)
    try:
        cycle = world.cycle()
        holders = {'controller': cycle.index, 'worker': cycle.worker.index,
                   'canonical': cycle.canonical.index, 'orphans': cycle.orphans.index}
        for name, held in holders.items():
            assert isinstance(held, WorkerIndexView), name
            for forbidden in ('rebuild', 'delete', 'upsert', 'revision_for', 'query'):
                assert not hasattr(held, forbidden), (name, forbidden)
        for i in range(3):
            world.write(f'doc-{i}')
        assert world.finish().state == 'CYCLE_COMPLETE'
        (world.root / 'doc-0.md').unlink()
        world.at += timedelta(minutes=10)
        assert world.finish().state == 'REVIEW_REQUIRED'
        assert world.index.evidence_for('doc-0') is not None            # orphan kept
        world.at += timedelta(minutes=10)
        assert world.tick().state == 'ACTIVE'                           # a new cycle has started
        world.index.rebuild(world.root)                                 # host-side admin, mid-cycle
        world.at += timedelta(seconds=1)
        assert world.tick().state == 'RESTART_REQUIRED'                 # generation change still observed
    finally:
        world.client.close()
