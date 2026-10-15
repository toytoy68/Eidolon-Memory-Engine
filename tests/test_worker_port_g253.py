# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_worker_port_g253.py
# Description : Production maintenance receives only the verified worker capability.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from datetime import timedelta
import pytest
from tests.test_index_maintenance import world  # noqa: F401


@pytest.mark.parametrize('component', ['controller', 'worker', 'canonical', 'orphans'])
def test_every_maintenance_component_has_no_administrative_methods(world, component):
    cycle = world.cycle()
    index = cycle.index if component == 'controller' else getattr(cycle, component).index
    for method in ('delete', 'rebuild', 'upsert', 'revision_for', 'query', 'client'):
        assert not hasattr(index, method), (component, method)
    with pytest.raises(AttributeError):
        index.delete = lambda *_: None
    assert callable(world.index.delete) and callable(world.index.rebuild)


def test_all_children_share_the_same_restricted_view(world):
    from core.indexing.worker_port import WorkerIndexView
    cycle = world.cycle()
    assert isinstance(cycle.index, WorkerIndexView)
    assert all(child.index is cycle.index for child in (cycle.worker, cycle.canonical, cycle.orphans))
    wrapped = world.cycle(index=cycle.index)
    assert wrapped.index is cycle.index


def test_full_cycle_and_orphan_review_work_without_admin_access(world):
    for ident in ('a', 'b', 'c'):
        world.write(ident, intent=False)
    assert world.finish().state == 'CYCLE_COMPLETE'
    assert world.index.status().documents == 3
    (world.root / 'a.md').unlink()
    world.at += timedelta(minutes=10)
    assert world.finish().state == 'REVIEW_REQUIRED'
    assert world.index.evidence_for('a') is not None


def test_view_observes_external_generation_change_instead_of_caching(world):
    view = world.cycle().index
    old = view.active_generation()
    world.write('a', intent=False)
    world.index.rebuild(world.root)
    assert view.active_generation() == world.index.active_generation() != old
    assert view.evidence_for('a').canonical_sha256 == world.index.evidence_for('a').canonical_sha256


def test_an_extended_view_cannot_reintroduce_admin_methods_into_the_cycle(world):
    from core.indexing.worker_port import WorkerIndexView
    class ExtendedView(WorkerIndexView):
        def delete(self, information_id):
            return self._adapter.delete(information_id)
    supplied = ExtendedView(world.index)
    assert callable(supplied.delete)
    cycle = world.cycle(index=supplied)
    assert all(not hasattr(index, 'delete') for index in
               (cycle.index, cycle.worker.index, cycle.canonical.index, cycle.orphans.index))
