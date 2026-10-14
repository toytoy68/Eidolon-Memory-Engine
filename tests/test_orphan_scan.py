# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_orphan_scan.py
# Description : Inverse inventory and stale orphan review with real local stores.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.change_journal import ChangeJournal
from core.indexing.worker_canonical import CanonicalReader

qdrant = pytest.importorskip("qdrant_client")
from core.indexing.qdrant_index import QdrantIndex


@pytest.fixture
def world(tmp_path):
    class World:
        def __init__(self):
            self.root = tmp_path / "persistent"
            self.backend = FilesystemBackend(self.root, tmp_path / "history")
            self.journal = ChangeJournal(tmp_path / "changes.sqlite3")
            self.checkpoint = tmp_path / "orphans.sqlite3"
            self.client = qdrant.QdrantClient(":memory:")
            self.index = QdrantIndex(self.client, "eidolon_orphans", embed=lambda _: [1., 0.],
                                     dimensions=2, embedding_id="synthetic-v1", create=True)
            self.allowed = True

        def point(self, ident="doc", revision=1):
            return self.index.upsert_verified(Memory(ident, revision=revision, content="example"),
                                               canonical_sha256="a" * 64)

        def scanner(self, **kwargs):
            from core.indexing.orphan_scan import OrphanScan
            opts = dict(canonical_root=self.root, index=self.index,
                        authorize=lambda *args: self.allowed, profile_id="owner",
                        expected_profile_id="owner", expected_model_id="synthetic-v1")
            opts.update(kwargs)
            return OrphanScan(self.checkpoint, self.journal, **opts)

        def finish(self, **kwargs):
            for _ in range(20):
                report = self.scanner(**kwargs).run_page(limit=1)
                if report.state != "RUNNING":
                    return report
            pytest.fail("scan did not exhaust")

    w = World()
    yield w
    w.client.close()


def test_absence_requires_missing_leaf_under_unchanged_root(world):
    reader = CanonicalReader(world.root)
    assert reader.proven_absent("doc") is True
    (world.root / "doc.md").symlink_to(world.root / "missing")
    assert reader.proven_absent("doc") is False
    world.root.rename(world.root.with_name("moved"))
    world.root.mkdir()
    with pytest.raises(ValueError, match="root"):
        reader.proven_absent("doc")


def test_inventory_paginates_all_information_without_descriptor(world):
    for ident in ("a", "b", "c"):
        world.point(ident)
    generation = world.index.active_generation()
    seen, offset = [], None
    for _ in range(10):
        page = world.index.inventory_page(generation=generation, offset=offset, limit=1)
        seen.extend(record.information_id for record in page.records)
        offset = page.next_offset
        if offset is None:
            break
    assert sorted(seen) == ["a", "b", "c"]
    assert world.index.status().documents == 3


def test_resumed_orphans_are_review_only_and_reappearance_invalidates(world):
    world.point("a")
    world.point("b")
    assert world.finish().state == "EXHAUSTED"
    review = world.scanner().review_page()
    assert {item.state for item in review.items} == {"DELETE_CANDIDATE"}
    assert len(review.items) == 2
    world.backend.store(Memory("a", content="restored"))
    states = {item.information_id: item.state for item in world.scanner().review_page().items}
    assert states == {"a": "CANONICAL_PRESENT", "b": "DELETE_CANDIDATE"}
    assert world.journal.pending() == ()
    assert world.index.status().documents == 2


@pytest.mark.parametrize("kind", ["file", "directory", "fifo", "link"])
def test_any_leaf_is_present_even_if_not_readable_markdown(world, kind):
    import os
    leaf = world.root / "doc.md"
    if kind == "file":
        leaf.write_bytes(b"\xffmalformed")
    elif kind == "directory":
        leaf.mkdir()
    elif kind == "fifo":
        os.mkfifo(leaf)
    else:
        leaf.symlink_to(world.root / "missing")
    world.point()
    assert world.finish().observed_candidates == 0
    assert world.scanner().review_page().items[0].state == "CANONICAL_PRESENT"


