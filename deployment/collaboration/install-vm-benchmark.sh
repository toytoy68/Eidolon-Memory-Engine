#!/usr/bin/env bash
# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : deployment/collaboration/install-vm-benchmark.sh
# Description : Install the fixed sandbox benchmark on Eidolon-Memory.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
set -Eeuo pipefail
umask 077
repo=${1:?Repository path required}
commit=${2:?Pinned commit required}
[[ $EUID == 0 && $commit =~ ^[0-9a-f]{40}$ ]]
[[ $(hostname) == Eidolon-Memory ]]
base=/opt/eidolon-collaboration
gateway=/usr/local/lib/eidolon-vm
config=/etc/eidolon-vm-gateway.json
lab=/home/toytoy/eidolon-hybrid-lab
corpus=/home/toytoy/eidolon-corpus-factual-v2-test
jobs=/var/lib/eidolon-vm/jobs
[[ -L $base/app && -f $config && -f $gateway/vm_gateway.py ]]
[[ -x /usr/bin/bwrap ]] || {
  echo '[ERREUR] Installer bubblewrap : sudo apt-get install bubblewrap'; exit 1;
}
[[ -x $lab/.venv/bin/python && -d $lab/models && -d $corpus ]]
# Probe the same user, runtime and isolation before changing anything active.
runuser -u toytoy -- /usr/bin/bwrap --die-with-parent --new-session --unshare-all \
  --cap-drop ALL --ro-bind / / --proc /proc --dev /dev \
  --tmpfs /home --tmpfs /run --tmpfs /tmp \
  --ro-bind "$lab" /runtime --clearenv --setenv PATH /usr/bin:/bin \
  /runtime/.venv/bin/python -c \
  'import sentence_transformers, torch; print("Isolation et dépendances disponibles")'
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
for file in vm_gateway.py vm_benchmark.py independent_benchmark.py experimental_router.py server.py vm_client.py baselines/router_v3_original.py; do
  mkdir -p "$tmp/$(dirname "$file")"
  git -c safe.directory="$repo" -C "$repo" show "$commit:services/collaboration/$file" > "$tmp/$file"
done
python3 - "$tmp" <<'PY'
import ast
from pathlib import Path
import sys
for path in Path(sys.argv[1]).rglob('*.py'):
    ast.parse(path.read_text())
print('Syntaxe vérifiée')
PY
old=$(readlink -f "$base/app")
new=$(mktemp -d "$base/release.vm-benchmark.XXXXXXXX")
chmod 0755 "$new"
cp -a "$old/." "$new/"
for file in server.py vm_client.py; do
  install -o root -g root -m 0644 "$tmp/$file" "$new/services/collaboration/$file"
done
(cd "$new"; runuser -u eidolon-collaboration -- "$base/venv/bin/python" -B -c \
  'from services.collaboration.server import create_server; from services.collaboration.vm_client import VMClient; print("Import MCP vérifié")')
backup=$(mktemp -d /etc/eidolon-collaboration/backup.vm-benchmark.XXXXXXXX)
cp -a "$config" "$backup/config.json"
cp -a "$gateway/vm_gateway.py" "$backup/vm_gateway.py"
printf '%s\n' "$old" > "$backup/previous-release"
install -d -o root -g root -m 0755 /var/lib/eidolon-vm
if [[ -e $jobs ]]; then
  [[ -d $jobs && ! -L $jobs && $(stat -c %U "$jobs") == toytoy ]]
else
  install -d -o toytoy -g toytoy -m 0700 "$jobs"
fi
switch() {
  ln -s "$1" "$base/app.benchmark.$$"
  mv -Tf "$base/app.benchmark.$$" "$base/app"
}
rollback() {
  trap - ERR
  cp -a "$backup/config.json" "$config"
  cp -a "$backup/vm_gateway.py" "$gateway/vm_gateway.py"
  switch "$old"
  systemctl restart eidolon-collaboration
  echo '[ERREUR] Ancienne configuration rétablie.'
  exit 1
}
trap rollback ERR
install -d -o root -g root -m 0755 "$gateway/baselines"
for file in vm_gateway.py vm_benchmark.py independent_benchmark.py experimental_router.py baselines/router_v3_original.py; do
  install -o root -g root -m 0644 "$tmp/$file" "$gateway/$file"
done
python3 - "$config" "$jobs" "$corpus" "$lab" "$repo" <<'PY'
import json, os
from pathlib import Path
import sys
path = Path(sys.argv[1])
data = json.loads(path.read_text())
data['benchmark'] = dict(zip(('jobs','corpus','lab','repo'), sys.argv[2:]))
temporary = path.with_suffix('.benchmark.tmp')
temporary.write_text(json.dumps(data))
os.chmod(temporary, 0o644)
os.replace(temporary, path)
PY
switch "$new"
systemctl restart eidolon-collaboration
systemctl is-active --quiet eidolon-collaboration
for attempt in 1 2 3 4 5; do
  code=$(curl --max-time 5 -sS -D "$tmp/headers" -o /dev/null \
    -w '%{http_code}' -H 'Host: mcp.eidolon.re' http://127.0.0.1:8765/mcp || true)
  [[ $code == 401 ]] && break
  sleep 1
done
[[ $code == 401 ]]
python3 - "$tmp/headers" <<'PY'
from pathlib import Path
import sys
assert 'scope="eidolon:exchange eidolon:vm:read"' in Path(sys.argv[1]).read_text()
PY
trap - ERR
echo "[OK] Passerelle et MCP actifs : $new"
echo "[INFO] Sauvegarde : $backup"
echo '[INFO] Aucun benchmark exécuté pendant installation. Rafraîchir les outils du connecteur.'
