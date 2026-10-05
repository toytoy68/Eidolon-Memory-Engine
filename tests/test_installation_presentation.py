# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : test_installation_presentation.py
# Description : Aperçus sans installation et paquet autonome
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Exercise presentation without root, network or installation commands."""
from pathlib import Path
import subprocess

import pytest

from tools.prepare_collaboration_deployment import build_package

ROOT = Path(__file__).resolve().parents[1]


def preview(script, tmp_path):
    marker = tmp_path / 'unexpected-command'
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    for name in ('systemctl', 'install', 'python3', 'ssh-keygen', 'id', 'curl', 'ss', 'chmod'):
        stub = binaries / name
        stub.write_text(f'#!/bin/bash\nprintf invoked > "{marker}"\nexit 99\n')
        stub.chmod(0o755)
    result = subprocess.run(['bash', str(script), '--presentation-preview'],
                            env={'PATH': f'{binaries}:/usr/bin:/bin'},
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    assert not result.stderr
    assert 'Eidolon Core Technologies (ECT)' in result.stdout
    assert 'sans installation' in result.stdout
    assert '[OK]' not in result.stdout
    assert '\x1b' not in result.stdout
    return result.stdout


@pytest.mark.parametrize('relative', [
    'deployment/dashboard/install-dashboard-service.sh',
    'deployment/collaboration/install-vm.sh',
])
def test_preview_never_reaches_system_operations(relative, tmp_path):
    preview(ROOT / relative, tmp_path)


def test_packaged_installer_preview_is_self_contained(tmp_path):
    bundle = tmp_path / 'bundle'
    manifest = build_package(bundle)
    assert 'presentation.sh' in manifest['files_sha256']
    assert (bundle / 'presentation.sh').read_bytes() == (ROOT / 'deployment/presentation.sh').read_bytes()
    preview(bundle / 'install-vm.sh', tmp_path)


def test_helper_is_pure_and_neutralizes_terminal_controls():
    result = subprocess.run(['bash', '-c',
        'source "$1"; eidolon_message INFO "$2"; printf "still-running\\n"',
        'test', str(ROOT / 'deployment/presentation.sh'), 'text\x1b[31m\rvalue'],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert result.stdout == '[INFO] text[31mvalue\nstill-running\n'
    assert not result.stderr