def test_absence_permission_error_is_unknown_not_candidate(world, monkeypatch):
    world.point()
    original = __import__("os").stat
    def denied(path, *args, **kwargs):
        if path == "doc.md":
            raise PermissionError("denied")
        return original(path, *args, **kwargs)
    monkeypatch.setattr("os.stat", denied)
    assert world.finish().observed_candidates == 0
    assert world.scanner().review_page().items[0].state == "ABSENCE_UNKNOWN"


def test_missing_root_is_not_missing_document(world):
    reader = CanonicalReader(world.root)
    world.root.rename(world.root.with_name("moved"))
    with pytest.raises(ValueError, match="unknown"):
        reader.proven_absent("doc")


def test_reappearance_during_point_read_prevents_candidate(world, monkeypatch):
    world.point()
    original = world.index.evidence_for
    def restore(ident):
        value = original(ident)
        if not (world.root / "doc.md").exists():
            world.backend.store(Memory("doc", content="back"))
        return value
    monkeypatch.setattr(world.index, "evidence_for", restore)
    assert world.finish().observed_candidates == 0
    assert world.scanner().review_page().items[0].state == "CANONICAL_PRESENT"


@pytest.mark.parametrize("allowed", [False, 1, "yes", None])
def test_permissions_require_exact_true_on_each_review(world, allowed):
    world.point()
    assert world.finish().observed_candidates == 1
    world.allowed = allowed
    assert world.scanner().review_page().items[0].state == "FORBIDDEN"


def test_wrong_profile_and_delete_specific_permission(world):
    world.point()
    assert world.finish(profile_id="other").observed_candidates == 0
    # Same checkpoint cannot silently change its authorization scope.
    with pytest.raises(ValueError, match="context"):
        world.scanner().review_page()


def test_delete_authorization_is_rechecked_after_point_observation(world, monkeypatch):
    world.point()
    seen = []
    def authorize(profile, ident, action):
        seen.append((profile, ident, action))
        return world.allowed
    original = world.index.evidence_for
    def revoke(ident):
        value = original(ident)
        world.allowed = False
        return value
    monkeypatch.setattr(world.index, "evidence_for", revoke)
    assert world.finish(authorize=authorize).observed_candidates == 0
    assert len(seen) == 2 and {v[2] for v in seen} == {"index.delete"}


@pytest.mark.parametrize("operation", ["UPSERT", "DELETE"])
def test_pending_intent_beyond_first_journal_page_blocks_candidate(world, operation):
    world.point()
    for i in range(100):
        world.journal.begin("other" + str(i), 1, "DELETE")
    seq = world.journal.begin("doc", 1, operation, "a" * 64 if operation == "UPSERT" else None)
    assert "doc" not in {x.information_id for x in world.journal.pending()}
    assert world.finish().observed_candidates == 0
    assert world.scanner().review_page().items[0].state == "PENDING_JOURNAL"
    world.journal.close_terminal(seq, "ABANDONED", "isolated test resolved")
    assert world.scanner().review_page().items[0].state == "DELETE_CANDIDATE"


def test_new_pending_intent_during_read_blocks_candidate(world, monkeypatch):
    world.point()
    original = world.index.evidence_for
    def pending(ident):
        value = original(ident)
        world.journal.begin(ident, 1, "UPSERT", "a" * 64)
        return value
    monkeypatch.setattr(world.index, "evidence_for", pending)
    assert world.finish().observed_candidates == 0


