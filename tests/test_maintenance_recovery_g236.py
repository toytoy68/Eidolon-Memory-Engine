# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_maintenance_recovery_g236.py
# Description : Audited clock recovery and configurable orphan inventory budget.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from datetime import timedelta
import json
import sqlite3
import pytest
from tests.test_index_maintenance import world


def fault(world):
    future = world.at + timedelta(days=365)
    world.tick(at=future, last_activity=future-timedelta(hours=1), boot_at=future-timedelta(hours=2))
    assert world.tick().state == 'CLOCK_REVERSED'
    return dict(at=world.at, expected_last_at=future.timestamp(), expected_cycle=1,
                actor='operator-test', reason='Clock corrected after isolated test', request_id='reset-1')


def test_clock_fault_survives_restart_and_time_catching_up(world, monkeypatch):
    world.write()
    args = fault(world)
    assert world.cycle().status().state == 'REVIEW_REQUIRED'
    def forbidden(*a, **k):
        pytest.fail('clock fault contacted index')
    monkeypatch.setattr(world.index, 'active_generation', forbidden)
    future = world.at + timedelta(days=366)
    assert world.tick(at=future, last_activity=future-timedelta(hours=1),
                      boot_at=future-timedelta(hours=2)).state == 'CLOCK_REVERSED'
    assert world.cycle().status().detail['clock_fault']['observed_at'] == world.at.timestamp()


def test_explicit_recovery_is_audited_idempotent_and_eventually_converges(world):
    seq = world.write()
    args = fault(world)
    receipt = world.cycle().recover_clock(**args)
    assert receipt['previous_cycle'] == 1 and receipt['cycle'] == 2
    assert receipt['previous_last_at'] == args['expected_last_at']
    assert receipt['at'] == world.at.timestamp()
    assert world.cycle().recover_clock(**args) == receipt
    assert world.journal.intent(seq).state == 'PUBLISHED'
    assert world.index.status().documents == 0
    status = world.cycle().status()
    assert status.state == 'ACTIVE' and status.stage == 'FIRST' and status.cycle == 2
    assert status.detail['last_at'] == world.at.timestamp()
    assert world.cycle().clock_recoveries()['items'] == [receipt]
    assert world.finish().state == 'CYCLE_COMPLETE'
    assert world.journal.intent(seq).state == 'INDEXED'
    # Retrying a successful request after later progress cannot reset that progress.
    completed = world.cycle().status()
    assert world.cycle().recover_clock(**args) == receipt
    assert world.cycle().status() == completed


@pytest.mark.parametrize('change', [dict(expected_cycle=2), dict(expected_last_at=1.),
    dict(at=None), dict(actor=''), dict(reason='x'*513), dict(request_id='bad\nrequest'),
    dict(expected_last_at=float('nan')), dict(expected_cycle=True)])
def test_invalid_or_stale_recovery_preserves_state_and_audit(world, change):
    args = fault(world)
    args.update(change)
    before = world.cycle().status()
    with pytest.raises(ValueError):
        world.cycle().recover_clock(**args)
    assert world.cycle().status() == before
    assert world.cycle().clock_recoveries()['items'] == []


def test_recovery_requires_observed_clock_fault_and_backward_correction(world):
    world.tick()
    with pytest.raises(ValueError):
        world.cycle().recover_clock(at=world.at-timedelta(seconds=1), expected_last_at=world.at.timestamp(),
            expected_cycle=1, actor='test', reason='test', request_id='reset')
    args = fault(world)
    args['at'] = world.at + timedelta(days=366)
    with pytest.raises(ValueError):
        world.cycle().recover_clock(**args)


def test_request_id_cannot_be_reused_for_a_different_decision(world):
    args = fault(world)
    world.cycle().recover_clock(**args)
    args['reason'] = 'another decision'
    with pytest.raises(ValueError, match='request'):
        world.cycle().recover_clock(**args)
    assert len(world.cycle().clock_recoveries()['items']) == 1


