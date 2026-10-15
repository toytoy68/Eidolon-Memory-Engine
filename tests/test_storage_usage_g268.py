# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_storage_usage_g268.py
# Description : Distingue erreurs CLI et états du diagnostic canonique
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Diagnostic usage errors never probe storage or borrow a business-state exit code."""
import sys

import pytest
from services import memory_bridge as bridge


@pytest.mark.parametrize('args', [
    ['--check-storage'],
    ['--root', '/unused', '--check-storage', '--port', '18765'],
    ['--root', '/unused', '--check-storage', '--port', 'invalid'],
    ['--root', '/unused', '--check-storage', '--reranker-cache', '/unused'],
    ['--root', '/unused', '--check-storage', '--unknown'],
    ['--root', '/unused', '--check-storage=yes'],
    ['--check-stor'],
])
def test_diagnostic_usage_is_64_without_storage_or_model_work(monkeypatch, capsys, args):
    monkeypatch.setattr(sys, 'argv', ['memory-bridge', *args])
    def forbidden(*args, **kwargs):
        pytest.fail('usage error reached application work')
    monkeypatch.setattr(bridge, 'check_storage', forbidden)
    monkeypatch.setattr(bridge, 'build_recall', forbidden)
    with pytest.raises(SystemExit) as exc:
        bridge.main()
    assert exc.value.code == 64
    assert exc.value.code not in bridge.STORAGE_CHECK_EXIT.values()
    output = capsys.readouterr()
    assert output.out == '' and 'usage:' in output.err


def test_server_usage_stays_2_and_help_stays_0(monkeypatch, capsys):
    for args, code in [(['--port', 'bad'], 2), (['--check-storage', '--help'], 0),
                       (['--', '--check-storage'], 2)]:
        monkeypatch.setattr(sys, 'argv', ['memory-bridge', *args])
        with pytest.raises(SystemExit) as exc:
            bridge.main()
        assert exc.value.code == code
        capsys.readouterr()
