# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_journal_v2_probes_g209.py
# Description : Contre-revue Claude G207-G209 : migration v2, clôture terminale, aperçu de réconciliation
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Independent probes (Claude) on GPT's journal v2 (c86bddb..26bcb0c, G209 to G214). GPT's files are not modified.
Positive tests pin what holds; strict xfail documents a finding and turns red once fixed."""
import hashlib
import multiprocessing
import os
import sqlite3

import pytest

from core.indexing.change_journal import ChangeJournal
from core.indexing.journal_migration import migrate_v2
from core.indexing.reconcile_preview import preview_reconciliation
from core.indexing import reconcile_plan as plan_module

DIGEST = hashlib.sha256(b"canonical").hexdigest()


V1_SCHEMA = """CREATE TABLE intents (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    information_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    operation TEXT NOT NULL,
    canonical_sha256 TEXT,
    state TEXT NOT NULL CHECK(state IN ('INTENT','PUBLISHED','INDEXED')),
    created REAL NOT NULL,
    updated REAL NOT NULL
)"""


def v1_journal(path):
    """A journal as created before a04ea1c (schema v1), written independently of GPT's fixture."""
    with sqlite3.connect(path) as raw:
        raw.execute(V1_SCHEMA)
        raw.execute("CREATE INDEX intent_state_seq ON intents(state,seq)")
    os.chmod(path, 0o600)
    return ChangeJournal(path)


def v2_journal(tmp_path, name="changes.sqlite3"):
    path = tmp_path / name
    return ChangeJournal(path), path                                    # native v2 since a04ea1c (M4)


def test_migration_keeps_rows_is_idempotent_and_enables_closing(tmp_path):
    path = tmp_path / "changes.sqlite3"
    old = v1_journal(path)
    a = old.begin("a", 1, "UPSERT", DIGEST)
    b = old.begin("b", 1, "DELETE")
    old.published(b)
    assert migrate_v2(path) == "MIGRATED_V2"
    assert migrate_v2(path) == "ALREADY_V2"
    journal = ChangeJournal(path)
    assert [(i.sequence, i.state) for i in journal.pending()] == [(a, "INTENT"), (b, "PUBLISHED")]
    journal.close_terminal(a, "ABANDONED", "never visible")
    journal.close_terminal(a, "ABANDONED", "never visible")                    # idempotent
    with pytest.raises(ValueError):
        journal.close_terminal(a, "SUPERSEDED", "other terminal")
    assert [i.sequence for i in journal.pending()] == [b]


def _close(path, sequence, queue):
    try:
        ChangeJournal(path).close_terminal(sequence, "SUPERSEDED", "race")
        queue.put("ok")
    except Exception as exc:
        queue.put(type(exc).__name__ + ":" + str(exc))