def test_recovery_rollback_retains_fault_without_audit(world, monkeypatch):
    args = fault(world)
    cycle = world.cycle()
    save = cycle._save
    def fail(db, state):
        save(db, state)
        raise RuntimeError('crash before commit')
    monkeypatch.setattr(cycle, '_save', fail)
    with pytest.raises(RuntimeError, match='crash'):
        cycle.recover_clock(**args)
    assert world.cycle().status().state == 'REVIEW_REQUIRED'
    assert world.cycle().clock_recoveries()['items'] == []
    assert world.cycle().recover_clock(**args)['cycle'] == 2


def test_recovery_never_contacts_index_or_closes_journal(world, monkeypatch):
    world.write()
    args = fault(world)
    def forbidden(*a, **k):
        pytest.fail('recovery touched external effects')
    for name in ('active_generation', 'upsert_verified', 'evidence_for'):
        monkeypatch.setattr(world.index, name, forbidden)
    for name in ('published', 'indexed', 'close_terminal'):
        monkeypatch.setattr(world.journal, name, forbidden)
    assert world.cycle().recover_clock(**args)['cycle'] == 2


def test_old_schema_migrates_without_changing_context_state_or_reviews(world):
    world.write()
    world.tick()
    path = world.base / 'cycle.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE IF EXISTS clock_fault')
        db.execute('DROP TABLE IF EXISTS clock_recoveries')
        db.execute('PRAGMA user_version=1')
        before = db.execute('SELECT * FROM maintenance').fetchall()
        db.execute("INSERT INTO reviews VALUES (991, 'FORBIDDEN', 12)")
    world.cycle()
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2
        assert db.execute('SELECT * FROM maintenance').fetchall() == before
        assert db.execute('SELECT * FROM reviews').fetchall() == [(991, 'FORBIDDEN', 12.)]


def test_orphan_budget_can_complete_exact_bound_and_is_context_bound(world):
    for i in range(3):
        world.write(str(i))
    def finish(budget):
        for _ in range(100):
            report = world.cycle(max_points=budget).tick(at=world.at, last_activity=world.at-timedelta(hours=1),
                boot_at=world.at-timedelta(hours=2), load_ok=True)
            if report.state in ('CYCLE_COMPLETE', 'REVIEW_REQUIRED'):
                return report
        pytest.fail('did not finish')
    assert finish(3).state == 'CYCLE_COMPLETE'
    with pytest.raises(ValueError, match='context'):
        world.cycle(max_points=4)
    assert world.cycle(max_points=3).status().state == 'CYCLE_COMPLETE'


def test_incomplete_orphan_inventory_stays_review_required(world):
    for i in range(3):
        world.write(str(i))
    for _ in range(100):
        report = world.cycle(max_points=2).tick(at=world.at, last_activity=world.at-timedelta(hours=1),
            boot_at=world.at-timedelta(hours=2), load_ok=True)
        if report.state == 'REVIEW_REQUIRED':
            break
    assert report.state == 'REVIEW_REQUIRED' and report.detail['orphan_review'] >= 1
    assert world.index.status().documents == 3


@pytest.mark.parametrize('value', [True, 0, -1, 1.5, None])
def test_invalid_orphan_budgets_refused_before_checkpoint_creation(world, value):
    with pytest.raises(ValueError):
        world.cycle(max_points=value)
    assert not (world.base/'cycle.sqlite3').exists()


def test_audit_pagination_is_bounded_and_stable(world):
    for i in range(3):
        args = fault(world)
        args.update(expected_cycle=1+i, request_id=f'reset-{i}')
        world.cycle().recover_clock(**args)
    first = world.cycle().clock_recoveries(limit=2)
    assert len(first['items']) == 2 and first['next_after'] == 2
    last = world.cycle().clock_recoveries(after=first['next_after'], limit=2)
    assert len(last['items']) == 1 and last['next_after'] is None
    assert first['items'][0]['request_id'] == 'reset-0'
    with pytest.raises(ValueError):
        world.cycle().clock_recoveries(limit=1000)


