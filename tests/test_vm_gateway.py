"""Security checks for the forced-command gateway, no VM accessed."""
import pytest
from services.collaboration.vm_gateway import dispatch, read_file


def test_read_provenance(tmp_path):
    (tmp_path / "router.py").write_text("print('synthetic')\n")
    result = dispatch({"action": "read", "root": "tools", "path": "router.py"}, {"tools": tmp_path})
    assert result["trust"] == "UNVERIFIED"
    assert len(result["sha256"]) == 64
    assert result["content"] == "print('synthetic')\n"


@pytest.mark.parametrize("path", ["../secret.json", "/etc/passwd", ".env", "file.sh", ".private/key.json"])
def test_reject_paths(tmp_path, path):
    with pytest.raises(ValueError):
        read_file(tmp_path, path)


def test_reject_symlink_and_large_file(tmp_path):
    (tmp_path / "real.json").write_text("{}")
    (tmp_path / "link.json").symlink_to(tmp_path / "real.json")
    with pytest.raises(OSError):
        read_file(tmp_path, "link.json")
    (tmp_path / "large.json").write_bytes(b"x" * 65537)
    with pytest.raises(ValueError):
        read_file(tmp_path, "large.json")


@pytest.mark.parametrize("payload", [{"action": "shell", "cmd": "id"}, {"action": "diagnostic", "cmd": "id"},
                                     {"action": "read", "root": "secret", "path": "x.json"}])
def test_reject_unapproved_actions(tmp_path, payload):
    with pytest.raises(ValueError):
        dispatch(payload, {"tools": tmp_path})


def test_vm_client_fixed_target_and_ssh_options(monkeypatch):
    import json
    from types import SimpleNamespace
    from services.collaboration.vm_client import VMClient
    seen = []
    def fake_run(argv, **kwargs):
        seen.append(argv)
        kwargs["stdout"].write(json.dumps({"ok": True, "result": {"synthetic": True}}).encode())
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr("services.collaboration.vm_client.subprocess.run", fake_run)
    client = VMClient({"core": {"destination": "toytoy@192.0.2.1", "key": "/keys/test", "known_hosts": "/keys/hosts"}})
    with pytest.raises(ValueError):
        client.diagnostic("arbitrary-host")
    assert seen == []
    assert client.diagnostic("core")["synthetic"]
    assert "StrictHostKeyChecking=yes" in seen[0]
    assert "BatchMode=yes" in seen[0]
    assert seen[0][-1].startswith("eidolon-read-v1 ")