@pytest.mark.parametrize("change", ["revision", "digest", "removed"])
def test_point_changed_after_inventory_is_not_a_current_candidate(world, change):
    world.point()
    assert world.finish().observed_candidates == 1
    if change == "revision":
        world.point(revision=2)
    elif change == "digest":
        world.index.upsert_verified(Memory("doc", content="new"), canonical_sha256="b" * 64)
    else:
        world.index.delete("doc")  # explicit isolated test setup, never scanner effect
    assert world.scanner().review_page().items[0].state == "POINT_CHANGED"


def test_legacy_point_is_visible_but_never_a_delete_candidate(world):
    world.index.upsert(Memory("doc", content="legacy"))
    assert world.finish().observed_candidates == 0
    assert world.scanner().review_page().items[0].state == "PROVENANCE_MISSING"
    assert world.index.status().documents == 1


def test_alias_switch_invalidates_checkpoint_and_review(world):
    world.point()
    world.finish()
    world.index.rebuild(world.root)
    assert world.scanner().review_page().state == "RESTART_REQUIRED"
    assert world.scanner().run_page().state == "RESTART_REQUIRED"
    assert world.scanner().run_page().state == "EXHAUSTED"
    assert world.scanner().review_page().items == ()


def test_alias_switch_during_scroll_refuses_entire_page(world, monkeypatch):
    world.point()
    original = world.client.scroll
    def switch(*args, **kwargs):
        result = original(*args, **kwargs)
        world.index.rebuild(world.root)
        return result
    monkeypatch.setattr(world.client, "scroll", switch)
    report = world.scanner().run_page()
    assert (report.state, report.inspected) == ("INDEX_UNAVAILABLE", 0)


def test_index_outage_after_one_observation_retries_whole_page(world, monkeypatch):
    world.point("a")
    world.point("b")
    original = world.index.evidence_for
    calls = []
    def offline(ident):
        calls.append(ident)
        if len(calls) == 2:
            raise ConnectionError("offline")
        return original(ident)
    monkeypatch.setattr(world.index, "evidence_for", offline)
    report = world.scanner().run_page()
    assert (report.state, report.inspected) == ("INDEX_UNAVAILABLE", 0)
    monkeypatch.setattr(world.index, "evidence_for", original)
    report = world.scanner().run_page()
    assert (report.state, report.inspected, report.observed_candidates) == ("EXHAUSTED", 2, 2)


def test_limit_does_not_certify_or_skip_unrecorded_points(world):
    for ident in ("a", "b", "c"):
        world.point(ident)
    report = world.finish(max_points=1)
    assert (report.state, report.inspected) == ("LIMIT_REACHED", 1)
    report = world.finish(max_points=3)
    assert (report.state, report.inspected) == ("EXHAUSTED", 3)


def test_new_point_behind_cursor_needs_explicit_new_pass(world):
    from core.indexing.qdrant_index import _point_id
    names = sorted(["item" + str(i) for i in range(20)], key=_point_id)
    world.point(names[-1])
    assert world.finish().inspected == 1
    world.point(names[0])
    assert world.scanner().run_page().inspected == 1
    report = world.scanner().run_page(restart=True)
    assert (report.state, report.inspected) == ("EXHAUSTED", 2)


def test_review_pagination_does_not_drop_or_duplicate_observations(world):
    for ident in ("a", "b", "c"):
        world.point(ident)
    world.finish()
    seen, after = [], -1
    for _ in range(5):
        page = world.scanner().review_page(after=after, limit=1)
        seen.extend(i.information_id for i in page.items)
        if page.next_after is None:
            break
        after = page.next_after
    assert sorted(seen) == ["a", "b", "c"]


def test_model_mismatch_and_replaced_journal_refuse_review(world):
    world.point()
    world.finish()
    world.index.embedding_id = "other"
    assert world.scanner().review_page().state == "INDEX_INCOMPATIBLE"
    assert world.scanner().run_page().state == "INDEX_INCOMPATIBLE"
    world.index.embedding_id = "synthetic-v1"
    from pathlib import Path
    Path(world.journal.path).rename(Path(world.journal.path).with_suffix(".old"))
    world.journal = ChangeJournal(world.journal.path)
    with pytest.raises(ValueError, match="context"):
        world.scanner().review_page()