def test_concurrent_identical_closures_all_succeed_once(tmp_path):
    journal, path = v2_journal(tmp_path)
    sequence = journal.begin("doc", 1, "DELETE")
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    workers = [context.Process(target=_close, args=(path, sequence, queue)) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(30)
    assert sorted(queue.get(timeout=10) for _ in workers) == ["ok"] * 4
    assert journal.pending() == ()


def test_sequence_numbers_are_never_reused_after_compaction_and_migration(tmp_path):
    """M2 (G209), fixed in 3820208: sqlite_sequence is carried over."""
    path = tmp_path / "changes.sqlite3"
    old = v1_journal(path)
    for i in range(3):
        old.begin(f"doc-{i}", 1, "DELETE")
    with sqlite3.connect(path) as raw:                                         # future compaction of seq 3
        raw.execute("DELETE FROM intents WHERE seq=3")
    migrate_v2(path)
    assert ChangeJournal(path).begin("new", 1, "DELETE") == 4


def test_a_new_journal_supports_closing_without_migration(tmp_path):
    """M4 (G209), fixed in a04ea1c: a new journal is created directly in v2."""
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    journal.close_terminal(journal.begin("doc", 1, "DELETE"), "ABANDONED", "never visible")


def test_preview_accepts_a_complete_journal_of_exactly_limit_rows(tmp_path):
    """M7 (G209), fixed in 854ebbe: limit + 1 rows are read to detect truncation."""
    journal, _ = v2_journal(tmp_path)
    for i in range(3):
        journal.begin(f"doc-{i}", 1, "DELETE")
    preview_reconciliation(journal, {}, {}, limit=3)


@pytest.mark.xfail(not hasattr(plan_module, "ABSENT"), strict=True, reason="Claude finding M8 (G209, critical): with the integrated reconcile_plan, "
                   "an id MISSING from the canonical snapshot is taken as deleted: a DELETE intent whose canon was "
                   "not read becomes MARK_PUBLISHED, and indexed ids get ENQUEUE_DELETE. Memory patch 0013 fixes it.")
def test_preview_never_publishes_or_deletes_from_an_unread_canonical_state(tmp_path):
    journal, _ = v2_journal(tmp_path)
    journal.begin("doc", 3, "DELETE")
    preview = preview_reconciliation(journal, {}, {"doc": 3, "other": 2})
    assert {a.kind for a in preview.actions} <= {"WAIT"}


def test_an_abandonment_always_requires_review(tmp_path):
    """M9 (G209), fixed in 854ebbe."""
    journal, path = v2_journal(tmp_path)
    journal.begin("doc", 5, "UPSERT", DIGEST)
    from core.indexing.reconcile_plan import Canonical
    preview = preview_reconciliation(journal, {"doc": Canonical(4, DIGEST)}, {"doc": 4},
                                     now=10**10, grace_seconds=600)
    assert [a.kind for a in preview.actions] == ["CLOSE_ABANDONED"]
    assert preview.requires_review


def test_migration_refuses_a_public_or_linked_journal_without_touching_it(tmp_path):
    path = tmp_path / "changes.sqlite3"
    v1_journal(path)
    os.chmod(path, 0o644)
    with pytest.raises(ValueError):
        migrate_v2(path)
    os.chmod(path, 0o600)
    link = tmp_path / "link.sqlite3"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        migrate_v2(link)
    with sqlite3.connect(path) as raw:
        assert "ABANDONED" not in raw.execute("SELECT sql FROM sqlite_master WHERE name='intents'").fetchone()[0]


def test_m2_holds_when_everything_was_compacted_and_on_a_second_migration_attempt(tmp_path):
    path = tmp_path / "changes.sqlite3"
    old = v1_journal(path)
    last = [old.begin(f"doc-{i}", 1, "DELETE") for i in range(4)][-1]
    with sqlite3.connect(path) as raw:
        raw.execute("DELETE FROM intents")
    assert migrate_v2(path) == "MIGRATED_V2"
    assert migrate_v2(path) == "ALREADY_V2"
    assert ChangeJournal(path).begin("new", 1, "DELETE") == last + 1


def test_a_v1_journal_keeps_working_and_refuses_closing_without_change(tmp_path):
    """G212: v1 compatibility. Before migration the full v1 life cycle works, and close_terminal fails
    without altering the row."""
    path = tmp_path / "changes.sqlite3"
    journal = v1_journal(path)
    seq = journal.begin("doc", 1, "UPSERT", DIGEST)
    journal.published(seq)
    other = journal.begin("other", 1, "DELETE")
    with pytest.raises(Exception):
        journal.close_terminal(other, "ABANDONED", "never visible")
    journal.indexed(seq)
    assert [(i.sequence, i.state) for i in journal.pending()] == [(other, "INTENT")]


def test_preview_limit_is_999_with_one_row_of_lookahead(tmp_path):
    """M10 (G212), fixed in 06e0ef8: the preview caps at 999 and reads one more row; 1000 is refused up front."""
    journal, _ = v2_journal(tmp_path)
    for i in range(999):
        journal.begin(f"doc-{i}", 1, "DELETE")
    assert preview_reconciliation(journal, {}, {}, limit=999).pending_count == 999
    journal.begin("one-more", 1, "DELETE")
    with pytest.raises(ValueError, match="truncated"):
        preview_reconciliation(journal, {}, {}, limit=999)
    with pytest.raises(ValueError, match="invalid limit"):
        preview_reconciliation(journal, {}, {}, limit=1000)


def _schema(path):
    with sqlite3.connect(path) as raw:
        return (raw.execute("SELECT sql FROM sqlite_master WHERE name='intents'").fetchone()[0],
                raw.execute("PRAGMA user_version").fetchone()[0],
                raw.execute("SELECT * FROM intents ORDER BY seq").fetchall(),
                raw.execute("SELECT seq FROM sqlite_sequence WHERE name='intents'").fetchall())


def test_opening_an_existing_v1_or_v2_journal_never_mutates_it(tmp_path):
    """G214-1: ChangeJournal() on an existing base neither migrates nor rewrites it."""
    path = tmp_path / "changes.sqlite3"
    v1_journal(path).begin("doc", 1, "DELETE")
    v1 = _schema(path)
    ChangeJournal(path)
    assert _schema(path) == v1 and v1[1] == 0
    migrate_v2(path)
    v2 = _schema(path)
    ChangeJournal(path)
    assert _schema(path) == v2 and v2[1] == 2


def test_repeated_migrations_change_nothing_and_keep_terminal_rows(tmp_path):
    """G214-1: ALREADY_V2 is a no-op, terminal rows and their reasons are retained (no automatic purge)."""
    journal, path = v2_journal(tmp_path)
    a = journal.begin("a", 1, "DELETE")
    journal.close_terminal(a, "ABANDONED", "never visible")
    before = _schema(path)
    for _ in range(3):
        assert migrate_v2(path) == "ALREADY_V2"
    assert _schema(path) == before
    assert [row[-1] for row in before[2]] == ["never visible"]


def test_migration_refused_while_a_writer_holds_the_journal_changes_nothing(tmp_path):
    """G214-1: a live writer (open write transaction) makes the offline migration fail without change."""
    path = tmp_path / "changes.sqlite3"
    v1_journal(path).begin("doc", 1, "DELETE")
    before = _schema(path)
    writer = sqlite3.connect(path)
    writer.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(sqlite3.OperationalError):
            migrate_v2(path)
    finally:
        writer.rollback()
        writer.close()
    assert _schema(path) == before


def test_with_a_snapshot_dict_a_write_in_between_gives_a_false_alert(tmp_path):
    """M11 (G214), pinned limit of the dict form: the caller's snapshot predates the journal read."""
    from core.indexing.reconcile_plan import Canonical
    journal, _ = v2_journal(tmp_path)
    canonical = {"doc": Canonical(1, DIGEST)}                        # snapshot taken first
    seq = journal.begin("doc", 2, "UPSERT", hashlib.sha256(b"v2").hexdigest())
    journal.published(seq)                                           # writer finishes in between
    kinds = {a.kind for a in preview_reconciliation(journal, canonical, {"doc": 1}).actions}
    assert kinds == {"INTEGRITY_ALERT"}


def test_a_canonical_reader_called_after_the_journal_removes_the_false_alert(tmp_path):
    """M11 (G214), fixed by patch 0027: the canon is read after the journal."""
    from core.indexing.reconcile_plan import Canonical
    journal, _ = v2_journal(tmp_path)
    v2 = hashlib.sha256(b"v2").hexdigest()
    canon = {"doc": Canonical(1, DIGEST)}
    seq = journal.begin("doc", 2, "UPSERT", v2)
    canon["doc"] = Canonical(2, v2)
    journal.published(seq)
    seen = []

    def reader(ids):
        seen.append(set(ids))
        late = journal.begin("late", 1, "UPSERT", DIGEST)            # a write landing DURING the preview
        canon["late"] = Canonical(1, DIGEST)
        journal.published(late)
        return dict(canon)
    preview = preview_reconciliation(journal, reader, {"doc": 1})
    assert [(a.kind, a.information_id) for a in preview.actions] == [("INDEX_UPSERT", "doc"),
                                                                    ("ENQUEUE_UPSERT", "late")]
    assert seen == [{"doc"}] and not preview.requires_review
def _shape(path):
    with sqlite3.connect(path) as raw:
        columns = [(r[1], r[2], r[3], r[5]) for r in raw.execute("PRAGMA table_info(intents)")]
        indexes = sorted(r[1] for r in raw.execute("PRAGMA index_list(intents)"))
    return columns, indexes


def test_native_and_migrated_v2_journals_have_the_same_shape_and_states(tmp_path):
    """G214-1: a04ea1c's native v2 matches migrate_v2's result (columns, types, constraints, index, states)."""
    native = tmp_path / "native.sqlite3"
    ChangeJournal(native)
    migrated = tmp_path / "migrated.sqlite3"
    v1_journal(migrated)
    migrate_v2(migrated)
    assert _shape(native) == _shape(migrated)
    assert migrate_v2(native) == "ALREADY_V2"
    for path in (native, migrated):
        journal = ChangeJournal(path)
        journal.close_terminal(journal.begin("doc", 1, "DELETE"), "SUPERSEDED", "newer")
        with pytest.raises(sqlite3.IntegrityError):
            with sqlite3.connect(path) as raw:
                raw.execute("UPDATE intents SET state='BOGUS'")


def test_native_v2_journal_declares_its_version(tmp_path):
    """M12 (G214), fixed in 35f40be/13b6efa: version 2 at creation only; an existing v1 base keeps 0."""
    path = tmp_path / "changes.sqlite3"
    ChangeJournal(path)
    assert _schema(path)[1] == 2
    legacy = tmp_path / "legacy.sqlite3"
    v1_journal(legacy)
    ChangeJournal(legacy)
    assert _schema(legacy)[1] == 0 and "ABANDONED" not in _schema(legacy)[0]
    assert migrate_v2(legacy) == "MIGRATED_V2" and _schema(legacy)[1] == 2


def test_concurrent_creation_of_a_new_journal_is_consistent(tmp_path):
    """M12 follow-up: several processes creating the same new journal agree on schema v2 and version 2."""
    path = tmp_path / "changes.sqlite3"
    context = multiprocessing.get_context("fork")
    queue = context.Queue()

    def create():
        try:
            ChangeJournal(path).begin("doc", 1, "DELETE")
            queue.put("ok")
        except Exception as exc:
            queue.put(type(exc).__name__)
    workers = [context.Process(target=create) for _ in range(6)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(30)
    assert sorted(queue.get(timeout=10) for _ in workers) == ["ok"] * 6
    schema, version, rows, _ = _schema(path)
    assert "ABANDONED" in schema and version == 2 and len(rows) == 6
