"""Dashboard installer: rollback never exposes the token in argv; HTTP checks require 401.

Runs the installer's own shell functions with stub commands; no root, no systemd,
no network. The token is a dummy value.
"""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(shutil.which('bash') is None or os.name == 'nt', reason='POSIX bash')

SCRIPT = Path(__file__).resolve().parents[1] / 'deployment/dashboard/install-dashboard-service.sh'
TOKEN = 'dummy-token-4f3a9c'


def functions(*names):
    """Top-level shell functions of the installer, extracted verbatim."""
    lines, out, inside = SCRIPT.read_text(encoding='utf-8').splitlines(), [], False
    for line in lines:
        if any(line.startswith(f'{name}()') for name in names):
            out.append(line)
            inside = not line.rstrip().endswith('}')
        elif inside:
            out.append(line)
            inside = line != '}'
    return '\n'.join(out)


def stub(directory, name, body):
    path = directory / name
    path.write_text('#!/bin/bash\n' + body + '\n', encoding='utf-8')
    path.chmod(0o755)


def test_rollback_relaunch_keeps_token_out_of_every_command_line(tmp_path):
    bin_dir, record = tmp_path / 'bin', tmp_path / 'record'
    bin_dir.mkdir(); record.mkdir()
    for name in ('systemctl', 'ss'):
        stub(bin_dir, name, 'exit 0')
    # Paths are written into the stubs: the relaunch must not inherit our environment.
    stub(bin_dir, 'setsid', f'printf "%s\\0" setsid "$@" >> {record}/argv; exec "$@"')
    # Whichever launcher the installer uses records its argv and the environment it got.
    for name in ('runuser', 'setpriv', 'env'):
        stub(bin_dir, name, f'printf "%s\\0" {name} "$@" >> {record}/argv; /usr/bin/env -0 > {record}/environ.tmp; mv {record}/environ.tmp {record}/environ; exit 0')
    harness = f'''
set -euo pipefail
{functions('say', 'listener_pid', 'relaunch_manual', 'rollback')}
UNIT=eidolon-dashboard LOG={tmp_path}/dashboard.log OLD_CWD={tmp_path} PORT=8766 ADDR=127.0.0.1
: > "$LOG"
OLD_ENV=(PATH={bin_dir}:/usr/bin:/bin EIDOLON_DASHBOARD_TOKEN={TOKEN} LANG=C.UTF-8)
OLD_ARGS=(/opt/eidolon-memory-engine/.venv/bin/python -B -m core.monitoring.dashboard --port 8766)
sleep() {{ :; }}
rollback
'''
    env = dict(os.environ, PATH=f'{bin_dir}:/usr/bin:/bin', HARNESS_ONLY='leak')
    result = subprocess.run(['bash', '-c', harness], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1, result.stderr
    for _ in range(100):
        if (record / 'environ').exists():
            break
        subprocess.run(['sleep', '0.05'])
    argv = (record / 'argv').read_text(encoding='utf-8')
    environ = dict(item.split('=', 1) for item in (record / 'environ').read_text(encoding='utf-8').split('\0') if '=' in item)
    assert TOKEN not in argv, 'token visible in a process command line'
    assert 'core.monitoring.dashboard' in argv
    assert environ.get('EIDOLON_DASHBOARD_TOKEN') == TOKEN
    assert 'HARNESS_ONLY' not in environ


@pytest.mark.parametrize('anonymous,expected', [('401', 0), ('200', 1), ('000', 1)])
def test_http_check_requires_401_without_authentication(tmp_path, anonymous, expected):
    bin_dir = tmp_path / 'bin'; bin_dir.mkdir()
    # Authenticated requests (header on stdin, -H @-) get 200 and a page with resource-text.
    stub(bin_dir, 'curl', '''out=/dev/null; auth=0
while [ $# -gt 0 ]; do case "$1" in -o) out=$2; shift;; -H) auth=1;; esac; shift; done
if [ $auth = 1 ]; then echo '<p class="resource-text">x</p>' > "$out"; printf 200; else printf "$ANON"; fi''')
    env_file = tmp_path / 'environment'
    env_file.write_text(f'EIDOLON_DASHBOARD_TOKEN={TOKEN}\n', encoding='utf-8')
    harness = f'''
set -euo pipefail
{functions('say', 'http_code', 'auth_get', 'check_http')}
URL=http://127.0.0.1:8766/ ENV_FILE={env_file}
check_http test
'''
    env = dict(os.environ, PATH=f'{bin_dir}:/usr/bin:/bin', ANON=anonymous)
    result = subprocess.run(['bash', '-c', harness], env=env, capture_output=True, text=True, timeout=30)
    assert (result.returncode != 0) == bool(expected), result.stdout + result.stderr
    assert TOKEN not in result.stdout + result.stderr
