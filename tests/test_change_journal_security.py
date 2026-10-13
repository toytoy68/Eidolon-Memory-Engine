"""Security and transition regression tests for the advisory change journal."""
import os
import stat
import pytest
from core.indexing.change_journal import ChangeJournal


def test_journal_is_private(tmp_path):
    journal = ChangeJournal(tmp_path / "journal.sqlite3")
    assert stat.S_IMODE(os.stat(journal.path).st_mode) == 0o600


def test_world_readable_existing_file_is_rejected(tmp_path):
    path = tmp_path / "journal.sqlite3"
    path.write_bytes(b"")
    path.chmod(0o644)
    with pytest.raises(ValueError, match="private"):
        ChangeJournal(path)


def test_symlink_file_is_rejected(tmp_path):
    target = tmp_path / "target.sqlite3"
    target.write_bytes(b"")
    link = tmp_path / "link.sqlite3"
    link.symlink_to(target)
    with pytest.raises(OSError):
        ChangeJournal(link)


def test_public_parent_is_rejected(tmp_path):
    directory = tmp_path / "public"
    directory.mkdir(mode=0o755)
    directory.chmod(0o755)
    with pytest.raises(ValueError, match="private"):
        ChangeJournal(directory / "journal.sqlite3")


def test_state_transition_does_not_go_backwards(tmp_path):
    journal = ChangeJournal(tmp_path / "journal.sqlite3")
    seq = journal.begin("a", 1, "DELETE")
    journal.published(seq)
    journal.indexed(seq)
    with pytest.raises(ValueError, match="transition"):
        journal.published(seq)
    assert journal.pending() == ()
