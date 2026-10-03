#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -x "$TASK_ROOT/.venv/bin/python" ]]; then
  echo 'Environnement Python du projet absent : consulter docs/MONITORING.md.' >&2
  exit 1
fi
cd -- "$TASK_ROOT"
exec "$TASK_ROOT/.venv/bin/python" -B -m core.monitoring.dashboard --root "$TASK_ROOT" "$@"
