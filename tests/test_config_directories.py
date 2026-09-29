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