@pytest.mark.parametrize("mutation", ["foreign", "bad_digest", "wrong_id", "bad_kind"])
def test_invalid_or_foreign_point_is_not_hidden_by_inventory_filter(world, mutation):
    from qdrant_client import models
    from core.indexing.qdrant_index import _point_id
    from uuid import uuid4
    world.point()
    generation = world.index.active_generation()
    point = world.client.retrieve(generation, ids=[_point_id("doc")])[0]
    payload, ident = dict(point.payload), point.id
    if mutation == "foreign":
        payload, ident = {"kind": "external"}, str(uuid4())
    elif mutation == "bad_digest":
        payload["canonical_sha256"] = "invalid"
    elif mutation == "wrong_id":
        ident = str(uuid4())
    else:
        payload["kind"] = "descriptor"
    world.client.upsert(generation, [models.PointStruct(id=ident, vector=[1., 0.], payload=payload)])
    report = world.scanner().run_page()
    assert (report.state, report.inspected) == ("INDEX_UNAVAILABLE", 0)


@pytest.mark.parametrize("mutation", ["repeat_cursor", "reverse", "too_many"])
def test_malformed_scroll_response_cannot_advance_checkpoint(world, monkeypatch, mutation):
    world.point("a")
    world.point("b")
    original = world.client.scroll
    def malformed(*args, **kwargs):
        records, offset = original(*args, **kwargs)
        if mutation == "repeat_cursor":
            offset = records[0].id
        elif mutation == "reverse":
            records = list(reversed(records))
        else:
            records = records * 101
        return records, offset
    monkeypatch.setattr(world.client, "scroll", malformed)
    report = world.scanner().run_page()
    assert (report.state, report.inspected) == ("INDEX_UNAVAILABLE", 0)


def test_two_concurrent_scanners_share_durable_progress(world):
    from concurrent.futures import ThreadPoolExecutor
    for ident in ("a", "b", "c"):
        world.point(ident)
    scanners = [world.scanner(), world.scanner()]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda scan: scan.run_page(limit=1), scanners))
    assert all(r.state in ("RUNNING", "BUSY") for r in results)
    assert world.finish().inspected == 3
    assert len(world.scanner().review_page().items) == 3


def test_checkpoint_cannot_alias_journal_or_existing_canonical_scan(world):
    import os
    os.link(world.journal.path, world.checkpoint)
    with pytest.raises(ValueError, match="separate"):
        world.scanner()
    world.checkpoint.unlink()
    from core.indexing.reconcile_scan import ReconciliationScan
    ReconciliationScan(world.checkpoint, world.journal, canonical_root=world.root,
                       index=world.index, authorize=lambda *args: True, profile_id="owner",
                       expected_profile_id="owner", expected_model_id="synthetic-v1")
    with pytest.raises(ValueError, match="not an orphan"):
        world.scanner()


def test_corrupt_checkpoint_count_is_not_trusted(world):
    import sqlite3
    world.point()
    world.finish()
    with sqlite3.connect(world.checkpoint) as db:
        db.execute("UPDATE orphan_scan SET seen=100")
    with pytest.raises(ValueError, match="incomplete"):
        world.scanner().review_page()


def test_scan_and_review_never_call_index_or_journal_mutations(world, monkeypatch):
    world.point()
    def forbidden(*args, **kwargs):
        pytest.fail("orphan scan attempted a write outside its checkpoint")
    for method in ("upsert", "delete", "create_collection", "update_collection_aliases"):
        monkeypatch.setattr(world.client, method, forbidden)
    for method in ("begin", "ensure_upsert_intent", "published", "indexed", "close_terminal"):
        monkeypatch.setattr(world.journal, method, forbidden)
    assert world.finish().observed_candidates == 1
    assert world.scanner().review_page().items[0].state == "DELETE_CANDIDATE"


