import pytest

from core import persistence


def test_atomic_write_text_preserves_previous_file_if_publish_fails(tmp_path, monkeypatch):
    target = tmp_path / "information.md"
    target.write_text("previous")

    def interrupted(*args):
        raise OSError("simulated interrupted rename")

    monkeypatch.setattr(persistence, "durable_replace", interrupted)
    with pytest.raises(OSError, match="interrupted rename"):
        persistence.atomic_write_text(target, "replacement")
    assert target.read_text() == "previous"
    assert list(tmp_path.glob(".*.tmp")) == []


def test_atomic_write_text_publishes_unicode_content(tmp_path):
    target = tmp_path / "history" / "event.md"
    persistence.atomic_write_text(target, "mémoire 🚀\n")
    assert target.read_text(encoding="utf-8") == "mémoire 🚀\n"
