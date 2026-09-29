import json

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.indexing.cli import main


def test_index_cli_compares_copies_without_writing_or_exposing_content(tmp_path, capsys):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old_backend = FilesystemBackend(old / "memory/persistent", old / "memory/history")
    new_backend = FilesystemBackend(new / "memory/persistent", new / "memory/history")
    old_backend.store(Memory("changed", content="private old"))
    old_backend.store(Memory("removed", content="private removed"))
    new_backend.store(Memory("changed", content="private new"))
    new_backend.store(Memory("added", content="private added"))
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert main(["--root", str(old), "--compare-root", str(new)]) == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["source"]["count"] == 2
    assert report["comparison"]["added"] == 1
    assert report["comparison"]["updated"] == 1
    assert report["comparison"]["removed"] == 1
    assert "private" not in output
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before


def test_index_cli_blocks_invalid_source(tmp_path, capsys):
    root = tmp_path / "engine"
    persistent = root / "memory/persistent"
    persistent.mkdir(parents=True)
    (persistent / "wrong.md").write_text(FilesystemBackend._serialize(Memory("other")))
    with pytest.raises(SystemExit) as exc:
        main(["--root", str(root)])
    assert exc.value.code == 2
    assert "identity mismatch" in capsys.readouterr().err