@pytest.mark.parametrize('phase', ['before_commit', 'after_commit'])
def test_process_death_preserves_atomic_recovery_and_retry(world, phase):
    import subprocess
    import sys
    args = fault(world)
    code = '''
import os, sys
from pathlib import Path
from datetime import datetime
from core.indexing.change_journal import ChangeJournal
from core.indexing.maintenance import IndexMaintenance
class Index:
    alias = "eidolon_maintenance"
    embedding_id = "synthetic-v1"
    def active_generation(self): raise AssertionError("index contacted")
    def evidence_for(self, *a): raise AssertionError("index contacted")
    def upsert_verified(self, *a): raise AssertionError("index contacted")
    def inventory_page(self, *a): raise AssertionError("index contacted")
base = Path(sys.argv[1])
cycle = IndexMaintenance(base/"cycle.sqlite3", ChangeJournal(base/"changes.sqlite3"),
    canonical_checkpoint=base/"canonical.sqlite3", orphan_checkpoint=base/"orphans.sqlite3",
    canonical_root=base/"persistent", index=Index(), authorize=lambda *a: True,
    profile_id="owner", expected_profile_id="owner", expected_model_id="synthetic-v1",
    page_size=2, pending_limit=2)
if sys.argv[4] == "before_commit":
    save = cycle._save
    def interrupted(db, state):
        save(db, state)
        os._exit(81)
    cycle._save = interrupted
cycle.recover_clock(at=datetime.fromisoformat(sys.argv[2]), expected_last_at=float(sys.argv[3]),
    expected_cycle=1, actor="operator-test", reason="Clock corrected after isolated test", request_id="reset-1")
os._exit(82)
'''
    child = subprocess.run([sys.executable, '-c', code, str(world.base), world.at.isoformat(),
                            str(args['expected_last_at']), phase], capture_output=True, timeout=20)
    assert child.returncode == (81 if phase == 'before_commit' else 82), child.stderr.decode()
    assert world.cycle().status().state == ('REVIEW_REQUIRED' if phase == 'before_commit' else 'ACTIVE')
    assert len(world.cycle().clock_recoveries()['items']) == (0 if phase == 'before_commit' else 1)
    assert world.cycle().recover_clock(**args)['cycle'] == 2
    assert len(world.cycle().clock_recoveries()['items']) == 1


def test_recovery_cannot_bypass_writer_lock(world):
    import threading
    from core.persistence import exclusive_write, RepositoryBusy
    args = fault(world)
    cycle = world.cycle()
    errors = []
    def recover():
        try:
            cycle.recover_clock(**args)
        except RepositoryBusy as exc:
            errors.append(exc)
    with exclusive_write(world.root):
        thread = threading.Thread(target=recover)
        thread.start()
        thread.join(5)
        assert not thread.is_alive()
    assert len(errors) == 1
    assert world.cycle().clock_recoveries()['items'] == []


def test_recovery_keeps_future_intents_for_review_and_restarts_completed_scans(world):
    world.write('first')
    assert world.finish().state == 'CYCLE_COMPLETE'
    world.write('later', intent=False)
    seq = world.write('future')
    args = fault(world)
    args['expected_cycle'] = 2  # future tick started the next cycle
    with sqlite3.connect(world.journal.path) as db:
        db.execute('UPDATE intents SET created=? WHERE seq=?', (args['expected_last_at'], seq))
    world.cycle().recover_clock(**args)
    assert world.finish().state == 'REVIEW_REQUIRED'
    assert world.journal.intent(seq).state == 'PUBLISHED'
    assert world.index.evidence_for('later') is not None
    assert world.index.evidence_for('future') is None
    assert any(row['reason'] == 'INVALID_TIMESTAMP' for row in world.cycle().reviews()['items'])
