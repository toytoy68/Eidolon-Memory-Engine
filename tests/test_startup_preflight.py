import pytest

from core.preflight import check_environment, PreflightError


def test_preflight_reports_realpath_space_and_write_access(tmp_path):
    result = check_environment(tmp_path, min_free_bytes=1)
    assert result["realpath"] == str(tmp_path.resolve())
    assert result["free_bytes"] >= 1
    assert result["writable"] is True
    assert not list(tmp_path.iterdir())


def test_preflight_rejects_link_with_actionable_realpath(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "link"
    link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(PreflightError) as error:
        check_environment(link, min_free_bytes=0)
    assert str(link) in str(error.value)
    assert str(actual) in str(error.value)


def test_preflight_rejects_old_python_and_insufficient_space(tmp_path, monkeypatch):
    with pytest.raises(PreflightError, match="Python 3.11"):
        check_environment(tmp_path, python_version=(3, 10), min_free_bytes=0)
    with pytest.raises(PreflightError, match="free space"):
        check_environment(tmp_path, min_free_bytes=10**30)


def test_preflight_reports_unwritable_root(tmp_path, monkeypatch):
    import core.preflight as preflight

    def denied(**kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(preflight.tempfile, "NamedTemporaryFile", denied)
    with pytest.raises(PreflightError, match="not writable"):
        check_environment(tmp_path, min_free_bytes=0)


def test_operation_cli_checks_preflight_before_creating_repositories(monkeypatch):
    import sys
    import core.operations.cli as cli

    def blocked(root):
        raise PreflightError("preflight stopped writer")

    monkeypatch.setattr(cli, "check_environment", blocked, raising=False)
    monkeypatch.setattr(cli, "ThreadStorage", lambda root: (_ for _ in ()).throw(
        AssertionError("repository constructed before preflight")))
    monkeypatch.setattr(sys, "argv", ["operations", "recover"])
    with pytest.raises(PreflightError, match="preflight stopped writer"):
        cli.main()
