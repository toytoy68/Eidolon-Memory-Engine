import os

from core.monitoring.metrics import collect_metrics, memory_bytes, tree_bytes


def test_metrics_separate_host_volume_and_engine_data(tmp_path):
    data = tmp_path / "memory" / "persistent"
    data.mkdir(parents=True)
    original = data / "info.md"
    original.write_bytes(b"private content")
    os.link(original, data / "same-inode.md")
    outside = tmp_path / "outside"
    outside.write_bytes(b"more private content")
    (data / "external.md").symlink_to(outside)
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       1000 kB\nMemAvailable:    400 kB\n")

    result = collect_metrics(tmp_path, meminfo_path=meminfo)

    assert result["ram_bytes"] == {"total": 1024000, "available": 409600, "used": 614400}
    assert result["volume_bytes"]["total"] >= result["volume_bytes"]["free"]
    assert result["engine_data"] == {
        "files": 1, "bytes": len(b"private content"), "symlinks_skipped": 1,
    }
    assert result["data_path"] == str(tmp_path / "memory")
    assert result["host"]
    assert result["measured_at"].endswith("+00:00")
    assert "private content" not in str(result)
    assert not (data / ".write.lock").exists()


def test_missing_memory_tree_and_linked_root(tmp_path):
    assert tree_bytes(tmp_path / "absent") == {
        "files": 0, "bytes": 0, "symlinks_skipped": 0,
    }
    (tmp_path / "memory").symlink_to(tmp_path / "outside")
    import pytest
    with pytest.raises(ValueError, match="symlink"):
        collect_metrics(tmp_path)


def test_meminfo_rejects_inconsistent_values(tmp_path):
    import pytest
    path = tmp_path / "meminfo"
    path.write_text("MemTotal: 100 kB\nMemAvailable: 200 kB\n")
    with pytest.raises(ValueError, match="invalid"):
        memory_bytes(path)
