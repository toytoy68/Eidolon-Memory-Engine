"""Deployment packages preserve source and reject unsafe config before writing."""
import hashlib
import json
import subprocess

import pytest
from tools.prepare_collaboration_deployment import build_package, render_config, ROOT, SOURCE_FILES


CONFIG = dict(domain="exchange.example.org", issuer="https://auth.example.org/",
              jwks="https://auth.example.org/jwks", subject="auth0|owner")


def test_template_package_has_verifiable_source_and_no_live_config(tmp_path):
    destination = tmp_path / "bundle"
    result = build_package(destination)
    assert not result["configured"]
    assert not (destination / "environment").exists()
    for relative in SOURCE_FILES:
        assert (destination / "app" / relative).read_bytes() == (ROOT / relative).read_bytes()
    subprocess.run(["sha256sum", "--check", "SHA256SUMS"], cwd=destination, check=True, capture_output=True)
    subprocess.run(["bash", "-n", str(destination / "install-vm.sh")], check=True)
    manifest = json.loads((destination / "manifest.json").read_text())
    for relative, digest in manifest["files_sha256"].items():
        assert hashlib.sha256((destination / relative).read_bytes()).hexdigest() == digest


def test_rendered_package_has_exact_audience_and_private_permissions(tmp_path):
    destination = tmp_path / "configured"
    assert build_package(destination, CONFIG)["configured"]
    env = (destination / "environment").read_text()
    assert "EIDOLON_EXCHANGE_URL=https://exchange.example.org/mcp\n" in env
    assert "EIDOLON_OAUTH_SUBJECTS=auth0|owner\n" in env
    assert "EIDOLON_OAUTH_JWKS=https://auth.example.org/jwks\n" in env
    assert "REPLACE_WITH" not in env
    assert (destination / "environment").stat().st_mode & 0o777 == 0o600
    assert (destination / "Caddyfile").read_text().startswith("exchange.example.org {")


@pytest.mark.parametrize("change", [
    {"domain": "$(touch /tmp/unsafe)"}, {"domain": "https://example.org"},
    {"domain": "example.org\nother"}, {"issuer": "http://auth.example.org"},
    {"jwks": "https://user:secret@auth.example.org/jwks"},
    {"issuer": "https://auth.example.org/\nINJECT=1"},
    {"subject": "owner\nOTHER=1"}, {"subject": "owner,other"},
])
def test_bad_configuration_does_not_create_package(tmp_path, change):
    destination = tmp_path / "rejected"
    with pytest.raises(ValueError):
        build_package(destination, {**CONFIG, **change})
    assert not destination.exists()


def test_existing_package_is_not_overwritten(tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "keep").write_text("previous package")
    with pytest.raises(ValueError):
        build_package(destination)
    assert (destination / "keep").read_text() == "previous package"
