import os
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "services/memory-relations/memory_relation_engine.py"
ROOT = Path(__file__).resolve().parents[1]


def invoke(root, source, *, relation="INVALID"):
    environment = dict(os.environ, MEMORY_ENGINE_ROOT=str(root), PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "add", str(source),
         "--relation", relation, "--target", "info-2"],
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


def test_legacy_relation_add_keeps_yaml_front_matter_and_body(tmp_path):
    import yaml

    working = tmp_path / "memory/working"
    events = tmp_path / "memory/history/events"
    working.mkdir(parents=True)
    events.mkdir(parents=True)
    source = working / "info-1.md"
    source.write_text("---\nid: info-1\nrevision: 1\n"
                      "epistemic_status: UNVERIFIED\nrelations: []\n"
                      "---\n# Information\nprivate body\n")
    (working / "info-2.md").write_text(
        "---\nid: info-2\nrevision: 1\nepistemic_status: UNVERIFIED\n"
        "relations: []\n---\n# Information\nother body\n")
    result = invoke(tmp_path, source, relation="SUPPORTS")
    assert result.returncode == 0, result.stdout + result.stderr
    text = source.read_text()
    header, body = text.split("---\n", 2)[1:]
    data = yaml.safe_load(header)
    assert data["revision"] == 2
    assert data["relations"] == [{"type": "SUPPORTS", "target": "info-2"}]
    assert body == "# Information\nprivate body\n"
    assert len(list(events.glob("*.md"))) == 1
    assert invoke(tmp_path, source, relation="SUPPORTS").returncode == 1
    assert source.read_text() == text


def test_legacy_relation_add_rejects_unsupported_relation_block(tmp_path):
    working = tmp_path / "memory/working"
    working.mkdir(parents=True)
    source = working / "info-1.md"
    source.write_text("---\nid: info-1\nrevision: 1\n"
                      "epistemic_status: UNVERIFIED\nrelations:\n"
                      "  - type: SUPPORTS\n    target: info-2\n"
                      "    private_detail: keep\n---\n# Information\nbody\n")
    (working / "info-2.md").write_text(
        "---\nid: info-2\nrevision: 1\nepistemic_status: UNVERIFIED\n"
        "relations: []\n---\n# Information\nbody\n")
    original = source.read_bytes()
    result = invoke(tmp_path, source, relation="CONTRADICTS")
    assert result.returncode == 1
    assert "bloc relations non pris en charge" in result.stdout
    assert source.read_bytes() == original
