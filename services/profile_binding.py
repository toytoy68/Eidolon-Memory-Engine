# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : services/profile_binding.py
# Description : Explicit immutable profile identity for an isolated Memory root
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Prepare a new isolated root, never re-label an existing profile.

This technical file is outside canonical persistent/history directories. Serving
an authenticated profile requires it; a name supplied on the command line alone
cannot label the same root as two different people's memory. No corpus is moved.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
from core.runtime_json import read_json_snapshot
from core.persistence import has_symlink_component

NAME = 'profile-binding.json'


def binding(root, profile, *, apply=False):
    root = Path(root).absolute()
    if (type(profile) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', profile)
            or has_symlink_component(root) or not root.is_dir()
            or not all((root/'memory'/name).is_dir() for name in ('persistent', 'history'))):
        raise ValueError('existing isolated profile root required')
    value = {'schema': 'eidolon-memory-profile/1', 'profile_id': profile}
    path = root/NAME
    if not path.exists() and apply:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(json.dumps(value).encode()); stream.flush(); os.fsync(stream.fileno())
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(directory)
        finally: os.close(directory)
    if not path.exists():
        return {'state': 'NOT_PREPARED', 'profile_id': profile}
    observed = read_json_snapshot(str(root), NAME, max_bytes=1024)
    if observed != value:
        raise ValueError('profile identity mismatch; re-labeling refused')
    return {'state': 'BOUND', 'profile_id': profile}


def require_binding(root, profile):
    if binding(root, profile)['state'] != 'BOUND':
        raise ValueError('profile binding must be explicitly prepared')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Check or explicitly bind an isolated Memory root to one profile')
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = binding(args.root, args.profile, apply=args.apply)
        print(json.dumps(result))
        return 0 if result['state'] == 'BOUND' else 2
    except Exception:
        print(json.dumps({'state': 'REFUSED_OR_INCOMPLETE'}))
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
