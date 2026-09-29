import os
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "services/memory-relations/memory_relation_engine.py"
ROOT = Path(__file__).resolve().parents[1]


def invoke(root, source):
    environment = dict(os.environ, MEMORY_ENGINE_ROOT=str(root), PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "add", str(source),
         "--relation", "INVALID", "--target", "info-2"],
        env=environment, cwd=ROOT, capture_output=True, text=True, check=False,
    )


def test_legacy_relation_command_rejects_persistent_source(tmp_path):
    persistent = tmp_path / "memory/persistent"
    persistent.mkdir(parents=True)
    source = persistent / "info-1.md"
    source.write_text("---\nid: info-1\n---\nprivate content\n")
    original = source.read_bytes()
    result = invoke(tmp_path, source)
    assert result.returncode == 1
    assert "Working Memory" in result.stdout
    assert source.read_bytes() == original
    assert not (persistent / ".write.lock").exists()


def test_legacy_relation_command_accepts_working_boundary(tmp_path):
    working = tmp_path / "memory/working"
    working.mkdir(parents=True)
    source = working / "info-1.md"
    source.write_text("---\nid: info-1\n---\nprivate content\n")
    result = invoke(tmp_path, source)
    assert result.returncode == 1
    assert "relation invalide" in result.stdout
    assert "Working Memory" not in result.stdout
