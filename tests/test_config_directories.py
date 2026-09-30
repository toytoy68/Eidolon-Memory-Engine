import pytest

import core.config as config


def test_ensure_directories_rejects_linked_parent_before_creating_anything(tmp_path,
                                                                          monkeypatch):
    external = tmp_path / "external"
    external.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(external, target_is_directory=True)
    monkeypatch.setattr(config, "WORKING_ROOT", tmp_path / "safe/working")
    monkeypatch.setattr(config, "PERSISTENT_ROOT", linked / "persistent")
    monkeypatch.setattr(config, "EVENTS_ROOT", tmp_path / "safe/history/events")
    monkeypatch.setattr(config, "REVIEWS_ROOT", tmp_path / "safe/history/reviews")
    monkeypatch.setattr(config, "OPERATIONS_ROOT", tmp_path / "safe/history/operations")
    with pytest.raises(ValueError, match="symlink"):
        config.ensure_directories()
    assert not (external / "persistent").exists()
    assert not (tmp_path / "safe").exists()


def test_env_root_symlink_is_not_resolved_away_before_guard(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    external = tmp_path / "external"
    external.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(external, target_is_directory=True)
    project = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-c", "from core.config import ensure_directories; ensure_directories()"],
        cwd=project, env={**os.environ, "MEMORY_ENGINE_ROOT": str(alias)},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0 and "symlink" in result.stderr
    assert not (external / "memory").exists()