def test_root_replaced_during_final_leaf_check_is_not_absence(world, monkeypatch):
    reader = CanonicalReader(world.root)
    original = __import__("os").stat
    calls = []
    def replace(path, *args, **kwargs):
        if path == "doc.md":
            calls.append(path)
            if len(calls) == 2:
                world.root.rename(world.root.with_name("moved"))
                world.root.mkdir()
        return original(path, *args, **kwargs)
    monkeypatch.setattr("os.stat", replace)
    with pytest.raises(ValueError, match="root changed"):
        reader.proven_absent("doc")


@pytest.mark.parametrize("when", ["before_commit", "after_commit"])
def test_real_process_exit_keeps_page_and_cursor_atomic(tmp_path, when):
    import os
    from contextlib import closing
    from pathlib import Path
    import sqlite3
    import subprocess
    import sys
    from core.indexing.orphan_scan import OrphanScan

    root, history = tmp_path / "persistent", tmp_path / "history"
    FilesystemBackend(root, history)
    journal = ChangeJournal(tmp_path / "changes.sqlite3")
    client = qdrant.QdrantClient(path=str(tmp_path / "qdrant"))
    index = QdrantIndex(client, "eidolon_crash", embed=lambda _: [1., 0.], dimensions=2,
                        embedding_id="synthetic-v1", create=True)
    for ident in ("a", "b"):
        index.upsert_verified(Memory(ident, content="test"), canonical_sha256="a" * 64)
    checkpoint = tmp_path / "orphans.sqlite3"
    OrphanScan(checkpoint, journal, canonical_root=root, index=index,
               authorize=lambda *args: True, profile_id="owner", expected_profile_id="owner",
               expected_model_id="synthetic-v1")
    client.close()
    code = '''
import os, sys
from pathlib import Path
from contextlib import contextmanager
from qdrant_client import QdrantClient
from core.indexing.qdrant_index import QdrantIndex
from core.indexing.orphan_scan import OrphanScan
from core.indexing.change_journal import ChangeJournal
base, when = Path(sys.argv[1]), sys.argv[2]
client = QdrantClient(path=str(base / "qdrant"))
index = QdrantIndex(client, "eidolon_crash", embed=lambda _: [1., 0.], dimensions=2,
                    embedding_id="synthetic-v1")
scan = OrphanScan(base / "orphans.sqlite3", ChangeJournal(base / "changes.sqlite3"),
                  canonical_root=base / "persistent", index=index, authorize=lambda *args: True,
                  profile_id="owner", expected_profile_id="owner", expected_model_id="synthetic-v1")
original = scan._db
@contextmanager
def crash():
    with original() as db:
        yield db
        assert db.execute("SELECT count(*) FROM observations").fetchone()[0] == 2
        if when == "before_commit":
            os._exit(73)
    os._exit(73)
scan._db = crash
scan.run_page()
'''
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path), when],
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 73, result.stderr
    with sqlite3.connect(checkpoint) as db:
        assert db.execute("SELECT count(*) FROM observations").fetchone()[0] == (0 if when == "before_commit" else 2)
    with closing(qdrant.QdrantClient(path=str(tmp_path / "qdrant"))) as client:
        index = QdrantIndex(client, "eidolon_crash", embed=lambda _: [1., 0.], dimensions=2,
                            embedding_id="synthetic-v1")
        scan = OrphanScan(checkpoint, journal, canonical_root=root, index=index,
                          authorize=lambda *args: True, profile_id="owner", expected_profile_id="owner",
                          expected_model_id="synthetic-v1")
        report = scan.run_page()
        assert (report.state, report.inspected, report.observed_candidates) == ("EXHAUSTED", 2, 2)
        assert len(scan.review_page().items) == 2
        assert index.status().documents == 2 and journal.pending() == ()
