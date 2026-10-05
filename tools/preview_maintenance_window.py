# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tools/preview_maintenance_window.py
# Description : Preview explicit maintenance timing; does not install jobs or inspect/write memory.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Preview explicit maintenance timing; does not install jobs or inspect/write memory."""
import argparse
from datetime import datetime, time
import json

from core.maintenance.window import preview_window


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--at', required=True, help='Timezone-aware current timestamp')
    parser.add_argument('--last-activity', required=True, help='Timezone-aware observed activity timestamp')
    parser.add_argument('--start', required=True, help='Local window start, HH:MM')
    parser.add_argument('--end', required=True, help='Local window end, HH:MM (excluded)')
    parser.add_argument('--timezone', required=True, help='IANA timezone, e.g. Europe/Paris')
    parser.add_argument('--minimum-idle-minutes', type=int, required=True)
    args = parser.parse_args(argv)
    try:
        result = preview_window(at=datetime.fromisoformat(args.at),
            last_activity=datetime.fromisoformat(args.last_activity),
            start=time.fromisoformat(args.start), end=time.fromisoformat(args.end),
            zone=args.timezone, minimum_idle_minutes=args.minimum_idle_minutes)
    except ValueError as exc:
        result = dict(status='BLOCKED', reason=str(exc), execution_performed=False)
    print(json.dumps(result))
    return int(result['status'] == 'BLOCKED')


if __name__ == '__main__':
    raise SystemExit(main())
